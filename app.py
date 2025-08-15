import os
import threading
import time
from flask import Flask, jsonify, request
from slack_doc_bot import app as slack_app, client, chunks, chunk_sources, index, load_documents, embed_chunks, create_vector_index

# Initialize Flask app
app = Flask(__name__)

# Global variables for bot state
bot_initialized = False
bot_thread = None

def initialize_bot():
    """Initialize the Slack bot with documents and vector index"""
    global bot_initialized, chunks, chunk_sources, index
    
    try:
        print("🚀 Initializing Slack DocGPT bot...")
        
        # Load documents and create vector index
        chunks, chunk_sources = load_documents()
        print(f"📚 Loaded {len(chunks)} chunks from documents.")
        
        vectors = embed_chunks(chunks)
        index = create_vector_index(vectors)
        print("✅ Vector index created successfully.")
        
        bot_initialized = True
        print("🎉 Bot initialization complete!")
        
    except Exception as e:
        print(f"❌ Error initializing bot: {e}")
        bot_initialized = False

def start_slack_bot():
    """Start the Slack bot in a separate thread"""
    global bot_thread
    
    if bot_thread and bot_thread.is_alive():
        return
    
    def run_bot():
        try:
            from slack_bolt.adapter.socket_mode import SocketModeHandler
            SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
            if SLACK_APP_TOKEN:
                print("🔌 Starting Slack bot in Socket Mode...")
                SocketModeHandler(slack_app, SLACK_APP_TOKEN).start()
            else:
                print("⚠️ SLACK_APP_TOKEN not found, bot will run in webhook mode only")
        except Exception as e:
            print(f"❌ Error starting Slack bot: {e}")
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

@app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        "status": "success",
        "message": "Slack DocGPT Bot is running",
        "bot_initialized": bot_initialized,
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "webhook": "/slack/events"
        }
    })

@app.route('/health')
def health():
    """Health check endpoint required by Render"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "bot_initialized": bot_initialized
    })

@app.route('/status')
def status():
    """Detailed status endpoint"""
    return jsonify({
        "status": "success",
        "bot_initialized": bot_initialized,
        "chunks_loaded": len(chunks) if chunks else 0,
        "vector_index_ready": index is not None,
        "environment": {
            "slack_bot_token": "✅ Set" if os.getenv("SLACK_BOT_TOKEN") else "❌ Missing",
            "slack_app_token": "✅ Set" if os.getenv("SLACK_APP_TOKEN") else "❌ Missing",
            "openai_api_key": "✅ Set" if os.getenv("OPENAI_API_KEY") else "❌ Missing"
        }
    })

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events (alternative to Socket Mode)"""
    try:
        # Verify the request is from Slack
        if request.headers.get('Content-Type') == 'application/json':
            data = request.get_json()
            
            # Handle URL verification challenge
            if data.get('type') == 'url_verification':
                return jsonify({'challenge': data.get('challenge')})
            
            # Handle other Slack events
            if data.get('type') == 'event_callback':
                event = data.get('event', {})
                
                # Handle app mention events
                if event.get('type') == 'app_mention':
                    # Process the mention using your existing bot logic
                    # This would need to be adapted from your current respond function
                    return jsonify({'status': 'event_received'})
            
            return jsonify({'status': 'event_received'})
        
        return jsonify({'error': 'Invalid content type'}), 400
        
    except Exception as e:
        print(f"❌ Error handling Slack event: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/test')
def test():
    """Test endpoint to verify the bot is working"""
    if not bot_initialized:
        return jsonify({
            "status": "error",
            "message": "Bot not yet initialized",
            "retry_after": "30 seconds"
        }), 503
    
    return jsonify({
        "status": "success",
        "message": "Bot is ready and operational",
        "chunks_available": len(chunks) if chunks else 0,
        "vector_index_ready": index is not None
    })

if __name__ == '__main__':
    # Initialize bot on startup
    initialize_bot()
    
    # Start Slack bot in background thread
    start_slack_bot()
    
    # Get port from environment (Render requirement)
    port = int(os.environ.get('PORT', 5000))
    
    print(f"🌐 Starting Flask server on port {port}")
    print(f"🔗 Health check: http://localhost:{port}/health")
    print(f"📊 Status: http://localhost:{port}/status")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
