"""
Create and verify StringSession
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

API_ID = 25078350
API_HASH = "f544a1a967172e8cc8a05a0115b98b69"

async def create_session():
    print("="*60)
    print("  CREATE STRING SESSION")
    print("="*60)
    print()
    
    phone = input("Phone (+79031751130): ").strip() or "+79031751130"
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    try:
        await client.connect()
        print("Connected to Telegram")
        
        if not await client.is_user_authorized():
            print("\nSending code...")
            await client.send_code_request(phone)
            
            code = input("Code from Telegram: ").strip()
            
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                pwd = input("2FA password: ").strip()
                await client.sign_in(password=pwd)
        
        # Verify
        me = await client.get_me()
        print(f"\nSUCCESS! Logged in as: {me.first_name} (ID: {me.id})")
        
        # Get string
        session_str = client.session.save()
        
        print("\n" + "="*60)
        print("  YOUR STRING SESSION:")
        print("="*60)
        print(session_str)
        print("="*60)
        
        # Save to file
        with open("session_string_verified.txt", "w") as f:
            f.write(session_str)
        print("\nSaved to: session_string_verified.txt")
        
        # Test it immediately
        print("\nTesting session immediately...")
        await client.disconnect()
        
        # Reconnect with same session
        client2 = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client2.connect()
        
        if await client2.is_user_authorized():
            me2 = await client2.get_me()
            print(f"VERIFIED! Session works: {me2.first_name}")
            await client2.disconnect()
            return session_str
        else:
            print("WARNING: Session not authorized after reconnect!")
            await client2.disconnect()
            return None
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    session = asyncio.run(create_session())
    if session:
        print("\n" + "="*60)
        print("SUCCESS! Copy this session string to config.py")
        print("="*60)
        exit(0)
    else:
        print("\nFAILED to create session")
        exit(1)
