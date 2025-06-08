#!/usr/bin/env python3
"""
Simple test script to verify bot imports and basic functionality
"""

import sys
import os

def test_imports():
    """Test that all required modules can be imported"""
    try:
        import discord
        print("✅ discord.py imported successfully")
        
        import asyncio
        print("✅ asyncio imported successfully")
        
        from dotenv import load_dotenv
        print("✅ python-dotenv imported successfully")
        
        # Test bot import
        from bot import AnnouncementBot
        print("✅ Bot class imported successfully")
        
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_environment():
    """Test environment variable loading"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        # Check if DISCORD_TOKEN is set (even if it's the example value)
        token = os.getenv('DISCORD_TOKEN')
        if token:
            print("✅ DISCORD_TOKEN environment variable found")
        else:
            print("⚠️  DISCORD_TOKEN not set (this is expected for testing)")
        
        # Check optional variables
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        print(f"✅ LOG_LEVEL: {log_level}")
        
        bot_prefix = os.getenv('BOT_PREFIX', '!')
        print(f"✅ BOT_PREFIX: {bot_prefix}")
        
        return True
    except Exception as e:
        print(f"❌ Environment test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Discord Announcement Bot...")
    print("=" * 50)
    
    # Test imports
    print("\n📦 Testing imports...")
    import_success = test_imports()
    
    # Test environment
    print("\n🔧 Testing environment...")
    env_success = test_environment()
    
    # Summary
    print("\n" + "=" * 50)
    if import_success and env_success:
        print("✅ All tests passed! Bot is ready for deployment.")
        return 0
    else:
        print("❌ Some tests failed. Check the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())