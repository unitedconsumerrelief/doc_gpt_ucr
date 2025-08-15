@echo off
echo Installing dependencies using local venv...

venv\Scripts\python.exe -m pip install openai==0.28.1
venv\Scripts\python.exe -m pip install slack_bolt slack_sdk faiss-cpu python-dotenv PyMuPDF tqdm

echo Running Slack DocGPT Bot...
venv\Scripts\python.exe slack_doc_bot.py

pause

