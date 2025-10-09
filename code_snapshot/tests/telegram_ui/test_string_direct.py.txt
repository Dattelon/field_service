"""
Direct StringSession test
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 25078350
API_HASH = "f544a1a967172e8cc8a05a0115b98b69"
SESSION_STRING = "1ApWapzMBu2k9f1PKZu0sdT3q06Oa35jBdE5w6SjD6MFZAReNr0irKbYqw0nF-vqb6k67tLiap7I6W-evugFk5YKUShS9SftGOcDjxKi08jyVXNN1HI5fhsS7XTZJS7FcSOruSofx65vi-hVMGtJE-PJPLt5fzvsTzPW2y2Q2oxkwgyF8-Sk379NUKIwOuCvGZmJLi3YeB6MsoQ6hQNRUwHeltB-ajKxjeI_CeZcbFFSaMA3UPlkVN0UkpsRMe3BS86ZfTN3aVk1BgJ3KTZlIMs7rAZQbs-BaplTwFiNJSVlZh950kX6WG93yciOnUswYXsBEESy0QKGT2kVW274spEKKzOlYdls="

async def test():
    print("Testing StringSession...")
    print(f"Session string length: {len(SESSION_STRING)}")
    print(f"First 50 chars: {SESSION_STRING[:50]}...")
    
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    
    try:
        await client.connect()
        print("Connected!")
        
        is_auth = await client.is_user_authorized()
        print(f"Authorized: {is_auth}")
        
        if is_auth:
            me = await client.get_me()
            print(f"SUCCESS! User: {me.first_name} (ID: {me.id})")
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
    exit(0 if result else 1)
