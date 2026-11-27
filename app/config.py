"""
Централизованная конфигурация сервера.
Все параметры читаются из переменных окружения, чтобы на Render
(и локально) не хранить секреты в коде.

Базы данных нет: клиенты, скриншоты и сообщения хранятся в памяти
процесса (см. app/store.py) и сбрасываются при рестарте сервера.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Хранилище скриншотов ---
# Сами файлы картинок по-прежнему на диске (это не база данных, без файлов
# скриншоты хранить негде). Метаданные — в памяти, см. app/store.py.
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", str(BASE_DIR / "data" / "screenshots")))

# --- Секреты ---
# Общий ключ, который «зашит» в конфиг клиента на флешке. Нужен, чтобы
# зарегистрировать новый компьютер как клиента.
ENROLLMENT_KEY = os.environ.get("ENROLLMENT_KEY", "change-me-enrollment-key")

# Ключ администратора. Вводится один раз в веб-панели администратора
# (хранится в localStorage браузера) и передаётся как Bearer-токен.
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "change-me-admin-key")

# Через сколько секунд без heartbeat/сообщений клиент считается офлайн.
ONLINE_THRESHOLD_SECONDS = int(os.environ.get("ONLINE_THRESHOLD_SECONDS", "90"))

# Максимальный размер загружаемого скриншота (защита от случайного/
# злонамеренного переполнения диска), в байтах. 8 МБ с запасом.
MAX_SCREENSHOT_BYTES = int(os.environ.get("MAX_SCREENSHOT_BYTES", str(8 * 1024 * 1024)))
