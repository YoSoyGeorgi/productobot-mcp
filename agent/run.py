import uvicorn
import os
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).parent.parent))

if __name__ == "__main__":
    # Get port from environment variable or default to 8000
    port = int(os.environ.get("PORT", 8000))
    # Server configuration
    uvicorn.run("agent.app:api", host="0.0.0.0", port=port, reload=True) 