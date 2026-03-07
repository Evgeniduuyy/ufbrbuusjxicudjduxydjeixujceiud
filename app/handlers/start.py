from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User

router = Router()

@router.message(CommandStart(deep_link=True))
async def start_deep(message: Message, state: FSMContext, session: AsyncSession):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('ref_'):
        await state.update_data(referral_code=args[1][4:])
    await start(message, state, session)

@router.message(CommandStart())
async def start(message: Message, state: FSMContext, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        data = await state.get_data()
        ref_code = data.get('referral_code')
        referred_by = None
        if ref_code:
            result = await session.execute(select(User).where(User.referral_code == ref_code))
            u = result.scalar_one_or_none()
            referred_by = u.id if u else None
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            referred_by_id=referred_by
        )
        session.add(user)
        await session.commit()
        await message.answer(
            "🤖 *Добро пожаловать в CDZmonstr!*\n\n"
            "Я помогу решать цифровые домашние задания из МЭШ.\n\n"
            "⚠️ *ВАЖНО:* Использование автоматизированных средств может нарушать правила платформы. "
            "Вы несёте полную ответственность за возможную блокировку аккаунта.\n\n"
            "📸 *Отправь фото задания* или *ссылку на задание* – я найду ответ.\n\n"
            "🔑 /login – войти в МЭШ (для просмотра своих заданий)\n"
            "📋 /tasks – список невыполненных заданий (после логина)\n"
            "⚙️ /settings – настройки\n"
            "👥 /ref – реферальная программа\n"
            "💳 /buy – купить подписку (снимает лимиты)"
        )
    else:
        await message.answer("Вы уже зарегистрированы. Используйте /help")