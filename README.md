# Discord Announcement Bot 📢

A production-ready Discord bot that automatically publishes messages from announcement channels (NewsChannel type) to all following servers. Built with Python, discord.py, and Docker for easy deployment and scalability.

## Features ✨

- **Automatic Publishing**: Detects messages in announcement channels and publishes them automatically
- **Rate Limit Handling**: Graceful handling of Discord API rate limits with exponential backoff
- **Error Recovery**: Retry logic for failed publications with comprehensive error logging
- **Permission Management**: Checks and handles missing permissions gracefully
- **Statistics Tracking**: Built-in slash command to view publication statistics
- **Docker Support**: Fully containerized with Docker and docker-compose
- **Production Ready**: Comprehensive logging, health checks, and error handling

## Requirements 📋

- Python 3.11+
- Discord Bot Token
- Docker and Docker Compose (for containerized deployment)

## Quick Start 🚀

### 1. Clone and Setup

```bash
git clone https://github.com/PureCypher/info-publish
cd info-publish
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your Discord bot token
nano .env
```

Add your Discord bot token to the `.env` file:
```env
DISCORD_TOKEN=your_discord_bot_token_here
```

### 3. Deploy with Docker

```bash
# Build and start the bot
docker-compose up -d

# View logs
docker-compose logs -f discord-bot

# Stop the bot
docker-compose down
```

### 4. Alternative: Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

## Discord Bot Setup 🤖

### 1. Create Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section
4. Click "Add Bot"
5. Copy the bot token and add it to your `.env` file

### 2. Configure Bot Permissions

The bot needs these permissions:
- **Read Messages** - To detect new messages in announcement channels
- **Manage Webhooks** - To publish messages to announcement channels
- **Use Slash Commands** - For the `/status` command

### 3. Enable Required Intents

In the Discord Developer Portal, under Bot settings, enable:
- **Message Content Intent**
- **Server Members Intent** (optional, for better guild management)

### 4. Invite Bot to Server

Generate an invite link with the required permissions:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_CLIENT_ID&permissions=536870912&scope=bot%20applications.commands
```

Replace `YOUR_BOT_CLIENT_ID` with your bot's client ID from the Developer Portal.

## Usage 📖

### Automatic Publishing

The bot automatically monitors all announcement channels (NewsChannel type) it has access to. When a new message is posted in these channels, the bot will:

1. Check if it has the required permissions
2. Attempt to publish the message using `message.publish()`
3. Handle rate limits and retry on failure
4. Log the result (success or failure)

### Slash Commands

#### `/status`
Shows bot statistics including:
- Messages published in the last 24 hours
- Failed publications count
- Server and channel information
- Bot uptime
- Recent failure details

## Configuration ⚙️

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DISCORD_TOKEN` | Your Discord bot token | - | ✅ |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO | ❌ |
| `BOT_PREFIX` | Command prefix for text commands | ! | ❌ |

### Docker Configuration

The `docker-compose.yml` includes:
- **Auto-restart**: Bot restarts automatically on failure
- **Log rotation**: Prevents log files from growing too large
- **Volume mounting**: Logs are persisted outside the container
- **Health checks**: Monitors bot health and restarts if unhealthy

## Monitoring and Logs 📊

### Log Files

- `bot.log` - Main application log with timestamps
- Docker logs via `docker-compose logs discord-bot`

### Log Levels

- **INFO**: Normal operations, successful publications
- **WARNING**: Rate limits, retries
- **ERROR**: Failed publications, permission issues
- **DEBUG**: Detailed debugging information

### Health Monitoring

The bot includes health checks that verify:
- Python process is running
- Required dependencies are available
- Bot can respond to basic operations

## Troubleshooting 🔧

### Common Issues

#### Bot Not Publishing Messages
1. **Check Permissions**: Ensure bot has "Manage Webhooks" permission
2. **Verify Channel Type**: Only NewsChannel types are monitored
3. **Check Logs**: Look for permission errors in `bot.log`

#### Rate Limiting
- The bot handles rate limits automatically with exponential backoff
- Check logs for rate limit warnings
- Consider reducing message frequency if persistent

#### Docker Issues
```bash
# Rebuild container
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check container status
docker-compose ps

# View detailed logs
docker-compose logs --tail=100 discord-bot
```

### Debug Mode

Enable debug logging by setting `LOG_LEVEL=DEBUG` in your `.env` file:
```env
LOG_LEVEL=DEBUG
```

## Development 🛠️

### Project Structure

```
discord-announcer-bot/
├── bot.py              # Main bot application
├── requirements.txt    # Python dependencies
├── Dockerfile         # Container configuration
├── docker-compose.yml # Orchestration configuration
├── .env.example       # Environment template
└── README.md          # This file
```

### Key Components

- **AnnouncementBot**: Main bot class extending discord.py commands.Bot
- **Message Handler**: Detects and processes announcement channel messages
- **Retry Logic**: Handles failures with exponential backoff
- **Statistics**: Tracks publications and failures
- **Health Checks**: Monitors bot health for container orchestration

### Adding Features

The bot is designed to be extensible. Common additions:

1. **Database Integration**: Store statistics in a database
2. **Web Dashboard**: Create a web interface for monitoring
3. **Custom Filters**: Add message filtering before publishing
4. **Webhook Integration**: Send notifications to external services

## Security 🔒

- **Environment Variables**: Sensitive data stored in `.env` file
- **Non-root User**: Docker container runs as non-privileged user
- **Permission Checks**: Bot validates permissions before operations
- **Input Validation**: All user inputs are validated and sanitized

## Performance 📈

- **Async Operations**: All Discord API calls are asynchronous
- **Concurrent Processing**: Multiple channels handled simultaneously
- **Memory Management**: Automatic cleanup of old statistics
- **Resource Limits**: Docker container includes resource constraints

## Contributing 🤝

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details.

## Support 💬

For issues and questions:
1. Check the troubleshooting section
2. Review the logs for error messages
3. Open an issue on GitHub with:
   - Bot logs
   - Steps to reproduce
   - Expected vs actual behavior

---

**Note**: This bot requires announcement channels (NewsChannel type) to function. Regular text channels will not trigger the publishing functionality.