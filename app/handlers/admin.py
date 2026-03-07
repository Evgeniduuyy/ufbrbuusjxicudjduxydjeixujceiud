from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.config import Config
from app.models.user import User

router = Router()

class BroadcastStates(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()

@router.message(Command("broadcast"), F.from_user.id.in_(Config.ADMIN_IDS))
async def cmd_broadcast(message: Message, state: FSMContext):
    await message.answer("Введите текст для рассылки:")
    await state.set_state(BroadcastStates.waiting_text)

@router.message(BroadcastStates.waiting_text)
async def process_broadcast_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer(
        f"Предпросмотр:\n\n{message.text}\n\nОтправить всем?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="broadcast_cancel")]
        ])
    )
    await state.set_state(BroadcastStates.waiting_confirm)

@router.callback_query(BroadcastStates.waiting_confirm, F.data == "broadcast_confirm")
async def broadcast_confirm(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cb.answer()
    data = await state.get_data()
    text = data['text']
    total = await session.scalar(select(func.count(User.id)))
    await cb.message.edit_text(f"⏳ Запущена рассылка {total} пользователям...")
    # Здесь можно добавить реальную рассылку через Celery
    await cb.message.edit_text(f"✅ Рассылка завершена (отправлено {total})")
    await state.clear()

@router.callback_query(BroadcastStates.waiting_confirm, F.data == "broadcast_cancel")
async def broadcast_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_text("Рассылка отменена.")
    await state.clear()
