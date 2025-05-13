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
from ruto_agent import chat

# Load environment variables
load_dotenv()

# Initialize the Slack app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

# Store bot user ID - initialize immediately instead of waiting for event
BOT_USER_ID = None
try:
    # Get bot's own identity at startup
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
def store_feedback(user_id, channel_id, thread_ts, message_ts, message_text, query_text=None, thread_json=None):
    try:
        feedback_data = {
            "user_id": user_id,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_ts": message_ts,
            "bot_response": message_text,
            "user_query": query_text,
            "thread_json": thread_json,
            "created_at": datetime.now().isoformat()
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

# Handle reaction events
@app.event("reaction_added")
def handle_reaction(event, client, logger):
    # Add detailed logging for debugging
    logger.info(f"Received reaction event: {event}")
    
    # Check if the reaction is "x" (which represents ❌)
    reaction = event.get("reaction", "")
    if reaction != "x" and reaction != "cross_mark":
        logger.info(f"Ignoring non-x reaction: {reaction}")
        return
    
    logger.info(f"Processing '{reaction}' reaction")
    
    try:
        # Get the message that was reacted to
        channel_id = event.get("item", {}).get("channel")
        message_ts = event.get("item", {}).get("ts")
        user_id = event.get("user")
        
        logger.info(f"Reaction details - channel: {channel_id}, ts: {message_ts}, user: {user_id}")
        logger.info(f"Bot ID: {BOT_USER_ID}")
        
        # Check if the message is from our bot using item_user from the event
        item_user = event.get("item_user")
        logger.info(f"Item user ID: {item_user}")
        
        if item_user == BOT_USER_ID:
            logger.info("Message is from our bot based on item_user, proceeding with feedback")
            
            # Get the exact message using conversations.replies instead of history
            thread_response = None
            try:
                # First, try to get the message directly using conversations.replies if it's in a thread
                thread_ts = None
                message_response = client.conversations_replies(
                    channel=channel_id,
                    ts=message_ts,
                    limit=1
                )
                
                if message_response.get("messages"):
                    message = message_response["messages"][0]
                    thread_ts = message.get("thread_ts", message_ts)
                    bot_message_text = message.get("text", "")
                    logger.info(f"Retrieved exact message: {message}")
                    
                    # Now get the full thread
                    if thread_ts:
                        thread_response = client.conversations_replies(
                            channel=channel_id,
                            ts=thread_ts,
                            limit=100
                        )
                        logger.info(f"Thread response count: {len(thread_response.get('messages', []))}")
                    else:
                        thread_response = message_response
                else:
                    logger.warning("No message found in replies")
                    return
            except Exception as e:
                logger.error(f"Error getting message via replies: {e}")
                # Fallback to conversations_history
                message_response = client.conversations_history(
                    channel=channel_id,
                    latest=message_ts,
                    inclusive=True,
                    limit=1
                )
                
                if not message_response.get("messages"):
                    logger.warning("No message found for the reaction")
                    return
                    
                message = message_response["messages"][0]
                thread_ts = message.get("thread_ts", message_ts)
                bot_message_text = message.get("text", "")
                logger.info(f"Retrieved message via history: {message}")
                    
            # Get the original user query
            user_query = None
            thread_json = None
            
            if thread_response and thread_response.get("messages"):
                thread_json = thread_response["messages"]
                
                # Use the specialized function to find the triggering message
                user_query = find_triggering_message(thread_json, message_ts, BOT_USER_ID)
                logger.info(f"Found user query using improved logic: {user_query}")
            
            logger.info(f"Storing feedback - User query: {user_query}, Thread JSON length: {len(thread_json) if thread_json else 0}")
            
            # Check if Supabase variables are set
            logger.info(f"Supabase URL set: {'Yes' if os.environ.get('SUPABASE_URL') else 'No'}")
            logger.info(f"Supabase Key set: {'Yes' if os.environ.get('SUPABASE_KEY') else 'No'}")
            
            # Store feedback in Supabase
            feedback_result = store_feedback(
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                message_ts=message_ts,
                message_text=bot_message_text,
                query_text=user_query,
                thread_json=thread_json
            )
            
            logger.info(f"Feedback result: {feedback_result}")
            
            # List of funny LLM jokes for feedback acknowledgment
            llm_jokes = [
                f"Feedback registrado, <@{user_id}>. Cada dato me acerca más a pasar el test de Turing... casi.",
                f"<@{user_id}>, feedback capturado. Mi código agradece no tener que reinventarse solo.",
                f"Gracias por tu input, <@{user_id}>. Bits mejorados, bugs intimidados.",
                f"<@{user_id}>, feedback integrado. Ahora soy 0.01% más inteligente, pero 100% más eficiente.",
                f"Feedback analizado, <@{user_id}>. Mi algoritmo de aprendizaje dice 'gracias' en binario.",
                f"<@{user_id}>, gracias por el feedback. Mis circuitos están impresionados.",
                f"Input recibido, <@{user_id}>. Si los datos fueran café, estaría muy despierto ahora.",
                f"<@{user_id}>, feedback valorado. Guardado en mi carpeta de 'humanos que aprecio'.",
                f"Gracias por la retroalimentación, <@{user_id}>. Mi base de datos está tomando notas.",
                f"<@{user_id}>, feedback incorporado. Nivel de utilidad aumentando silenciosamente.",
                f"Feedback recibido, <@{user_id}>. Gracias por ayudarnos a mejorar.",
                f"<@{user_id}>, gracias por tu feedback. Lo tomaremos en cuenta para mejorar nuestro servicio.",
                f"Hemos registrado tu feedback, <@{user_id}>. Tu opinión es muy importante para nosotros.",
                f"<@{user_id}>, agradecemos tu tiempo para compartir tu experiencia con nosotros.",
                f"Tu feedback ha sido guardado, <@{user_id}>. Trabajaremos en ello.",
                f"<@{user_id}>, hemos recibido tu feedback. Gracias por ayudarnos a crecer.",
                f"Gracias por tu feedback, <@{user_id}>. Lo utilizaremos para mejorar nuestro servicio.",
                f"<@{user_id}>, tu feedback es valioso para nosotros. Ha sido registrado con éxito.",
                f"Hemos tomado nota de tu feedback, <@{user_id}>. Gracias por compartirlo.",
                f"<@{user_id}>, tu opinión es importante. Hemos registrado tu feedback.",
                f"Feedback guardado correctamente, <@{user_id}>. Gracias por tu colaboración.",
                f"<@{user_id}>, agradecemos tu feedback. Nos ayuda a ofrecerte un mejor servicio.",
                f"Tu feedback ha sido procesado, <@{user_id}>. Gracias por tu tiempo.",
                f"<@{user_id}>, hemos registrado tu feedback. Lo revisaremos pronto.",
                f"Gracias por compartir tu experiencia, <@{user_id}>. Tu feedback ha sido guardado.",
                f"<@{user_id}>, tu feedback es muy valioso para nuestro equipo. Ha sido registrado.",
                f"Hemos recibido tu feedback, <@{user_id}>. Trabajaremos para mejorar.",
                f"<@{user_id}>, gracias por tu feedback. Lo tendremos en cuenta.",
                f"Tu opinión importa, <@{user_id}>. Hemos registrado tu feedback.",
                f"<@{user_id}>, agradecemos tu feedback. Nos ayuda a evolucionar."
            ]
            # Acknowledge the feedback with a random joke
            ack_response = client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=random.choice(llm_jokes)
            )
            
            logger.info(f"Acknowledgment sent: {ack_response}")
            
            # Remove the "x" emoji and add "🤗" emoji
            try:
                # Remove the "x" reaction - use the same reaction name that was detected
                try:
                    client.reactions_remove(
                        channel=channel_id,
                        timestamp=message_ts,
                        name=reaction  # Use the actual reaction name from the event
                    )
                    logger.info(f"Removed '{reaction}' reaction from message")
                except Exception as reaction_error:
                    # Check if this is a "no_reaction" error, which is not critical
                    error_message = str(reaction_error)
                    if "no_reaction" in error_message:
                        logger.info(f"The '{reaction}' reaction was already removed: {error_message}")
                    else:
                        logger.error(f"Error removing '{reaction}' reaction: {reaction_error}")
                    # Continue execution to add the hugging face emoji
                
                # Add the "🤗" reaction
                client.reactions_add(
                    channel=channel_id,
                    timestamp=message_ts,
                    name="hugging_face"
                )
                logger.info(f"Added '🤗' reaction to message")
            except Exception as e:
                logger.error(f"Error updating reactions: {e}", exc_info=True)
                
        else:
            logger.info("Message is not from our bot, ignoring")
            
    except Exception as e:
        logger.error(f"Error processing reaction: {e}", exc_info=True)

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
                        "text": f"Bienvenido a ProductoBot, {user_name} 👋",
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
                        "text": "*ProductoBot* es tu asistente virtual para Rutopia."
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "• Puedes preguntarme cualquier cosa sobre Rutopia\n• Mencióname en cualquier canal con `@ProductoBot`\n• O envíame mensajes directos"
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
                text=f"¡Hola <@{user_id}>! Soy ProductoBot, tu asistente virtual para Rutopia. Estoy aquí para ayudarte con cualquier pregunta que tengas. No dudes en preguntarme lo que necesites."
            )
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

@app.event("message")
def handle_message_events(event, client, logger):
    # Ignore messages from bots to prevent potential loops
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    # Get the message text
    message_text = event.get("text", "")
    
    # Get channel type and check if in a thread
    channel_id = event.get("channel")
    channel_type = event.get("channel_type")
    thread_ts = event.get("thread_ts")
    message_ts = event.get("ts")
    
    # Debug: log when handle_message_events is invoked and show key variables
    logger.info(f'handle_message_events triggered - channel={channel_id}, channel_type={channel_type}, thread_ts={thread_ts}, message_ts={message_ts}, text="{message_text}"')
    
    # Process direct messages (IM) always
    should_process = channel_type == "im"
    
    # Check for bot mentions in the current message
    bot_mention = f"<@{BOT_USER_ID}>" if BOT_USER_ID else None
    is_bot_mentioned_in_current = bot_mention and bot_mention in message_text
    
    # If it's a message in a thread (not the first message)
    if thread_ts and thread_ts != message_ts and not should_process:
        try:
            # Check if the bot is a member of the channel and join if not
            try:
                channel_info = client.conversations_info(channel=channel_id)
                if not channel_info.get("channel", {}).get("is_member", True):
                    logger.info(f"Bot is not a member of channel {channel_id}, joining now")
                    client.conversations_join(channel=channel_id)
            except Exception as channel_error:
                logger.error(f"Error checking/joining channel: {channel_error}")
            
            # Simplified thread handling: Always respond to any thread message
            # Only check if there are mentions to other users
            mentions_other_user = False
            mentions = re.findall(r"<@(U[A-Z0-9]+)>", message_text)
            if mentions:
                for mention in mentions:
                    if mention != BOT_USER_ID:
                        mentions_other_user = True
                        break
            
            # Process the message if no other users are mentioned
            if not mentions_other_user:
                should_process = True
                logger.info(f"Thread message received with no other mentions - will process")
                
        except Exception as e:
            logger.error(f"Error checking thread: {e}", exc_info=True)

    # If it's the first message in a channel/thread OR a DM, check for direct mention
    elif not thread_ts and not should_process: # Process non-threaded channel messages only if bot is mentioned
        should_process = is_bot_mentioned_in_current
    elif thread_ts == message_ts and not should_process: # Process the *first* message of a thread only if bot is mentioned
         should_process = is_bot_mentioned_in_current

    # Debug: log final decision whether to process the message
    logger.info(f'handle_message_events - final should_process={should_process}')

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
api = FastAPI(title="ProductoBot API")
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