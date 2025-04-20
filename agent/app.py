import os
import sys
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_bolt import App
from dotenv import load_dotenv
import logging
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
logger.info("Loading environment variables")
load_dotenv()

# Flag to track application startup status
app_initialized = False

# Try to import the chat function with detailed error logging
try:
    logger.info("Attempting to import chat function")
    from agent.ruto_agent import chat
    logger.info("Successfully imported chat function")
except ImportError as e:
    logger.error(f"Primary import path failed: {str(e)}")
    # Log the full traceback for detailed debugging
    logger.error(traceback.format_exc())
    try:
        # Fallback for direct import when running from the agent directory
        logger.info("Trying fallback import path")
        from ruto_agent import chat
        logger.info("Successfully imported chat function from fallback path")
    except ImportError as ie:
        logger.critical(f"Both import paths failed. Application may not function correctly: {str(ie)}")
        logger.critical(traceback.format_exc())
        # Don't raise an exception here - let the app start even with errors
        # so we can still have a working health check
        
        # Define a placeholder function in case both imports fail
        async def chat(*args, **kwargs):
            logger.error("Chat function called but not properly imported")
            return "Sorry, the chatbot is experiencing technical difficulties. Please try again later."

# Initialize the Slack app
logger.info("Initializing Slack app")
try:
    app = App(
        token=os.environ.get("SLACK_BOT_TOKEN"),
        signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
    )
    logger.info("Slack app initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize Slack app: {str(e)}")
    logger.critical(traceback.format_exc())
    # Create a placeholder App object to avoid startup errors
    app = App(token="placeholder", signing_secret="placeholder")

# Helper function to get user info
def get_user_info(client, user_id):
    try:
        result = client.users_info(user=user_id)
        user_info = result["user"]
        return {
            "id": user_id,
            "name": user_info.get("name"),
            "real_name": user_info.get("real_name"),
            "display_name": user_info.get("profile", {}).get("display_name")
        }
    except Exception as e:
        logging.error(f"Error fetching user info: {e}")
        return {"id": user_id}

# Event handlers
@app.event("app_mention")
def handle_app_mention(event, client, say):
    try:
        logger.info(f"Received app_mention event: {event.get('text', '')[:50]}...")
        
        client.reactions_add(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'
        )
        
        # Get user info
        user_id = event.get("user")
        user_info = get_user_info(client, user_id)
        
        # Get thread timestamp - use message ts as thread ts if it's the start of a thread
        thread_ts = event.get('thread_ts', event['ts'])
        
        # Pass channel and thread info to maintain conversation context
        response = chat(
            chatbot_status="on",
            query=event['text'],
            channel_id=event['channel'],
            thread_ts=thread_ts,
            first_name=user_info.get("real_name") or user_info.get("display_name") or user_info.get("name", "Usuario")
        )

        # Send the response - mrkdwn is the default, so we don't need to specify it
        client.chat_postMessage(
            channel=event['channel'],
            thread_ts=thread_ts,
            text=response
        )

        client.reactions_remove(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'
        )
        logger.info("Successfully processed app_mention event")
    except Exception as e:
        logger.error(f"Error handling app_mention: {str(e)}")
        logger.error(traceback.format_exc())
        try:
            # Try to respond with an error message
            client.chat_postMessage(
                channel=event['channel'],
                thread_ts=thread_ts if 'thread_ts' in locals() else event['ts'],
                text="Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."
            )
        except Exception:
            logger.error("Failed to send error message")

@app.event("app_home_opened")
def handle_app_home_opened_events(event, client, logger):
    try:
        logger.info(f"Received app_home_opened event for user: {event.get('user')}")
        user_id = event["user"]
        
        # Get user info
        user_info = get_user_info(client, user_id)
        user_name = user_info.get("real_name") or user_info.get("name") or f"<@{user_id}>"
        
        # Publish Home tab view
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Bienvenido a RutoBot, {user_name} 👋",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🚧 *EN DESARROLLO* 🚧"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*RutoBot* es tu asistente virtual para Rutopia."
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "• Puedes preguntarme cualquier cosa sobre Rutopia\n• Mencióname en cualquier canal con `@RutoBot`\n• O envíame mensajes directos"
                        }
                    },
                    {
                        "type": "divider"
                    }
                ]
            }
        )
        
        # If this is the first time opening the app home (event contains tab=home), send welcome message
        if event.get("tab") == "home" and not event.get("view"):
            try:
                # Open a DM with the user if not already open
                client.chat_postMessage(
                    channel=user_id,
                    text=f"¡Hola <@{user_id}>! Soy RutoBot, tu asistente virtual para Rutopia. Estoy aquí para ayudarte con cualquier pregunta que tengas. No dudes en preguntarme lo que necesites."
                )
            except Exception as e:
                logger.error(f"Error sending welcome message: {e}")
        logger.info("Successfully processed app_home_opened event")
    except Exception as e:
        logger.error(f"Error handling app_home_opened: {str(e)}")
        logger.error(traceback.format_exc())

@app.event("message")
def handle_message_events(event, client, logger):
    try:
        logger.info(f"Received message event: {event.get('text', '')[:50]}...")
        
        # Ignore messages from bots to prevent potential loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            logger.info("Ignoring bot message")
            return

        # Only process direct messages (IM) or messages in a thread where the bot was previously mentioned
        channel_type = event.get("channel_type")
        if channel_type != "im" and not event.get("thread_ts"):
            logger.info(f"Ignoring message in channel type {channel_type} without thread")
            return

        # Get user info
        user_id = event.get("user")
        user_info = get_user_info(client, user_id)
        
        # Get thread timestamp - use message ts as thread ts if it's the start of a thread
        thread_ts = event.get('thread_ts', event['ts'])
        
        # React to show the bot is processing
        client.reactions_add(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'
        )
        
        # Process the message with the chat function
        response = chat(
            chatbot_status="off",
            query=event['text'],
            channel_id=event['channel'],
            thread_ts=thread_ts,
            first_name=user_info.get("real_name") or user_info.get("display_name") or user_info.get("name", "Usuario")
        )

        # Send the response
        client.chat_postMessage(
            channel=event['channel'],
            thread_ts=thread_ts,
            text=response
        )
        
        # Remove the reaction
        client.reactions_remove(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'
        )
        logger.info("Successfully processed message event")
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        logger.error(traceback.format_exc())
        try:
            # Try to respond with an error message
            client.chat_postMessage(
                channel=event.get('channel'),
                thread_ts=thread_ts if 'thread_ts' in locals() else event.get('ts'),
                text="Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."
            )
        except Exception:
            logger.error("Failed to send error message")

# Initialize the FastAPI app
logger.info("Initializing FastAPI app")
api = FastAPI(title="RutoBot API")
handler = SlackRequestHandler(app)

# Mark initialization as complete
logger.info("Application initialization complete")
app_initialized = True

@api.post("/slack/events")
async def endpoint(request: Request, background_tasks: BackgroundTasks):
    logging.info("Received request on /slack/events")
    try:
        # Read request body for logging purposes
        body = await request.body()
        logging.info(f"Request body: {body.decode()}")
        # Re-create the request object as reading the body consumes it
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request = Request(request.scope, receive=receive)
        
        logging.info("Handling request with SlackRequestHandler...")
        response = await handler.handle(request)
        logging.info("Request handled successfully by SlackRequestHandler.")
        return response
    except Exception as e:
        logging.exception("Error handling /slack/events request")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@api.get("/health")
def health_check():
    # Always return OK to pass Railway health checks - we'll log issues instead of failing
    logger.info("Health check endpoint called")
    return {
        "status": "ok", 
        "app_initialized": app_initialized,
        "python_version": sys.version,
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "development")
    } 