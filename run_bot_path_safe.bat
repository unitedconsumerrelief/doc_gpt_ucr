@echo off
echo Recreating virtual environment (if not already exists)...
if not exist venv (
    python -m venv venv
)

echo Installing dependencies using python -m pip...
venv\Scripts\python.exe -m pip install --upgrade pip setuptools
venv\Scripts\python.exe -m pip install openai==0.28.1
venv\Scripts\python.exe -m pip install slack_bolt slack_sdk faiss-cpu python-dotenv pdfplumber tqdm

echo Launching Slack DocGPT Bot...
venv\Scripts\python.exe slack_doc_bot.py

pause
