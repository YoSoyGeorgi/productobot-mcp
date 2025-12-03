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
from supabase import create_client, Client
import json
from datetime import datetime
import random
import re

# Add the current directory to sys.path
sys.path.append(str(Path(__file__).parent))

# Direct import - no try/except needed
from ruto_agent import chat, conversation_history
from ui_components import build_home_tab_view

# Load environment variables
load_dotenv()

# Initialize the Slack app (skip if invalid tokens to allow local testing)
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
app = None
try:
    if SLACK_TOKEN and SLACK_SECRET and not SLACK_TOKEN.startswith("xoxb-tu-token") and not SLACK_SECRET.startswith("tu_"):
        app = App(token=SLACK_TOKEN, signing_secret=SLACK_SECRET)
    else:
        logging.warning("Slack tokens invalid or placeholders; skipping Slack App init for local testing.")
except Exception as e:
    logging.error(f"Error initializing Slack App: {e}")
    app = None

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

BOT_USER_ID = None
if app:
    try:
        auth_response = app.client.auth_test()
        BOT_USER_ID = auth_response["user_id"]
        logging.info(f"Bot initialized with ID: {BOT_USER_ID}")
    except Exception as e:
        logging.error(f"Error getting bot ID: {e}")

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

# Store feedback in Supabase
def store_feedback(user_id, channel_id, thread_ts, message_ts, message_text, query_text=None, thread_json=None, feedback_type="positive", feedback_comment=None):
    try:
        feedback_data = {
            "user_id": user_id,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_ts": message_ts,
            "bot_response": message_text,
            "user_query": query_text,
            "thread_json": thread_json,
            "created_at": datetime.now().isoformat(),
            "feedback_type": feedback_type,
            "feedback_comment": feedback_comment
        }
        
        result = supabase.table("feedback").insert(feedback_data).execute()
        logging.info(f"Feedback stored: {result}")
        return result
    except Exception as e:
        logging.error(f"Error storing feedback: {e}", exc_info=True)
        return None

# Find the user message that most likely triggered a bot response
def find_triggering_message(messages, bot_message_ts, bot_id):
    """
    Find the most likely user message that triggered a specific bot response.
    
    Args:
        messages: List of messages in the thread
        bot_message_ts: Timestamp of the bot message that received feedback
        bot_id: The bot's user ID
        
    Returns:
        The text of the user's query or None if not found
    """
    # Sort messages by timestamp
    sorted_messages = sorted(messages, key=lambda x: float(x.get("ts", "0")))
    
    # Find the bot message index
    bot_msg_index = None
    for i, msg in enumerate(sorted_messages):
        if msg.get("ts") == bot_message_ts:
            bot_msg_index = i
            break
    
    if bot_msg_index is None:
        return None
    
    # Look for the most recent user message before the bot message
    for i in range(bot_msg_index - 1, -1, -1):
        msg = sorted_messages[i]
        # Check if it's a user message (not from the bot)
        if msg.get("user") != bot_id and not msg.get("bot_id"):
            return msg.get("text", "")
    
    return None

# Event handlers
if app:
    @app.event("app_mention")
    def handle_app_mention(event, client, say):
        try:
            client.reactions_add(
                channel=event['channel'],
                timestamp=event['ts'],
                name='eyes'
            )
        except Exception as e:
            # Log the error but continue execution
            logging.warning(f"Could not add reaction: {e}")
        
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

            # Send the response with feedback buttons
            client.chat_postMessage(
                channel=event['channel'],
                thread_ts=thread_ts,
                text=response,
                blocks=build_response_blocks(response)
            )
        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)
            client.chat_postMessage(
                channel=event['channel'],
                thread_ts=thread_ts,
                text="Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."
            )
        finally:
            try:
                client.reactions_remove(
                    channel=event['channel'],
                    timestamp=event['ts'],
                    name='eyes'
                )
            except Exception as e:
                # Log the error but continue execution
                logging.warning(f"Could not remove reaction: {e}")

if app:
    @app.event("app_home_opened")
    def handle_app_home_opened_events(event, client, logger):
        user_id = event["user"]
        
        # Get user info
        user_info = get_user_info(client, user_id)
        user_name = user_info.get("real_name") or user_info.get("name") or f"<@{user_id}>"
        
        # Publish Home tab view
        client.views_publish(
            user_id=user_id,
            view=build_home_tab_view(user_name)
        )
        
        # If this is the first time opening the app home (event contains tab=home), send welcome message
        if event.get("tab") == "home" and not event.get("view"):
            try:
                # Open a DM with the user if not already open
                client.chat_postMessage(
                    channel=user_id,
                    text=f"¡Hola <@{user_id}>! Soy ProductoBot, tu asistente virtual para Rutopia. Estoy aquí para ayudarte con cualquier pregunta que tengas. No dudes en preguntarme lo que necesites."
                )
            except Exception as e:
                logger.error(f"Error sending welcome message: {e}")

if app:
    @app.event("message")
    def handle_message_events(event, client, logger):
        # Ignore messages from bots to prevent potential loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        # Get the message text
        message_text = event.get("text", "")
        
        # Get channel type and check if in a thread
        channel_type = event.get("channel_type")
        is_in_thread = event.get("thread_ts") is not None
        thread_ts = event.get('thread_ts')
        
        # Process direct messages (IM) always
        should_process = channel_type == "im"
        
        # Check for bot mentions
        bot_mention = f"<@{BOT_USER_ID}>" if BOT_USER_ID else None
        is_bot_mentioned = bot_mention and bot_mention in message_text
        
        # Track threads where the bot has been tagged to respond without tagging again
        # Create a unique thread identifier
        thread_id = f"{event['channel']}_{thread_ts}" if is_in_thread and thread_ts else None
        
        # For messages in threads, process if no other users are mentioned (except the bot)
        if is_in_thread and not should_process:
            # Check if message mentions any users other than the bot
            mentions_other_user = False
            
            # Look for user mentions pattern <@U...>
            mentions = re.findall(r"<@(U[A-Z0-9]+)>", message_text)
            
            # If there are mentions and any mention is not the bot, skip this message
            if mentions:
                for mention in mentions:
                    if mention != BOT_USER_ID:
                        mentions_other_user = True
                        break
                
                # If bot is explicitly mentioned, we should process regardless of other mentions
                if is_bot_mentioned:
                    should_process = True
                else:
                    should_process = not mentions_other_user
            else:
                # No mentions in the message
                # Check if this is a thread where the bot was previously mentioned
                if thread_id and thread_id in conversation_history:
                    should_process = True
                # If bot not explicitly mentioned and no history, don't process
                else:
                    should_process = False
        # For messages in channels (not in thread), only process if bot is mentioned
        elif not is_in_thread and not should_process:
            should_process = is_bot_mentioned
        
        # If we shouldn't process this message, return
        if not should_process:
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

            # Send the response with feedback buttons
            client.chat_postMessage(
                channel=event['channel'],
                thread_ts=thread_ts,
                text=response,
                blocks=build_response_blocks(response)
            )
        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)
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

# Add button interaction handlers
if app:
    @app.action("feedback_positive")
    def handle_positive_feedback(ack, body, client, logger):
        ack()
        try:
            user_id = body["user"]["id"]
            channel_id = body["channel"]["id"]
            message_ts = body["message"]["ts"]
            thread_ts = body["message"].get("thread_ts", message_ts)
            
            # Get the bot message text
            bot_message_text = extract_message_text(body["message"])
            
            # Update the message to show positive feedback was selected
            original_response_text = None
            for block in body["message"].get("blocks", []):
                if block.get("type") == "section" and block.get("text") and "¿Te fue útil esta respuesta?" not in block.get("text", {}).get("text", ""):
                    original_response_text = block["text"]["text"]
                    break
            
            if original_response_text:
                updated_blocks = build_response_blocks_with_selection(original_response_text, "positive")
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text=original_response_text,
                    blocks=updated_blocks
                )
            
            # Get thread context to find user query
            thread_response = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=100
            )
            
            user_query = None
            thread_json = None
            
            if thread_response and thread_response.get("messages"):
                thread_json = thread_response["messages"]
                user_query = find_triggering_message(thread_json, message_ts, BOT_USER_ID)
            
            # Store positive feedback
            store_feedback(
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                message_ts=message_ts,
                message_text=bot_message_text,
                query_text=user_query,
                thread_json=thread_json,
                feedback_type="positive"
            )
            
            # Send acknowledgment
            positive_responses = [
                f"¡Gracias por tu feedback positivo, <@{user_id}>! 😊",
                f"<@{user_id}>, me alegra saber que te fue útil la respuesta 🎉",
                f"¡Excelente, <@{user_id}>! Gracias por confirmar que la información fue útil ✨",
                f"<@{user_id}>, tu feedback positivo nos motiva a seguir mejorando 🚀",
                f"¡Perfecto, <@{user_id}>! Me alegra haber podido ayudarte 👍"
            ]
            
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=random.choice(positive_responses)
            )
            
            logger.info(f"Positive feedback processed for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing positive feedback: {e}", exc_info=True)

if app:
    @app.action("feedback_negative")
    def handle_negative_feedback(ack, body, client, logger):
        ack()
        try:
            user_id = body["user"]["id"]
            channel_id = body["channel"]["id"]
            message_ts = body["message"]["ts"]
            thread_ts = body["message"].get("thread_ts", message_ts)
            
            # Update the message to show negative feedback was selected
            original_response_text = None
            for block in body["message"].get("blocks", []):
                if block.get("type") == "section" and block.get("text") and "¿Te fue útil esta respuesta?" not in block.get("text", {}).get("text", ""):
                    original_response_text = block["text"]["text"]
                    break
            
            if original_response_text:
                updated_blocks = build_response_blocks_with_selection(original_response_text, "negative")
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text=original_response_text,
                    blocks=updated_blocks
                )
            
            # Open modal for detailed feedback
            client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "feedback_modal",
                    "title": {
                        "type": "plain_text",
                        "text": "Feedback"
                    },
                    "submit": {
                        "type": "plain_text",
                        "text": "Enviar"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "Cancelar"
                    },
                    "private_metadata": json.dumps({
                        "channel_id": channel_id,
                        "message_ts": message_ts,
                        "thread_ts": thread_ts
                    }),
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Cuéntanos qué faltó o qué puedo mejorar 🛠️"
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "feedback_input",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "feedback_text",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Comparte tus comentarios aquí..."
                                }
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "Tu feedback"
                            }
                        }
                    ]
                }
            )
            
            logger.info(f"Feedback modal opened for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error opening feedback modal: {e}", exc_info=True)

if app:
    @app.view("feedback_modal")
    def handle_feedback_submission(ack, body, client, logger):
        ack()
        try:
            user_id = body["user"]["id"]
            feedback_text = body["view"]["state"]["values"]["feedback_input"]["feedback_text"]["value"]
            
            # Get metadata
            metadata = json.loads(body["view"]["private_metadata"])
            channel_id = metadata["channel_id"]
            message_ts = metadata["message_ts"]
            thread_ts = metadata["thread_ts"]
            
            # Get the bot message text and thread context
            bot_message_text = ""
            user_query = None
            thread_json = None
            
            try:
                # Get thread context
                thread_response = client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=100
                )
                
                if thread_response and thread_response.get("messages"):
                    thread_json = thread_response["messages"]
                    user_query = find_triggering_message(thread_json, message_ts, BOT_USER_ID)
                    
                    # Find the bot message
                    for msg in thread_json:
                        if msg.get("ts") == message_ts:
                            bot_message_text = extract_message_text(msg)
                            break
            except Exception as e:
                logger.error(f"Error getting thread context: {e}")
            
            # Store negative feedback with detailed comments
            store_feedback(
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                message_ts=message_ts,
                message_text=bot_message_text,
                query_text=user_query,
                thread_json=thread_json,
                feedback_type="negative",
                feedback_comment=feedback_text
            )
            
            # Send acknowledgment with the feedback content
            feedback_message = f"Gracias por tu feedback detallado, <@{user_id}>. Tomaremos en cuenta tus comentarios para mejorar nuestro servicio 🙏\n\n---\n**Feedback recibido:**\n{feedback_text}"
            
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=feedback_message
            )
            
            logger.info(f"Detailed feedback submitted by user {user_id}: {feedback_text}")
            
        except Exception as e:
            logger.error(f"Error processing feedback submission: {e}", exc_info=True)

# Helper function to add feedback buttons to messages
def add_feedback_buttons():
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "¿Te fue útil esta respuesta?"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👍 Sí, fue útil"
                    },
                    "action_id": "feedback_positive"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👎 No, necesita mejorar"
                    },
                    "action_id": "feedback_negative"
                }
            ]
        }
    ]

# Helper function to add feedback buttons with selection highlighting
def add_feedback_buttons_with_selection(selected_feedback):
    positive_button = {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": "👍 Sí, fue útil"
        },
        "action_id": "feedback_positive"
    }
    
    negative_button = {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": "👎 No, necesita mejorar"
        },
        "action_id": "feedback_negative"
    }
    
    # Add primary style to the selected button
    if selected_feedback == "positive":
        positive_button["style"] = "primary"
    elif selected_feedback == "negative":
        negative_button["style"] = "danger"
    
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "¿Te fue útil esta respuesta?"
            }
        },
        {
            "type": "actions",
            "elements": [positive_button, negative_button]
        }
    ]

# Helper function to build message blocks with response and feedback buttons
def build_response_blocks(response_text):
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": response_text
            }
        },
        {
            "type": "divider"
        }
    ]
    blocks.extend(add_feedback_buttons())
    return blocks

# Helper function to build message blocks with selected feedback highlighting
def build_response_blocks_with_selection(response_text, selected_feedback):
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": response_text
            }
        },
        {
            "type": "divider"
        }
    ]
    blocks.extend(add_feedback_buttons_with_selection(selected_feedback))
    return blocks

# Helper function to extract text from Slack message (handles both text and blocks)
def extract_message_text(message):
    """Extract text content from a Slack message, handling both text and blocks"""
    # Try to get direct text first
    if message.get("text"):
        return message["text"]
    
    # If no direct text, extract from blocks
    if message.get("blocks"):
        text_parts = []
        for block in message["blocks"]:
            if block.get("type") == "section" and block.get("text"):
                text_parts.append(block["text"].get("text", ""))
        return "\n".join(text_parts)
    
    return ""

api = FastAPI(title="ProductoBot API")
handler = SlackRequestHandler(app) if app else None

logging.basicConfig(level=logging.INFO)

@api.get("/")
def root():
    return {"message": "ProductoBot API is running", "status": "healthy"}

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
        
        if handler:
            logging.info("Handling request with SlackRequestHandler...")
            response = await handler.handle(request)
            logging.info("Request handled successfully by SlackRequestHandler.")
            return response
        else:
            logging.warning("Slack handler unavailable (tokens invalid).")
            return Response(status_code=503, content="Slack handler unavailable for local testing.")
    except Exception as e:
        logging.exception("Error handling /slack/events request")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@api.get("/health")
def health_check():
    return {"status": "ok"} 