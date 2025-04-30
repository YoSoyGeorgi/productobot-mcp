import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize OpenAI client with only the API key, no additional parameters
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# Dictionary to store conversation history by channel_thread_id
conversation_history = {}

system_message = """You are a helpful assistant for Rutopia named ProductoBot. Be friendly, conversational, and helpful. You are currently in development and do not have access to any knowledge Rutopia. Be extremely concise and to the point, since you are in development and do not have access to any knowledge Rutopia.

IMPORTANT: When formatting your responses for Slack, use the following Slack-specific markdown syntax:
- For *bold* text use single asterisks: *text* (not double)
- For _italic_ text use underscores: _text_
- For `code` use backticks
- For multiline code blocks use triple backticks: ```code```
- For blockquotes use >: >quote
- For ordered lists use numbers: 1. item
- For unordered lists use bullet points: • item

Always use this Slack-specific markdown formatting in your responses."""

def chat(chatbot_status: str, query: str, channel_id=None, thread_ts=None):
    if chatbot_status == "on":
    # Create a unique conversation ID from channel and thread
        conversation_id = f"{channel_id}_{thread_ts}" if channel_id and thread_ts else "default"
        
        # Initialize conversation history if it doesn't exist
        if conversation_id not in conversation_history:
            conversation_history[conversation_id] = [
                {"role": "system", "content": system_message}
            ]
        
        # Add user message to history
        conversation_history[conversation_id].append({"role": "user", "content": query})
        
        # Limit conversation history to last 10 messages to avoid token limits
        if len(conversation_history[conversation_id]) > 11:  # system message + 10 conversation turns
            conversation_history[conversation_id] = conversation_history[conversation_id][:1] + conversation_history[conversation_id][-10:]
        
        # Get response from OpenAI
        chat_completion = client.chat.completions.create(
            messages=conversation_history[conversation_id],
            model="gpt-4o-mini"
        )
        
        response = chat_completion.choices[0].message.content
        
        # Add assistant response to history
        conversation_history[conversation_id].append({"role": "assistant", "content": response})
        
        return response
    else:
        # Create a unique conversation ID from channel and thread
        conversation_id = f"{channel_id}_{thread_ts}" if channel_id and thread_ts else "default"
        
        # Check if this is the first message in the conversation
        is_first_message = conversation_id not in conversation_history
        
        # Initialize conversation history if it doesn't exist
        if is_first_message:
            conversation_history[conversation_id] = [
                {"role": "system", "content": system_message}
            ]
        
        # Add user message to history
        conversation_history[conversation_id].append({"role": "user", "content": query})
        
        # Limit conversation history to last 10 messages to avoid token limits
        if len(conversation_history[conversation_id]) > 11:  # system message + 10 conversation turns
            conversation_history[conversation_id] = conversation_history[conversation_id][:1] + conversation_history[conversation_id][-10:]
        
        # Get response from OpenAI
        chat_completion = client.chat.completions.create(
            messages=conversation_history[conversation_id],
            model="gpt-4o-mini"
        )
        
        ai_response = chat_completion.choices[0].message.content
        
        # Add assistant response to history
        conversation_history[conversation_id].append({"role": "assistant", "content": ai_response})
        
        # Prepend the disclaimer message to the AI response only for the first message
        if is_first_message:
            return "Hola 👋, soy ProductoBot 🤖, estoy en desarrollo, por lo pronto no estoy conectado a la base de conocimiento de Rutopía\n\n" + ai_response
        else:
            return ai_response
