# RutoBot - Chatbot Assistant for Rutopia

RutoBot is a Slack chatbot assistant for Rutopia built using the OpenAI API and Slack's Bolt framework.

## Features

- Responds to direct messages and mentions in Slack channels
- Maintains conversation context within threads
- Provides a welcoming home tab experience
- Built with FastAPI for production deployment

## Project Structure

```
├── agent/
│   ├── app.py         # FastAPI application
│   ├── rutoagent.py   # Chat functionality with OpenAI integration
│   ├── run.py         # Development server entry point
├── Dockerfile         # For containerized deployment
├── requirements.txt   # Python dependencies
├── DEPLOYMENT.md      # Deployment instructions
├── .env               # Environment variables (not tracked by git)
```

## Local Development Setup

1. Clone the repository:
   ```
   git clone https://github.com/polimataai/rutopia.git
   cd rutopia
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_SIGNING_SECRET=your-signing-secret
   ```

5. Run the development server:
   ```
   cd agent
   python run.py
   ```

6. For local testing, use a tool like ngrok to expose your local server:
   ```
   ngrok http 8000
   ```

7. Configure your Slack app with the ngrok URL.

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions on deploying to Digital Ocean.

## Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key
- `SLACK_BOT_TOKEN`: Your Slack bot token (starts with xoxb-)
- `SLACK_SIGNING_SECRET`: Your Slack app signing secret

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is proprietary and owned by Rutopia.

## Contact

For questions or support, please contact the Rutopia team. 