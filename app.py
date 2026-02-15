# woccon_app.py - Main application entry point

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from woccon_llama_integration import WocconAssistant
from woccon_enhancer import WocconEnhancer
from woccon_orthographic_validator import FactualGuardRailIntegration
from main import WocconT5
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from messenger_integration import MessengerIntegration
import os
import sys
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


def _use_local_llm() -> bool:
    """True = use local Ollama (CUDA/RunPod); False = use Microsoft Foundry."""
    v = os.environ.get("LOCAL_LLM", "").strip().lower()
    return v in ("true", "1", "yes")

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


def get_messenger():
    """Get MessengerIntegration with current env vars (e.g. after VERIFY_TOKEN update in Azure)."""
    return MessengerIntegration(
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
    Facebook webhook verification. Reads VERIFY_TOKEN at request time (for Azure env updates).
    Defensive: no exceptions to avoid 500; return 403 on any failure.
    """
    try:
        # Avoid any attribute that might not exist; use request.url.query and parse if needed
        q = getattr(request, "query_params", None)
        hub_mode = (q.get("hub.mode") if q else None) or ""
        hub_token = (q.get("hub.verify_token") if q else None) or ""
        raw_challenge = q.get("hub.challenge") if q else None
        challenge = "" if raw_challenge is None else str(raw_challenge)
        expected_token = (os.environ.get("VERIFY_TOKEN") or "").strip()
        if (hub_mode.strip() == "subscribe" and expected_token
                and hub_token.strip() == expected_token):
            return PlainTextResponse(challenge, status_code=200)
        return PlainTextResponse("Verification failed", status_code=403)
    except Exception:
        return PlainTextResponse("Verification failed", status_code=403)

# Replace your current webhook verification endpoint with this one
@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming messages from Facebook Messenger."""
    try:
        data = await request.json()
        # Facebook may send non-message events (delivery, read, etc.) - always return 200
        if not data.get("object") == "page":
            return JSONResponse(content={"status": "ignored"})

        messages = messenger.process_webhook(data)
        print(f"[DEBUG] Processed {len(messages)} messages from webhook")

        if not messages:
            return JSONResponse(content={"status": "ok", "message": "no messages to process"})

        # Make sure assistant is initialized
        if not assistant_ready.is_set():
            for msg in messages:
                messenger.send_message(
                    msg['user_id'],
                    "I'm still waking up. Please wait a moment..."
                )
            return JSONResponse(content={"status": "initializing"})

        for msg in messages:
            user_id = msg['user_id']
            text = msg['text']
            source = msg.get('source', 'text')

            # Show typing indicator immediately (no extra permission needed; uses same Send API)
            try:
                messenger.send_typing_indicator(user_id, True)
            except Exception as send_err:
                print(f"[DEBUG] Typing indicator send failed: {send_err}")

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
    
    print(f"[TRACE] process_message ENTRY: user_id={user_id}, text={text}, source={source}")
    print(f"[TRACE] user_id type: {type(user_id)}, length: {len(user_id)}")
    print(f"[TRACE] messenger object: {type(messenger)}")
    
    # CRITICAL: Store original user_id to detect if it gets corrupted
    original_user_id = str(user_id)
    print(f"[TRACE] Stored original_user_id: {original_user_id}")
    
    # Show typing indicator while processing (configurable)
    typing_indicator_active = False
    use_typing_indicators = os.environ.get('ENABLE_TYPING_INDICATORS', 'false').lower() == 'true'
    
    if use_typing_indicators:
        print(f"🔄 Attempting to send typing indicator to user {user_id}")
        typing_response = messenger.send_typing_indicator(user_id, True)
        if typing_response.get('error'):
            error_type = typing_response.get('error')
            if error_type == 'messaging_policy_violation':
                print(f"Info: Typing indicator disabled for {user_id} - Facebook policy restriction")
            elif error_type == 'typing_indicators_disabled_for_user':
                print(f"Info: Typing indicator skipped for {user_id} - previously failed")
            else:
                print(f"Warning: Could not send typing indicator: {typing_response}")
        else:
            typing_indicator_active = True
            print(f"✅ Typing indicator ON active for {user_id}")
    
    # Add a small delay to simulate processing time
    sleep(1.0)  # Increased delay to give typing indicator time to show
    
    try:
        # Special handling for Get Started button
        if text == "Hello! I'm interested in learning about Woccon." and source == 'postback':
            print("Processing Get Started postback")
            # Turn off typing indicator before sending welcome message
            if typing_indicator_active:
                messenger.send_typing_indicator(user_id, False)
                typing_indicator_active = False
                
            # Send welcome message
            print(f"[TRACE] Before welcome message: user_id={user_id}")
            
            # CRITICAL: Check if user_id was corrupted  
            if user_id != original_user_id:
                print(f"🚨 [BUG DETECTED] user_id CHANGED in welcome! original={original_user_id}, current={user_id}")
                user_id = original_user_id
                
            welcome_message = (
                "👋 Welcome to the Woccon Language Assistant!\n\n"
                "I'm here to help you learn about the Woccon language and culture. "
                "Feel free to ask me any questions about Woccon words, grammar, history, or culture!"
            )
            messenger.send_message(user_id, welcome_message)
            return
        
        # Check for special commands
        if text.lower() in ["help", "menu", "commands"]:
            # Turn off typing indicator before sending help message
            if typing_indicator_active:
                messenger.send_typing_indicator(user_id, False)
                typing_indicator_active = False
                
            help_message = (
                "📚 **How I can help you**\n\n"
                "• Ask questions about Woccon words and their meanings\n"
                "• Learn about Woccon grammar and language structure\n"
                "• Discover the history and culture of the Woccon people\n"
                "• Get help with pronunciation and language patterns\n\n"
                "If you'd like interactive practice, you can also ask for a 'vocabulary lesson' or 'grammar lesson'.\n\n"
                "**Admin commands:** 'reset typing' to re-enable typing indicators"
            )
            
            print(f"[TRACE] Before help message: user_id={user_id}")
            messenger.send_message(user_id, help_message)
            return
            
        # Admin command to reset typing indicator cache
        if text.lower() == "reset typing":
            if user_id in messenger.typing_indicator_failed_users:
                messenger.typing_indicator_failed_users.remove(user_id)
                messenger.send_message(user_id, "✅ Typing indicators reset for your account. They will be retried on next message.")
            else:
                messenger.send_message(user_id, "ℹ️ Typing indicators were not disabled for your account.")
            return
            
        # Process the message with WocconAssistant
        print(f"[TRACE] Before assistant.reply: user_id={user_id}")
        
        # CRITICAL: Check if user_id was corrupted before assistant call
        if user_id != original_user_id:
            print(f"🚨 [BUG DETECTED] user_id CHANGED before assistant! original={original_user_id}, current={user_id}")
            user_id = original_user_id
        
        print(f"Sending to assistant: {text}")
        response = assistant.reply(user_id, text)
        print(f"[TRACE] After assistant.reply: user_id={user_id}")
        
        # CRITICAL: Check if user_id was corrupted by assistant call
        if user_id != original_user_id:
            print(f"🚨 [BUG DETECTED] user_id CHANGED by assistant! original={original_user_id}, current={user_id}")
            user_id = original_user_id
            
        print(f"Assistant response: {response}")
        print(f"[TRACE] Response length: {len(response) if response else 0}")
        print(f"[TRACE] Response type: {type(response)}")
        
        # CRITICAL FIX: If we get here, we MUST send some response to the user
        # Analyze the response to determine how to present it
        if not response:
            # If the assistant didn't return anything, send a default message
            messenger.send_message(user_id, "I'm sorry, I couldn't process that. Could you try again?")
            return
            
        # Check for lesson completion
        is_lesson_complete = "Lesson complete" in response or "lesson finished" in response
        
        if is_lesson_complete:
            # Turn off typing indicator before sending lesson completion
            if typing_indicator_active:
                messenger.send_typing_indicator(user_id, False)
                typing_indicator_active = False
                
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
            # Turn off typing indicator before sending quick replies
            if typing_indicator_active:
                messenger.send_typing_indicator(user_id, False)
                typing_indicator_active = False
                
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
            # Turn off typing indicator before sending quick replies
            if typing_indicator_active:
                messenger.send_typing_indicator(user_id, False)
                typing_indicator_active = False
                
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
            # Turn off typing indicator before sending message
            if typing_indicator_active:
                print(f"[DEBUG] Turning OFF typing indicator before sending message to {user_id}")
                messenger.send_typing_indicator(user_id, False)
                typing_indicator_active = False  # Mark as turned off
            
            print(f"[TRACE] Before final message send: user_id={user_id}")
            
            # CRITICAL: Check if user_id was corrupted
            if user_id != original_user_id:
                print(f"🚨 [BUG DETECTED] user_id CHANGED! original={original_user_id}, current={user_id}")
                print(f"🚨 [BUG DETECTED] Using original_user_id for message send")
                user_id = original_user_id
            
            # IMPORTANT: Default case - send a regular text message
            # This ensures a response is always sent back to the user
            messenger.send_message(user_id, response)
            
    except Exception as e:
        # Log the error
        print(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()
        
        # CRITICAL: Check if user_id was corrupted before error message
        if user_id != original_user_id:
            print(f"🚨 [BUG DETECTED] user_id CHANGED in exception handler! original={original_user_id}, current={user_id}")
            user_id = original_user_id
            
        # Send error message to user
        error_msg = "Sorry, I encountered an error. Please try again later."
        messenger.send_message(user_id, error_msg)
    finally:
        # Final cleanup - turn off typing indicator if it's still active
        if typing_indicator_active:
            print(f"[DEBUG] Final cleanup: turning OFF typing indicator for {user_id}")
            stop_typing_response = messenger.send_typing_indicator(user_id, False)
            if stop_typing_response.get('error'):
                print(f"Warning: Could not stop typing indicator in cleanup: {stop_typing_response}")
            else:
                print(f"[DEBUG] Final cleanup: typing indicator OFF sent successfully for {user_id}")

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

# Drive ingest: on-demand trigger (Phase 2). Use cron for every-12h; see DRIVE_INGEST.md.
_last_ingest_result: Optional[Dict[str, Any]] = None

def _require_ingest_secret(request: Request) -> None:
    """If INGEST_DRIVE_SECRET is set, require it in header X-Ingest-Secret or query param secret."""
    secret = os.environ.get("INGEST_DRIVE_SECRET")
    if not secret:
        return
    header = request.headers.get("X-Ingest-Secret")
    query = request.query_params.get("secret")
    if header != secret and query != secret:
        raise HTTPException(status_code=401, detail="Missing or invalid ingest secret")

@app.post("/admin/ingest-drive")
async def trigger_ingest_drive(request: Request):
    """
    Run Google Drive folder ingest (list + fetch Docs/PDFs). Returns summary.
    Optional: set INGEST_DRIVE_SECRET in env and pass it in header X-Ingest-Secret or ?secret=...
    """
    _require_ingest_secret(request)
    try:
        import drive_ingest
        summary = drive_ingest.run_phase1_verify()
        global _last_ingest_result
        _last_ingest_result = summary
        return summary
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "errors": [str(e)]},
        )

@app.get("/admin/ingest-drive/status")
async def ingest_drive_status(request: Request):
    """Return the result of the last ingest run (if any)."""
    _require_ingest_secret(request)
    if _last_ingest_result is None:
        return {"status": "no run yet", "last_result": None}
    return {"status": "last run", "last_result": _last_ingest_result}


@app.post("/admin/reload-language")
async def reload_language(request: Request):
    """
    Reload dictionary and rules from disk and rebuild RAG corpus (Phase 4).
    Use after merge_staging.py or when switching to unified files. Same auth as ingest (INGEST_DRIVE_SECRET).
    Optional body: {"dict_path": "...", "rules_path": "..."} to override paths for this reload only.
    """
    _require_ingest_secret(request)
    body = {}
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        pass
    dict_path = body.get("dict_path")
    rules_path = body.get("rules_path")
    try:
        result = assistant.reload_language_data(dict_path=dict_path, rules_path=rules_path)
        return {"status": "ok", **result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


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
    
    # Check if we're in an interactive environment
    if not sys.stdin.isatty():
        print("⚠️  CLI mode disabled - not running in interactive terminal")
        return
        
    print("\n🗣️  Woccon CLI — type 'control + C' to exit.\n")
    
    while True:
        try:
            msg = input("woccon> ").strip()
            if msg.lower() in ("quit", "exit"):
                break
            print("\n" + assistant.reply("cli_user", msg) + "\n")
        except KeyboardInterrupt:
            break
        except EOFError:
            print("\n⚠️  EOF detected - exiting CLI mode")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

def initialize_assistant():
    """Initialize the assistant and set the ready flag"""
    global assistant
    try:
        assistant = create_enhanced_assistant()
        print("Assistant initialization complete!")
        assistant_ready.set()
    except Exception as e:
        print(f"Error initializing assistant: {e}")

def pull_llama_model():
    """Ensure the LLaMA model is pulled before starting."""
    model_name = "llama3:8b"
    print(f"Checking if LLaMA model '{model_name}' is available...")
    
    # Command to pull the model
    cmd = f"ollama pull {model_name}"
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"Model '{model_name}' pulled successfully.")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error pulling model '{model_name}': {e.stderr}")

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
    if _use_local_llm():
        print("LOCAL_LLM=true: Starting Ollama 🦙")
        start_ollama()
        pull_llama_model()
    else:
        print("LOCAL_LLM=false: Using Microsoft Foundry (no local Ollama).")
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
    if _use_local_llm():
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