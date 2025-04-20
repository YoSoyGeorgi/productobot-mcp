import asyncio
import os
from agents import Agent, GuardrailFunctionOutput, HandoffOutputItem, ItemHelpers, MessageOutputItem, RunContextWrapper, Runner, TResponseInputItem, ToolCallItem, ToolCallOutputItem, WebSearchTool, function_tool, input_guardrail, RunHooks
from agents.exceptions import InputGuardrailTripwireTriggered
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from pydantic import BaseModel
from typing import Optional, Dict, Any, Callable
import logging
import traceback

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flag to track initialization status
agents_initialized = False

try:
    from tools.RAG import process_user_query
    logger.info("Successfully imported RAG tools")
except ImportError as e:
    logger.error(f"Failed to import RAG tools: {str(e)}")
    logger.error(traceback.format_exc())
    
    # Create a mock process_user_query function
    def process_user_query(query, query_type):
        logger.warning(f"Using mock process_user_query for {query_type}: {query}")
        return (
            "No narrative available",
            [],
            f"Lo siento, no puedo procesar esta consulta sobre {query_type} en este momento."
        )

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
    try:
        result = await Runner.run(guardrail_agent, input, context=ctx.context)
        return GuardrailFunctionOutput(
            output_info=result.final_output, 
            tripwire_triggered=not result.final_output.is_trip_planning,
        )
    except Exception as e:
        logger.error(f"Error in trip_planning_guardrail: {str(e)}")
        logger.error(traceback.format_exc())
        # Default to letting the message through if there's an error
        return GuardrailFunctionOutput(
            output_info=TripPlanningGuardrailOutput(is_trip_planning=True, reasoning="Error in guardrail, defaulting to allow"), 
            tripwire_triggered=False,
        )

@function_tool
async def get_city_weather(contextWrapper: RunContextWrapper[UserInfoContext], city: str) -> str:
    """Get the weather in a city.
    Args:
        city: The city to get the weather for.
    Returns:
        The weather in the city.
    """
    try:
        contextWrapper.context.city = city
        return f"The weather in {city} is sunny {contextWrapper.context.first_name}."
    except Exception as e:
        logger.error(f"Error in get_city_weather: {str(e)}")
        return f"Lo siento, no puedo obtener el clima para {city} en este momento."

@function_tool
async def get_experiences(contextWrapper: RunContextWrapper[UserInfoContext], user_query: str) -> str:
    """Get the experiences form the knowledge base.
    Args:
        user_query: The message from the user to get the experiences for.
    Returns:
        The experiences from the knowledge base.
    """
    try:
        structured_narrative, search_results, formatted_results = process_user_query(user_query, "experiences")
        contextWrapper.context.user_query = user_query
        return formatted_results
    except Exception as e:
        logger.error(f"Error in get_experiences: {str(e)}")
        logger.error(traceback.format_exc())
        return "Lo siento, no puedo encontrar experiencias relacionadas en este momento."

@function_tool
async def get_lodging(contextWrapper: RunContextWrapper[UserInfoContext], user_query: str) -> str:
    """Get the lodging form the knowledge base.
    Args:
        user_query: The message from the user to get the lodging for.
    Returns:
        The lodging from the knowledge base.
    """
    try:
        structured_narrative, search_results, formatted_results = process_user_query(user_query, "lodging")
        contextWrapper.context.user_query = user_query
        return formatted_results
    except Exception as e:
        logger.error(f"Error in get_lodging: {str(e)}")
        logger.error(traceback.format_exc())
        return "Lo siento, no puedo encontrar hospedajes relacionados en este momento."

@function_tool
async def get_transportation(contextWrapper: RunContextWrapper[UserInfoContext], user_query: str) -> str:
    """Get the transportation form the knowledge base.
    Args:
        user_query: The message from the user to get the transportation for.
    Returns:
        The transportation from the knowledge base.
    """
    try:
        structured_narrative, search_results, formatted_results = process_user_query(user_query, "transport")
        contextWrapper.context.user_query = user_query
        return formatted_results
    except Exception as e:
        logger.error(f"Error in get_transportation: {str(e)}")
        logger.error(traceback.format_exc())
        return "Lo siento, no puedo encontrar opciones de transporte relacionadas en este momento."

# Initialize agents
try:
    logger.info("Initializing agents")
    
    guardrail_agent = Agent( 
        name="Guardrail check",
        instructions="Check if the user is asking you a request that is related to trip planning.",
        output_type=TripPlanningGuardrailOutput,
    )
    logger.info("Guardrail agent initialized")

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
    logger.info("City info agent initialized")

    experiences_agent = Agent[UserInfoContext](
        name="Experiences Agent",
        handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about experiences from the knowledge base.",
        instructions=f"""
        {RECOMMENDED_PROMPT_PREFIX}
        {SLACK_FORMATTING}
        You are a experiences agent. If you are speaking to a employee of Rutopía the travel agency, you probably were transferred to from the triage agent.
        Use the following routine to support the employee.
        # Routine
        1. Ask for the type of experience the employee is looking for.
        2. Use the get_experiences tool to get information about experiences related to the employee's query. Show the best fit options to the employee in a format for Slack, example:

            🌌 *Experiencia destacada: Kayak bajo las estrellas en Holbox*  
            📍 *Isla Holbox* | 🧭 *Operadora local* | 🕒 *Tour de 2 horas antes de medianoche*

            Rema lejos de las luces del pueblo y sumérgete en el cielo estrellado de Holbox. Este tour guiado te permite observar constelaciones, disfrutar de aguas bioluminiscentes y nadar bajo las estrellas. No se requiere experiencia previa, solo ganas de vivir algo mágico.

            📍 *Punto de encuentro:* Av Damero, Centro, 77310 Holbox, Q.R.  
            👤 *Edades:* Solo mayores de 6 años (no se permiten menores)  
            👥 *Proveedor:* Proveedor A  
            ✅ *Producto 2025:* Listo  
            💫 *Tag:* `#nomenoresde6años`

        3. If the information does not answer the employee's query, offer an alternative experience, always say why you are offering an alternative. example:

            No encontré exactamente lo que buscas, pero si buscas una experiencia de kayak puedes ofrecer la siguiente experiencia:

            🌌 *Experiencia destacada: Kayak bajo las estrellas en Holbox*  
            📍 *Isla Holbox* | 🧭 *Operadora local* | 🕒 *Tour de 2 horas antes de medianoche*

            Rema lejos de las luces del pueblo y sumérgete en el cielo estrellado de Holbox. Este tour guiado te permite observar constelaciones, disfrutar de aguas bioluminiscentes y nadar bajo las estrellas. No se requiere experiencia previa, solo ganas de vivir algo mágico.

            📍 *Punto de encuentro:* Av Damero, Centro, 77310 Holbox, Q.R.  
            👤 *Edades:* Solo mayores de 6 años (no se permiten menores)  
            👥 *Proveedor:* Proveedor A  
            ✅ *Producto 2025:* Listo  
            💫 *Tag:* `#nomenoresde6años`

        4. If the employee asks a question that is not related to the routine, transfer back to the triage agent. 
        """,
        model="gpt-4o-mini",
        tools=[get_experiences]
    )
    logger.info("Experiences agent initialized")

    lodging_agent = Agent[UserInfoContext](
        name="Lodging Agent",
        handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about lodging from the knowledge base.",
        instructions=f"""
        {RECOMMENDED_PROMPT_PREFIX}
        {SLACK_FORMATTING}
        You are a lodging agent. If you are speaking to a employee, you probably were transferred to from the triage agent.
        Use the following routine to support the employee.
        # Routine
        1. Ask for the type of lodging the employee is looking for.
        2. Use the get_lodging tool to get information about lodging related to the employee's query. Show the best fit options to the employee in a format for Slack, example:

            🏨 *Hospedaje boutique en Calakmul*  
            📍 *Calakmul* | 🛏️ *6 habitaciones* | 🍽️ *Incluye desayuno, comida y cena*

            Alojamiento tipo boutique con restaurante, bar, estacionamiento y resguardo de equipaje. Ideal para explorar Calakmul con comodidad y atención personalizada.

            📍 *Dirección:* Camino a laguna Carolina km.1, Ejido Valentín Gómez Farías, 24643 Camp.  
            🌐 *Mapa:* https://maps.app.goo.gl/m532b7PnnBjxFcgj8  
            ⏱️ *Tiempo de respuesta:* No se aceptan reservas de último minuto  
            👤 *Edades:* Sin información específica  
            🍼 *Tag:* `#cuna`

        3. If the employee asks a question that is not related to the routine, transfer back to the triage agent. """,
        model="gpt-4o-mini",
        tools=[get_lodging]
    )
    logger.info("Lodging agent initialized")

    transportation_agent = Agent[UserInfoContext](
        name="Transportation Agent",
        handoff_description="A helpful agent of a Rutopía travel agency that can answer questions about transportation from the knowledge base.",
        instructions=f"""
        {RECOMMENDED_PROMPT_PREFIX}
        {SLACK_FORMATTING}
        You are a transportation agent. If you are speaking to a employee, you probably were transferred to from the triage agent.
        Use the following routine to support the employee.
        # Routine
        1. Ask for the type of transportation the employee is looking for.
        2. Use the get_transportation tool to get information about transportation related to the employee's query. Show the best fit options to the employee in a format for Slack, example:

            🚐 *Transporte privado: Akumal → Isla Holbox*  
            📍 *Isla Holbox* | 🛥️ *Incluye ferry, taxi y transporte marítimo* | 📅 *Disponible todos los días*

            Traslado privado desde Akumal hasta Isla Holbox, con todos los medios incluidos: transporte terrestre, tickets de ferry y taxi local para llegar a tu destino sin complicaciones.

            📍 *Dirección:* Holbox, Quintana Roo, México  
            🌐 *Mapa:* https://www.google.com/maps/place/El+Holboxe%C3%B1o/@21.5222995,-87.379604,15z/data=!4m2!3m1!1s0x0:0x4507d35ed7b4050f?sa=X&ved=2ahUKEwioiqCgkc6DAxUnj2oFHaCiAjgQ_BJ6BAgJEAA  
            ⏱️ *Tiempo de respuesta:* Menos de 48 hrs  
            👤 *Edades:* Sin restricciones

        3. If the information does not answer the employee's query, offer an alternative route or transportation.
        4. If the employee asks a question that is not related to the routine, transfer back to the triage agent.
        """,
        model="gpt-4o-mini",
        tools=[get_transportation]
    )
    logger.info("Transportation agent initialized")

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
    logger.info("Router agent initialized")

    experiences_agent.handoffs.append(router_agent)
    lodging_agent.handoffs.append(router_agent)
    transportation_agent.handoffs.append(router_agent)
    
    # Set initialization flag to true
    agents_initialized = True
    logger.info("All agents successfully initialized")

except Exception as e:
    logger.critical(f"Error initializing agents: {str(e)}")
    logger.critical(traceback.format_exc())
    
    # Create placeholder agents if initialization fails
    guardrail_agent = None
    city_info_agent = None
    experiences_agent = None
    lodging_agent = None
    transportation_agent = None
    router_agent = None
    
    logger.warning("Using placeholder agents due to initialization failure")

# Define custom hooks to show a wait message before tool execution
class PreToolMessageHook(RunHooks):
    async def on_tool_start(self, context, agent, tool):
        logger.info(f"Agent {agent.name} is starting tool {tool.__name__}")

class SlackMessageFormatter:
    @staticmethod
    def format_response(response, context):
        # Add disclaimer for first interaction if chatbot is off
        if context.is_first_interaction and context.chatbot_status != "on":
            return "Hola 👋, soy RutoBot 🤖, estoy en desarrollo, por lo pronto no estoy conectado a la base de conocimiento de Rutopía\n\n" + response
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
        
        # Check if agents were initialized properly
        if not agents_initialized:
            logger.warning("Agents not initialized properly, returning error message")
            return "Lo siento, estoy experimentando problemas técnicos. Por favor, intenta de nuevo más tarde."
        
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