"""
Parallel Agents Module for ProductoBot
Uses asyncio to execute specialized agents concurrently and combine their outputs via a meta-agent.
This reduces latency when handling multi-domain queries (e.g., experiences + lodging + transportation).
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, TypeVar, Generic
from agents import Agent, Runner, ModelSettings, RunContextWrapper
from pydantic import BaseModel

try:
    from parallel_config import (
        PARALLEL_EXECUTION_TIMEOUT,
        ENABLE_PARALLEL_AGENTS,
        LOG_EXECUTION_TIMELINE,
        DEBUG_AGENT_EXECUTION,
        should_use_parallel,
        detect_domains
    )
except ImportError:
    # Defaults if config not available
    PARALLEL_EXECUTION_TIMEOUT = 30
    ENABLE_PARALLEL_AGENTS = True
    LOG_EXECUTION_TIMELINE = False
    DEBUG_AGENT_EXECUTION = False
    def should_use_parallel(_detected_domains: List[str]) -> bool:
        return True
    def detect_domains(_query: str) -> List[str]:
        return []

logger = logging.getLogger(__name__)

if DEBUG_AGENT_EXECUTION:
    logger.setLevel(logging.DEBUG)

class UserInfoContext(BaseModel):
    """Context shared across parallel agents"""
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    user_query: str | None = None
    channel_id: str | None = None
    thread_ts: str | None = None
    is_first_interaction: bool = True
    chatbot_status: str = "on"


class ParallelAgentRunner:
    """Manager for running multiple agents in parallel and coordinating their outputs"""

    def __init__(self, meta_agent: Agent, parallel_agents: List[tuple]):
        """
        Args:
            meta_agent: The final agent that combines outputs from parallel agents
            parallel_agents: List of tuples (agent, description) to run in parallel
        """
        self.meta_agent = meta_agent
        self.parallel_agents = parallel_agents
        self.execution_times = {}

    async def run_single_agent(
        self,
        agent: Agent,
        query: str,
        context: Optional[UserInfoContext] = None
    ) -> Dict[str, Any]:
        """Run a single agent and track execution time"""
        import time
        
        agent_name = agent.name
        start_time = time.time()
        
        try:
            logger.info(f"Starting parallel agent: {agent_name}")
            result = await Runner.run(agent, query, context=context)
            
            execution_time = time.time() - start_time
            self.execution_times[agent_name] = execution_time
            
            logger.info(f"Completed {agent_name} in {execution_time:.2f}s")
            
            return {
                "agent_name": agent_name,
                "status": "success",
                "output": result.final_output if hasattr(result, 'final_output') else str(result),
                "execution_time": execution_time
            }
        except Exception as e:
            execution_time = time.time() - start_time
            self.execution_times[agent_name] = execution_time
            
            logger.error(f"Error in {agent_name}: {str(e)}")
            return {
                "agent_name": agent_name,
                "status": "error",
                "output": f"Error: {str(e)}",
                "execution_time": execution_time
            }

    async def run_parallel(
        self,
        query: str,
        context: Optional[UserInfoContext] = None
    ) -> str:
        """
        Execute multiple agents in parallel and combine results via meta-agent.
        
        Args:
            query: User query to process
            context: Optional context object passed to all agents
            
        Returns:
            Combined response from meta-agent
        """
        try:
            # 1. Run all parallel agents concurrently
            logger.info(f"Running {len(self.parallel_agents)} agents in parallel")
            
            tasks = [
                self.run_single_agent(agent, query, context)
                for agent, _ in self.parallel_agents
            ]
            
            # Run with timeout
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks),
                    timeout=PARALLEL_EXECUTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning(f"Parallel execution timeout after {PARALLEL_EXECUTION_TIMEOUT}s")
                results = []
                for task in tasks:
                    try:
                        result = await asyncio.wait_for(task, timeout=1)
                        results.append(result)
                    except:
                        results.append({
                            "agent_name": "Unknown",
                            "status": "timeout",
                            "output": "Agent execution timed out",
                            "execution_time": PARALLEL_EXECUTION_TIMEOUT
                        })
            
            # 2. Aggregate results into labeled summaries
            labeled_summaries = []
            for result in results:
                agent_name = result["agent_name"]
                output = result["output"]
                status = result["status"]
                exec_time = result.get("execution_time", 0)
                
                if status == "success":
                    if LOG_EXECUTION_TIMELINE:
                        labeled_summaries.append(f"### {agent_name} ({exec_time:.2f}s)\n{output}\n")
                    else:
                        labeled_summaries.append(f"### {agent_name}\n{output}\n")
                else:
                    logger.warning(f"Agent {agent_name} returned status '{status}': {output}")
            
            # 3. Pass aggregated summaries to meta-agent
            collected_summaries = "\n".join(labeled_summaries)
            logger.info("Passing aggregated results to meta-agent")
            
            meta_result = await Runner.run(self.meta_agent, collected_summaries, context=context)
            final_output = meta_result.final_output if hasattr(meta_result, 'final_output') else str(meta_result)
            
            logger.info("Parallel execution completed successfully")
            return final_output
            
        except Exception as e:
            logger.error(f"Error in parallel execution: {str(e)}", exc_info=True)
            raise


class HybridAgentOrchestrator:
    """
    Determines whether to use parallel or sequential execution based on query analysis.
    Uses a query analyzer agent to decide the best execution strategy.
    """

    def __init__(
        self,
        single_agent: Agent,
        query_analyzer: Agent,
        parallel_runner: Optional[ParallelAgentRunner] = None
    ):
        self.single_agent = single_agent
        self.query_analyzer = query_analyzer
        self.parallel_runner = parallel_runner

    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze query to determine if parallel execution would be beneficial.
        Returns: {
            "should_parallelize": bool,
            "domains": List[str],  # e.g., ["experiences", "lodging", "transportation"]
            "complexity": "simple" | "moderate" | "complex"
        }
        """
        analysis_prompt = f"""
        Analyze this user query and determine if it would benefit from parallel processing.
        
        Query: "{query}"
        
        Return a JSON response with:
        - should_parallelize: true if query covers multiple domains (experiences, lodging, transportation, etc.)
        - domains: list of relevant domains
        - complexity: "simple", "moderate", or "complex"
        
        Example: "Dame hoteles y experiencias en Cancún" -> should_parallelize: true, domains: ["lodging", "experiences"]
        """
        
        try:
            result = await Runner.run(self.query_analyzer, analysis_prompt)
            # Parse result and extract JSON
            output_text = result.final_output if hasattr(result, 'final_output') else str(result)
            
            # Basic JSON extraction (could be enhanced with regex)
            import json
            import re
            json_match = re.search(r'\{.*\}', output_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                domains = analysis.get("domains") or []
                analysis["should_parallelize"] = bool(analysis.get("should_parallelize")) and should_use_parallel(domains)
                return analysis
            
            # Fallback: simple heuristic
            keywords = {
                "experiences": ["actividad", "experiencia", "tour", "visita"],
                "lodging": ["hotel", "alojamiento", "hospedaje", "cabaña"],
                "transportation": ["transporte", "transfer", "ruta", "cómo llegar"]
            }
            
            found_domains = []
            for domain, terms in keywords.items():
                if any(term in query.lower() for term in terms):
                    found_domains.append(domain)
            
            return {
                "should_parallelize": should_use_parallel(found_domains),
                "domains": found_domains,
                "complexity": "complex" if len(found_domains) > 1 else "simple"
            }
            
        except Exception as e:
            logger.warning(f"Error analyzing query: {str(e)}")
            return {
                "should_parallelize": False,
                "domains": [],
                "complexity": "simple"
            }

    async def process(
        self,
        query: str,
        context: Optional[UserInfoContext] = None
    ) -> str:
        """
        Process query using either parallel or sequential execution based on analysis.
        """
        try:
            # Fast-path: keyword detection to avoid analyzer overhead when parallel won't be used
            detected_domains = detect_domains(query)
            if not should_use_parallel(detected_domains):
                analysis = {
                    "should_parallelize": False,
                    "domains": detected_domains,
                    "complexity": "complex" if len(detected_domains) > 1 else "simple"
                }
            else:
                # Analyze query (model-based)
                analysis = await self.analyze_query(query)
            logger.info(f"Query analysis: {analysis}")
            
            # Use parallel if beneficial and runner is available
            if analysis["should_parallelize"] and self.parallel_runner:
                logger.info(f"Using parallel execution for domains: {analysis['domains']}")
                return await self.parallel_runner.run_parallel(query, context)
            else:
                logger.info("Using sequential execution")
                result = await Runner.run(self.single_agent, query, context=context)
                return result.final_output if hasattr(result, 'final_output') else str(result)
                
        except Exception as e:
            logger.error(f"Error in orchestrator.process: {str(e)}", exc_info=True)
            # Fallback to single agent
            result = await Runner.run(self.single_agent, query, context=context)
            return result.final_output if hasattr(result, 'final_output') else str(result)


def create_parallel_agents_from_tools(
    tools_spec: List[Dict[str, str]]
) -> List[Agent]:
    """
    Factory function to create specialized agents from tool specifications.
    
    Args:
        tools_spec: List of dicts with keys: name, instructions, tools
        
    Returns:
        List of Agent instances
    """
    agents = []
    for spec in tools_spec:
        agent = Agent(
            name=spec["name"],
            instructions=spec["instructions"],
            model="gpt-4-mini",
            tools=spec.get("tools", [])
        )
        agents.append(agent)
    return agents
