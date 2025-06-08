import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class AnnouncementBot(commands.Bot):
    def __init__(self):
        # Configure intents - only use non-privileged intents
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        
        super().__init__(
            command_prefix=os.getenv('BOT_PREFIX', '!'),
            intents=intents,
            help_command=None
        )
        
        # Statistics tracking
        self.published_messages: Dict[int, datetime] = {}
        self.failed_publications: List[Dict] = []
        self.start_time = datetime.utcnow()
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Bot is starting up...")
        # Start background tasks
        self.cleanup_stats.start()
        
    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Log announcement channels the bot can see
        announcement_channels = []
        for guild in self.guilds:
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel) and channel.type == discord.ChannelType.news:
                    announcement_channels.append(f"{guild.name}#{channel.name}")
        
        logger.info(f'Monitoring {len(announcement_channels)} announcement channels')
        if announcement_channels:
            logger.info(f'Channels: {", ".join(announcement_channels)}')
    
    async def on_message(self, message):
        """Handle new messages"""
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Check if message is in an announcement channel
        if isinstance(message.channel, discord.TextChannel) and message.channel.type == discord.ChannelType.news:
            await self.handle_announcement_message(message)
        
        # Process commands
        await self.process_commands(message)
    
    async def handle_announcement_message(self, message):
        """Handle messages in announcement channels"""
        channel = message.channel
        guild = message.guild
        
        logger.info(f'New announcement message in {guild.name}#{channel.name} by {message.author}')
        
        try:
            # Check if bot has permission to publish messages
            if not channel.permissions_for(guild.me).manage_webhooks:
                logger.error(f'Missing Manage Webhooks permission in {guild.name}#{channel.name}')
                self.failed_publications.append({
                    'message_id': message.id,
                    'channel': f'{guild.name}#{channel.name}',
                    'error': 'Missing Manage Webhooks permission',
                    'timestamp': datetime.utcnow()
                })
                return
            
            # Publish the message with retry logic
            await self.publish_with_retry(message)
            
        except Exception as e:
            logger.error(f'Unexpected error handling announcement in {guild.name}#{channel.name}: {e}')
            self.failed_publications.append({
                'message_id': message.id,
                'channel': f'{guild.name}#{channel.name}',
                'error': str(e),
                'timestamp': datetime.utcnow()
            })
    
    async def publish_with_retry(self, message, max_retries=3):
        """Publish message with retry logic and rate limit handling"""
        for attempt in range(max_retries):
            try:
                await message.publish()
                
                # Log successful publication
                self.published_messages[message.id] = datetime.utcnow()
                logger.info(f'Successfully published message {message.id} in {message.guild.name}#{message.channel.name}')
                return
                
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = e.retry_after if hasattr(e, 'retry_after') else 60
                    logger.warning(f'Rate limited. Retrying after {retry_after} seconds (attempt {attempt + 1}/{max_retries})')
                    await asyncio.sleep(retry_after)
                elif e.status == 403:  # Forbidden
                    logger.error(f'Forbidden to publish message in {message.guild.name}#{message.channel.name}: {e}')
                    self.failed_publications.append({
                        'message_id': message.id,
                        'channel': f'{message.guild.name}#{message.channel.name}',
                        'error': f'Forbidden: {e}',
                        'timestamp': datetime.utcnow()
                    })
                    return
                else:
                    logger.error(f'HTTP error publishing message (attempt {attempt + 1}/{max_retries}): {e}')
                    if attempt == max_retries - 1:
                        self.failed_publications.append({
                            'message_id': message.id,
                            'channel': f'{message.guild.name}#{message.channel.name}',
                            'error': str(e),
                            'timestamp': datetime.utcnow()
                        })
                    else:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.error(f'Unexpected error publishing message (attempt {attempt + 1}/{max_retries}): {e}')
                if attempt == max_retries - 1:
                    self.failed_publications.append({
                        'message_id': message.id,
                        'channel': f'{message.guild.name}#{message.channel.name}',
                        'error': str(e),
                        'timestamp': datetime.utcnow()
                    })
                else:
                    await asyncio.sleep(2 ** attempt)
    
    @tasks.loop(hours=1)
    async def cleanup_stats(self):
        """Clean up old statistics to prevent memory bloat"""
        cutoff_time = datetime.utcnow() - timedelta(days=1)
        
        # Clean published messages older than 1 days
        old_messages = [msg_id for msg_id, timestamp in self.published_messages.items() 
                       if timestamp < cutoff_time]
        for msg_id in old_messages:
            del self.published_messages[msg_id]
        
        # Clean failed publications older than 1 days
        self.failed_publications = [failure for failure in self.failed_publications 
                                  if failure['timestamp'] > cutoff_time]
        
        if old_messages or len(self.failed_publications) > 0:
            logger.info(f'Cleaned up {len(old_messages)} old published message records')
    
    @commands.command(name="status")
    async def status_command(self, ctx):
        """Command to show bot status and statistics"""
        try:
            # Calculate stats for last 24 hours
            last_24h = datetime.utcnow() - timedelta(hours=24)
            
            published_24h = sum(1 for timestamp in self.published_messages.values() 
                              if timestamp > last_24h)
            
            failed_24h = sum(1 for failure in self.failed_publications 
                           if failure['timestamp'] > last_24h)
            
            # Count announcement channels
            announcement_channels = 0
            for guild in self.guilds:
                for channel in guild.channels:
                    if isinstance(channel, discord.TextChannel) and channel.type == discord.ChannelType.news:
                        announcement_channels += 1
            
            uptime = datetime.utcnow() - self.start_time
            uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
            
            embed = discord.Embed(
                title="📊 Bot Status",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📈 Last 24 Hours",
                value=f"✅ Published: {published_24h}\n❌ Failed: {failed_24h}",
                inline=True
            )
            
            embed.add_field(
                name="🏢 Server Info",
                value=f"Guilds: {len(self.guilds)}\nAnnouncement Channels: {announcement_channels}",
                inline=True
            )
            
            embed.add_field(
                name="⏱️ Uptime",
                value=uptime_str,
                inline=True
            )
            
            # Recent failures
            if self.failed_publications:
                recent_failures = sorted(self.failed_publications, 
                                       key=lambda x: x['timestamp'], reverse=True)[:3]
                failure_text = "\n".join([
                    f"• {failure['channel']}: {failure['error'][:50]}..."
                    for failure in recent_failures
                ])
                embed.add_field(
                    name="🚨 Recent Failures",
                    value=failure_text or "None",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in status command: {e}')
            await ctx.send("❌ Error retrieving status information.")

async def main():
    """Main function to run the bot"""
    # Get Discord token from environment
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('DISCORD_TOKEN environment variable not found!')
        sys.exit(1)
    
    # Create and run bot
    bot = AnnouncementBot()
    
    try:
        await bot.start(token)
    except discord.LoginFailure:
        logger.error('Invalid Discord token!')
        sys.exit(1)
    except Exception as e:
        logger.error(f'Error starting bot: {e}')
        sys.exit(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Fatal error: {e}')
        sys.exit(1)