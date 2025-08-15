# Slack DocGPT Bot - Render.com Deployment Instructions

## Overview
This Slack bot uses OpenAI GPT to answer questions about debt relief program policies by searching through document chunks and providing bilingual responses.

## Environment Variables Required

### Slack Configuration
- `SLACK_BOT_TOKEN` - Your Slack bot user OAuth token (starts with xoxb-)
- `SLACK_APP_TOKEN` - Your Slack app-level token (starts with xapp-)

### OpenAI Configuration  
- `OPENAI_API_KEY` - Your OpenAI API key (starts with sk-)

## Local Setup (Previously Working)
1. Install Python 3.8+
2. Create virtual environment: `python -m venv venv`
3. Activate venv: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux)
4. Install dependencies: `pip install -r requirements.txt`
5. Create `.env` file with the environment variables above
6. Run: `python slack_doc_bot.py`

## Render.com Deployment Requirements

### Missing Files to Create:
1. **render.yaml** - Render deployment configuration
2. **Dockerfile** - Container configuration  
3. **app.py** - Web server wrapper for the bot
4. **requirements.txt** - Already exists ✅

### Environment Variables in Render:
Set these in your Render service environment variables:
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN` 
- `OPENAI_API_KEY`

### Deployment Steps:
1. Create the missing files listed above
2. Push to GitHub
3. Connect GitHub repo to Render
4. Set environment variables in Render dashboard
5. Deploy

## Current Issues for Render:
- Bot uses Socket Mode (local only)
- No web server for Render's HTTP requirements
- No health check endpoint
- No port binding for Render's PORT environment variable

## Next Steps:
The bot needs to be modified to work with Render's web service requirements while maintaining Slack functionality.
