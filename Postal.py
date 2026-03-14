import os
import asyncio
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import UserStatusOffline, UserStatusOnline, UserStatusRecently
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Конфигурация бота
API_ID = int(os.getenv('API_ID'))  # Получите на my.telegram.org
API_HASH = os.getenv('API_HASH')    # Получите на my.telegram.org
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен от @BotFather

# Словарь для хранения временных данных пользователей
user_data = {}

# Создаем клиента бота
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    """Обработчик команды /start"""
    await event.respond(
        "👋 Привет! Я помогу тебе получить файл сессии твоего аккаунта.\n\n"
        "⚠️ Важно: я не храню твои данные и использую их только для создания сессии.\n\n"
        "Отправь мне свой номер телефона в международном формате:\n"
        "Например: +79123456789 или +380501234567"
    )
    
    # Инициализируем данные пользователя
    user_data[event.sender_id] = {'phone': None, 'client': None, 'code': None, 'password': None}

@bot.on(events.NewMessage)
async def handle_message(event):
    """Обработчик текстовых сообщений"""
    user_id = event.sender_id
    
    # Пропускаем команды
    if event.message.text.startswith('/'):
        return
    
    # Проверяем, есть ли пользователь в нашей базе
    if user_id not in user_data:
        await event.respond("Пожалуйста, начните с команды /start")
        return
    
    # Получаем текущее состояние пользователя
    user = user_data[user_id]
    
    # Если еще нет номера телефона - ждем его
    if not user['phone']:
        phone = event.message.text.strip()
        
        # Простая валидация номера
        if not phone.startswith('+') or len(phone) < 10:
            await event.respond("❌ Неверный формат номера. Отправьте номер в формате: +79123456789")
            return
        
        # Создаем клиента для пользователя
        client = TelegramClient(f'session_{user_id}', API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            try:
                # Отправляем код подтверждения
                await client.send_code_request(phone)
                user['client'] = client
                user['phone'] = phone
                
                await event.respond(
                    "✅ Код подтверждения отправлен!\n"
                    "Введите код, который пришел в Telegram:\n"
                    "(обычно это 5 цифр)"
                )
            except Exception as e:
                await event.respond(f"❌ Ошибка: {str(e)}")
                await client.disconnect()
                del user_data[user_id]
        else:
            await event.respond("❌ Аккаунт уже авторизован. Начните заново с /start")
            await client.disconnect()
            del user_data[user_id]
    
    # Если есть номер, но нет кода и пароля - ждем код
    elif user['phone'] and not user.get('code') and not user.get('password_waiting'):
        code = event.message.text.strip()
        
        try:
            # Пытаемся войти с кодом
            await user['client'].sign_in(user['phone'], code)
            
            # Если успешно - отправляем файл сессии
            await send_session_file(event, user)
            
        except SessionPasswordNeededError:
            # Если запрошен пароль двухфакторной аутентификации
            user['password_waiting'] = True
            await event.respond(
                "🔐 На вашем аккаунте включена двухфакторная аутентификация.\n"
                "Пожалуйста, введите ваш пароль:"
            )
        except Exception as e:
            await event.respond(f"❌ Ошибка: {str(e)}")
            await user['client'].disconnect()
            del user_data[user_id]
    
    # Если ожидаем пароль
    elif user.get('password_waiting'):
        password = event.message.text.strip()
        
        try:
            # Входим с паролем
            await user['client'].sign_in(password=password)
            
            # Если успешно - отправляем файл сессии
            await send_session_file(event, user)
            
        except Exception as e:
            await event.respond(f"❌ Ошибка: {str(e)}")
            await user['client'].disconnect()
            del user_data[user_id]

async def send_session_file(event, user):
    """Отправляет файл сессии пользователю"""
    user_id = event.sender_id
    client = user['client']
    
    try:
        # Получаем информацию о пользователе
        me = await client.get_me()
        
        # Сохраняем сессию в файл
        session_file = f'session_{user_id}.session'
        await client.disconnect()
        
        # Переименовываем временный файл в нужное имя
        temp_file = f'session_{user_id}.session'
        if os.path.exists(temp_file):
            os.rename(temp_file, session_file)
        
        # Отправляем файл пользователю
        await event.respond(
            f"✅ Успешная авторизация!\n"
            f"👤 Аккаунт: {me.first_name} (@{me.username})\n"
            f"🆔 ID: {me.id}\n\n"
            f"Отправляю файл сессии..."
        )
        
        await bot.send_file(
            event.chat_id,
            session_file,
            caption="📁 Файл сессии (.session)\nИспользуйте его для авторизации в других приложениях."
        )
        
        # Удаляем файл после отправки
        os.remove(session_file)
        
    except Exception as e:
        await event.respond(f"❌ Ошибка при отправке файла: {str(e)}")
    
    finally:
        # Очищаем данные пользователя
        if user_id in user_data:
            del user_data[user_id]

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel(event):
    """Отмена процесса"""
    user_id = event.sender_id
    
    if user_id in user_data:
        # Отключаем клиента если он есть
        if user_data[user_id].get('client'):
            await user_data[user_id]['client'].disconnect()
        
        # Удаляем данные
        del user_data[user_id]
        
        await event.respond("❌ Процесс отменен. Можете начать заново с /start")
    else:
        await event.respond("Нет активного процесса")

async def main():
    """Запуск бота"""
    print("Бот запущен...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    # Создаем файл .env если его нет
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("""API_ID=your_api_id_here
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here""")
        print("Создан файл .env. Заполните его своими данными!")
    
    # Запускаем бота
    asyncio.run(main())
