import uvicorn

if __name__ == "__main__":
    # Development server
    uvicorn.run("agent.app:api", host="0.0.0.0", port=8000, reload=True) 