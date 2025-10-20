# Field Service – Telegram Mini WebApps

## ⚠️ Важное изменение архитектуры

**КЛИЕНТСКОГО ВЕБ-ПРИЛОЖЕНИЯ НЕТ И НЕ БУДЕТ!**

Система состоит из **двух Telegram Mini WebApps**:
1. **🔧 Мастер WebApp** - для исполнителей заказов
2. **⚙️ Админ WebApp** - для администраторов и логистов

Заказы создаются **только через админ-панель**. Подробнее см. [docs/WEBAPP_ARCHITECTURE.md](docs/WEBAPP_ARCHITECTURE.md)

---

## 📊 Структура проекта

```
C:\ProjectF\
├── master-webapp/          # 🔧 Мастер Mini WebApp
├── admin-webapp/           # ⚙️ Админ Mini WebApp  
├── backend/               # 🔙 Backend API
├── field-service/         # 📦 Старый проект (2 бота) - для справки
├── control-bot/           # 🤖 Control Bot (мониторинг)
└── docs/                  # 📚 Документация
```

---

## 🚀 Быстрый старт

### Backend API
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Настроить .env
python -m uvicorn main:app --reload
```

### Мастер WebApp
```bash
cd master-webapp
npm install
npm run dev
```

### Админ WebApp
```bash
cd admin-webapp
npm install
npm run dev
```

---

## 📖 Документация

- **[WEBAPP_ARCHITECTURE.md](docs/WEBAPP_ARCHITECTURE.md)** - Архитектура Mini WebApps (ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ!)
- **[docs/README.md](docs/README.md)** - Индекс всей документации
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Деплой на сервер
- **[TZ(old).docx](TZ(old).docx)** - Старое ТЗ (3 бота) - устарело!

---

## 🔄 Миграция со старой архитектуры

**Было:** 3 Telegram бота (клиент, мастер, админ)  
**Стало:** 2 Telegram Mini WebApps (мастер, админ)

### Что изменилось:
- ❌ Удален клиент-бот
- ❌ Удалены callback'ы с префиксом `cl:*`
- ❌ Удалены клиентские FSM состояния
- ✅ Создание заказов только через админ-панель
- ✅ Мастер и админ - современные веб-приложения

Подробности миграции: [docs/WEBAPP_ARCHITECTURE.md](docs/WEBAPP_ARCHITECTURE.md)

---

## 🛠️ Технологии

### Frontend (оба WebApp)
- **Framework:** React 18 + TypeScript
- **Build:** Vite
- **UI:** Telegram Mini Apps SDK + shadcn/ui
- **State:** Zustand
- **API:** Axios + React Query
- **WebSocket:** Socket.io-client

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL 15+
- **ORM:** SQLAlchemy 2.0
- **Auth:** JWT
- **WebSocket:** Socket.io
- **Task Queue:** Celery + Redis (для распределения)

---

## 📦 Установка зависимостей

### Backend
```bash
cd backend
pip install -r requirements.txt
```

### Frontend (оба приложения)
```bash
cd master-webapp  # или admin-webapp
npm install
```

---

## 🗄️ База данных

### Миграции
```bash
cd backend
alembic upgrade head
```

### Seed данных
```bash
python scripts/seed_data.py
```

---

## 🧪 Тестирование

### Backend
```bash
cd backend
pytest
```

### Frontend
```bash
cd master-webapp  # или admin-webapp
npm run test
```

---

## 🚀 Деплой

Подробная инструкция: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

Краткая версия:
```bash
# 1. Backend на сервере
git pull
cd backend
pip install -r requirements.txt
alembic upgrade head
systemctl restart field-service-api

# 2. Frontend (сборка и деплой)
cd master-webapp
npm run build
# Загрузить dist/ на Telegram Mini App
```

---

## 📊 Мониторинг

### Backend API
- **Health Check:** `GET /api/health`
- **Metrics:** `GET /api/metrics`
- **Logs:** `tail -f logs/api.log`

### Database
```bash
# Backup
./ops/backup_db.sh

# Restore
./ops/restore_db.sh <backup_file>
```

---

## 🔐 Безопасность

- Все API endpoints требуют JWT токен
- Telegram Mini Apps используют initData для верификации
- Пароли хешируются bcrypt
- Номера карт маскируются в логах
- CORS настроен только для Telegram domains

---

## 📞 Поддержка

- **Issues:** GitHub Issues (если используется)
- **Документация:** `docs/`
- **Архитектура:** [docs/WEBAPP_ARCHITECTURE.md](docs/WEBAPP_ARCHITECTURE.md)

---

## 🎯 Roadmap

- [x] Архитектура Mini WebApps
- [x] Backend API design
- [ ] Мастер WebApp MVP
- [ ] Админ WebApp MVP  
- [ ] Интеграция с Telegram
- [ ] Production deployment
- [ ] Performance optimization
- [ ] Advanced features

---

## 📝 Changelog

### v1.0.0 (Октябрь 2025)
- 🎉 Переход на Telegram Mini WebApps
- ❌ Удален клиентский бот
- ✅ Создание заказов через админ-панель
- ✅ Новая архитектура frontend/backend

### v0.5.0 (Сентябрь 2025)
- Старая версия с 3 ботами (устарела)

---

## ⚖️ Лицензия

Proprietary - Все права защищены

---

**Последнее обновление:** 12 октября 2025  
**Версия:** WebApp v1.0
