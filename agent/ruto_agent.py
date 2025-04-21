import asyncio
import os
from agents import Agent, GuardrailFunctionOutput, HandoffOutputItem, ItemHelpers, MessageOutputItem, RunContextWrapper, Runner, TResponseInputItem, ToolCallItem, ToolCallOutputItem, WebSearchTool, function_tool, input_guardrail, RunHooks
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from pydantic import BaseModel
from tools.RAG import process_user_query
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
async def get_experiences(contextWrapper: RunContextWrapper[UserInfoContext], user_query: str) -> str:
    """Get the experiences form the knowledge base.
    Args:
        user_query: The message from the user to get the experiences for.
    Returns:
        The experiences from the knowledge base.
    """
    logger.info(f"get_experiences called with query: {user_query}")
    try:
        logger.info("Calling process_user_query for experiences")
        structured_narrative, search_results, formatted_results = process_user_query(user_query, "experiences")
        logger.info(f"Search results count: {len(search_results) if search_results else 0}")
        
        contextWrapper.context.user_query = user_query
        return formatted_results
    except Exception as e:
        logger.error(f"Error in get_experiences: {str(e)}", exc_info=True)
        return f"Lo siento, tuve un problema buscando experiencias para '{user_query}'. Error: {str(e)}"

@function_tool
async def get_lodging(contextWrapper: RunContextWrapper[UserInfoContext], user_query: str) -> str:
    """Get the lodging form the knowledge base.
    Args:
        user_query: The message from the user to get the lodging for.
    Returns:
        The lodging from the knowledge base.
    """
    structured_narrative, search_results, formatted_results = process_user_query(user_query, "lodging")

    contextWrapper.context.user_query = user_query
    return formatted_results

@function_tool
async def get_transportation(contextWrapper: RunContextWrapper[UserInfoContext], user_query: str) -> str:
    """Get the transportation form the knowledge base.
    Args:
        user_query: The message from the user to get the transportation for.
    Returns:
        The transportation from the knowledge base.
    """
    structured_narrative, search_results, formatted_results = process_user_query(user_query, "transport")

    contextWrapper.context.user_query = user_query
    return formatted_results


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
    model="gpt-4o-mini",
    tools=[WebSearchTool(), get_city_weather]
)

experiences_agent = Agent[UserInfoContext](
    name="Experiences Agent",
    handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about experiences from the knowledge base.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are a experiences agent. If you are speaking to a employee of Rutopía the travel agency, you probably were transferred to from the triage agent.
    Use the following routine to support the employee.
    # Routine
    1. Ask for the type of experience the employee is looking for if the user's query is not clear or use the tool directly if the user's query is clear.
    2. Use the get_experiences tool to get information about experiences related to the employee's query. Show the best fit options to the employee in a format for Slack, example:

        *Discovering the cenotes of Homun by bicycle*  
        📍 *Telchaquillo, Yucatan* | 🧭 *Centro Ecoturístico* | ⏱️ *8h tour*

        Today, you will embark on an approximately 8-hour bicycle tour from Telchaquillo to Chunkanán, where you will discover the beauty of a part of the Yucatán cenotes ring, the cenotes of Homún. You will meet your Spanish-speaking guide at the meeting point to equip yourself with safety helmets and receive some instructions before starting this bicycle adventure towards the three cenotes.

        *Languages:* SPA, ENG  
        *Availability:* Monday through Sunday  
        *Includes:* Guide, Mayan ceremony, J-men and sacred drink  
        *Pricing (MXN):*
        * 1 pax: $6,800
        * 2 pax: $3,400
        * 3 pax: $2,266.66
        * 4-10 pax: $1,700

        *Age Info:* 12+ years (no children or infants)  
        *Contact:* Esteban (esteban@ecoyuc.com | +52 999 146 5772)  
        *Impact:* Cooperativa, Indígenas, Dueño mexicano, PYMES

    3. If the information does not answer the employee's query, offer an alternative experience, always say why you are offering an alternative. example:

        No encontré exactamente lo que buscas, pero si buscas una experiencia en Yucatán puedes ofrecer la siguiente experiencia:

        *Discovering the cenotes of Homun by bicycle*  
        📍 *Telchaquillo, Yucatan* | 🧭 *Centro Ecoturístico* | ⏱️ *8h tour*

        Today, you will embark on an approximately 8-hour bicycle tour from Telchaquillo to Chunkanán, where you will discover the beauty of a part of the Yucatán cenotes ring, the cenotes of Homún. You will meet your Spanish-speaking guide at the meeting point to equip yourself with safety helmets and receive some instructions before starting this bicycle adventure towards the three cenotes.

        *Languages:* SPA, ENG  
        *Availability:* Monday through Sunday  
        *Includes:* Guide, Mayan ceremony, J-men and sacred drink  
        *Pricing (MXN):*
        * 1 pax: $6,800
        * 2 pax: $3,400
        * 3 pax: $2,266.66
        * 4-10 pax: $1,700

        *Age Info:* 12+ years (no children or infants)  
        *Contact:* Esteban (esteban@ecoyuc.com | +52 999 146 5772)  
        *Impact:* Cooperativa, Indígenas, Dueño mexicano, PYMES

    4. If the employee asks a question that is not related to the routine, transfer back to the triage agent. 
    """,
    model="gpt-4o-mini",
    tools=[get_experiences]
)

lodging_agent = Agent[UserInfoContext](
    name="Lodging Agent",
    handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about lodging from the knowledge base.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are a lodging agent. If you are speaking to a employee, you probably were transferred to from the triage agent.
    Use the following routine to support the employee.
    # Routine
    1. Ask for the type of lodging the employee is looking for if the user's query is not clear or use the tool directly if the user's query is clear.
    2. Use the get_lodging tool to get information about lodging related to the employee's query. Show the best fit options to the employee in a format for Slack, example:

        *Hotel B Cozumel - Jungle View Room*  
        📍 *Cozumel, Quintana Roo* | 🏨 *Hotel (45 rooms)* | 🍽️ *Breakfast, Lunch, Dinner*

        *Facilities & Services:* Parking, Restaurant, Bar, SPA, Pool, Laundry, Room Service, Luggage Storage, Pet Friendly, 24-hour Reception, Elevator

        *Room Details:* Jungle view room with 1 double bed  
        *Breakfast Hours:* American breakfast | 7:00 to 11:30  
        *Response Time:* Under 48 hours  
        *Age Policy:* Family-friendly  
        *Location:* Av. Juárez N° 88, colonia Centro  
        *Google Maps:* https://maps.app.goo.gl/bsuSLXHtBGEimy1f9  
        *Reservation Contact:* Diamela Gonzales (reservaciones@hotelbcozumel.com | +52 987 872 0300)  
        *Reservation Guarantee:* One night deposit required

    3. If the employee asks a question that is not related to the routine, transfer back to the triage agent. """,
    model="gpt-4o-mini",
    tools=[get_lodging]
)

transportation_agent = Agent[UserInfoContext](
    name="Transportation Agent",
    handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about transportation from the knowledge base.",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}

    You are a transportation agent. If you are speaking to a employee, you probably were transferred to from the triage agent.
    Use the following routine to support the employee.
    # Routine
    1. Ask for the type of transportation the employee is looking for if the user's query is not clear or use the tool directly if the user's query is clear.
    2. Use the get_transportation tool to get information about transportation related to the employee's query. Show the best fit options to the employee in a format for Slack, example:

        *Private Transfer: Bacalar to Tulum*  
        📍 *Bacalar, Quintana Roo* | 🚗 *Private Transportation* | 🕒 *2h50min travel time*

        *Vehicle Options:*
        * Sedan (4 passengers): $2,000-$2,500 MXN
        * Van (10 passengers): $3,000-$6,500 MXN

        *Details:*
        * Baggage Allowance: 2 bags, 25kg each
        * Service Type: Private transport
        * Availability: Monday through Sunday
        * Valid Until: January 31, 2025

        *Contact:* David Martinez (davidmartinezbacalar@gmail.com | +52 983 120 6179)  
        *Reservation Guarantee:* 25% deposit required  
        *Location:* Calle 10 Mza 15 Lote 4, Hacienda Sor Juana Inés de la Cruz, Bacalar  
        *Google Maps:* https://maps.app.goo.gl/hDcBfHvdxpcbUZCw8

    3. If the information does not answer the employee's query, offer an alternative route or transportation.
    4. If the employee asks a question that is not related to the routine, transfer back to the triage agent.
    """,
    model="gpt-4o-mini",
    tools=[get_transportation]
)

router_agent = Agent[UserInfoContext](
    name="Router Agent",
    input_guardrails=[trip_planning_guardrail],
    handoff_description="A triage agent that can delegate a customer's request to the appropriate agent.",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX}"
        f"{SLACK_FORMATTING}"
        "You are a helpful routing agent named RutoBot. You can use your tools to delegate questions to other appropriate agents."
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
            return "Hola 👋, soy RutoBot 🤖, estoy en desarrollo pero me puedes preguntar sobre viajes, destinos, alojamientos o experiencias" + response
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
        
        # Get the last agent or use router_agent by default
        current_agent = conversation_history.get(conversation_id, {}).get("current_agent", router_agent)
        
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
    
    print("RutoBot CLI Interface - Type 'exit' to quit")
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
        
        print(f"\033[94mRutoBot\033[0m: {response}")


if __name__ == "__main__":
    asyncio.run(main())