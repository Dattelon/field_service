"""
Improved authorization script with detailed output
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE


async def authorize():
    print("="*60)
    print("  TELEGRAM AUTHORIZATION")
    print("="*60)
    print()
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH[:8]}...")
    print(f"Session will be saved to: {SESSION_FILE}")
    print()
    print("-"*60)
    print()
    
    phone = input("Enter phone number (e.g. +79991234567): ").strip()
    
    if not phone.startswith("+"):
        print("ERROR: Phone must start with +")
        return False
    
    print(f"\nConnecting to Telegram with phone {phone}...")
    
    session_name = str(SESSION_FILE.parent / SESSION_FILE.stem)
    print(f"Session path: {session_name}")
    
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    try:
        await client.connect()
        print("Connected to Telegram!")
        
        if not await client.is_user_authorized():
            print("\nSending code request...")
            await client.send_code_request(phone)
            
            code = input("\nEnter the code from Telegram: ").strip()
            
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input("\nEnter 2FA password: ").strip()
                await client.sign_in(password=password)
        
        me = await client.get_me()
        
        print()
        print("="*60)
        print("  SUCCESS!")
        print("="*60)
        print(f"Name: {me.first_name} {me.last_name or ''}")
        print(f"Username: @{me.username or 'N/A'}")
        print(f"Phone: {me.phone}")
        print(f"ID: {me.id}")
        print()
        print(f"Session saved to: {SESSION_FILE}")
        print("="*60)
        
        return True
        
    except Exception as e:
        print()
        print("="*60)
        print("  ERROR!")
        print("="*60)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.disconnect()


if __name__ == "__main__":
    result = asyncio.run(authorize())
    
    if result:
        print("\nYou can now run tests!")
        sys.exit(0)
    else:
        print("\nAuthorization failed. Please try again.")
        sys.exit(1)
