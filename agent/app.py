import os
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_bolt import App
from dotenv import load_dotenv
from agent.rutoagent import chat

# Load environment variables
load_dotenv()

# Initialize the Slack app
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Event handlers
@app.event("app_mention")
def handle_app_mention(event, client, say):
    client.reactions_add(
        channel=event['channel'],
        timestamp=event['ts'],
        name='eyes'
    )
    
    # Get thread timestamp - use message ts as thread ts if it's the start of a thread
    thread_ts = event.get('thread_ts', event['ts'])
    
    # Pass channel and thread info to maintain conversation context
    response = chat(
        chatbot_status="on",
        query=event['text'],
        channel_id=event['channel'],
        thread_ts=thread_ts
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

@app.event("app_home_opened")
def handle_app_home_opened_events(event, client, logger):
    user_id = event["user"]
    
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
                        "text": "Bienvenido a RutoBot 👋",
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
        thread_ts=thread_ts
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

# Initialize the FastAPI app
api = FastAPI(title="RutoBot API")
handler = SlackRequestHandler(app)

@api.post("/slack/events")
async def endpoint(request: Request, background_tasks: BackgroundTasks):
    return await handler.handle(request, background_tasks)

@api.get("/health")
def health_check():
    return {"status": "ok"} 