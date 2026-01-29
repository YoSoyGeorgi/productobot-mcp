"""
Example: Using Parallel Agents for Multi-Domain Queries
Demonstrates the benefits of parallel execution in ProductoBot
"""

import asyncio
import logging
from ruto_agent import chat, UserInfoContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demonstrate_parallel_agents():
    """
    Examples showing how parallel agents improve response time for multi-domain queries.
    """
    
    # Example 1: Multi-domain query (benefits from parallelization)
    print("\n" + "="*60)
    print("EXAMPLE 1: Multi-Domain Query (Parallel Execution)")
    print("="*60)
    multi_domain_query = "Quiero ir a Cancún durante 5 días. Necesito un hotel bonito, experiencias de buceo y saber cómo llegar desde la capital."
    
    print(f"\nQuery: {multi_domain_query}")
    print("\nThis query involves:")
    print("  • Lodging (hotel)")
    print("  • Experiences (buceo)")
    print("  • Transportation (how to get there)")
    print("\nWith parallel execution, all 3 agents run concurrently!")
    
    response = await chat(
        query=multi_domain_query,
        first_name="María",
        use_parallel=True  # Enable parallel execution
    )
    print(f"\nResponse:\n{response}")
    
    
    # Example 2: Single-domain query (uses sequential agent)
    print("\n" + "="*60)
    print("EXAMPLE 2: Single-Domain Query (Sequential Execution)")
    print("="*60)
    single_domain_query = "¿Qué hoteles hay en Playa del Carmen con piscina?"
    
    print(f"\nQuery: {single_domain_query}")
    print("\nThis query only involves lodging, so sequential execution is used.")
    
    response = await chat(
        query=single_domain_query,
        first_name="Carlos",
        use_parallel=False  # Or True - orchestrator will detect it's simple
    )
    print(f"\nResponse:\n{response}")
    
    
    # Example 3: Complex query with data lookup
    print("\n" + "="*60)
    print("EXAMPLE 3: Complex Multi-Domain Query")
    print("="*60)
    complex_query = "Dame opciones de alojamiento de lujo en Tulum, experiencias de yoga y senderismo, y quiero saber disponibilidad para el próximo mes de julio."
    
    print(f"\nQuery: {complex_query}")
    print("\nThis query involves:")
    print("  • Lodging (luxury accommodation)")
    print("  • Experiences (yoga, hiking)")
    print("  • Database lookup (July availability)")
    
    response = await chat(
        query=complex_query,
        first_name="Ana",
        use_parallel=True
    )
    print(f"\nResponse:\n{response}")


async def benchmark_parallel_vs_sequential():
    """
    Comparison of execution times: parallel vs sequential
    """
    import time
    
    print("\n" + "="*60)
    print("PERFORMANCE BENCHMARK: Parallel vs Sequential")
    print("="*60)
    
    test_query = "Quiero un hotel en Cancún, tours de snorkel y un transfer desde el aeropuerto."
    
    # Sequential
    print("\n[SEQUENTIAL] Processing...")
    start = time.time()
    response_seq = await chat(query=test_query, first_name="Test", use_parallel=False)
    seq_time = time.time() - start
    print(f"Sequential time: {seq_time:.2f}s")
    
    # Parallel
    print("\n[PARALLEL] Processing...")
    start = time.time()
    response_par = await chat(query=test_query, first_name="Test", use_parallel=True)
    par_time = time.time() - start
    print(f"Parallel time: {par_time:.2f}s")
    
    # Calculate improvement
    improvement = ((seq_time - par_time) / seq_time * 100) if seq_time > 0 else 0
    print(f"\nSpeedup: {seq_time/par_time:.1f}x faster (≈{improvement:.0f}% improvement)")


async def main():
    """Run all examples"""
    
    print("\n" + "="*80)
    print("ProductoBot: Parallel Agents Framework Demo")
    print("="*80)
    print("""
This demo shows how ProductoBot uses parallel agents to handle complex travel queries.

Key Features:
✓ Automatic query analysis (simple vs multi-domain)
✓ Parallel execution for independent queries
✓ Specialized agents for each domain (experiences, lodging, transportation, data)
✓ Meta-agent coordinator to synthesize results
✓ Fallback to sequential ReAct agent if needed
✓ Latency reduction for complex queries
    """)
    
    try:
        await demonstrate_parallel_agents()
        await benchmark_parallel_vs_sequential()
    except Exception as e:
        logger.error(f"Error in demo: {str(e)}", exc_info=True)
    
    print("\n" + "="*80)
    print("Demo completed!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
