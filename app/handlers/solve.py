from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.services.auth import MESAuth
from app.services.parser import TaskParser
from app.services.answer_finder import AnswerFinder
from app.services.limits import check_and_reset_daily_limits, can_use_solve, can_use_auto, increment_solve_usage
from app.models.user import User
from app.services.ocr import ocr_task

router = Router()

class SolveStates(StatesGroup):
    waiting_url = State()

@router.message(F.photo)
async def handle_photo(message: Message, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    await check_and_reset_daily_limits(user, session)
    if not await can_use_solve(user, session):
        await message.answer("Дневной лимит (3) исчерпан. Купите подписку /buy")
        return
    file = await message.bot.get_file(message.photo[-1].file_id)
    file_bytes = await file.download(destination=io.BytesIO())
    await message.answer("🖼 Распознаю текст...")
    task = ocr_task.delay(file_bytes.getvalue())
    try:
        text = task.get(timeout=30)
    except:
        await message.answer("Ошибка распознавания.")
        return
    if not text:
        await message.answer("Не удалось извлечь текст.")
        return
    task_data = {
        'url': 'photo',
        'question': text,
        'options': [],
        'task_type': 'input',
        'attempts_left': None
    }
    finder = AnswerFinder(session)
    answer = await finder.find(task_data)
    if answer:
        await message.answer(f"✅ *Ответ:* {answer.get('text','')}", parse_mode="Markdown")
        await increment_solve_usage(user, session)
    else:
        await message.answer("❌ Не удалось найти ответ.")

@router.message(Command("solve"))
async def cmd_solve(message: Message, state: FSMContext, session: AsyncSession):
    user = await session.get(User, message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    await check_and_reset_daily_limits(user, session)
    if not await can_use_solve(user, session):
        await message.answer("Дневной лимит (3) исчерпан. Купите подписку /buy")
        return
    await message.answer("Отправьте ссылку на задание в МЭШ:")
    await state.set_state(SolveStates.waiting_url)

@router.message(SolveStates.waiting_url)
async def process_url(message: Message, state: FSMContext, session: AsyncSession):
    url = message.text.strip()
    if not url.startswith("https://school.mos.ru/"):
        await message.answer("Ссылка должна начинаться с https://school.mos.ru/")
        return
    await state.update_data(url=url)
    await message.answer("Парсим задание...")
    auth = MESAuth(message.from_user.id, session)
    try:
        await auth.get_session()
    except:
        await message.answer("Ошибка авторизации. Выполните /login заново")
        await state.clear()
        return
    parser = TaskParser(auth)
    task_data = await parser.parse(url)
    if not task_data.get('task_type'):
        await message.answer("Не удалось распознать задание.")
        await state.clear()
        return
    await state.update_data(task_data=task_data)
    text = f"📝 {task_data.get('question','')[:200]}...\nТип: {task_data['task_type']}"
    if task_data.get('attempts_left'):
        text += f"\nПопыток: {task_data['attempts_left']}"
    await message.answer(text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Только ответы", callback_data="solve_only")],
        [InlineKeyboardButton(text="Автовыполнение", callback_data="auto_do")]
    ])
    await message.answer("Выберите действие:", reply_markup=kb)

@router.callback_query(F.data == "solve_only")
async def solve_only(cb: CallbackQuery, state: FSMContext, session: AsyncSession):
    await cb.answer()
    data = await state.get_data()
    task_data = data['task_data']
    finder = AnswerFinder(session)
    ans = await finder.find(task_data)
    if ans:
        await cb.message.answer(f"✅ Ответ: {ans.get('text','')}")
        user = await session.get(User, cb.from_user.id)
        await increment_solve_usage(user, session)
    else:
        await cb.message.answer("Не удалось найти ответ.")
    await state.clear()
