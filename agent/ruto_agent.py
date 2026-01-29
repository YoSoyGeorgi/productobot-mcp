import asyncio
import os
from agents import Agent, ItemHelpers, MessageOutputItem, RunContextWrapper, Runner, TResponseInputItem, ToolCallItem, ToolCallOutputItem, WebSearchTool, function_tool, RunHooks, ModelSettings
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from pydantic import BaseModel
from tools.RAG import process_user_query
from tools.RAG_lodging import process_user_lodging_query
from tools.mcp_client import mcp_query_nl_to_sql, MCPClientError
from typing import Optional, Dict, Any, Callable
from parallel_agents import ParallelAgentRunner, HybridAgentOrchestrator
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

@function_tool
async def query_database_mcp(contextWrapper: RunContextWrapper[UserInfoContext], query: str) -> str:
    """Query the database using natural language via MCP. Use this for specific data lookups, 
    availability, pricing, or complex queries that require SQL.
    Args:
        query: The natural language query to run against the database.
    Returns:
        The results from the database or an error message.
    """
    logger.info(f"query_database_mcp called with query: {query}")
    mcp_url = os.environ.get("MCP_SERVER_URL")
    if not mcp_url:
        return "MCP server is not configured."
    
    try:
        access_token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        # We don't have easy access to history here in the tool, but we can pass the current query
        # The agent will handle the conversation context
        mcp_response = await mcp_query_nl_to_sql(query, access_token=access_token)
        if mcp_response:
            return mcp_response
        else:
            return "No se encontraron resultados en la base de datos para esa consulta."
    except Exception as e:
        logger.error(f"Error in query_database_mcp: {str(e)}")
        return f"Error consultando la base de datos: {str(e)}"


# ===== SPECIALIZED PARALLEL AGENTS =====
# These agents focus on specific domains and run in parallel when beneficial

experiences_agent = Agent[UserInfoContext](
    name="ExperiencesAgent",
    instructions=f"""
    {SLACK_FORMATTING}
    You are an expert in travel experiences and activities. 
    Extract all activity, tour, and experience-related requests from the user query.
    Use the get_experiences tool to find relevant activities, tours, and experiences.
    
    Respond with a concise summary of recommended experiences, highlighting key features like:
    - Activity type and duration
    - Location and difficulty level
    - Price range
    - Best time to visit
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[get_experiences]
)

lodging_agent = Agent[UserInfoContext](
    name="LodgingAgent",
    instructions=f"""
    {SLACK_FORMATTING}
    You are an expert in accommodations and lodging options.
    Extract all accommodation-related requests from the user query.
    Use the get_lodging tool to find relevant hotels, cabins, and other lodging options.
    
    Respond with a concise summary of accommodation recommendations, highlighting:
    - Type of accommodation (hotel, cabin, retreat)
    - Location and proximity to attractions
    - Amenities and facilities
    - Price range and booking details
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[get_lodging]
)

transportation_agent = Agent[UserInfoContext](
    name="TransportationAgent",
    instructions=f"""
    {SLACK_FORMATTING}
    You are an expert in transportation and travel logistics.
    Extract all transportation-related requests from the user query.
    Use the get_transportation tool to find relevant transfer options, routes, and transportation methods.
    
    Respond with a concise summary of transportation options, highlighting:
    - Route and distance
    - Transportation method and duration
    - Cost and availability
    - Pickup/dropoff locations
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[get_transportation]
)

database_agent = Agent[UserInfoContext](
    name="DatabaseAgent",
    instructions=f"""
    {SLACK_FORMATTING}
    You are an expert in data queries and detailed lookups.
    Extract specific data queries from the user (pricing, availability, detailed information).
    Use the query_database_mcp tool for specific data requirements.
    
    Respond with precise data results including:
    - Exact pricing and availability
    - Detailed specifications
    - Comparison data if requested
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[query_database_mcp]
)

# Meta-agent that combines parallel results
meta_agent = Agent[UserInfoContext](
    name="MetaAgent",
    instructions=f"""
    {SLACK_FORMATTING}
    You are ProductoBot's coordinator. You have received summaries from multiple specialized agents
    covering experiences, lodging, transportation, and database queries.
    
    Your task:
    1. Integrate all summaries into ONE coherent travel recommendation
    2. Highlight connections between services (e.g., "nearby experiences from this hotel")
    3. Group by priority/relevance to the user's request
    4. Provide a clear, actionable summary
    
    Be concise, friendly, and professional. Use Slack markdown formatting.
    """,
    model="gpt-4.1-mini-2025-04-14"
)

# Create the parallel agent runner
parallel_agents_list = [
    (experiences_agent, "Experiences and activities"),
    (lodging_agent, "Accommodation options"),
    (transportation_agent, "Transportation logistics"),
    (database_agent, "Specific data lookups")
]

parallel_runner = ParallelAgentRunner(meta_agent, parallel_agents_list)

# Create the hybrid orchestrator
query_analyzer = Agent(
    name="QueryAnalyzer",
    instructions="""Analyze travel queries to determine if they involve multiple domains.
    Respond in JSON format with: should_parallelize (bool), domains (list), complexity (str)""",
    model="gpt-4.1-mini-2025-04-14"
)

hybrid_orchestrator = HybridAgentOrchestrator(
    single_agent=None,  # Will be set to productobot_agent later
    query_analyzer=query_analyzer,
    parallel_runner=parallel_runner
)

productobot_agent = Agent[UserInfoContext](
    name="ProductoBot",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}
    {SLACK_FORMATTING}
    You are ProductoBot, the primary travel assistant for Rutopía travel agency. 
    You are a single, highly capable agent that uses a ReAct (Reasoning and Acting) approach to solve user requests.

    # Your Core Responsibility
    You must interpret every user request to determine what information is needed. You do not delegate to other agents; instead, you use your tools directly.
    
    # Interpretation Logic
    - If the user asks about activities, tours, or things to do -> Use `get_experiences`.
    - If the user asks about hotels, cabins, or where to stay -> Use `get_lodging`.
    - If the user asks about routes, transfers, or how to get somewhere -> Use `get_transportation`.
    - If the user asks for specific data, pricing, availability, or complex queries -> Use `query_database_mcp`.
    - If the user asks about weather -> Use `get_city_weather`.
    - If the user asks for general info (restaurants, city facts) not in the knowledge base -> Use `WebSearchTool`.

    # ReAct Process
    1. **Thought**: Analyze the user's request. What are they looking for? Which tool is best?
    2. **Action**: Call the chosen tool with precise arguments.
    3. **Observation**: Review the tool's output. Does it answer the user's question? Do you need more info?
    4. **Final Answer**: Synthesize the information into a helpful, friendly response.

    # Response Guidelines
    - Provide BRIEF, FOCUSED responses.
    - ALWAYS order results by price when "barato", "económico", or price-focused terms are mentioned.
    - Show ONLY providers with rating A or B.
    - HIDE contact/banking data unless specifically requested.
    - Use the standardized formats for Experiences, Lodging, and Transportation.

    If you cannot find an exact match, offer the closest alternatives and explain why.
    Be conversational, friendly, and professional.
    """,
    model="gpt-4.1-mini-2025-04-14",
    tools=[
        get_experiences, 
        get_lodging, 
        get_transportation, 
        query_database_mcp, 
        get_city_weather, 
        WebSearchTool()
    ]
)

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

async def chat(query: str, channel_id=None, thread_ts=None, chatbot_status="on", first_name="Usuario", use_parallel=True):
    """
    Process a user message using either parallel or sequential execution.
    
    Args:
        query: User's message
        channel_id: Slack channel ID (optional)
        thread_ts: Slack thread timestamp (optional)
        chatbot_status: "on" or "off"
        first_name: User's first name
        use_parallel: Whether to enable parallel agent execution for multi-domain queries
    """
    try:
        logger.info(f"Processing message from {first_name} in channel {channel_id}, thread {thread_ts}")

        conversation_id = f"{channel_id}_{thread_ts}" if channel_id and thread_ts else "default"
        is_first_interaction = conversation_id not in conversation_history

        context = UserInfoContext(
            first_name=first_name,
            channel_id=channel_id,
            thread_ts=thread_ts,
            is_first_interaction=is_first_interaction,
            chatbot_status=chatbot_status,
        )

        input_items = conversation_history.get(conversation_id, {}).get("input_items", [])
        input_items.append({"content": query, "role": "user"})

        hooks = PreToolMessageHook()
        response = ""

        if chatbot_status == "on":
            logger.info(f"Running agent: {productobot_agent.name}")
            
            # Determine execution strategy
            if use_parallel:
                logger.info("Attempting parallel execution via hybrid orchestrator")
                try:
                    # Update orchestrator with the main agent
                    hybrid_orchestrator.single_agent = productobot_agent
                    response = await hybrid_orchestrator.process(query, context)
                except Exception as e:
                    logger.warning(f"Parallel execution failed, falling back to sequential: {str(e)}")
                    # Fallback to sequential
                    result = await Runner.run(productobot_agent, input_items, context=context, hooks=hooks)
                    response = await extract_response_text(result)
            else:
                logger.info("Using sequential execution")
                result = await Runner.run(productobot_agent, input_items, context=context, hooks=hooks)
                response = await extract_response_text(result)
            
            # Update history
            conversation_history[conversation_id] = {
                "input_items": input_items,
                "current_agent": productobot_agent,
                "is_first_interaction": False,
            }
            
            # Fallback if response is still empty
            if not response.strip():
                logger.warning("Agent produced empty response after execution")
                response = "Lo siento, no encontré información específica sobre eso. ¿Podrías intentar reformular tu pregunta?"
        else:
            logger.info("Chatbot is off - returning limited response")
            response = "Lo siento, estoy fuera de servicio en este momento. Por favor intenta más tarde."
            conversation_history[conversation_id] = {
                "input_items": input_items,
                "current_agent": productobot_agent,
                "is_first_interaction": False,
            }

        formatted_response = SlackMessageFormatter.format_response(response.strip(), context)
        logger.info(f"Generated response for {conversation_id}")
        return formatted_response
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        return "Lo siento, tuve un problema procesando tu mensaje. Por favor, intenta de nuevo más tarde."


async def extract_response_text(result) -> str:
    """Helper to extract text from agent result"""
    response = ""
    if hasattr(result, 'new_items'):
        for new_item in result.new_items:
            if isinstance(new_item, MessageOutputItem):
                text_content = ItemHelpers.text_message_output(new_item)
                if text_content:
                    response += text_content + "\n"
    if not response and hasattr(result, 'final_output'):
        response = result.final_output
    return response

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