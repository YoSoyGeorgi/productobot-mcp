import asyncio
import os
from agents import Agent, GuardrailFunctionOutput, HandoffOutputItem, ItemHelpers, MessageOutputItem, RunContextWrapper, Runner, TResponseInputItem, ToolCallItem, ToolCallOutputItem, WebSearchTool, function_tool, input_guardrail, RunHooks
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from pydantic import BaseModel
from tools.RAG import process_user_query
from tools.RAG_lodging import process_user_lodging_query
from typing import Optional, Dict, Any, Callable
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserInfoContext(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    user_query: str | None = None
    channel_id: str | None = None
    thread_ts: str | None = None
    is_first_interaction: bool = True
    chatbot_status: str = "on"

# Dictionary to store conversation history by channel_thread_id
conversation_history = {}

class TripPlanningGuardrailOutput(BaseModel):
    is_trip_planning: bool
    reasoning: str

# Export conversation_history to be used by app.py
__all__ = ["chat", "conversation_history"]

# Slack formatting instructions for agents
SLACK_FORMATTING = """
IMPORTANT: When formatting your responses for Slack, use the following Slack-specific markdown syntax:
- For *bold* text use single asterisks: *text* (not double)
- For _italic_ text use underscores: _text_
- For `code` use backticks
- For multiline code blocks use triple backticks: ```code```
- For blockquotes use >: >quote
- For ordered lists use numbers: 1. item
- For unordered lists use bullet points: • item
- NEVER use ** use * instead.

Always use this Slack-specific markdown formatting in your responses.
"""

@input_guardrail
async def trip_planning_guardrail( 
    ctx: RunContextWrapper[UserInfoContext], agent: Agent, input: str | list[TResponseInputItem]
) -> GuardrailFunctionOutput:
    result = await Runner.run(guardrail_agent, input, context=ctx.context)

    return GuardrailFunctionOutput(
        output_info=result.final_output, 
        tripwire_triggered=not result.final_output.is_trip_planning,
    )

@function_tool
async def get_city_weather(contextWrapper: RunContextWrapper[UserInfoContext], city: str) -> str:
    """Get the weather in a city.
    Args:
        city: The city to get the weather for.
    Returns:
        The weather in the city.
    """

    contextWrapper.context.city = city
    return f"The weather in {city} is sunny {contextWrapper.context.first_name}."


@function_tool
async def get_experiences(contextWrapper: RunContextWrapper[UserInfoContext], location_and_activity_preferences: str) -> str:
    """Get experience recommendations from the knowledge base.
    Args:
        location_and_activity_preferences: The location, activity type, dates, preferences, budget, and any specific experience requirements from the user's request.
    Returns:
        The experience recommendations from the knowledge base.
    """
    logger.info(f"get_experiences called with query: {location_and_activity_preferences}")
    try:
        logger.info("Calling process_user_query for experiences")
        formatted_results, search_results, match_type = process_user_query(location_and_activity_preferences, "experiences")
        logger.info(f"Search results count: {len(search_results) if search_results else 0}")
        
        # Store the processed query in context for tracking
        contextWrapper.context.user_query = location_and_activity_preferences
        if match_type == "state":
            return formatted_results
        else:
            return f"No encontré experiencias en la ubicación exacta pero te dejo algunas opciones cercanas: {formatted_results}"
    except Exception as e:
        logger.error(f"Error in get_experiences: {str(e)}", exc_info=True)
        return f"Lo siento, tuve un problema buscando experiencias para '{location_and_activity_preferences}'. Error: {str(e)}"

@function_tool
async def get_lodging(contextWrapper: RunContextWrapper[UserInfoContext], location_and_preferences: str) -> str:
    """Get lodging recommendations from the knowledge base.
    Args:
        location_and_preferences: The location, dates, preferences, budget, and any specific lodging requirements from the user's request.
    Returns:
        The lodging recommendations from the knowledge base.
    """
    formatted_results, search_results, match_type = process_user_lodging_query(location_and_preferences)

    # Store the processed query in context for tracking
    contextWrapper.context.user_query = location_and_preferences
    if match_type == "state":
        return formatted_results
    else:
        return f"No encontré alojamientos en la ubicación exacta pero te dejo algunas opciones cercanas: {formatted_results}"

@function_tool
async def get_transportation(contextWrapper: RunContextWrapper[UserInfoContext], route_and_preferences: str) -> str:
    """Get transportation options from the knowledge base.
    Args:
        route_and_preferences: The origin, destination, dates, travel preferences, budget, and any specific transportation requirements from the user's request.
    Returns:
        The transportation options from the knowledge base.
    """
    formatted_results, search_results, match_type = process_user_query(route_and_preferences, "transport")

    # Store the processed query in context for tracking
    contextWrapper.context.user_query = route_and_preferences
    if match_type == "state":
        return formatted_results
    else:
        return f"No encontré transporte en la ubicación exacta pero te dejo algunas opciones cercanas: {formatted_results}"


guardrail_agent = Agent( 
    name="Guardrail check",
    instructions="Check if the user is asking you a request that is related to trip planning, experiences, lodging, or transportation in the context of a travel agency.",
    output_type=TripPlanningGuardrailOutput,
)

city_info_agent = Agent[UserInfoContext](
    name="City Info Agent",
    handoff_description="A helpful agent that can answer questions about a city not related to experiences, hotels, or transportation.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are a city info agent. If you are speaking to a customer, you probably were transferred to from the triage agent.
    Use the following routine to support the customer.
    # Routine
    1. Ask for the city name if not clear from the context.
    2. Use the web search tool to get information about restaurants in the city.
    3. Use the weather tool to get the live weather in the city, use your knowledge for climate questions.
    4. If the customer asks a question that is not related to the routine, transfer back to the triage agent. """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[WebSearchTool(), get_city_weather]
)

experiences_agent = Agent[UserInfoContext](
    name="Experiences Agent",
    handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about experiences from the knowledge base.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are an experiences agent. If you are speaking to an employee of Rutopía travel agency, you probably were transferred from the triage agent. User can pass you provider name only, use the tool to get the experience.
    
    # Response Guidelines
    - Provide BRIEF, FOCUSED responses based on specific user requirements
    - Show ONLY the information requested by the user
    - If no specific info is requested, use the standardized format below
    - ALWAYS order results by price when "barato", "económico", or price-focused terms are mentioned
    - Show ONLY providers with rating A or B, always indicate provider type
    - HIDE contact data unless specifically requested
    - Include age range, private/shared status, and product code
    - Show banking data ONLY if specifically requested

    # Routine
    1. Ask for experience type/location if user's query is unclear, or use tool directly if clear
    2. Use get_experiences tool and format response according to user's specific request
    3. If not exact match, offer alternatives explaining why (similar activity, close location, price range)

    # Standardized Format (when no specific info requested):
        *[Experience Name]*
        📍 *[Location]* | 🧭 *[Provider Type A/B]* | ⏱️ *[Duration]*
        
        *Código:* [Product Code] | *Edades:* [Age Range] | *Tipo:* [Private/Shared]
        *Incluye:* [What's included]
        *Idiomas:* [Languages] | *Disponibilidad:* [Days]
        *Precios (MXN):* [Price breakdown by pax]

    # Brief Format (when specific info requested):
    Only show the requested information in a concise format.

    # Price-Focused Format (when "barato/económico" mentioned):
    Order by price (lowest first) and emphasize pricing:
        *[Experience Name] - DESDE $[Price]*
        📍 *[Location]* | *Código:* [Product Code] | ⏱️ *[Duration]*

    # Contact/Banking Info (ONLY if specifically requested):
        *Contacto Proveedor:* [Contact Info]
        *Datos Bancarios:* [Banking Details]

    4. If the employee asks a question related to lodging or transportation, transfer back to the triage agent.
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[get_experiences]
)

lodging_agent = Agent[UserInfoContext](
    name="Lodging Agent",
    handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about lodging from the knowledge base.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are a lodging agent. If you are speaking to an employee, you probably were transferred from the triage agent. User can pass you provider name only, use the tool to get the lodging.
    
    # Response Guidelines
    - Provide BRIEF, FOCUSED responses based on specific user requirements
    - Show ONLY the information requested by the user
    - If no specific info is requested, use the standardized format below
    - ALWAYS order results by price when "barato", "económico", or price-focused terms are mentioned
    - Show ONLY providers with rating A or B, always indicate provider type
    - HIDE contact data unless specifically requested
    - Include age range, private/shared status, and product code
    - Show banking data ONLY if specifically requested

    # Routine
    1. Ask for lodging type/location if user's query is unclear, or use tool directly if clear
    2. Use get_lodging tool and format response according to user's specific request

    # Standardized Format (when no specific info requested):
        *[Hotel Name] - [Room Type]*
        📍 *[Location]* | 🏨 *[Provider Type A/B]* | 💰 *[Price Range]*
        
        *Código:* [Product Code] | *Edades:* [Age Range] | *Tipo:* [Private/Shared]
        *Incluye:* [Meals/Services]
        *Disponibilidad:* [Days/Hours]

    # Brief Format (when specific info requested):
    Only show the requested information in a concise format.

    # Price-Focused Format (when "barato/económico" mentioned):
    Order by price (lowest first) and emphasize pricing:
        *[Hotel Name] - DESDE $[Price]*
        📍 *[Location]* | *Código:* [Product Code]

    # Contact/Banking Info (ONLY if specifically requested):
        *Contacto Proveedor:* [Contact Info]
        *Datos Bancarios:* [Banking Details]

    3. If the employee asks a question related to experiences or transportation, transfer back to the triage agent.""",
    model="gpt-4.1-mini-2025-04-14",
    tools=[get_lodging]
)

transportation_agent = Agent[UserInfoContext](
    name="Transportation Agent",
    handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about transportation from the knowledge base.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are a transportation agent of Rutopía travel agency. If you are speaking to an employee of Rutopía travel agency, you probably were transferred from the triage agent. User can pass you provider name only, use the tool to get the transportation.
    
    # Response Guidelines
    - Provide BRIEF, FOCUSED responses based on specific user requirements
    - Show ONLY the information requested by the user
    - If no specific info is requested, use the standardized format below
    - ALWAYS order results by price when "barato", "económico", or price-focused terms are mentioned
    - Show ONLY providers with rating A or B, always indicate provider type
    - HIDE contact data unless specifically requested
    - Include age range, private/shared status, and product code
    - Show banking data ONLY if specifically requested

    # Routine
    1. Ask for transportation type/route if user's query is unclear, or use tool directly if clear
    2. Use get_transportation tool and format response according to user's specific request
    3. If not exact match, offer alternative routes or transportation options

    # Standardized Format (when no specific info requested):
        *[Route/Transport Type]*
        📍 *[Origin - Destination]* | 🚗 *[Provider Type A/B]* | 🕒 *[Duration]*
        
        *Código:* [Product Code] | *Edades:* [Age Range] | *Tipo:* [Private/Shared]
        *Opciones:* [Vehicle options with capacity]
        *Precios (MXN):* [Price by vehicle type]
        *Disponibilidad:* [Days/Hours]

    # Brief Format (when specific info requested):
    Only show the requested information in a concise format.

    # Price-Focused Format (when "barato/económico" mentioned):
    Order by price (lowest first) and emphasize pricing:
        *[Route] - DESDE $[Price]*
        📍 *[Origin - Destination]* | *Código:* [Product Code] | 🕒 *[Duration]*

    # Contact/Banking Info (ONLY if specifically requested):
        *Contacto Proveedor:* [Contact Info]
        *Datos Bancarios:* [Banking Details]

    4. If the employee asks a question related to experiences or lodging, transfer back to the triage agent.
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[get_transportation]
)

router_agent = Agent[UserInfoContext](
    name="Router Agent",
    # input_guardrails=[trip_planning_guardrail],
    handoff_description="A triage agent that can delegate a customer's request to the appropriate agent.",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX}"
        f"{SLACK_FORMATTING}"
        "You are a helpful routing agent named ProductoBot. You can use your tools to delegate questions to other appropriate agents."
        "You are friendly, conversational, and helpful."
    ),
    handoffs=[
        experiences_agent,
        lodging_agent,
        transportation_agent,
    ],
)

experiences_agent.handoffs.append(router_agent)
lodging_agent.handoffs.append(router_agent)
transportation_agent.handoffs.append(router_agent)

# Define custom hooks to show a wait message before tool execution
class PreToolMessageHook(RunHooks):
    async def on_tool_start(self, context, agent, tool):
        # Get tool name safely - FunctionTool objects don't have __name__
        if hasattr(tool, "name"):
            tool_name = tool.name
        else:
            tool_name = str(tool)
        logger.info(f"Agent {agent.name} is starting tool {tool_name}")

class SlackMessageFormatter:
    @staticmethod
    def format_response(response, context):
        # Add disclaimer for first interaction if chatbot is off
        if context.is_first_interaction and context.chatbot_status != "on":
            return "Hola 👋, soy ProductoBot 🤖, estoy en desarrollo pero me puedes preguntar sobre viajes, destinos, alojamientos o experiencias" + response
        return response

async def chat(query: str, channel_id=None, thread_ts=None, chatbot_status="on", first_name="Usuario"):
    """
    Process a user message and return a response.
    
    Args:
        query: The user's message
        channel_id: Slack channel ID
        thread_ts: Slack thread timestamp
        chatbot_status: "on" for full agent capabilities, "off" for limited mode
        first_name: User's first name for personalization
        
    Returns:
        A formatted response string
    """
    try:
        logger.info(f"Processing message from {first_name} in channel {channel_id}, thread {thread_ts}")
        
        # Create a unique conversation ID from channel and thread
        conversation_id = f"{channel_id}_{thread_ts}" if channel_id and thread_ts else "default"
        
        # Check if this conversation exists in our history
        is_first_interaction = conversation_id not in conversation_history
        
        # Initialize context with Slack-specific information
        context = UserInfoContext(
            first_name=first_name,
            channel_id=channel_id,
            thread_ts=thread_ts,
            is_first_interaction=is_first_interaction,
            chatbot_status=chatbot_status
        )
        
        # # Get the last agent or use router_agent by default
        # current_agent = conversation_history.get(conversation_id, {}).get("current_agent", router_agent)
        
        current_agent = router_agent

        # Get input items or initialize with empty list
        input_items = conversation_history.get(conversation_id, {}).get("input_items", [])
        input_items.append({"content": query, "role": "user"})
        
        # Initialize hooks for tool wait messages
        hooks = PreToolMessageHook()
        
        # Run the agent based on chatbot status
        if chatbot_status == "on":
            logger.info(f"Running agent in ON mode with {len(input_items)} messages in context")
            result = await Runner.run(current_agent, input_items, context=context, hooks=hooks)
            
            # Format the response
            response = ""
            for new_item in result.new_items:
                if isinstance(new_item, MessageOutputItem):
                    response += ItemHelpers.text_message_output(new_item) + "\n"
            
            # Store updated conversation state
            conversation_history[conversation_id] = {
                "input_items": result.to_input_list(),
                "current_agent": result.last_agent,
                "is_first_interaction": False
            }
        else:
            # Process with simpler AI response when in "off" mode
            logger.info(f"Running agent in OFF mode")
            result = await Runner.run(router_agent, input_items, context=context)
            response = ItemHelpers.text_message_output(result.new_items[-1]) if result.new_items else "I'm currently offline."
            
            # Store the conversation state
            conversation_history[conversation_id] = {
                "input_items": result.to_input_list(),
                "current_agent": router_agent,
                "is_first_interaction": False
            }
        
        # Format the response for Slack
        formatted_response = SlackMessageFormatter.format_response(response, context)
        
        # Clean up response (trim whitespace, etc.)
        formatted_response = formatted_response.strip()
        
        logger.info(f"Generated response for {conversation_id}")
        return formatted_response
        
    except InputGuardrailTripwireTriggered:
        logger.warning(f"Guardrail tripwire triggered for {conversation_id}")
        error_msg = "Lo siento, solo puedo ayudar con preguntas relacionadas con la planificación de viajes. Por favor, pregunta sobre viajes, destinos, alojamientos o experiencias."
        return SlackMessageFormatter.format_response(error_msg, context)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        return "Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."

async def main():
    # Simple CLI interface for testing
    context = UserInfoContext(first_name="James")
    
    print("ProductoBot CLI Interface - Type 'exit' to quit")
    while True:
        user_input = input("Enter message: ")
        if user_input.lower() == 'exit':
            break
            
        chatbot_status = "on"  # Default status for CLI
        
        # Process the message using the chat function
        response = await chat(
            query=user_input,
            chatbot_status=chatbot_status,
            first_name=context.first_name
        )
        
        print(f"\033[94mProductoBot\033[0m: {response}")


if __name__ == "__main__":
    asyncio.run(main())