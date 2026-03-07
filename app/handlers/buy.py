from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    await message.answer(
        "💳 Купить подписку:\n"
        "30 дней - 100 руб\n"
        "Для оплаты свяжитесь с @admin"
    )
