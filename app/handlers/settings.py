from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, SpeedMode

router = Router()

class SettingsStates(StatesGroup):
    waiting_attempts = State()

@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    text = f"⚙️ Настройки\nОшибок по умолч.: {user.default_max_attempts}\nСкорость: {user.default_speed.value}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить ошибки", callback_data="set_attempts")],
        [InlineKeyboardButton(text="Изменить скорость", callback_data="set_speed")]
    ])
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "set_attempts")
async def set_attempts_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.answer("Введите число ошибок по умолчанию:")
    await state.set_state(SettingsStates.waiting_attempts)

@router.message(SettingsStates.waiting_attempts)
async def process_attempts(message: Message, state: FSMContext, session: AsyncSession):
    try:
        val = int(message.text.strip())
        if val < 0: raise
    except:
        await message.answer("Введите неотрицательное число")
        return
    user = await session.get(User, message.from_user.id)
    user.default_max_attempts = val
    await session.commit()
    await message.answer("✅ Сохранено")
    await state.clear()

@router.callback_query(F.data == "set_speed")
async def set_speed_cb(cb: CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Быстро", callback_data="speed_fast")],
        [InlineKeyboardButton(text="Средне", callback_data="speed_medium")],
        [InlineKeyboardButton(text="Медленно", callback_data="speed_slow")]
    ])
    await cb.message.answer("Выберите скорость:", reply_markup=kb)

@router.callback_query(F.data.startswith("speed_"))
async def speed_chosen(cb: CallbackQuery, session: AsyncSession):
    await cb.answer()
    mapping = {"speed_fast": SpeedMode.FAST, "speed_medium": SpeedMode.MEDIUM, "speed_slow": SpeedMode.SLOW}
    user = await session.get(User, cb.from_user.id)
    user.default_speed = mapping[cb.data]
    await session.commit()
    await cb.message.answer("✅ Скорость сохранена")
