import os
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_bolt import App
from dotenv import load_dotenv
import logging
import sys
import asyncio
from pathlib import Path
from functools import wraps

# Add the current directory to sys.path
sys.path.append(str(Path(__file__).parent))

# Direct import - no try/except needed
from ruto_agent import chat

# Load environment variables
load_dotenv()

# Initialize the Slack app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

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

# Helper to run async functions in sync context
def run_async(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If no event loop exists, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # Create a future in the running loop
            future = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop)
            return future.result()
        else:
            # If loop is not running, run the coroutine until complete
            return loop.run_until_complete(func(*args, **kwargs))
    return wrapper

# Synchronous wrapper for the async chat function
@run_async
async def sync_chat(**kwargs):
    return await chat(**kwargs)

# Event handlers
@app.event("app_mention")
def handle_app_mention(event, client, say):
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
    
    try:
        # Pass channel and thread info to maintain conversation context
        response = sync_chat(
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
    except Exception as e:
        logging.error(f"Error processing message: {e}", exc_info=True)
        client.chat_postMessage(
            channel=event['channel'],
            thread_ts=thread_ts,
            text="Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."
        )
    finally:
        client.reactions_remove(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'
        )

@app.event("app_home_opened")
def handle_app_home_opened_events(event, client, logger):
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

@app.event("message")
def handle_message_events(event, client, logger):
    # Ignore messages from bots to prevent potential loops
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    # Only process direct messages (IM) or messages in a thread where the bot was previously mentioned
    channel_type = event.get("channel_type")
    if channel_type != "im" and not event.get("thread_ts"):
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
    
    try:
        # Process the message with the chat function
        response = sync_chat(
            chatbot_status="on",
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
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        client.chat_postMessage(
            channel=event['channel'],
            thread_ts=thread_ts,
            text="Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."
        )
    finally:
        # Remove the reaction
        client.reactions_remove(
            channel=event['channel'],
            timestamp=event['ts'],
            name='eyes'
        )

# Initialize the FastAPI app
api = FastAPI(title="RutoBot API")
handler = SlackRequestHandler(app)

logging.basicConfig(level=logging.INFO)

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
    return {"status": "ok"} 