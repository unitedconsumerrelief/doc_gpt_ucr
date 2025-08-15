# 🚀 Render.com Deployment Guide

## Overview
This guide will walk you through deploying your Slack DocGPT Bot to Render.com, transforming it from a local Socket Mode bot to a cloud-based web service.

## Prerequisites
- GitHub account with your code repository
- Render.com account
- Slack app configured with webhook endpoints
- OpenAI API key

## Step 1: Prepare Your Repository

### Files Created for Render:
- ✅ `app.py` - Flask web server wrapper
- ✅ `render.yaml` - Render deployment configuration
- ✅ `Dockerfile` - Container configuration
- ✅ `.dockerignore` - Docker optimization
- ✅ `requirements.txt` - Updated with Flask

### Repository Structure:
```
slack_doc_gpt_bot/
├── app.py                 # Main Flask application
├── slack_doc_bot.py      # Your existing bot logic
├── policy_codex_full_ready.py
├── requirements.txt       # Dependencies
├── render.yaml           # Render configuration
├── Dockerfile            # Container setup
├── .dockerignore         # Docker optimization
├── documents/            # Your PDF documents
└── DEPLOYMENT_GUIDE.md   # This file
```

## Step 2: Configure Slack App for Webhooks

### Current Setup (Socket Mode):
- Uses `SLACK_APP_TOKEN` for Socket Mode
- Works locally only

### New Setup (Webhook Mode):
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Select your app
3. Go to **Event Subscriptions**
4. Enable events and add your Render URL: `https://your-app-name.onrender.com/slack/events`
5. Subscribe to bot events:
   - `app_mention` - When someone mentions your bot
   - `message.im` - Direct messages to your bot

## Step 3: Deploy to Render

### Option A: Using render.yaml (Recommended)
1. Push your code to GitHub
2. Go to [render.com](https://render.com)
3. Click **New +** → **Web Service**
4. Connect your GitHub repository
5. Render will auto-detect the `render.yaml` configuration
6. Set your environment variables:
   - `SLACK_BOT_TOKEN` (xoxb-...)
   - `SLACK_APP_TOKEN` (xapp-...)
   - `OPENAI_API_KEY` (sk-...)
7. Click **Create Web Service**

### Option B: Manual Configuration
1. Create new Web Service
2. Connect GitHub repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `python app.py`
5. Set environment variables
6. Set health check path: `/health`

## Step 4: Verify Deployment

### Health Check Endpoints:
- **Home**: `https://your-app.onrender.com/`
- **Health**: `https://your-app.onrender.com/health`
- **Status**: `https://your-app.onrender.com/status`
- **Test**: `https://your-app.onrender.com/test`

### Expected Response:
```json
{
  "status": "success",
  "message": "Slack DocGPT Bot is running",
  "bot_initialized": true,
  "endpoints": {
    "health": "/health",
    "status": "/status",
    "webhook": "/slack/events"
  }
}
```

## Step 5: Test Slack Integration

1. Mention your bot in a Slack channel: `@YourBotName`
2. Check Render logs for any errors
3. Verify the bot responds correctly

## Troubleshooting

### Common Issues:

#### 1. Bot Not Responding
- Check Render logs for errors
- Verify environment variables are set correctly
- Ensure Slack webhook URL is correct

#### 2. Import Errors
- Check `requirements.txt` includes all dependencies
- Verify Python version compatibility

#### 3. Document Loading Issues
- Ensure documents are in the `documents/` folder
- Check file permissions

#### 4. Memory Issues
- Consider upgrading to a higher Render plan
- Optimize document chunking in your code

### Logs and Debugging:
- View logs in Render dashboard
- Use `/status` endpoint to check bot state
- Monitor health check endpoint

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `SLACK_BOT_TOKEN` | Bot user OAuth token | `xoxb-1234567890-...` |
| `SLACK_APP_TOKEN` | App-level token | `xapp-1234567890-...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-1234567890...` |
| `PORT` | Web server port | `5000` (auto-set by Render) |

## Cost Considerations

- **Starter Plan**: $7/month (512MB RAM, 0.1 CPU)
- **Standard Plan**: $25/month (1GB RAM, 0.5 CPU)
- **Pro Plan**: $50/month (2GB RAM, 1 CPU)

For document processing, consider Standard or Pro plans.

## Security Notes

- Never commit `.env` files to Git
- Use Render's environment variable management
- Consider adding Slack signature verification
- Monitor API usage and costs

## Next Steps

1. **Deploy and test** the basic functionality
2. **Add Slack signature verification** for security
3. **Implement rate limiting** to control costs
4. **Add monitoring and alerting**
5. **Optimize document processing** for better performance

## Support

If you encounter issues:
1. Check Render logs first
2. Verify all environment variables are set
3. Test endpoints manually
4. Check Slack app configuration
5. Review this guide for common solutions

---

**Happy Deploying! 🎉**
