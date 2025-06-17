import asyncio
import logging
import os
import sys
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging with more detailed format
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())

# Create handlers list
handlers = [logging.StreamHandler(sys.stdout)]

# Try to add file handler if possible
try:
    if os.path.exists('/app/logs') and os.access('/app/logs', os.W_OK):
        handlers.append(logging.FileHandler('/app/logs/bot.log', mode='a'))
    elif os.path.exists('./logs') and os.access('./logs', os.W_OK):
        handlers.append(logging.FileHandler('./logs/bot.log', mode='a'))
except (PermissionError, OSError):
    pass  # Continue with just stdout logging

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

class GracefulShutdown:
    """Handle graceful shutdown of the bot"""
    def __init__(self):
        self.shutdown = False
        self.tasks = []
        
    def add_task(self, task):
        """Add a task to be cancelled on shutdown"""
        self.tasks.append(task)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown = True
        
    async def cleanup(self):
        """Cancel all running tasks"""
        logger.info("Cleaning up running tasks...")
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("All tasks cleaned up")

class ConnectionManager:
    """Manage aiohttp connections and prevent memory leaks"""
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None
        
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper connection management"""
        if self.session is None or self.session.closed:
            # Create connector with connection limits and timeout
            self.connector = aiohttp.TCPConnector(
                limit=100,  # Total connection pool size
                limit_per_host=30,  # Per-host connection limit
                ttl_dns_cache=300,  # DNS cache TTL
                use_dns_cache=True,
                keepalive_timeout=30,  # Keep connections alive for 30s
                enable_cleanup_closed=True  # Clean up closed connections
            )
            
            # Create session with timeout and connector
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=timeout,
                headers={'User-Agent': 'Discord-Bot/1.0'}
            )
            logger.info("Created new aiohttp session with connection management")
            
        return self.session
        
    async def close(self):
        """Properly close aiohttp session and connector"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Closed aiohttp session")
            
        if self.connector:
            await self.connector.close()
            logger.info("Closed aiohttp connector")
            
        # Wait a bit for connections to close
        await asyncio.sleep(0.1)

class AnnouncementBot(commands.Bot):
    def __init__(self):
        # Configure intents properly - check if privileged intents are needed
        intents = discord.Intents.default()
        
        # Only enable message_content if PRIVILEGED_INTENTS is set to true
        if os.getenv('PRIVILEGED_INTENTS', 'false').lower() == 'true':
            intents.message_content = True
            logger.info("Privileged intents enabled - message content access available")
        else:
            intents.message_content = False
            logger.warning("Privileged intents disabled - message content access limited")
            
        # Essential intents for announcement bot functionality
        intents.guilds = True
        intents.guild_messages = True
        
        super().__init__(
            command_prefix=None,
            intents=intents,
            help_command=None
        )
        
        # Statistics tracking
        self.published_messages: Dict[int, datetime] = {}
        self.failed_publications: List[Dict] = []
        self.processed_messages: Dict[int, datetime] = {}
        self.start_time = datetime.utcnow()
        
        # Connection and shutdown management
        self.connection_manager = ConnectionManager()
        self.shutdown_handler = GracefulShutdown()
        self.is_shutting_down = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.shutdown_handler.signal_handler)
        signal.signal(signal.SIGINT, self.shutdown_handler.signal_handler)
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Bot is starting up...")
        try:
            # Start background tasks
            cleanup_task = asyncio.create_task(self.start_cleanup_task())
            self.shutdown_handler.add_task(cleanup_task)
            
            # Initialize connection manager
            await self.connection_manager.get_session()
            
            logger.info("Bot setup completed successfully")
        except Exception as e:
            logger.error(f"Error in setup_hook: {e}")
            raise
            
    async def start_cleanup_task(self):
        """Start the cleanup task with error handling"""
        try:
            self.cleanup_stats.start()
        except Exception as e:
            logger.error(f"Error starting cleanup task: {e}")
            
    async def close(self):
        """Override close method for proper cleanup"""
        logger.info("Bot is shutting down...")
        self.is_shutting_down = True
        
        try:
            # Stop background tasks
            if self.cleanup_stats.is_running():
                self.cleanup_stats.cancel()
                
            # Close connection manager
            await self.connection_manager.close()
            
            # Call parent close
            await super().close()
            
            # Cleanup shutdown handler tasks
            await self.shutdown_handler.cleanup()
            
            logger.info("Bot shutdown completed")
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")

    async def on_ready(self):
        """Called when the bot is ready"""
        try:
            logger.info(f'{self.user} has connected to Discord!')
            logger.info(f'Bot is in {len(self.guilds)} guilds')
            
            # Check intents configuration
            if self.intents.message_content:
                logger.info("✅ Message content intent is enabled")
            else:
                logger.warning("⚠️ Message content intent is disabled - some functionality may be limited")
            
            # Log announcement channels the bot can see
            announcement_channels = []
            for guild in self.guilds:
                try:
                    for channel in guild.channels:
                        if isinstance(channel, discord.TextChannel) and channel.type == discord.ChannelType.news:
                            announcement_channels.append(f"{guild.name}#{channel.name}")
                except Exception as e:
                    logger.warning(f"Error checking channels in guild {guild.name}: {e}")
            
            logger.info(f'Monitoring {len(announcement_channels)} announcement channels')
            if announcement_channels:
                logger.info(f'Channels: {", ".join(announcement_channels[:10])}{"..." if len(announcement_channels) > 10 else ""}')
                
        except Exception as e:
            logger.error(f"Error in on_ready: {e}")

    async def on_error(self, event, *args, **kwargs):
        """Handle errors in event handlers"""
        logger.error(f"Error in event {event}: {sys.exc_info()[1]}", exc_info=True)
        
    async def on_message(self, message):
        """Handle new messages with improved error handling"""
        try:
            # Check if we're shutting down
            if self.is_shutting_down:
                return
                
            # Check if message is in an announcement channel
            if isinstance(message.channel, discord.TextChannel) and message.channel.type == discord.ChannelType.news:
                # Handle webhook messages (they come from bot users but should be published)
                if message.webhook_id is not None:
                    logger.info(f'Detected webhook message from {message.author} in {message.guild.name}#{message.channel.name}')
                    await self.handle_announcement_message(message)
                # Handle regular user messages (ignore other bot messages)
                elif not message.author.bot:
                    await self.handle_announcement_message(message)
                else:
                    logger.debug(f'Ignoring bot message (not webhook) from {message.author} in {message.guild.name}#{message.channel.name}')
                    
        except Exception as e:
            logger.error(f"Error in on_message: {e}", exc_info=True)
    
    async def on_raw_message_create(self, payload):
        """Handle raw message creation events with better error handling"""
        try:
            if self.is_shutting_down:
                return
                
            # Get the channel
            channel = self.get_channel(payload.channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return
            
            # Only process announcement channels
            if channel.type != discord.ChannelType.news:
                return
            
            # Get the message with retry logic
            message = await self.fetch_message_with_retry(channel, payload.message_id)
            if not message:
                return
            
            # Handle webhook messages specifically
            if message.webhook_id is not None:
                logger.info(f'Raw event: Detected webhook message from {message.author} in {message.guild.name}#{message.channel.name}')
                await self.handle_announcement_message(message)
                
        except Exception as e:
            logger.error(f'Error in on_raw_message_create: {e}', exc_info=True)
            
    async def fetch_message_with_retry(self, channel, message_id, max_retries=3):
        """Fetch message with retry logic"""
        for attempt in range(max_retries):
            try:
                return await channel.fetch_message(message_id)
            except discord.NotFound:
                logger.warning(f'Message {message_id} not found in {channel.guild.name}#{channel.name}')
                return None
            except discord.Forbidden:
                logger.warning(f'No permission to fetch message {message_id} in {channel.guild.name}#{channel.name}')
                return None
            except discord.HTTPException as e:
                if attempt == max_retries - 1:
                    logger.error(f'Failed to fetch message {message_id} after {max_retries} attempts: {e}')
                    return None
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f'Unexpected error fetching message {message_id}: {e}')
                return None
        return None
    
    async def handle_announcement_message(self, message):
        """Handle messages in announcement channels with improved error handling"""
        try:
            # Check if we've already processed this message
            if message.id in self.processed_messages:
                logger.debug(f'Message {message.id} already processed, skipping')
                return
            
            # Mark message as processed
            self.processed_messages[message.id] = datetime.utcnow()
            
            channel = message.channel
            guild = message.guild
            
            # Log message details for debugging
            webhook_info = f" (webhook: {message.webhook_id})" if message.webhook_id else ""
            logger.info(f'New announcement message in {guild.name}#{channel.name} by {message.author}{webhook_info}')
            
            # Check if bot has permission to publish messages
            if not channel.permissions_for(guild.me).manage_webhooks:
                error_msg = 'Missing Manage Webhooks permission'
                logger.error(f'{error_msg} in {guild.name}#{channel.name}')
                self.failed_publications.append({
                    'message_id': message.id,
                    'channel': f'{guild.name}#{channel.name}',
                    'error': error_msg,
                    'timestamp': datetime.utcnow()
                })
                return
            
            # Publish the message with retry logic
            await self.publish_with_retry(message)
            
        except Exception as e:
            logger.error(f'Unexpected error handling announcement in {message.guild.name}#{message.channel.name}: {e}', exc_info=True)
            self.failed_publications.append({
                'message_id': message.id,
                'channel': f'{message.guild.name}#{message.channel.name}',
                'error': str(e),
                'timestamp': datetime.utcnow()
            })
    
    async def publish_with_retry(self, message, max_retries=3):
        """Publish message with enhanced retry logic and rate limit handling"""
        for attempt in range(max_retries):
            try:
                await message.publish()
                
                # Log successful publication
                self.published_messages[message.id] = datetime.utcnow()
                logger.info(f'✅ Successfully published message {message.id} in {message.guild.name}#{message.channel.name}')
                return
                
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = getattr(e, 'retry_after', 60)
                    logger.warning(f'⏱️ Rate limited. Retrying after {retry_after} seconds (attempt {attempt + 1}/{max_retries})')
                    await asyncio.sleep(retry_after)
                elif e.status == 403:  # Forbidden
                    error_msg = f'Forbidden: {e}'
                    logger.error(f'❌ {error_msg} in {message.guild.name}#{message.channel.name}')
                    self.failed_publications.append({
                        'message_id': message.id,
                        'channel': f'{message.guild.name}#{message.channel.name}',
                        'error': error_msg,
                        'timestamp': datetime.utcnow()
                    })
                    return
                else:
                    logger.error(f'❌ HTTP error publishing message (attempt {attempt + 1}/{max_retries}): {e}')
                    if attempt == max_retries - 1:
                        self.failed_publications.append({
                            'message_id': message.id,
                            'channel': f'{message.guild.name}#{message.channel.name}',
                            'error': str(e),
                            'timestamp': datetime.utcnow()
                        })
                    else:
                        await asyncio.sleep(min(2 ** attempt, 60))  # Exponential backoff with cap
            except Exception as e:
                logger.error(f'❌ Unexpected error publishing message (attempt {attempt + 1}/{max_retries}): {e}')
                if attempt == max_retries - 1:
                    self.failed_publications.append({
                        'message_id': message.id,
                        'channel': f'{message.guild.name}#{message.channel.name}',
                        'error': str(e),
                        'timestamp': datetime.utcnow()
                    })
                else:
                    await asyncio.sleep(min(2 ** attempt, 60))
    
    @tasks.loop(hours=1)
    async def cleanup_stats(self):
        """Clean up old statistics to prevent memory bloat"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=1)
            
            # Clean published messages older than 1 day
            old_published = [msg_id for msg_id, timestamp in self.published_messages.items()
                            if timestamp < cutoff_time]
            for msg_id in old_published:
                del self.published_messages[msg_id]
            
            # Clean processed messages older than 1 day
            old_processed = [msg_id for msg_id, timestamp in self.processed_messages.items()
                            if timestamp < cutoff_time]
            for msg_id in old_processed:
                del self.processed_messages[msg_id]
            
            # Clean failed publications older than 1 day
            self.failed_publications = [failure for failure in self.failed_publications
                                      if failure['timestamp'] > cutoff_time]
            
            if old_published or old_processed:
                logger.info(f'🧹 Cleaned up {len(old_published)} published and {len(old_processed)} processed message records')
                
        except Exception as e:
            logger.error(f"Error in cleanup_stats: {e}")
    
    @cleanup_stats.before_loop
    async def before_cleanup_stats(self):
        """Wait for bot to be ready before starting cleanup"""
        await self.wait_until_ready()
    

async def main():
    """Main function to run the bot with proper error handling"""
    # Get Discord token from environment
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('❌ DISCORD_TOKEN environment variable not found!')
        return 1
    
    # Validate token format
    if not token.startswith(('Bot ', 'Bearer ')) and '.' not in token:
        logger.error('❌ Invalid Discord token format!')
        return 1
    
    # Create bot instance
    bot = AnnouncementBot()
    
    try:
        logger.info("🚀 Starting Discord bot...")
        await bot.start(token)
        
    except discord.LoginFailure as e:
        logger.error(f'❌ Discord login failed: {e}')
        logger.error('This usually means:')
        logger.error('1. Invalid bot token')
        logger.error('2. Bot token has been regenerated')
        logger.error('3. Bot has been deleted from Discord Developer Portal')
        return 1
        
    except discord.PrivilegedIntentsRequired as e:
        logger.error(f'❌ Privileged intents required but not enabled: {e}')
        logger.error('Please enable the required intents in Discord Developer Portal:')
        logger.error('1. Go to https://discord.com/developers/applications')
        logger.error('2. Select your bot application')
        logger.error('3. Go to "Bot" section')
        logger.error('4. Enable "Message Content Intent" under "Privileged Gateway Intents"')
        logger.error('5. Save changes and restart the bot')
        return 1
        
    except discord.HTTPException as e:
        logger.error(f'❌ Discord HTTP error: {e}')
        if e.status == 401:
            logger.error('Unauthorized - check your bot token')
        elif e.status == 403:
            logger.error('Forbidden - check bot permissions and intents')
        return 1
        
    except Exception as e:
        logger.error(f'❌ Unexpected error starting bot: {e}', exc_info=True)
        return 1
        
    finally:
        # Ensure proper cleanup
        if not bot.is_closed():
            await bot.close()
        logger.info("🛑 Bot shutdown complete")
        
    return 0

if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info('🛑 Bot stopped by user (Ctrl+C)')
        sys.exit(0)
    except Exception as e:
        logger.error(f'💥 Fatal error: {e}', exc_info=True)
        sys.exit(1)