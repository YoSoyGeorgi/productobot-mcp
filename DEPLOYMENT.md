# RutoBot Deployment Guide

This guide provides instructions for deploying RutoBot to a Digital Ocean Droplet.

## Prerequisites

- A Digital Ocean account
- GitHub repository with the RutoBot code
- Slack app configured with appropriate tokens and permissions

## Setup Digital Ocean Droplet

1. Create a new Droplet on Digital Ocean:
   - Choose Ubuntu 20.04 (LTS) x64
   - Select Basic plan (minimum 1GB RAM / 1 CPU)
   - Choose a datacenter region closest to your users
   - Add SSH keys for secure access
   - Click "Create Droplet"

2. Once the Droplet is created, connect to it via SSH:
   ```
   ssh root@your_droplet_ip
   ```

## Deploy the Application

### Option 1: Docker Deployment (Recommended)

1. Install Docker on the Droplet:
   ```
   apt update
   apt install -y apt-transport-https ca-certificates curl software-properties-common
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
   add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
   apt update
   apt install -y docker-ce
   ```

2. Clone the repository:
   ```
   git clone https://github.com/polimataai/rutopia.git
   cd rutopia
   ```

3. Create a `.env` file with your environment variables:
   ```
   nano .env
   ```

   Add the following (replace with your actual values):
   ```
   OPENAI_API_KEY=your_openai_api_key
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_SIGNING_SECRET=your-signing-secret
   ```

4. Build and run the Docker container:
   ```
   docker build -t rutobot .
   docker run -d -p 8000:8000 --env-file .env --name rutobot rutobot
   ```

### Option 2: Direct Deployment

1. Install required system packages:
   ```
   apt update
   apt install -y python3-pip python3-dev nginx
   ```

2. Clone the repository:
   ```
   git clone https://github.com/polimataai/rutopia.git
   cd rutopia
   ```

3. Install Python dependencies:
   ```
   pip3 install -r requirements.txt
   ```

4. Create a `.env` file with your environment variables.

5. Set up a systemd service for the application:
   ```
   nano /etc/systemd/system/rutobot.service
   ```

   Add the following content:
   ```
   [Unit]
   Description=RutoBot Gunicorn Daemon
   After=network.target

   [Service]
   User=root
   Group=www-data
   WorkingDirectory=/root/rutopia
   Environment="PATH=/root/rutopia/venv/bin"
   ExecStart=/usr/local/bin/gunicorn agent.app:api --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

   [Install]
   WantedBy=multi-user.target
   ```

6. Start and enable the service:
   ```
   systemctl start rutobot
   systemctl enable rutobot
   ```

## Configure Nginx as a Reverse Proxy

1. Create an Nginx configuration file:
   ```
   nano /etc/nginx/sites-available/rutobot
   ```

   Add the following content:
   ```
   server {
       listen 80;
       server_name your_droplet_ip_or_domain;

       location / {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

2. Enable the site and restart Nginx:
   ```
   ln -s /etc/nginx/sites-available/rutobot /etc/nginx/sites-enabled
   systemctl restart nginx
   ```

## Configure Slack App

1. Visit the [Slack API website](https://api.slack.com/apps) and navigate to your app
2. Under "Event Subscriptions":
   - Set the Request URL to `https://your_droplet_ip_or_domain/slack/events`
   - Subscribe to the bot events: `app_mention`, `message.im`, `app_home_opened`
3. Save changes

## Verify Deployment

1. Test the health endpoint: `http://your_droplet_ip_or_domain/health`
2. Test the bot in Slack by mentioning it or sending a direct message

## Troubleshooting

- Check logs with `journalctl -u rutobot.service` or `docker logs rutobot`
- Ensure all environment variables are correctly set
- Verify Slack Event Subscriptions URL verification is working 