"""
Advanced session check with multiple connection attempts
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE


async def test_session_advanced():
    print("="*60)
    print("  ADVANCED SESSION DIAGNOSTICS")
    print("="*60)
    print()
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH[:8]}...")
    print(f"SESSION_FILE: {SESSION_FILE}")
    print(f"File exists: {SESSION_FILE.exists()}")
    print(f"File size: {SESSION_FILE.stat().st_size if SESSION_FILE.exists() else 0} bytes")
    print()
    
    # Попробуем несколько вариантов пути
    paths_to_try = [
        str(SESSION_FILE),  # С .session
        str(SESSION_FILE).replace('.session', ''),  # Без .session
        SESSION_FILE.stem,  # Только имя файла без расширения
    ]
    
    for i, session_path in enumerate(paths_to_try, 1):
        print(f"Attempt {i}: {session_path}")
        
        client = TelegramClient(session_path, API_ID, API_HASH)
        try:
            await client.connect()
            is_auth = await client.is_user_authorized()
            
            if is_auth:
                me = await client.get_me()
                print(f"SUCCESS! Authorization status: AUTHORIZED")
                print(f"User: {me.first_name} {me.last_name or ''}")
                print(f"User ID: {me.id}")
                print(f"Username: @{me.username or 'N/A'}")
                print(f"Phone: {me.phone or 'N/A'}")
                print()
                await client.disconnect()
                return True
            else:
                print(f"NOT AUTHORIZED")
                
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
        finally:
            if client.is_connected():
                await client.disconnect()
        
        print()
    
    print("="*60)
    print("ALL ATTEMPTS FAILED")
    print("Please ensure you ran: python tests\\telegram_ui\\setup_client.py")
    print("="*60)
    return False


if __name__ == "__main__":
    result = asyncio.run(test_session_advanced())
    sys.exit(0 if result else 1)
