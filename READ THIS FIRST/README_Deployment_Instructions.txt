
==============================
Slack DocGPT Bot Deployment Guide
==============================

This guide helps you deploy the Slack-connected GPT document bot to a new PC.

------------------------------
✅ 1. Copy Project Folder
------------------------------
Copy the entire 'slack_doc_gpt_bot/' folder to the new PC.

Make sure it includes:
- slack_doc_bot.py
- documents/ (PDFs go here)
- .env (with your Slack + OpenAI keys)
- run_bot.bat (for quick launch)
- requirements.txt

------------------------------
✅ 2. Install Python
------------------------------
Install Python 3.10+ from: https://www.python.org/downloads

During setup, check: "Add Python to PATH"

------------------------------
✅ 3. Open CMD and Navigate to the Bot Folder
------------------------------
Use the command prompt to go to the folder:
> cd path\to\slack_doc_gpt_bot

------------------------------
✅ 4. Create Virtual Environment
------------------------------
Run:
> python -m venv venv

Activate it:
- On Windows:
> venv\Scripts\activate

------------------------------
✅ 5. Install Required Libraries
------------------------------
> pip install -r requirements.txt

------------------------------
✅ 6. Verify .env File
------------------------------
Open .env and make sure it includes:
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
OPENAI_API_KEY=sk-...

------------------------------
✅ 7. Run the Bot
------------------------------
Double-click:
> run_bot.bat

This launches the bot in CMD with environment activated.

------------------------------
🧠 Tips
------------------------------
- Add more PDFs into the /documents folder
- Bot responds in Slack when @mentioned
- Auto-detects Spanish or English questions

You're now ready to run the bot on any PC!
