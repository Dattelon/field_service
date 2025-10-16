import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='field_user',
        password='owo?8x-YA@vRN*',
        database='field_service'
    )
    
    try:
        # Переименование колонок
        await conn.execute('ALTER TABLE distribution_metrics RENAME COLUMN category TO category_name;')
        print("✅ Переименована колонка category → category_name")
        
        await conn.execute('ALTER TABLE distribution_metrics RENAME COLUMN order_type TO type_name;')
        print("✅ Переименована колонка order_type → type_name")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
