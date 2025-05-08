# woccon_app.py - Main application entry point

from woccon_llama_integration import WocconAssistant
from woccon_enhancer import WocconEnhancer
from woccon_orthographic_validator import FactualGuardRailIntegration
from main import WocconT5
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from messenger_integration import MessengerIntegration
import os
import threading
import time
import uvicorn
from typing import Dict, Any, Optional

llama_model_path = os.environ.get('LLAMA_MODEL_PATH', '/workspace/models/llama3-8b')
t5_model_path = os.environ.get('T5_MODEL_PATH', '/workspace/models/t5-base')

# Initialize FastAPI app
app = FastAPI(
    title="Wocconwaker API",
    description="A FastAPI server for the Wocconwaker language assistant with Messenger integration",
    version="1.0.0"
)

# Create a global assistant instance
assistant = None
assistant_ready = threading.Event()
user_states = {}

def create_enhanced_assistant():
    """
    Create a fully enhanced WocconAssistant with both linguistic analysis
    capabilities and protection against hallucinating diacritical marks.
    """
    # Step 1: Create and enhance WocconT5 with linguistic capabilities
    woccon = WocconT5()
    linguistic_enhancer = WocconEnhancer(woccon, rules_path="woccon_language/rules.json")
    # Now woccon has enhanced linguistic analysis features
    
    # Step 2: Create assistant with the linguistically enhanced WocconT5
    assistant = WocconAssistant()
    
    # Step 3: Add factual guard rails to prevent hallucination
    fact_checker = FactualGuardRailIntegration(
        dict_path="woccon_language/dictionary.json",
        rules_path="woccon_language/rules.json"
    )
    enhanced_assistant = fact_checker.enhance_assistant(assistant)
    
    # Return the fully enhanced assistant
    return enhanced_assistant

# Initialize the Messenger integration
messenger = MessengerIntegration(
    page_access_token=os.environ.get('PAGE_ACCESS_TOKEN'),
    verify_token=os.environ.get('VERIFY_TOKEN')
)

@app.get("/webhook")
async def verify_webhook(hub_mode: str = None, hub_verify_token: str = None, hub_challenge: str = None):
    """Webhook verification endpoint for Facebook."""
    if hub_mode and hub_verify_token and hub_challenge:
        if messenger.verify_webhook(hub_mode, hub_verify_token):
            return Response(content=hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming messages from Facebook Messenger."""
    data = await request.json()
    messages = messenger.process_webhook(data)
    
    # Make sure assistant is initialized
    if not assistant_ready.is_set():
        return JSONResponse(content={"status": "initializing", "message": "Assistant is still initializing"})
    
    for msg in messages:
        user_id = msg['user_id']
        text = msg['text']
        
        # Use background task to handle message so we can return quickly
        background_tasks.add_task(process_message, user_id, text)
    
    return JSONResponse(content={"status": "ok"})

async def process_message(user_id: str, text: str):
    """Process a message in the background."""
    global assistant
    
    # Show typing indicator while processing
    messenger.send_typing_indicator(user_id, True)
    
    # Process the message with WocconAssistant
    response = assistant.reply(user_id, text)
    
    # Send the response back to user
    messenger.send_message(user_id, response)
    
    # Stop typing indicator
    messenger.send_typing_indicator(user_id, False)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "assistant_ready": assistant_ready.is_set()}

# API endpoint to get information about the assistant
@app.get("/info")
async def get_info():
    """Get information about the Wocconwaker assistant."""
    if not assistant_ready.is_set():
        return {"status": "initializing"}
    
    return {
        "status": "ready",
        "name": "Wocconwaker",
        "version": "1.0.0", 
        "description": "Language assistant with linguistic analysis capabilities"
    }

# API endpoint to send a direct message to the assistant
@app.post("/message")
async def send_message(message: Dict[str, Any]):
    """
    Send a direct message to the assistant via API.
    
    Body: {
        "user_id": "optional-user-id",
        "text": "Your message here"
    }
    """
    if not assistant_ready.is_set():
        return {"status": "error", "message": "Assistant is still initializing"}
    
    user_id = message.get("user_id", "api_user")
    text = message.get("text")
    
    if not text:
        raise HTTPException(status_code=400, detail="Message text is required")
    
    response = assistant.reply(user_id, text)
    
    return {"status": "success", "response": response}

def run_cli():
    """Run the CLI interface in a separate thread"""
    global assistant
    print("\n🗣️  Woccon CLI — type 'control + C' to exit.\n")
    
    while True:
        try:
            msg = input("woccon> ").strip()
            if msg.lower() in ("quit", "exit"):
                break
            print("\n" + assistant.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

def initialize_assistant():
    """Initialize the assistant and set the ready flag"""
    global assistant
    try:
        assistant = create_enhanced_assistant()
        print("Assistant initialization complete!")
        assistant_ready.set()
    except Exception as e:
        print(f"Error initializing assistant: {e}")

@app.on_event("startup")
async def startup_event():
    """Run when the FastAPI server starts up."""
    threading.Thread(target=initialize_assistant, daemon=True).start()

if __name__ == "__main__":
    # Determine mode from environment variable
    mode = os.environ.get('WOCCON_MODE', 'cli').lower()
    
    if mode == 'server':
        # Run in server mode
        print("Starting in server mode...")
        port = int(os.environ.get('PORT', 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)
    elif mode == 'hybrid':
        # Run both CLI and server
        print("Starting in hybrid mode...")
        # Start initializing the assistant
        threading.Thread(target=initialize_assistant, daemon=True).start()
        # Wait for assistant to be ready
        assistant_ready.wait()
        # Start CLI in a separate thread
        cli_thread = threading.Thread(target=run_cli)
        cli_thread.daemon = True
        cli_thread.start()
        
        # Start server
        port = int(os.environ.get('PORT', 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Default to CLI mode
        initialize_assistant()
        run_cli()