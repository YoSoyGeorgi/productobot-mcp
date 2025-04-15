import uvicorn

if __name__ == "__main__":
    # Development server
    uvicorn.run("app:api", host="0.0.0.0", port=8000, reload=True) 