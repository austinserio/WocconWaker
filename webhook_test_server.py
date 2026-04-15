# webhook_test_server.py - A minimal server for testing Facebook webhook verification
from fastapi import FastAPI, Request, Response, HTTPException
import uvicorn
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("webhook_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("webhook_test")

# Create a minimal FastAPI app
app = FastAPI(title="Webhook Test Server")

# Get the verification token from environment
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
_vt = VERIFY_TOKEN or ""
logger.info(
    "Server starting; VERIFY_TOKEN %s",
    "set (masked)" if _vt else "not set",
)
if _vt:
    logger.debug("VERIFY_TOKEN prefix: %s****", _vt[:4] if len(_vt) > 4 else "****")

@app.get("/")
async def root():
    """Root endpoint for basic testing."""
    logger.info("Root endpoint accessed")
    return {"status": "running", "message": "Webhook test server is running"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Webhook verification endpoint for Facebook."""
    # Get query parameters
    params = dict(request.query_params)
    
    # Log all request details
    logger.info("Webhook verification request received")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Request parameters: {params}")
    
    # Extract challenge parameters
    hub_mode = params.get("hub.mode")
    hub_verify_token = params.get("hub.verify_token")
    hub_challenge = params.get("hub.challenge")
    
    logger.info(f"hub.mode: {hub_mode}")
    logger.info(f"hub.verify_token: {hub_verify_token}")
    logger.info(f"hub.challenge: {hub_challenge}")
    logger.info(f"Expected verify_token: {VERIFY_TOKEN}")
    
    # Verify the webhook
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("Verification successful! Returning challenge.")
        return Response(content=hub_challenge)
    else:
        logger.error("Verification failed")
        if hub_mode != "subscribe":
            logger.error(f"Invalid hub.mode: {hub_mode}")
        if hub_verify_token != VERIFY_TOKEN:
            logger.error(f"Token mismatch: received '{hub_verify_token}', expected '{VERIFY_TOKEN}'")
        
        raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def webhook(request: Request):
    """Handle incoming webhook data."""
    try:
        data = await request.json()
        logger.info("Received webhook data")
        logger.debug(f"Data: {data}")
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting webhook test server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)