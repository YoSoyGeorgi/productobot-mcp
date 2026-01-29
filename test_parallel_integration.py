#!/usr/bin/env python3
"""
Quick test to verify parallel agents integration
"""

import asyncio
import sys
from pathlib import Path

# Add agent directory to path
sys.path.insert(0, str(Path(__file__).parent / "agent"))

async def test_imports():
    """Test that all imports work correctly"""
    print("Testing imports...")
    try:
        from ruto_agent import chat, productobot_agent
        print("✓ ruto_agent imports OK")
        
        from parallel_agents import ParallelAgentRunner, HybridAgentOrchestrator
        print("✓ parallel_agents imports OK")
        
        from parallel_config import (
            ENABLE_PARALLEL_AGENTS,
            get_enabled_domains,
            detect_domains,
            should_use_parallel
        )
        print("✓ parallel_config imports OK")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


async def test_query_detection():
    """Test query detection logic"""
    print("\nTesting query detection...")
    try:
        from parallel_config import detect_domains, should_use_parallel
        
        test_cases = [
            ("Quiero un hotel", ["lodging"]),
            ("Dame tours de buceo", ["experiences"]),
            ("Hotel y tours", ["lodging", "experiences"]),
            ("Todo: alojamiento, actividades y transporte", 
             ["lodging", "experiences", "transportation"]),
        ]
        
        for query, expected_domains in test_cases:
            detected = detect_domains(query)
            use_parallel = should_use_parallel(detected)
            
            # Check if main expected domains are detected
            status = "✓" if any(d in detected for d in expected_domains) else "✗"
            print(f"{status} Query: '{query}'")
            print(f"   Detected: {detected}, Parallel: {use_parallel}")
        
        return True
    except Exception as e:
        print(f"✗ Query detection test failed: {e}")
        return False


async def test_config():
    """Test configuration"""
    print("\nTesting configuration...")
    try:
        from parallel_config import print_config
        print_config()
        return True
    except Exception as e:
        print(f"✗ Config test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("="*60)
    print("ProductoBot Parallel Agents - Integration Test")
    print("="*60)
    
    results = []
    
    results.append(("Imports", await test_imports()))
    results.append(("Query Detection", await test_query_detection()))
    results.append(("Configuration", await test_config()))
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("="*60)
    if all_passed:
        print("All tests passed! ✓")
        return 0
    else:
        print("Some tests failed. ✗")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
