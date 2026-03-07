# CDZmonstr Bot

Telegram-бот для автоматического решения заданий из МЭШ.

## Установка и запуск

1. Скопируйте `.env.example` в `.env` и заполните свои данные
2. Установите зависимости: `pip install -r requirements.txt`
3. Запустите бота: `python -m app.main`
4. (Опционально) Запустите Celery: `celery -A app.celery_app worker --loglevel=info`
