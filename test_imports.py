#!/usr/bin/env python3
"""Test that all required imports work correctly."""

import sys
import os
from dotenv import load_dotenv

# Load real environment variables
load_dotenv()

# Set placeholders only if not already set
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-secret")

print("Testing imports...")

try:
    print("✓ Importing FastAPI...")
    from fastapi import FastAPI
    
    print("✓ Importing uvicorn...")
    import uvicorn
    
    print("✓ Importing slack_bolt...")
    from slack_bolt import App
    
    print("✓ Importing openai...")
    import openai
    
    print("✓ Importing httpx...")
    import httpx
    
    print("✓ Importing supabase...")
    from supabase import create_client
    
    print("✓ Importing dotenv...")
    from dotenv import load_dotenv
    
    print("\n✓ All imports successful!")
    print("\nTesting app initialization...")
    
    # Add agent directory to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
    
    print("✓ Importing agent.app...")
    from agent.app import api
    
    print("✓ App initialized successfully!")
    print("\n✅ All tests passed! The app should work on Railway.")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
