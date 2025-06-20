import os
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
from io import StringIO

# Load environment variables
load_dotenv()

class TwitchNotifier:
    def __init__(self):
        # API credentials
        self.discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.b7h30_webhook_url = os.getenv('B7H30_WEBHOOK_URL')
        self.twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
        self.twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
        
        # Configuration
        self.csv_url = os.getenv('STREAMERS_CSV_URL', '')  # GitHub raw URL for CSV
        self.check_interval = 60  # seconds between checks
        self.max_retries = 3  # maximum number of API call retries
        self.retry_delay = 5  # seconds between retries
        
        # State tracking
        self.access_token = None
        self.streamers_data: Dict[str, dict] = {}  # {twitch_username: {'youtube': url, 'is_live': bool}}

    def _make_request_with_retry(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make an HTTP request with retry logic"""
        for attempt in range(self.max_retries):
            try:
                response = requests.request(method, url, **kwargs)
                if response.status_code == 401 and self.get_twitch_access_token():
                    # Update authorization header with new token and retry
                    if 'headers' in kwargs:
                        kwargs['headers']['Authorization'] = f'Bearer {self.access_token}'
                    continue
                return response
            except requests.RequestException as e:
                print(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        return None

    def get_twitch_access_token(self) -> bool:
        """Get Twitch access token using client credentials"""
        url = 'https://id.twitch.tv/oauth2/token'
        params = {
            'client_id': self.twitch_client_id,
            'client_secret': self.twitch_client_secret,
            'grant_type': 'client_credentials'
        }
        
        response = self._make_request_with_retry('POST', url, params=params)
        if response and response.status_code == 200:
            self.access_token = response.json()['access_token']
            return True
        return False

    def update_streamers_from_csv(self) -> bool:
        """Fetch and update streamers data from GitHub CSV"""
        try:
            # Fetch CSV from GitHub
            response = self._make_request_with_retry('GET', self.csv_url)
            if not response:
                print("Failed to fetch streamers CSV")
                return False

            # Parse CSV content
            df = pd.read_csv(StringIO(response.text), header=None, names=['twitch_username', 'youtube_link'])
            
            # Update streamers data
            new_data = {row['twitch_username']: {
                'youtube': row['youtube_link'],
                'is_live': self.streamers_data.get(row['twitch_username'], {}).get('is_live', False)
            } for _, row in df.iterrows()}
            
            self.streamers_data = new_data
            print(f"Updated streamers list: {len(self.streamers_data)} streamers")
            return True
            
        except Exception as e:
            print(f"Error updating streamers data: {str(e)}")
            return False

    def check_stream_status(self, username: str) -> bool:
        """Check if a specific Twitch channel is live"""
        if not self.access_token and not self.get_twitch_access_token():
            print("Failed to get Twitch access token")
            return False

        url = f'https://api.twitch.tv/helix/streams?user_login={username}'
        headers = {
            'Client-ID': self.twitch_client_id,
            'Authorization': f'Bearer {self.access_token}'
        }

        response = self._make_request_with_retry('GET', url, headers=headers)
        if response and response.status_code == 200:
            data = response.json()['data']
            return len(data) > 0
        return False

    def get_webhook_url(self, username: str) -> str:
        """Get the appropriate webhook URL for the user"""
        return self.b7h30_webhook_url if username.lower() == 'b7h30' else self.discord_webhook_url

    def send_discord_notification(self, username: str) -> bool:
        """Send a notification to Discord when stream goes live"""
        streamer_data = self.streamers_data.get(username)
        if not streamer_data:
            return False

        webhook_url = self.get_webhook_url(username)
        is_b7h30 = username.lower() == 'b7h30'
        
        # Build message content
        content = []
        
        # Add stream notification with or without role mention
        if is_b7h30:
            content.append(f'🔴 **{username}** is now live on Twitch! <@&1119439250472046662>')
        else:
            content.append(f"🔴 **{username}** is now live on Twitch! - Courtesy of GoProSlowYo's <https://infosecstreams.com/>")
        
        # Add Twitch link
        content.append(f'Watch here: https://twitch.tv/{username}')
        
        # Add YouTube link only if it exists and is a valid URL
        youtube_link = streamer_data.get('youtube')
        if youtube_link and isinstance(youtube_link, str) and youtube_link.startswith('http'):
            content.append(f'YouTube Channel: <{youtube_link}>')
        
        message = {
            'content': '\n'.join(content)
        }
        
        response = self._make_request_with_retry('POST', webhook_url, json=message)
        return response and response.status_code == 204

    def run(self):
        """Main loop to check stream status and send notifications"""
        print("Starting Twitch stream monitor")
        
        while True:
            try:
                # Update streamers list from CSV
                self.update_streamers_from_csv()
                
                # Check each streamer's status
                for username, data in self.streamers_data.items():
                    current_status = self.check_stream_status(username)
                    
                    # If stream just went live
                    if current_status and not data['is_live']:
                        print(f"{username} just went live!")
                        if self.send_discord_notification(username):
                            print("Discord notification sent successfully")
                        else:
                            print("Failed to send Discord notification")
                        self.streamers_data[username]['is_live'] = True
                    
                    # If stream just went offline
                    elif not current_status and data['is_live']:
                        print(f"{username} went offline")
                        self.streamers_data[username]['is_live'] = False
                
                # Wait before next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"Error occurred: {str(e)}")
                time.sleep(self.check_interval)

if __name__ == "__main__":
    notifier = TwitchNotifier()
    notifier.run()
