from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.auth import MESAuth
from app.services.tasks_fetcher import TasksFetcher
from app.models.user import User

router = Router()

@router.message(Command("tasks"))
async def cmd_tasks(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    auth = MESAuth(message.from_user.id, session)
    try:
        await auth.get_session()
    except:
        await message.answer("Не авторизован в МЭШ. Выполните /login")
        return
    fetcher = TasksFetcher(auth)
    tasks = await fetcher.fetch_tasks()
    if not tasks:
        await message.answer("Нет актуальных заданий.")
        return
    lines = ["📋 *Ваши задания:*"]
    for t in tasks[:10]:
        status = "✅" if t['status'] == 'done' else "⏳"
        lines.append(f"{status} {t['subject']}: {t['title']}\nСрок: {t['deadline']}\n[Ссылка]({t['url']})")
    await message.answer("\n\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)
