"""
Test StringSession connection
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import ADMIN_BOT_USERNAME

async def test():
    print("="*60)
    print("  TESTING STRING SESSION CONNECTION")
    print("="*60)
    print()
    
    async with BotTestClient() as client:
        print("\nConnection successful!")
        print("\nSending /start to admin bot...")
        
        message = await client.send_command(ADMIN_BOT_USERNAME, "/start")
        
        print(f"\nResponse text preview:")
        print(message.text[:300] if message.text else "(no text)")
        
        if message.buttons:
            print(f"\nButtons found: {len(message.buttons)} rows")
            for i, row in enumerate(message.buttons):
                print(f"  Row {i+1}: {[btn.text for btn in row]}")
        
        print("\n" + "="*60)
        print("  SUCCESS!")
        print("="*60)
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test())
        exit(0 if result else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
