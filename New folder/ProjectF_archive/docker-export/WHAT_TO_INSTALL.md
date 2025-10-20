# 🖥️ ЧТО НУЖНО УСТАНОВИТЬ НА ЧИСТЫЙ WINDOWS SERVER

## ✅ Краткий ответ

**ТОЛЬКО ОДНО:**
- Docker Desktop for Windows

Всё остальное (Python, PostgreSQL, библиотеки) уже находится внутри Docker-контейнеров!

---

## 📦 Обязательная установка

### 1. Docker Desktop for Windows

**Что это:**
- Платформа для запуска контейнеров
- Включает Docker Engine + Docker Compose
- Единственное требуемое ПО для развёртывания

**Где скачать:**
```
https://www.docker.com/products/docker-desktop
```

**Как установить:**

1. Скачайте `Docker Desktop Installer.exe`

2. Запустите установщик

3. В настройках установки выберите:
   - ✅ **Use WSL 2 instead of Hyper-V** (рекомендуется)
   - ✅ **Add shortcut to desktop**

4. Нажмите **Install**

5. **ОБЯЗАТЕЛЬНО перезагрузите компьютер** после установки

6. После перезагрузки запустите **Docker Desktop**

7. Дождитесь полного запуска (иконка в трее станет зелёной)

**Проверка установки:**
```powershell
# Откройте PowerShell
docker --version
# Должно вывести: Docker version 24.x.x

docker-compose --version  
# Должно вывести: Docker Compose version 2.x.x

docker ps
# Должно вывести пустой список контейнеров (без ошибок)
```

---

## 🚫 НЕ НУЖНО устанавливать

Следующее ПО **НЕ ТРЕБУЕТСЯ**, так как уже включено в контейнеры:

❌ **Python** (внутри контейнеров ботов)
❌ **PostgreSQL** (отдельный контейнер)
❌ **pip и библиотеки** (установлены в контейнерах)
❌ **Node.js** (не используется)
❌ **Nginx/Apache** (не требуется, боты работают напрямую с Telegram)
❌ **Git** (не обязательно, если копируете готовые файлы)

---

## 📝 Опционально (для удобства)

Можно установить для комфортной работы:

### Windows Terminal
- Современный терминал с вкладками
- Скачать из **Microsoft Store**
- Или: https://aka.ms/terminal

### Visual Studio Code
- Удобный редактор для .env файлов
- Скачать: https://code.visualstudio.com/

### Git for Windows
- Нужен только если планируете клонировать репозиторий
- Скачать: https://git-scm.com/download/win

---

## 💻 Системные требования

### Минимальные:
- **ОС**: Windows Server 2019/2022 или Windows 10/11 Pro
  - ❌ Windows Home НЕ поддерживается!
- **CPU**: 2 ядра (с поддержкой виртуализации VT-x/AMD-V)
- **RAM**: 4 GB
- **Диск**: 20 GB свободного места
- **Интернет**: Стабильное подключение

### Рекомендуемые:
- **CPU**: 4+ ядра
- **RAM**: 8+ GB
- **Диск**: 50+ GB (SSD)

---

## 🔧 Настройки Windows

### BIOS (если виртуализация отключена):
1. Перезагрузите компьютер
2. Войдите в BIOS (обычно F2, F10, Del или Esc при загрузке)
3. Найдите настройки:
   - Intel: **Intel VT-x** или **Virtualization Technology**
   - AMD: **AMD-V** или **SVM Mode**
4. Включите виртуализацию
5. Сохраните и перезагрузитесь

### Windows Features (автоматически при установке Docker):
Docker Desktop автоматически включит:
- WSL 2 (Windows Subsystem for Linux)
- Hyper-V (если WSL 2 недоступен)
- Virtual Machine Platform

Если нужно включить вручную:
```powershell
# Запустить PowerShell от имени администратора
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
```

---

## 📋 Пошаговый план установки ПО

### Шаг 1: Проверьте систему
```powershell
# Версия Windows
systeminfo | findstr /C:"OS"

# Должно быть: Windows Server 2019/2022 или Windows 10/11 Pro

# Оперативная память
systeminfo | findstr /C:"Total Physical Memory"

# Должно быть минимум 4 GB
```

### Шаг 2: Скачайте Docker Desktop
- Перейдите на https://www.docker.com/products/docker-desktop
- Скачайте установщик для Windows

### Шаг 3: Установите Docker Desktop
- Запустите `Docker Desktop Installer.exe`
- Следуйте инструкциям
- Выберите WSL 2 backend
- **Перезагрузите компьютер**

### Шаг 4: Запустите Docker Desktop
- Запустите приложение Docker Desktop
- Дождитесь зелёной иконки в трее
- Согласитесь с условиями использования (если попросит)

### Шаг 5: Проверьте установку
```powershell
docker --version
docker-compose --version
docker ps
docker run hello-world
```

Если все команды работают без ошибок - установка завершена! ✅

---

## 🎯 Готовы к следующему шагу?

После установки Docker Desktop:

1. ✅ Скопируйте папку `docker-export` на сервер
2. ✅ Откройте `INDEX.md` или `QUICKSTART.md`
3. ✅ Следуйте дальнейшим инструкциям

---

## 🆘 Проблемы при установке Docker

### Docker не запускается после установки

**Причина:** Не включена виртуализация в BIOS

**Решение:**
1. Перезагрузите в BIOS
2. Включите VT-x (Intel) или AMD-V (AMD)
3. Сохраните и перезагрузитесь

---

### Ошибка "WSL 2 installation is incomplete"

**Решение:**
```powershell
# Скачайте и установите обновление WSL 2 kernel:
# https://aka.ms/wsl2kernel

# После установки перезапустите Docker Desktop
```

---

### Требуется Windows Pro/Enterprise

**Проблема:** У вас Windows Home

**Решение:**
- Обновите до Windows 10/11 Pro
- Или используйте Windows Server
- Docker Desktop НЕ работает на Windows Home

---

## 📞 Дополнительная помощь

**Официальная документация Docker:**
- https://docs.docker.com/desktop/install/windows-install/

**Системные требования Docker:**
- https://docs.docker.com/desktop/install/windows-install/#system-requirements

---

## ✅ Финальный чеклист

Перед переходом к развёртыванию убедитесь:

- [ ] Windows Server 2019+/Windows 10/11 Pro установлена
- [ ] Виртуализация включена в BIOS
- [ ] Docker Desktop установлен
- [ ] Docker Desktop запущен (зелёная иконка)
- [ ] Команды `docker --version` и `docker ps` работают
- [ ] Тестовый контейнер `docker run hello-world` запустился

Если всё ✅ - переходите к развёртыванию!

---

**Время установки Docker Desktop:** 10-15 минут + перезагрузка  
**Сложность:** Простая (следуйте мастеру установки)
