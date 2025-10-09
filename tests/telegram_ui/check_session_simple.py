"""
Simple session check without emojis
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE


async def test_session():
    print("="*60)
    print("  SESSION DIAGNOSTICS")
    print("="*60)
    print()
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH[:8]}...")
    print(f"SESSION_FILE: {SESSION_FILE}")
    print(f"File exists: {SESSION_FILE.exists()}")
    print()
    
    # Test connection without .session extension
    session_path = str(SESSION_FILE).replace('.session', '')
    print(f"Connection path: {session_path}")
    
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        is_auth = await client.is_user_authorized()
        print(f"Authorization status: {'AUTHORIZED' if is_auth else 'NOT AUTHORIZED'}")
        
        if is_auth:
            me = await client.get_me()
            print(f"User: {me.first_name} {me.last_name or ''}")
            print(f"User ID: {me.id}")
            print(f"Username: @{me.username or 'N/A'}")
            print(f"Phone: {me.phone or 'N/A'}")
            return True
        else:
            print("ERROR: Session exists but not authorized")
            print("Please run: python tests\\telegram_ui\\setup_client.py")
            return False
            
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return False
    finally:
        await client.disconnect()


if __name__ == "__main__":
    result = asyncio.run(test_session())
    sys.exit(0 if result else 1)
