"""
Minimal session test
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE


async def test():
    session_name = str(SESSION_FILE.parent / SESSION_FILE.stem)
    print(f"Using session: {session_name}")
    
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"SUCCESS!")
            print(f"Name: {me.first_name} {me.last_name or ''}")
            print(f"ID: {me.id}")
            print(f"Phone: {me.phone}")
            return True
        else:
            print("NOT AUTHORIZED")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()


if __name__ == "__main__":
    result = asyncio.run(test())
    sys.exit(0 if result else 1)
