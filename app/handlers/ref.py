from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.user import User
from app.models.referral import Referral

router = Router()

@router.message(Command("ref"))
async def cmd_ref(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_id == user.id, 
            Referral.reward_granted == True
        )
    )
    cnt = result.scalar() or 0
    bot = await message.bot.me()
    link = f"https://t.me/{bot.username}?start=ref_{user.referral_code}"
    await message.answer(
        f"🔗 Ваша ссылка:\n{link}\n"
        f"Приглашено друзей: {cnt}\n"
        f"За каждого друга, вошедшего в МЭШ, +2 дня подписки вам и другу!"
    )
