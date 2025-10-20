# P2.3: REPOSITORY PATTERN - DESIGN & IMPLEMENTATION PLAN

## ЦЕЛЬ
Рефакторинг `services_db.py` (2000+ строк, 5 классов) в Repository Pattern для:
- Разделения ответственности (Single Responsibility Principle)
- Упрощения тестирования
- Повторного использования запросов
- Улучшения читаемости

---

## ТЕКУЩАЯ ПРОБЛЕМА

`services_db.py` содержит:
- `DBStaffService` (~400 строк)
- `DBOrdersService` (~800 строк)
- `DBDistributionService` (~300 строк)
- `DBFinanceService` (~200 строк)
- `DBMastersService` (~300+ строк)

**Проблемы:**
- Смешение бизнес-логики и запросов к БД
- Дублирование запросов (например, `get_city` используется во многих местах)
- Сложность unit-тестирования (нужно мокать всю БД)
- Нет переиспользования общих паттернов

---

## ЦЕЛЕВАЯ АРХИТЕКТУРА

```
field_service/bots/admin_bot/
├── repositories/               # ← НОВАЯ СТРУКТУРА
│   ├── __init__.py
│   ├── base.py                # BaseRepository
│   ├── orders_repository.py
│   ├── masters_repository.py
│   ├── staff_repository.py
│   ├── commissions_repository.py
│   └── cities_repository.py
│
├── services/                   # ← СУЩЕСТВУЮЩИЕ СЕРВИСЫ
│   ├── __init__.py
│   ├── orders_service.py      # Бизнес-логика для заказов
│   ├── finance_service.py     # Бизнес-логика для финансов
│   └── distribution_service.py
│
└── services_db.py             # ← LEGACY (удалить после миграции)
```

---

## ПРИНЦИПЫ REPOSITORY PATTERN

### 1. Repository = "Коллекция объектов в памяти"
Repositories предоставляют интерфейс для работы с данными, скрывая детали SQL/ORM.

**Пример:**
```python
# BAD (текущий подход - сервис делает всё)
class DBOrdersService:
    async def get_card(self, order_id: int) -> OrderDetail:
        async with self._session_factory() as session:
            stmt = select(m.orders, m.cities.name, ...)  # ← SQL в сервисе
            row = await session.execute(stmt)
            # ...
            return OrderDetail(...)

# GOOD (Repository Pattern)
class OrdersRepository:
    async def get_by_id(self, order_id: int) -> Optional[m.orders]:
        """Загрузить заказ по ID (только данные БД)."""
        async with self._session() as session:
            return await session.get(m.orders, order_id)

class OrdersService:
    def __init__(self, orders_repo: OrdersRepository, cities_repo: CitiesRepository):
        self._orders = orders_repo
        self._cities = cities_repo
    
    async def get_card(self, order_id: int) -> OrderDetail:
        """Получить карточку заказа (бизнес-логика)."""
        order = await self._orders.get_by_id(order_id)
        if not order:
            return None
        city = await self._cities.get_by_id(order.city_id)
        # ... форматирование, валидация
        return OrderDetail(...)
```

### 2. Repositories - только CRUD + простые запросы
- `get_by_id(id)` - получить по ID
- `find_by_status(status)` - найти по статусу
- `list_all(page, filters)` - список с пагинацией
- `add(entity)` - создать
- `update(entity)` - обновить
- `delete(id)` - удалить

### 3. Services - бизнес-логика
- Валидация
- Трансформация данных
- Комплексные операции (несколько репозиториев)
- Вызов внешних сервисов

---

## MIGRATION PLAN

### ЭТАП 1: Создать базовый Repository
**Файл:** `repositories/base.py`

```python
from typing import Generic, TypeVar, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from field_service.db.session import SessionLocal

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """Базовый репозиторий с общими методами."""
    
    def __init__(self, model: type[T], session_factory=SessionLocal):
        self.model = model
        self._session_factory = session_factory
    
    async def get_by_id(self, entity_id: int) -> Optional[T]:
        async with self._session_factory() as session:
            return await session.get(self.model, entity_id)
    
    async def add(self, entity: T) -> T:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(entity)
                await session.flush()
                await session.refresh(entity)
            return entity
    
    async def update(self, entity: T) -> T:
        async with self._session_factory() as session:
            async with session.begin():
                await session.merge(entity)
                await session.flush()
            return entity
    
    async def delete(self, entity_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                entity = await session.get(self.model, entity_id)
                if entity:
                    await session.delete(entity)
                    return True
                return False
```

### ЭТАП 2: Создать OrdersRepository
**Файл:** `repositories/orders_repository.py`

```python
from typing import Optional, Sequence
from datetime import date
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from .base import BaseRepository

class OrdersRepository(BaseRepository[m.orders]):
    def __init__(self, session_factory=SessionLocal):
        super().__init__(m.orders, session_factory)
    
    async def find_by_status(
        self,
        status: m.OrderStatus,
        *,
        city_ids: Optional[list[int]] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[Sequence[m.orders], bool]:
        """Найти заказы по статусу с фильтрами."""
        offset = max(page - 1, 0) * page_size
        
        async with self._session_factory() as session:
            stmt = (
                select(m.orders)
                .where(m.orders.status == status)
                .order_by(m.orders.created_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )
            
            if city_ids:
                stmt = stmt.where(m.orders.city_id.in_(city_ids))
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            has_next = len(rows) > page_size
            return rows[:page_size], has_next
    
    async def find_active_by_master(
        self,
        master_id: int,
    ) -> Sequence[m.orders]:
        """Найти активные заказы мастера."""
        async with self._session_factory() as session:
            stmt = (
                select(m.orders)
                .where(
                    and_(
                        m.orders.assigned_master_id == master_id,
                        m.orders.status.in_([
                            m.OrderStatus.ASSIGNED,
                            m.OrderStatus.EN_ROUTE,
                            m.OrderStatus.WORKING,
                            m.OrderStatus.PAYMENT,
                        ])
                    )
                )
                .order_by(m.orders.created_at.asc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def count_active_by_master(self, master_id: int) -> int:
        """Подсчитать активные заказы мастера."""
        async with self._session_factory() as session:
            stmt = (
                select(func.count())
                .select_from(m.orders)
                .where(
                    and_(
                        m.orders.assigned_master_id == master_id,
                        m.orders.status.in_([
                            m.OrderStatus.ASSIGNED,
                            m.OrderStatus.EN_ROUTE,
                            m.OrderStatus.WORKING,
                            m.OrderStatus.PAYMENT,
                        ])
                    )
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
    
    async def has_active_guarantee(
        self,
        source_order_id: int,
        *,
        city_ids: Optional[list[int]] = None,
    ) -> bool:
        """Проверить наличие активной гарантийной заявки."""
        async with self._session_factory() as session:
            stmt = (
                select(1)
                .where(m.orders.guarantee_source_order_id == source_order_id)
                .where(~m.orders.status.in_([
                    m.OrderStatus.CANCELED,
                    m.OrderStatus.CLOSED,
                ]))
                .limit(1)
            )
            
            if city_ids:
                stmt = stmt.where(m.orders.city_id.in_(city_ids))
            
            result = await session.execute(stmt)
            return result.first() is not None
```

### ЭТАП 3: Создать OrdersService
**Файл:** `services/orders_service.py`

```python
from typing import Optional
from datetime import datetime

from ..dto import OrderDetail, OrderListItem
from ..repositories.orders_repository import OrdersRepository
from ..repositories.cities_repository import CitiesRepository
from ..repositories.masters_repository import MastersRepository

class OrdersService:
    """Бизнес-логика для работы с заказами."""
    
    def __init__(
        self,
        orders_repo: OrdersRepository,
        cities_repo: CitiesRepository,
        masters_repo: MastersRepository,
    ):
        self._orders = orders_repo
        self._cities = cities_repo
        self._masters = masters_repo
    
    async def get_card(
        self,
        order_id: int,
        *,
        city_ids: Optional[list[int]] = None,
    ) -> Optional[OrderDetail]:
        """
        Получить карточку заказа с полной информацией.
        
        Включает:
        - Данные заказа
        - Название города/района/улицы
        - Данные мастера (если назначен)
        - Вложения
        """
        # 1. Загрузить заказ
        order = await self._orders.get_by_id(order_id)
        if not order:
            return None
        
        # 2. RBAC: Проверить доступ
        if city_ids and order.city_id not in city_ids:
            return None
        
        # 3. Загрузить связанные данные
        city = await self._cities.get_by_id(order.city_id)
        master = None
        if order.assigned_master_id:
            master = await self._masters.get_by_id(order.assigned_master_id)
        
        # 4. Форматировать для UI
        return OrderDetail(
            id=order.id,
            city_id=order.city_id,
            city_name=city.name if city else None,
            status=order.status.value,
            # ... остальные поля
        )
    
    async def list_queue(
        self,
        *,
        city_ids: Optional[list[int]] = None,
        status_filter: Optional[OrderStatus] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[OrderListItem], bool]:
        """Список заказов в очереди с фильтрами."""
        # 1. Загрузить из репозитория
        orders, has_next = await self._orders.find_by_status(
            status_filter or OrderStatus.SEARCHING,
            city_ids=city_ids,
            page=page,
            page_size=page_size,
        )
        
        # 2. Преобразовать в DTO
        items = []
        for order in orders:
            city = await self._cities.get_by_id(order.city_id)
            items.append(
                OrderListItem(
                    id=order.id,
                    city_name=city.name if city else None,
                    status=order.status.value,
                    # ...
                )
            )
        
        return items, has_next
```

---

## ПРЕИМУЩЕСТВА НОВОГО ПОДХОДА

### 1. Тестируемость
**БЫЛО:** Нужно мокать весь SessionLocal
```python
@pytest.mark.asyncio
async def test_get_card_old():
    # Мокать SessionLocal сложно
    service = DBOrdersService()
    # ...
```

**СТАЛО:** Мокаем только репозиторий
```python
@pytest.mark.asyncio
async def test_get_card_new():
    # Простой mock
    orders_repo = Mock(OrdersRepository)
    orders_repo.get_by_id.return_value = fake_order
    
    service = OrdersService(orders_repo, cities_repo, masters_repo)
    result = await service.get_card(123)
    assert result.id == 123
```

### 2. Повторное использование
```python
# Один репозиторий для всех сервисов
orders_repo = OrdersRepository()

orders_service = OrdersService(orders_repo, ...)
distribution_service = DistributionService(orders_repo, ...)
finance_service = FinanceService(orders_repo, ...)
```

### 3. Простота SQL-запросов
```python
# Репозиторий: чистый SQL
async def find_by_status(self, status):
    return await session.execute(select(m.orders).where(...))

# Сервис: бизнес-логика
async def get_pending_orders(self):
    orders = await self._repo.find_by_status(OrderStatus.SEARCHING)
    # валидация, фильтрация, трансформация
    return [self._to_dto(o) for o in orders if self._is_valid(o)]
```

---

## MIGRATION ROADMAP

### Week 1: Infrastructure
- [ ] Создать `repositories/` структуру
- [ ] Написать `BaseRepository`
- [ ] Создать `CitiesRepository` (простой, для примера)
- [ ] Unit-тесты для `BaseRepository`

### Week 2: Orders Module
- [ ] `OrdersRepository` (все методы из `DBOrdersService`)
- [ ] `OrdersService` (бизнес-логика)
- [ ] Обновить `handlers/orders.py` для использования нового сервиса
- [ ] Integration tests

### Week 3: Masters & Staff
- [ ] `MastersRepository`
- [ ] `StaffRepository`
- [ ] Обновить admin handlers

### Week 4: Finance & Distribution
- [ ] `CommissionsRepository`
- [ ] `FinanceService`
- [ ] `DistributionService` (с новыми репозиториями)

### Week 5: Cleanup
- [ ] Удалить `services_db.py`
- [ ] Обновить все импорты
- [ ] Проверить все тесты
- [ ] Code review

---

## NEXT STEPS

1. **Создать proof-of-concept:**
   - `repositories/base.py`
   - `repositories/orders_repository.py`
   - `services/orders_service.py`
   - Один handler с новым сервисом

2. **Написать тесты:**
   - Unit-тесты для репозиториев
   - Integration-тесты для сервисов
   - E2E-тесты для handlers

3. **Постепенная миграция:**
   - Не переписывать всё сразу
   - Новый код - новый паттерн
   - Legacy код - мигрировать по одному модулю

---

## CONCLUSION

Repository Pattern для `services_db.py` - **масштабная задача** (4-5 недель work).

**Рекомендация:** Отложить на отдельный спринт после завершения P2 задач.

**Альтернатива:** Исправить только **критичные проблемы** в `services_db.py`:
- Вынести дублирующиеся запросы в helper-функции
- Разбить монолитные классы на более мелкие
- Добавить типизацию для всех методов
