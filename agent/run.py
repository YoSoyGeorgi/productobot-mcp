import uvicorn
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Get port from environment variable or default to 8000
    port = int(os.environ.get("PORT", 8000))
    
    # Log startup information
    logger.info(f"Starting server on port {port}")
    logger.info(f"Python path: {os.environ.get('PYTHONPATH', 'Not set')}")
    logger.info(f"Current directory: {os.getcwd()}")
    
    # Check if required environment variables are set
    required_vars = ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"]
    for var in required_vars:
        if os.environ.get(var):
            logger.info(f"Environment variable {var} is set")
        else:
            logger.warning(f"Environment variable {var} is not set")
    
    # Server configuration
    logger.info("Starting uvicorn server with agent.app:api")
    uvicorn.run("agent.app:api", host="0.0.0.0", port=port, reload=True, log_level="info") 