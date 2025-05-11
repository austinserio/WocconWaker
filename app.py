# woccon_app.py - Main application entry point

from woccon_llama_integration import WocconAssistant
from woccon_enhancer import WocconEnhancer
from woccon_orthographic_validator import FactualGuardRailIntegration
from main import WocconT5
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from messenger_integration import MessengerIntegration
import os
import shutil, subprocess, time, socket
import threading
import time
import uvicorn
from typing import Dict, Any, Optional
import asyncio
import re
from time import sleep
from fastapi.responses import PlainTextResponse


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

# instantiate once
assistant = WocconAssistant(
    dict_path="woccon_language/dictionary.json",
    rules_path="woccon_language/rules.json",
    model="llama3:8b"
)

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


# Add these utility functions to your app.py 

def setup_webhook_logging():
    """Configure enhanced logging for webhook diagnostics."""
    import logging
    
    # Create webhook logger
    webhook_logger = logging.getLogger("webhook")
    webhook_logger.setLevel(logging.DEBUG)
    
    # Create file handler
    file_handler = logging.FileHandler("webhook_debug.log")
    file_handler.setLevel(logging.DEBUG)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    webhook_logger.addHandler(file_handler)
    webhook_logger.addHandler(console_handler)
    
    return webhook_logger

# Initialize the logger
webhook_logger = setup_webhook_logging()

#Accept verification from facebook
@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Facebook webhook verification.
    """
    hub_mode  = request.query_params.get("hub.mode")
    hub_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if messenger.verify_webhook(hub_mode, hub_token):
        # Echo back the challenge code
        return PlainTextResponse(challenge, status_code=200)

    # Token mismatch
    return PlainTextResponse("Verification failed", status_code=403)

# Add a diagnostic endpoint to help with debugging

# Replace your current webhook verification endpoint with this one
@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming messages from Facebook Messenger."""
    try:
        data = await request.json()
        print(f"Received webhook data: {data}")  # Debug log
        
        messages = messenger.process_webhook(data)
        print(f"Processed messages: {messages}")  # Debug log
        
        # Make sure assistant is initialized
        if not assistant_ready.is_set():
            # Send a temporary message to the user
            for msg in messages:
                messenger.send_message(
                    msg['user_id'], 
                    "I'm still waking up. Please wait a moment..."
                )
            return JSONResponse(content={"status": "initializing"})
        
        for msg in messages:
            user_id = msg['user_id']
            text = msg['text']
            source = msg.get('source', 'text')  # Get the source (text, quick_reply, or postback)
            
            print(f"Processing message from {user_id}: {text} (source: {source})")
            
            # Use background task to handle message so we can return quickly
            background_tasks.add_task(process_message, user_id, text, source)
        
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        print(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()  # Print full stack trace
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )



@app.get("/webhook-debug")
async def webhook_debug():
    """Diagnostic endpoint to check webhook configuration."""
    verify_token = os.environ.get('VERIFY_TOKEN', 'unknown')
    page_token = os.environ.get('PAGE_ACCESS_TOKEN', 'unknown')
    
    # Mask tokens for security
    masked_verify = verify_token[:4] + '****' if len(verify_token) > 4 else '****'
    masked_page = page_token[:4] + '****' if len(page_token) > 4 else '****'
    
    return {
        "status": "running",
        "verify_token_configured": verify_token != 'unknown',
        "verify_token_preview": masked_verify,
        "page_token_configured": page_token != 'unknown',
        "page_token_previ"
        "ew": masked_page,
        "messenger_initialized": messenger is not None,
        "assistant_ready": assistant_ready.is_set() if 'assistant_ready' in globals() else False
    }

# Add this new POST endpoint for webhook testing
@app.post("/webhook-test")
async def webhook_test(request: Request):
    """Test endpoint that echoes back webhook data."""
    try:
        data = await request.json()
        webhook_logger.info("Received test webhook data")
        webhook_logger.debug(f"Data: {data}")
        return {"status": "received", "data": data}
    except Exception as e:
        webhook_logger.error(f"Error in test webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/test")
async def test_endpoint():
    """Simple test endpoint to confirm server is running."""
    return {"status": "ok", "message": "Server is running"}

async def process_message(user_id: str, text: str, source: str = 'text'):
    """
    Process a message and route it to the Woccon assistant.
    
    This function focuses on routing messages to the assistant and handling
    special cases, but delegates all Messenger-specific formatting to 
    the MessengerIntegration class.
    
    Args:
        user_id: Facebook user ID
        text: Message text or payload
        source: Source of the message ('text', 'quick_reply', or 'postback')
    """
    global assistant, messenger
    
    print(f"Processing message: user={user_id}, text={text}, source={source}")
    
    # Show typing indicator while processing
    messenger.send_typing_indicator(user_id, True)
    sleep(0.5)
    
    try:
        # Special handling for Get Started button
        if text == "Hello! I'm interested in learning about Woccon." and source == 'postback':
            print("Processing Get Started postback")
            # Send welcome message
            welcome_message = (
                "👋 Welcome to the Woccon Language Assistant!\n\n"
                "I'm here to help you learn about the Woccon language and culture."
            )
            messenger.send_message(user_id, welcome_message)
            
            # Send a carousel with learning options after a short delay
            await asyncio.sleep(1)
            messenger.send_welcome_carousel(user_id)
            return
        
        # Check for special commands
        if text.lower() in ["help", "menu", "commands"]:
            help_message = (
                "📚 **Woccon Assistant Commands**\n\n"
                "• Type any question about the Woccon language\n"
                "• Say 'vocabulary lesson' to start learning words\n"
                "• Say 'grammar lesson' to learn grammar patterns\n"
                "• Ask how to say specific phrases in Woccon\n"
                "• Ask about the history and culture of the Woccon people"
            )
            
            # Send help message with quick replies
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "Vocab Lesson",
                    "payload": "VOCAB_LESSON"
                },
                {
                    "content_type": "text",
                    "title": "Grammar Lesson",
                    "payload": "GRAMMAR_LESSON"
                },
                {
                    "content_type": "text",
                    "title": "About Woccon",
                    "payload": "ABOUT_WOCCON"
                }
            ]
            messenger.send_quick_replies(user_id, help_message, quick_replies)
            return
            
        # Process the message with WocconAssistant
        print(f"Sending to assistant: {text}")
        response = assistant.reply(user_id, text)
        print(f"Assistant response: {response}")
        
        # CRITICAL FIX: If we get here, we MUST send some response to the user
        # Analyze the response to determine how to present it
        if not response:
            # If the assistant didn't return anything, send a default message
            messenger.send_message(user_id, "I'm sorry, I couldn't process that. Could you try again?")
            return
            
        # Check for lesson completion
        is_lesson_complete = "Lesson complete" in response or "lesson finished" in response
        
        if is_lesson_complete:
            # Parse the score from the response
            score_match = re.search(r"score:?\s*(\d+)", response.lower())
            score = int(score_match.group(1)) if score_match else 70
            
            # Determine lesson type
            lesson_type = "vocab" if "vocabulary" in response.lower() else "grammar"
            
            # Send the regular response first
            messenger.send_message(user_id, response)
            
            # Then send a card celebrating completion
            await asyncio.sleep(1)  # Small delay for better UX
            messenger.send_lesson_complete_card(user_id, lesson_type, score)
            return
        
        # Check for scenarios where quick replies are appropriate
        if any(phrase in response.lower() for phrase in ["vocabulary lesson", "grammar lesson", "start a lesson"]):
            # Add lesson-related quick replies
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "Start Vocab Lesson",
                    "payload": "VOCAB_LESSON"
                },
                {
                    "content_type": "text",
                    "title": "Start Grammar Lesson",
                    "payload": "GRAMMAR_LESSON"
                },
                {
                    "content_type": "text",
                    "title": "No Thanks",
                    "payload": "NO_LESSON"
                }
            ]
            messenger.send_quick_replies(user_id, response, quick_replies)
        elif any(phrase in response.lower() for phrase in ["yes to begin", "say 'yes'", "say yes"]):
            # Add yes/no quick replies
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "Yes",
                    "payload": "YES"
                },
                {
                    "content_type": "text",
                    "title": "No",
                    "payload": "NO"
                }
            ]
            messenger.send_quick_replies(user_id, response, quick_replies)
        else:
            # IMPORTANT: Default case - send a regular text message
            # This ensures a response is always sent back to the user
            messenger.send_message(user_id, response)
            
    except Exception as e:
        # Log the error
        print(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()
        
        # Send error message to user
        error_msg = "Sorry, I encountered an error. Please try again later."
        messenger.send_message(user_id, error_msg)
    finally:
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

def start_ollama():
    """Start Ollama exactly as `ollama serve &> ollama.log &`, and wait for it."""
    # 1️⃣ Verify the binary is on PATH
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        print("❌  Could not find 'ollama' in your $PATH")
        return

    # 2️⃣ Check if a process is already listening on 11434
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=1):
            print("✅  Ollama already up on port 11434")
            return
    except OSError:
        pass

    # 3️⃣ Fire off the exact shell command you use manually
    cmd = f"{ollama_path} serve &> ollama.log &"
    subprocess.Popen(
        cmd,
        shell=True,
        executable="/bin/bash",
        close_fds=True
    )
    print("🚀  Launched: ollama serve &> ollama.log &")

    # 4️⃣ Wait up to 20s for the socket to open
    start = time.time()
    while time.time() - start < 20:
        try:
            with socket.create_connection(("127.0.0.1", 11434), timeout=1):
                print("🟢  Ollama is now listening on 11434")
                return
        except OSError:
            time.sleep(0.5)

@app.on_event("startup")
async def startup_event():
    """Run when the FastAPI server starts up."""
    print("Starting Ollama 🦙")
    start_ollama()
    # Initialize assistant
    threading.Thread(target=initialize_assistant, daemon=True).start()
    
    # Set up Messenger profile features if tokens are available
    if os.environ.get('PAGE_ACCESS_TOKEN') and os.environ.get('VERIFY_TOKEN'):
        try:
            print("Setting up Messenger profile features...")
            messenger.setup_get_started_button()
            messenger.setup_persistent_menu()
            print("Messenger profile features set up successfully!")
        except Exception as e:
            print(f"Error setting up Messenger profile: {e}")

if __name__ == "__main__":
    # Determine mode from environment variable
    mode = os.environ.get('WOCCON_MODE', 'cli').lower()
    start_ollama()

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