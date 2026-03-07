from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.auth import MESAuth
from app.services.limits import add_subscription_days
from app.models.user import User
from app.models.referral import Referral
from sqlalchemy import select

router = Router()

class LoginStates(StatesGroup):
    waiting_login = State()
    waiting_password = State()
    waiting_otp = State()

@router.message(Command("login"))
async def cmd_login(message: Message, state: FSMContext):
    await message.answer("Введите логин (номер телефона или email) от school.mos.ru:")
    await state.set_state(LoginStates.waiting_login)

@router.message(LoginStates.waiting_login)
async def process_login(message: Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await message.answer("Введите пароль:")
    await state.set_state(LoginStates.waiting_password)

@router.message(LoginStates.waiting_password)
async def process_password(message: Message, state: FSMContext, session: AsyncSession):
    await state.update_data(password=message.text.strip())
    data = await state.get_data()
    auth = MESAuth(message.from_user.id, session)
    try:
        ok = await auth.login(data['login'], data['password'])
    except Exception as e:
        await message.answer(f"Ошибка: {e}. Попробуйте ещё раз /login")
        await state.clear()
        return
    if ok:
        await message.answer("✅ Успешный вход!")
        user = await session.get(User, message.from_user.id)
        if user and user.referred_by_id:
            stmt = select(Referral).where(Referral.referred_id == user.id)
            result = await session.execute(stmt)
            ref = result.scalar_one_or_none()
            if not ref:
                ref = Referral(referrer_id=user.referred_by_id, referred_id=user.id)
                session.add(ref)
                await session.commit()
            if not ref.reward_granted:
                await add_subscription_days(user.referred_by_id, 2, session)
                await add_subscription_days(user.id, 2, session)
                ref.reward_granted = True
                await session.commit()
                await message.answer("🎉 Вы и пригласивший получили +2 дня подписки!")
        await state.clear()
    else:
        await message.answer("Неверные данные. Возможно, требуется двухфакторная аутентификация?")
        await state.clear()
