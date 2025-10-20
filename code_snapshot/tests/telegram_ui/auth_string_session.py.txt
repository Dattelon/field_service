"""
Export session to string
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.telegram_ui.config import API_ID, API_HASH


async def authorize_and_export():
    print("="*60)
    print("  AUTHORIZATION WITH STRING SESSION")
    print("="*60)
    print()
    
    phone = input("Enter phone number: ").strip()
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = input("Enter code: ").strip()
            
            try:
                await client.sign_in(phone, code)
            except:
                password = input("Enter 2FA password: ").strip()
                await client.sign_in(password=password)
        
        me = await client.get_me()
        
        print("\n" + "="*60)
        print("  SUCCESS!")
        print("="*60)
        print(f"Name: {me.first_name} {me.last_name or ''}")
        print(f"ID: {me.id}")
        print()
        
        session_string = client.session.save()
        print("Session string:")
        print(session_string)
        print()
        print("Save this string to use in tests!")
        print("="*60)
        
        # Save to file
        config_path = Path(__file__).parent / "session_string.txt"
        with open(config_path, 'w') as f:
            f.write(session_string)
        print(f"\nSaved to: {config_path}")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()


if __name__ == "__main__":
    result = asyncio.run(authorize_and_export())
    sys.exit(0 if result else 1)
