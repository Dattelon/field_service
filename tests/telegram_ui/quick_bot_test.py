"""
Quick test - send /start to admin bot
"""
import asyncio
from telethon import TelegramClient
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE, ADMIN_BOT_USERNAME

async def test_admin_bot():
    session_name = str(SESSION_FILE.parent / SESSION_FILE.stem)
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            print("NOT AUTHORIZED")
            return False
        
        print(f"Sending /start to @{ADMIN_BOT_USERNAME}...")
        
        await client.send_message(ADMIN_BOT_USERNAME, '/start')
        print("Message sent!")
        
        print("Waiting for response...")
        await asyncio.sleep(3)
        
        async for message in client.iter_messages(ADMIN_BOT_USERNAME, limit=1):
            print(f"\nReceived: {message.text[:200] if message.text else '(no text)'}")
            if message.reply_markup:
                print(f"Has buttons: {len(message.reply_markup.rows)} rows")
            return True
        
        print("No response")
        return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()

if __name__ == "__main__":
    result = asyncio.run(test_admin_bot())
    sys.exit(0 if result else 1)
