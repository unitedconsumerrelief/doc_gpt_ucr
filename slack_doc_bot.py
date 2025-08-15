import os
import re
import openai
import faiss
import numpy as np
import pdfplumber
from PIL import Image
import pytesseract
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient
from dotenv import load_dotenv
from policy_codex_full_ready import POLICY_CODEX

load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

app = App(token=SLACK_BOT_TOKEN)
client = WebClient(token=SLACK_BOT_TOKEN)

index = None
chunks = []
chunk_sources = []

def extract_chunks_from_text(text, source):
    output = []
    lines = text.split("\n")
    buffer = []
    max_chunk_words = 120
    
    # Keywords that indicate important policy content even in short chunks
    policy_keywords = [
        "credit union", "secured loan", "furniture", "military", "federal", 
        "student loan", "auto loan", "mortgage", "collections", "ach",
        "minimum payment", "enrollment", "eligible", "disqualified", "restricted",
        "capped", "limit", "requirement", "condition", "waiver", "approval",
        "not allowed", "prohibited", "excluded", "restricted", "conditional",
        "must", "only if", "required", "necessary", "mandatory"
    ]
    
    # Emojis that indicate important policy status
    policy_emojis = ["❌", "✅", "⚠️", "🚫", "💳", "🏦", "💰", "📋", "🔒", "⚡"]

    def is_important_content(text):
        """Check if content contains important policy indicators"""
        text_lower = text.lower()
        has_keywords = any(keyword in text_lower for keyword in policy_keywords)
        has_emojis = any(emoji in text for emoji in policy_emojis)
        has_bullets = "-" in text or "•" in text
        has_restrictions = any(term in text_lower for term in ["not allowed", "prohibited", "excluded", "restricted"])
        has_requirements = any(term in text_lower for term in ["must", "only if", "required", "necessary"])
        return has_keywords or has_emojis or has_bullets or has_restrictions or has_requirements

    def is_policy_header(line):
        """Check if line is a policy header (all caps, short, likely creditor name)"""
        return (line.isupper() and 
                len(line.split()) <= 4 and  # Reduced from 8 to 4 for shorter headers like "OPORTUN"
                len(line) >= 2 and
                not line.startswith("-") and
                not line.startswith("•"))

    def is_bullet_or_indented(line):
        """Check if line is a bullet point or indented policy line"""
        return (line.startswith("-") or 
                line.startswith("•") or 
                line.startswith("  ") or  # Indented lines
                line.startswith("\t"))    # Tab-indented lines

    def should_merge_with_previous(line, buffer):
        """Determine if line should be merged with previous content"""
        if not buffer:
            return False
        
        # Always merge bullet points or indented lines with previous content
        if is_bullet_or_indented(line):
            return True
        
        # Merge short lines that seem related to previous content
        if len(line.split()) <= 5 and is_important_content(line):
            return True
        
        # Merge lines that continue a policy rule (containing emojis or keywords)
        if is_important_content(line) and is_important_content(" ".join(buffer)):
            return True
        
        # Merge if previous content is a policy header and current line is related
        if buffer and is_policy_header(buffer[0]) and is_important_content(line):
            return True
        
        # Merge if we have a policy header and current line is short and related
        if buffer and is_policy_header(buffer[0]) and len(line.split()) <= 8:
            return True
        
        return False

    def is_policy_block(buffer):
        """Check if buffer contains a complete policy block worth preserving"""
        if not buffer:
            return False
        
        # If it has a header and bullet points, it's definitely a policy block
        if len(buffer) >= 2 and is_policy_header(buffer[0]):
            has_bullets = any(is_bullet_or_indented(line) for line in buffer[1:])
            if has_bullets:
                return True
        
        # If it contains important policy content with emojis or restrictions, preserve it
        joined = " ".join(buffer)
        if is_important_content(joined):
            return True
        
        # If it's a short header with any related content, preserve it
        if len(buffer) >= 2 and is_policy_header(buffer[0]):
            return True
        
        return False

    def flush_buffer():
        if buffer:
            joined = " ".join(buffer).strip()
            # Always preserve policy blocks, regardless of length
            if is_policy_block(buffer) or len(joined.split()) >= 3:
                output.append((joined, source))
            buffer.clear()

    for line in lines:
        line = line.strip()
        
        if line == "":
            flush_buffer()
        elif should_merge_with_previous(line, buffer):
            # Merge with previous content instead of creating new chunk
            buffer.append(line)
        elif is_policy_header(line):
            # This is likely a policy header - flush previous and start new
            flush_buffer()
            buffer.append(line)
        else:
            buffer.append(line)
            # Check if we've exceeded max chunk size
            if len(" ".join(buffer).split()) > max_chunk_words:
                flush_buffer()

    flush_buffer()
    return output

def load_documents(folder_path="documents"):
    print("📄 Loading and chunking documents...")
    all_chunks = []
    all_sources = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf") or filename.endswith(".txt"):
            path = os.path.join(folder_path, filename)
            print(f"🔍 Processing: {filename}")
            try:
                if filename.endswith(".pdf"):
                    with pdfplumber.open(path) as pdf:
                        text_blocks = []
                        for page in pdf.pages:
                            text = page.extract_text()
                            if not text:
                                img = page.to_image(resolution=300).original
                                pil_image = Image.frombytes("RGB", img.size, img.tobytes())
                                text = pytesseract.image_to_string(pil_image)
                            text_blocks.append(text.strip())
                        combined = "\n".join(text_blocks)
                else:
                    with open(path, "r", encoding="utf-8") as f:
                        combined = f.read()
                doc_chunks = extract_chunks_from_text(combined, filename)
                for chunk, source in doc_chunks:
                    all_chunks.append(chunk)
                    all_sources.append(filename)
                print(f"✅ Extracted {len(doc_chunks)} chunks from: {filename}")
            except Exception as e:
                print(f"❌ ERROR processing {filename}: {str(e)}")
    return all_chunks, all_sources

def embed_chunks(chunks):
    print("🔢 Creating embeddings...")
    response = openai.Embedding.create(model="text-embedding-ada-002", input=chunks)
    return [np.array(r["embedding"], dtype=np.float32) for r in response["data"]]

def create_vector_index(vectors):
    dim = len(vectors[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(vectors))
    return index

def search_codex(question):
    question_lower = question.lower()
    matched = []
    for entry in POLICY_CODEX:
        if any(k.lower() in question_lower for k in entry["keywords"]):
            matched.append(entry)
    return matched

def ask_gpt(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message["content"].strip()

def detect_language(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": f"What language is this question in? Just reply with one word.\n{text}"}]
    )
    return response.choices[0].message["content"].strip().lower()

def translate_answer(answer, target_lang):
    prompt = f"Translate the following text to {target_lang}:\n{answer}"
    return ask_gpt(prompt)

def get_top_chunks(question, k=5):
    question_vec = openai.Embedding.create(model="text-embedding-ada-002", input=[question])["data"][0]["embedding"]
    D, I = index.search(np.array([question_vec], dtype=np.float32), k)
    return [(chunks[i], chunk_sources[i]) for i in I[0] if i < len(chunks)]



def is_valid_primary_chunk(chunk, source):
    """
    Check if a chunk is valid for primary document-based answers.
    Must have at least 5 words and come from relevant policy documents.
    """
    # Check word count (reduced from 10 to 5 for important policy content)
    word_count = len(chunk.split())
    if word_count < 5:
        return False
    
    # Check if source is from relevant policy documents
    source_lower = source.lower()
    
    # Primary program documents
    is_clarity = "clarity" in source_lower or "affiliate_training_packet" in source_lower
    is_elevate = "elevate" in source_lower
    
    # Policy and reference documents
    is_policy = any(term in source_lower for term in [
        "disqualified", "unacceptable", "state", "comparison", "list", "criteria", "unacceptablecreditunion"
    ])
    
    # Check if chunk contains important policy indicators (override word count)
    chunk_lower = chunk.lower()
    has_policy_indicators = any(term in chunk_lower for term in [
        "❌", "✅", "⚠️", "not allowed", "prohibited", "disqualified", "restricted", "mortgage", "secured"
    ])
    
    # Always include chunks with important policy content
    if has_policy_indicators:
        return True
    
    return (is_clarity or is_elevate or is_policy) and word_count >= 5

def get_program_sources_from_chunks(chunk_sources):
    """
    Extract program names from chunk sources, only counting Clarity and Elevate.
    """
    programs = set()
    for source in chunk_sources:
        source_lower = source.lower()
        if "clarity" in source_lower or "affiliate_training_packet" in source_lower:
            programs.add("Clarity")
        if "elevate" in source_lower:
            programs.add("Elevate")
    return sorted(list(programs))

def ask_gpt_with_system_prompt(system_prompt, user_prompt):
    """
    Ask GPT with a specific system prompt.
    """
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message["content"].strip()

def handle_question(question):
    print(f"🚀 handle_question called with: {question}")
    # Step 1: Normalize question
    question_clean = question.lower()
    print(f"🔍 Normalized question: {question_clean}")
    
    # Step 2: Comprehensive hardcoded acceptance/rejection logic
    hard_rejections = {
        # DEBT TYPES - NOT ACCEPTED
        "mortgage": {
            "global": (
                "❌ *Elevate:* Mortgage loans are not accepted.\n"
                "❌ *Clarity:* Mortgage loans are not accepted.\n"
                "📝 *Please inform the client that mortgage loans must be resolved outside the program.*",
                "❌ *Elevate:* Los préstamos hipotecarios no se aceptan.\n"
                "❌ *Clarity:* Los préstamos hipotecarios no se aceptan.\n"
                "📝 *Por favor informe al cliente que los préstamos hipotecarios deben resolverse fuera del programa.*"
            )
        },
        "secured loan": {
            "global": (
                "❌ *Elevate:* Secured loans are not accepted.\n"
                "❌ *Clarity:* Secured loans are not accepted.\n"
                "📝 *Please inform the client that secured loans must be resolved outside the program.*",
                "❌ *Elevate:* Los préstamos con garantía no se aceptan.\n"
                "❌ *Clarity:* Los préstamos con garantía no se aceptan.\n"
                "📝 *Por favor informe al cliente que los préstamos con garantía deben resolverse fuera del programa.*"
            )
        },
        "federal student loan": {
            "global": (
                "❌ *Elevate:* Federal student loans are not accepted.\n"
                "❌ *Clarity:* Federal student loans are not accepted.\n"
                "📝 *Please inform the client that federal student loans must be resolved outside the program.*",
                "❌ *Elevate:* Los préstamos estudiantiles federales no se aceptan.\n"
                "❌ *Clarity:* Los préstamos estudiantiles federales no se aceptan.\n"
                "📝 *Por favor informe al cliente que los préstamos estudiantiles federales deben resolverse fuera del programa.*"
            )
        },
        "auto loan": {
            "global": (
                "❌ *Elevate:* Auto loans are not accepted.\n"
                "❌ *Clarity:* Auto loans are not accepted (except post-repossession deficiencies).\n"
                "📝 *Please inform the client that auto loans must be resolved outside the program.*",
                "❌ *Elevate:* Los préstamos de auto no se aceptan.\n"
                "❌ *Clarity:* Los préstamos de auto no se aceptan (excepto deficiencias post-embargo).\n"
                "📝 *Por favor informe al cliente que los préstamos de auto deben resolverse fuera del programa.*"
            )
        },
        "irs": {
            "global": (
                "❌ *Elevate:* IRS/tax debt is not accepted.\n"
                "❌ *Clarity:* IRS/tax debt is not accepted.\n"
                "📝 *Please inform the client that IRS/tax debt must be resolved outside the program.*",
                "❌ *Elevate:* La deuda del IRS/impuestos no se acepta.\n"
                "❌ *Clarity:* La deuda del IRS/impuestos no se acepta.\n"
                "📝 *Por favor informe al cliente que la deuda del IRS/impuestos debe resolverse fuera del programa.*"
            )
        },
        "judgment": {
            "global": (
                "❌ *Elevate:* Judgments are not accepted.\n"
                "❌ *Clarity:* Judgments are not accepted (unless filed 6+ months ago with no active collection).\n"
                "📝 *Please inform the client that judgments must be resolved outside the program.*",
                "❌ *Elevate:* Los juicios no se aceptan.\n"
                "❌ *Clarity:* Los juicios no se aceptan (a menos que se presentaron hace 6+ meses sin cobro activo).\n"
                "📝 *Por favor informe al cliente que los juicios deben resolverse fuera del programa.*"
            )
        },
        "alimony": {
            "global": (
                "❌ *Elevate:* Alimony/child support is not accepted.\n"
                "❌ *Clarity:* Alimony/child support is not accepted.\n"
                "📝 *Please inform the client that alimony/child support must be resolved outside the program.*",
                "❌ *Elevate:* La pensión alimenticia no se acepta.\n"
                "❌ *Clarity:* La pensión alimenticia no se acepta.\n"
                "📝 *Por favor informe al cliente que la pensión alimenticia debe resolverse fuera del programa.*"
            )
        },
        "gambling": {
            "global": (
                "❌ *Elevate:* Gambling debts are not accepted.\n"
                "❌ *Clarity:* Gambling debts are not accepted.\n"
                "📝 *Please inform the client that gambling debts must be resolved outside the program.*",
                "❌ *Elevate:* Las deudas de juego no se aceptan.\n"
                "❌ *Clarity:* Las deudas de juego no se aceptan.\n"
                "📝 *Por favor informe al cliente que las deudas de juego deben resolverse fuera del programa.*"
            )
        },
        "timeshare": {
            "global": (
                "❌ *Elevate:* Timeshares are not accepted.\n"
                "❌ *Clarity:* Timeshares are not accepted.\n"
                "📝 *Please inform the client that timeshares must be resolved outside the program.*",
                "❌ *Elevate:* Los tiempos compartidos no se aceptan.\n"
                "❌ *Clarity:* Los tiempos compartidos no se aceptan.\n"
                "📝 *Por favor informe al cliente que los tiempos compartidos deben resolverse fuera del programa.*"
            )
        },
        "property tax": {
            "global": (
                "❌ *Elevate:* Property taxes are not accepted.\n"
                "❌ *Clarity:* Property taxes are not accepted.\n"
                "📝 *Please inform the client that property taxes must be resolved outside the program.*",
                "❌ *Elevate:* Los impuestos sobre la propiedad no se aceptan.\n"
                "❌ *Clarity:* Los impuestos sobre la propiedad no se aceptan.\n"
                "📝 *Por favor informe al cliente que los impuestos sobre la propiedad deben resolverse fuera del programa.*"
            )
        },
        "bail bond": {
            "global": (
                "❌ *Elevate:* Bail bonds are not accepted.\n"
                "❌ *Clarity:* Bail bonds are not accepted.\n"
                "📝 *Please inform the client that bail bonds must be resolved outside the program.*",
                "❌ *Elevate:* Las fianzas no se aceptan.\n"
                "❌ *Clarity:* Las fianzas no se aceptan.\n"
                "📝 *Por favor informe al cliente que las fianzas deben resolverse fuera del programa.*"
            )
        },
        
        # SPECIFIC CREDITORS - NOT ACCEPTED
        "ncb": {
            "global": (
                "❌ *Elevate:* NCB Management Services is not accepted.\n"
                "❌ *Clarity:* NCB Management Services is not accepted.\n"
                "📝 *Please inform the client that NCB debts must be resolved outside the program.*",
                "❌ *Elevate:* NCB Management Services no se acepta.\n"
                "❌ *Clarity:* NCB Management Services no se acepta.\n"
                "📝 *Por favor informe al cliente que las deudas de NCB deben resolverse fuera del programa.*"
            )
        },
        "rocket loan": {
            "global": (
                "❌ *Elevate:* Rocket Loans is not accepted.\n"
                "❌ *Clarity:* Rocket Loans is not accepted.\n"
                "📝 *Please inform the client that Rocket Loans must be resolved outside the program.*",
                "❌ *Elevate:* Rocket Loans no se acepta.\n"
                "❌ *Clarity:* Rocket Loans no se acepta.\n"
                "📝 *Por favor informe al cliente que Rocket Loans debe resolverse fuera del programa.*"
            )
        },
        "goodleap": {
            "global": (
                "❌ *Elevate:* GoodLeap is not accepted.\n"
                "❌ *Clarity:* GoodLeap is not accepted.\n"
                "📝 *Please inform the client that GoodLeap must be resolved outside the program.*",
                "❌ *Elevate:* GoodLeap no se acepta.\n"
                "❌ *Clarity:* GoodLeap no se acepta.\n"
                "📝 *Por favor informe al cliente que GoodLeap debe resolverse fuera del programa.*"
            )
        },
        "military star": {
            "global": (
                "❌ *Elevate:* Military Star is not accepted.\n"
                "❌ *Clarity:* Military Star is not accepted.\n"
                "📝 *Please inform the client that Military Star must be resolved outside the program.*",
                "❌ *Elevate:* Military Star no se acepta.\n"
                "❌ *Clarity:* Military Star no se acepta.\n"
                "📝 *Por favor informe al cliente que Military Star debe resolverse fuera del programa.*"
            )
        },
        "tower loan": {
            "global": (
                "❌ *Elevate:* Tower Loan is not accepted.\n"
                "❌ *Clarity:* Tower Loan is not accepted.\n"
                "📝 *Please inform the client that Tower Loan must be resolved outside the program.*",
                "❌ *Elevate:* Tower Loan no se acepta.\n"
                "❌ *Clarity:* Tower Loan no se acepta.\n"
                "📝 *Por favor informe al cliente que Tower Loan debe resolverse fuera del programa.*"
            )
        },
        "aqua finance": {
            "global": (
                "❌ *Elevate:* Aqua Finance is not accepted.\n"
                "❌ *Clarity:* Aqua Finance is not accepted.\n"
                "📝 *Please inform the client that Aqua Finance must be resolved outside the program.*",
                "❌ *Elevate:* Aqua Finance no se acepta.\n"
                "❌ *Clarity:* Aqua Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que Aqua Finance debe resolverse fuera del programa.*"
            )
        },
        "pentagon": {
            "global": (
                "❌ *Elevate:* Pentagon FCU installment loans are not accepted (credit cards only).\n"
                "❌ *Clarity:* Pentagon FCU installment loans are not accepted.\n"
                "📝 *Please inform the client that Pentagon FCU installment loans must be resolved outside the program.*",
                "❌ *Elevate:* Los préstamos a plazos de Pentagon FCU no se aceptan (solo tarjetas de crédito).\n"
                "❌ *Clarity:* Los préstamos a plazos de Pentagon FCU no se aceptan.\n"
                "📝 *Por favor informe al cliente que los préstamos a plazos de Pentagon FCU deben resolverse fuera del programa.*"
            )
        },
        "koalafi": {
            "global": (
                "❌ *Elevate:* KOALAFI is not accepted.\n"
                "❌ *Clarity:* KOALAFI is not accepted.\n"
                "📝 *Please inform the client that KOALAFI must be resolved outside the program.*",
                "❌ *Elevate:* KOALAFI no se acepta.\n"
                "❌ *Clarity:* KOALAFI no se acepta.\n"
                "📝 *Por favor informe al cliente que KOALAFI debe resolverse fuera del programa.*"
            )
        },
        "republic finance": {
            "global": (
                "❌ *Elevate:* Republic Finance is not accepted.\n"
                "❌ *Clarity:* Republic Finance is not accepted.\n"
                "📝 *Please inform the client that Republic Finance must be resolved outside the program.*",
                "❌ *Elevate:* Republic Finance no se acepta.\n"
                "❌ *Clarity:* Republic Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que Republic Finance debe resolverse fuera del programa.*"
            )
        },
        "snap tools": {
            "global": (
                "❌ *Elevate:* Snap Tools is not accepted.\n"
                "❌ *Clarity:* Snap Tools is not accepted.\n"
                "📝 *Please inform the client that Snap Tools must be resolved outside the program.*",
                "❌ *Elevate:* Snap Tools no se acepta.\n"
                "❌ *Clarity:* Snap Tools no se acepta.\n"
                "📝 *Por favor informe al cliente que Snap Tools debe resolverse fuera del programa.*"
            )
        },
        "cnh": {
            "global": (
                "❌ *Elevate:* CNH Industrial is not accepted.\n"
                "❌ *Clarity:* CNH Industrial is not accepted.\n"
                "📝 *Please inform the client that CNH Industrial must be resolved outside the program.*",
                "❌ *Elevate:* CNH Industrial no se acepta.\n"
                "❌ *Clarity:* CNH Industrial no se acepta.\n"
                "📝 *Por favor informe al cliente que CNH Industrial debe resolverse fuera del programa.*"
            )
        },
        "duvera": {
            "global": (
                "❌ *Elevate:* Duvera Finance is not accepted.\n"
                "❌ *Clarity:* Duvera Finance is not accepted.\n"
                "📝 *Please inform the client that Duvera Finance must be resolved outside the program.*",
                "❌ *Elevate:* Duvera Finance no se acepta.\n"
                "❌ *Clarity:* Duvera Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que Duvera Finance debe resolverse fuera del programa.*"
            )
        },
        "grt american": {
            "global": (
                "❌ *Elevate:* GRT American Financial is not accepted.\n"
                "❌ *Clarity:* GRT American Financial is not accepted.\n"
                "📝 *Please inform the client that GRT American Financial must be resolved outside the program.*",
                "❌ *Elevate:* GRT American Financial no se acepta.\n"
                "❌ *Clarity:* GRT American Financial no se acepta.\n"
                "📝 *Por favor informe al cliente que GRT American Financial debe resolverse fuera del programa.*"
            )
        },
        "service finance": {
            "global": (
                "❌ *Elevate:* Service Finance is not accepted.\n"
                "❌ *Clarity:* Service Finance is not accepted.\n"
                "📝 *Please inform the client that Service Finance must be resolved outside the program.*",
                "❌ *Elevate:* Service Finance no se acepta.\n"
                "❌ *Clarity:* Service Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que Service Finance debe resolverse fuera del programa.*"
            )
        },
        "schools first": {
            "global": (
                "❌ *Elevate:* Schools First CU loans are not accepted (credit cards only).\n"
                "❌ *Clarity:* Schools First CU loans are not accepted.\n"
                "📝 *Please inform the client that Schools First CU loans must be resolved outside the program.*",
                "❌ *Elevate:* Los préstamos de Schools First CU no se aceptan (solo tarjetas de crédito).\n"
                "❌ *Clarity:* Los préstamos de Schools First CU no se aceptan.\n"
                "📝 *Por favor informe al cliente que los préstamos de Schools First CU deben resolverse fuera del programa.*"
            )
        },
        "nebraska furniture": {
            "global": (
                "❌ *Elevate:* Nebraska Furniture is not accepted.\n"
                "❌ *Clarity:* Nebraska Furniture is not accepted.\n"
                "📝 *Please inform the client that Nebraska Furniture must be resolved outside the program.*",
                "❌ *Elevate:* Nebraska Furniture no se acepta.\n"
                "❌ *Clarity:* Nebraska Furniture no se acepta.\n"
                "📝 *Por favor informe al cliente que Nebraska Furniture debe resolverse fuera del programa.*"
            )
        },
        "aaron": {
            "global": (
                "❌ *Elevate:* Aaron's Rent is not accepted.\n"
                "❌ *Clarity:* Aaron's Rent is not accepted.\n"
                "📝 *Please inform the client that Aaron's Rent must be resolved outside the program.*",
                "❌ *Elevate:* Aaron's Rent no se acepta.\n"
                "❌ *Clarity:* Aaron's Rent no se acepta.\n"
                "📝 *Por favor informe al cliente que Aaron's Rent debe resolverse fuera del programa.*"
            )
        },
        "sofi": {
            "global": (
                "❌ *Elevate:* SoFi is not accepted if federally backed.\n"
                "❌ *Clarity:* SoFi is not accepted if federally backed.\n"
                "📝 *Please inform the client that SoFi must be resolved outside the program.*",
                "❌ *Elevate:* SoFi no se acepta si está respaldado federalmente.\n"
                "❌ *Clarity:* SoFi no se acepta si está respaldado federalmente.\n"
                "📝 *Por favor informe al cliente que SoFi debe resolverse fuera del programa.*"
            )
        },
        "rc willey": {
            "global": (
                "❌ *Elevate:* RC Willey is not accepted.\n"
                "❌ *Clarity:* RC Willey is not accepted.\n"
                "📝 *Please inform the client that RC Willey must be resolved outside the program.*",
                "❌ *Elevate:* RC Willey no se acepta.\n"
                "❌ *Clarity:* RC Willey no se acepta.\n"
                "📝 *Por favor informe al cliente que RC Willey debe resolverse fuera del programa.*"
            )
        },
        "fortiva": {
            "global": (
                "❌ *Elevate:* Fortiva is not accepted.\n"
                "❌ *Clarity:* Fortiva is not accepted.\n"
                "📝 *Please inform the client that Fortiva must be resolved outside the program.*",
                "❌ *Elevate:* Fortiva no se acepta.\n"
                "❌ *Clarity:* Fortiva no se acepta.\n"
                "📝 *Por favor informe al cliente que Fortiva debe resolverse fuera del programa.*"
            )
        },
        "omni financial": {
            "global": (
                "❌ *Elevate:* OMNI Financial is not accepted.\n"
                "❌ *Clarity:* OMNI Financial is not accepted.\n"
                "📝 *Please inform the client that OMNI Financial must be resolved outside the program.*",
                "❌ *Elevate:* OMNI Financial no se acepta.\n"
                "❌ *Clarity:* OMNI Financial no se acepta.\n"
                "📝 *Por favor informe al cliente que OMNI Financial debe resolverse fuera del programa.*"
            )
        },
        "srvfinco": {
            "global": (
                "❌ *Elevate:* SRVFINCO is not accepted.\n"
                "❌ *Clarity:* SRVFINCO is not accepted.\n"
                "📝 *Please inform the client that SRVFINCO must be resolved outside the program.*",
                "❌ *Elevate:* SRVFINCO no se acepta.\n"
                "❌ *Clarity:* SRVFINCO no se acepta.\n"
                "📝 *Por favor informe al cliente que SRVFINCO debe resolverse fuera del programa.*"
            )
        },
        "bhg": {
            "global": (
                "❌ *Elevate:* BHG Bankers Healthcare Group is not accepted.\n"
                "❌ *Clarity:* BHG Bankers Healthcare Group is not accepted.\n"
                "📝 *Please inform the client that BHG must be resolved outside the program.*",
                "❌ *Elevate:* BHG Bankers Healthcare Group no se acepta.\n"
                "❌ *Clarity:* BHG Bankers Healthcare Group no se acepta.\n"
                "📝 *Por favor informe al cliente que BHG debe resolverse fuera del programa.*"
            )
        },
        "mariner finance": {
            "global": (
                "❌ *Elevate:* Mariner Finance is not accepted.\n"
                "❌ *Clarity:* Mariner Finance is not accepted.\n"
                "📝 *Please inform the client that Mariner Finance must be resolved outside the program.*",
                "❌ *Elevate:* Mariner Finance no se acepta.\n"
                "❌ *Clarity:* Mariner Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que Mariner Finance debe resolverse fuera del programa.*"
            )
        },
        "security finance": {
            "global": (
                "❌ *Elevate:* Security Finance is not accepted.\n"
                "❌ *Clarity:* Security Finance is not accepted.\n"
                "📝 *Please inform the client that Security Finance must be resolved outside the program.*",
                "❌ *Elevate:* Security Finance no se acepta.\n"
                "❌ *Clarity:* Security Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que Security Finance debe resolverse fuera del programa.*"
            )
        },
        "pioneer credit": {
            "global": (
                "❌ *Elevate:* Pioneer Credit is not accepted.\n"
                "❌ *Clarity:* Pioneer Credit is not accepted.\n"
                "📝 *Please inform the client that Pioneer Credit must be resolved outside the program.*",
                "❌ *Elevate:* Pioneer Credit no se acepta.\n"
                "❌ *Clarity:* Pioneer Credit no se acepta.\n"
                "📝 *Por favor informe al cliente que Pioneer Credit debe resolverse fuera del programa.*"
            )
        },
        "world finance": {
            "global": (
                "❌ *Elevate:* World Finance is not accepted.\n"
                "❌ *Clarity:* World Finance is not accepted.\n"
                "📝 *Please inform the client that World Finance must be resolved outside the program.*",
                "❌ *Elevate:* World Finance no se acepta.\n"
                "❌ *Clarity:* World Finance no se acepta.\n"
                "📝 *Por favor informe al cliente que World Finance debe resolverse fuera del programa.*"
            )
        },
        
        # CONDITIONAL ACCEPTANCE
        "oportun": {
            "california": (
                "❌ *Elevate:* Oportun is not accepted in California.\n"
                "❌ *Clarity:* Oportun is not accepted in California.\n"
                "📝 *Please inform the client that this debt must be resolved outside the program.*",
                "❌ *Elevate:* Oportun no se acepta en California.\n"
                "❌ *Clarity:* Oportun no se acepta en California.\n"
                "📝 *Por favor informe al cliente que esta deuda debe resolverse fuera del programa.*"
            ),
            "global": (
                "✅ *Elevate:* Oportun is accepted (max 25% of total debt).\n"
                "✅ *Clarity:* Oportun is accepted (no cap stated).\n"
                "📝 *Please ensure client meets all other program criteria.*",
                "✅ *Elevate:* Oportun se acepta (máx 25% de la deuda total).\n"
                "✅ *Clarity:* Oportun se acepta (sin límite establecido).\n"
                "📝 *Por favor asegúrese de que el cliente cumpla con todos los demás criterios del programa.*"
            )
        },
        "regional finance": {
            "global": (
                "❌ *Elevate:* Regional Finance is not accepted.\n"
                "✅ *Clarity:* Regional Finance is accepted if unsecured and meets standard criteria.\n"
                "📝 *Please check specific program requirements.*",
                "❌ *Elevate:* Regional Finance no se acepta.\n"
                "✅ *Clarity:* Regional Finance se acepta si es sin garantía y cumple con los criterios estándar.\n"
                "📝 *Por favor verifique los requisitos específicos del programa.*"
            )
        }
    }
    
    # Check for hardcoded rejections
    for creditor, conditions in hard_rejections.items():
        if creditor in question_clean:
            print(f"🔍 Found creditor: {creditor}")
            for condition, (eng_msg, spa_msg) in conditions.items():
                print(f"🔍 Checking condition: {condition}")
                print(f"🔍 Question contains 'california': {'california' in question_clean}")
                print(f"🔍 Question contains 'ca': {'ca' in question_clean}")
                print(f"🔍 Full question: {question_clean}")
                if condition == "global" or (condition in question_clean or "ca" in question_clean):
                    print(f"🔒 Hardcoded rejection triggered for {creditor} + {condition}")
                    return f"💬 *Answer (English):*\n{eng_msg}\n\n💬 *Respuesta (Spanish):*\n{spa_msg}"
                else:
                    print(f"❌ Condition not met: {condition} not in question and not 'ca'")
    
    # Step 3: Global disqualification check (additional creditors not in hardcoded rules)
    global_disqualified = [
        "accion usa", "diamond resorts", "cashnetusa", "advance financial", "armed forces bank",
        "army navy exchange", "ashley furniture", "avio credit", "b&f finance", "bannerbank",
        "blue green corp", "cc flow", "christianccu", "commonwealth cu", "conns credit",
        "cornwell tools", "credit america", "crest financial", "diamond resorts", "duvera finance",
        "educators cu", "enerbank", "founders fcu", "future income payments", "gecrb", "intermountain healthcare",
        "ispc", "john deere", "karrot loans", "lending usa", "lendmark", "loanmart", "loanosity",
        "mac credit", "mahindra finance", "mcservices", "monterey collections", "nasa fcu",
        "new credit america", "orange lake", "paramount", "payday loans", "qualstar cu",
        "schewels furniture", "snap tools", "spteachercu", "starwood vacation", "superior financial group",
        "teachers cu", "tempoe llc", "texans credit corp", "time investments", "tribal loans",
        "tsi trans world systems", "veridian credit union", "virginia cu", "webbank", "welk resort group",
        "wf/bobsfurniture", "wilshire commercial", "wilson b&t", "world acceptance corporation"
    ]
    
    for keyword in global_disqualified:
        if keyword in question_clean:
            eng = (
                "❌ *Elevate:* This creditor is disqualified and not eligible under any circumstances.\n"
                "❌ *Clarity:* This creditor is disqualified based on policy documents.\n"
                "📝 *Please advise the client to resolve this debt outside the program.*"
            )
            spa = translate_answer(eng, "spanish")
            return f"💬 *Answer (English):*\n{eng}\n\n💬 *Respuesta (Spanish):*\n{spa}"

    # Step 4: Embed and retrieve top 5 chunks
    top_chunks = get_top_chunks(question, k=5)
    valid_chunks = [(chunk, src) for chunk, src in top_chunks if is_valid_primary_chunk(chunk, src)]
    
    # Check if we have valid context
    if not valid_chunks:
        eng = (
            "⚠️ *Elevate:* No specific information found in policy documents.\n"
            "⚠️ *Clarity:* No specific information found in policy documents.\n"
            "📝 *Please consult the latest program guidelines or contact support for assistance.*"
        )
        spa = translate_answer(eng, "spanish")
        return f"💬 *Answer (English):*\n{eng}\n\n💬 *Respuesta (Spanish):*\n{spa}"
    
    context = "\n\n".join(f"[{src}]: {chunk}" for chunk, src in valid_chunks)

    # Step 5: Create new system prompt
    system_prompt = (
        "You are an expert in Elevate and Clarity debt relief programs. "
        "Use ONLY the provided document chunks to answer. "
        "Format answers clearly for each program, using emojis and friendly explanation.\n"
        "Always answer for *both* Elevate and Clarity, even if the question mentions only one.\n"
        "Use ✅ for accepted, ❌ for not accepted, ⚠️ for uncertain. "
        "If unsure or unsupported, say so clearly. If no info found in the chunks, say that too.\n\n"
        "If the question mentions a specific creditor (e.g., \"Oportun\", \"Regional Finance\", \"CashNetUSA\"), your response must evaluate that creditor's eligibility. Use rejection lists and conditional acceptance rules where found. Also check for conditions such as state restrictions (e.g., \"in California\").\n\n"
        "Be very specific when interpreting program policies. If a creditor is allowed under certain conditions (like \"Oportun not allowed in CA\"), explain those conditions clearly. Do not confuse this with overall program availability by state.\n\n"
        "If a creditor has conditional eligibility based on a state (e.g., \"Oportun not allowed in California\"), this restriction must override any general acceptance. Clearly state the condition and outcome, e.g.:\n\n"
        "> ❌ Oportun is not accepted in California, even though it may be accepted elsewhere.\n\n"
        "Do not say \"uncertain\" if a state-based restriction is present in the documents. Apply the rule directly when the question includes both the creditor and the state."
    )
    user_prompt = f"DOCUMENTS:\n{context}\n\nQUESTION:\n{question}"

    answer_en = ask_gpt_with_system_prompt(system_prompt, user_prompt)
    answer_es = translate_answer(answer_en, "spanish")
    return f"💬 *Answer (English):*\n{answer_en}\n\n💬 *Respuesta (Spanish):*\n{answer_es}"

def respond(channel, thread_ts, user_mention, question):
    try:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=f"🔍 Processing your question, {user_mention}...")
        lang = detect_language(question)
        if lang == "spanish":
            question_en = translate_answer(question, "english")
        else:
            question_en = question
        answer = handle_question(question_en)
        client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=answer)
    except Exception as e:
        print("❌ Error:", e)

@app.event("app_mention")
def handle_app_mention_events(body, event, say):
    text = event.get("text", "")
    channel = event["channel"]
    thread_ts = event.get("ts")
    user_mention = f"<@{event.get('user')}>"
    respond(channel, thread_ts, user_mention, text)

if __name__ == "__main__":
    print("🚀 Starting final patched Slack DocGPT bot with codex and document fallback...")
    chunks, chunk_sources = load_documents()
    print(f"📚 Loaded {len(chunks)} chunks from documents.")
    vectors = embed_chunks(chunks)
    index = create_vector_index(vectors)
    print("✅ Bot is ready.")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
