"""
Главный файл запуска бота.
"""
import asyncio
import logging
import sys
import os

# Добавляем родительскую папку в путь, чтобы гарантировать импорты
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import Config
from app.handlers import start, auth, solve, tasks, settings, ref, buy, admin
from app.models.base import Base

logging.basicConfig(level=logging.INFO)

async def main():
    # Подключение к БД
    engine = create_async_engine(Config.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # Redis
    redis = Redis.from_url(Config.REDIS_URL)
    storage = RedisStorage(redis)

    # Бот
    bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(auth.router)
    dp.include_router(solve.router)
    dp.include_router(tasks.router)
    dp.include_router(settings.router)
    dp.include_router(ref.router)
    dp.include_router(buy.router)
    dp.include_router(admin.router)

    @dp.update.outer_middleware()
    async def db_session_middleware(handler, event, data):
        async with async_session_maker() as session:
            data['session'] = session
            return await handler(event, data)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
