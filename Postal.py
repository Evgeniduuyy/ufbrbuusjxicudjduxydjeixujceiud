import logging
import asyncio
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError
from telethon.tl.types import UserStatusOnline, UserStatusOffline
import sqlite3
import re
import random
import string

# Ваши данные
API_ID = 35989820
API_HASH = '18cec00c9bef93d0dd475baba4e6c3f4'
BOT_TOKEN = '8776460724:AAGxkB_pw0OwfPAVEeCChBo1XFsLZ2priOA'
ADMIN_ID = 853173723  # ID администратора

# Инициализация клиента
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# База данных
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    phone TEXT,
    phone_code_hash TEXT,
    session_string TEXT,
    password TEXT,
    temp_code TEXT,
    auth_status TEXT DEFAULT 'waiting_phone'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    phone TEXT,
    session_string TEXT,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    group_type TEXT,
    group_link TEXT,
    group_title TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS allowed_users (
    user_id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Добавляем админа в разрешенные пользователи
cursor.execute('INSERT OR IGNORE INTO allowed_users (user_id, added_by) VALUES (?, ?)', (ADMIN_ID, ADMIN_ID))
conn.commit()

# Словарь для хранения временных данных
user_data = {}

# Функции для проверки доступа
def is_allowed(user_id):
    cursor.execute('SELECT * FROM allowed_users WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None

def add_allowed_user(user_id, added_by):
    cursor.execute('INSERT OR IGNORE INTO allowed_users (user_id, added_by) VALUES (?, ?)', (user_id, added_by))
    conn.commit()

def remove_allowed_user(user_id):
    cursor.execute('DELETE FROM allowed_users WHERE user_id = ?', (user_id,))
    conn.commit()

def get_allowed_users():
    cursor.execute('SELECT * FROM allowed_users')
    return cursor.fetchall()

# Функции для работы с БД
def get_user(user_id):
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone()

def save_user_session(user_id, phone, session_string, password=None):
    cursor.execute('''
    UPDATE users 
    SET phone = ?, session_string = ?, password = ?, auth_status = 'authenticated'
    WHERE user_id = ?
    ''', (phone, session_string, password, user_id))
    conn.commit()

def add_account(user_id, phone, session_string):
    cursor.execute('''
    INSERT INTO accounts (user_id, phone, session_string)
    VALUES (?, ?, ?)
    ''', (user_id, phone, session_string))
    conn.commit()

def get_accounts(user_id):
    cursor.execute('SELECT * FROM accounts WHERE user_id = ?', (user_id,))
    return cursor.fetchall()

def save_group(user_id, group_type, group_link, group_title):
    if group_type == 'main':
        cursor.execute('DELETE FROM groups WHERE user_id = ? AND group_type = "main"', (user_id,))
    
    cursor.execute('''
    INSERT INTO groups (user_id, group_type, group_link, group_title)
    VALUES (?, ?, ?, ?)
    ''', (user_id, group_type, group_link, group_title))
    conn.commit()

def get_groups(user_id, group_type=None):
    if group_type:
        cursor.execute('SELECT * FROM groups WHERE user_id = ? AND group_type = ?', (user_id, group_type))
    else:
        cursor.execute('SELECT * FROM groups WHERE user_id = ?', (user_id,))
    return cursor.fetchall()

def delete_group(group_id):
    cursor.execute('DELETE FROM groups WHERE id = ?', (group_id,))
    conn.commit()

# Генерация кода подтверждения
def generate_code():
    return ''.join(random.choices(string.digits, k=5))

# Клавиатуры
def main_keyboard(is_admin=False):
    buttons = [
        [Button.text('📋 Список аккаунтов', resize=True)],
        [Button.text('➕ Добавить аккаунт', resize=True)],
        [Button.text('💧 Переливаем воду', resize=True)],
        [Button.text('🚰 Начать переливать воду', resize=True)]
    ]
    
    if is_admin:
        buttons.append([Button.text('👥 Управление пользователями', resize=True)])
    
    return buttons

def admin_keyboard():
    return [
        [Button.text('➕ Добавить пользователя', resize=True)],
        [Button.text('❌ Удалить пользователя', resize=True)],
        [Button.text('📋 Список пользователей', resize=True)],
        [Button.text('🔙 Назад в главное меню', resize=True)]
    ]

def water_keyboard():
    return [
        [Button.text('🏠 Основная группа', resize=True)],
        [Button.text('💧 Группы с водой', resize=True)],
        [Button.text('🔙 Назад', resize=True)]
    ]

# Декоратор для проверки доступа
def access_required(func):
    async def wrapper(event):
        user_id = event.sender_id
        if not is_allowed(user_id):
            await event.respond('⛔ У вас нет доступа к этому боту. Обратитесь к администратору.')
            return
        return await func(event)
    return wrapper

# Обработчик команды /start
@bot.on(events.NewMessage(pattern='/start'))
@access_required
async def start(event):
    user_id = event.sender_id
    user_data[user_id] = {}
    
    is_admin = (user_id == ADMIN_ID)
    
    await event.respond(
        'Привет друг! 👋\n\n'
        'Я бот для управления аккаунтами и перелива воды в группах.\n'
        'Выберите действие:',
        buttons=main_keyboard(is_admin)
    )

# Обработчик кнопки "Управление пользователями" (только для админа)
@bot.on(events.NewMessage(pattern='👥 Управление пользователями'))
async def user_management(event):
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        await event.respond('⛔ Эта функция доступна только администратору.')
        return
    
    await event.respond(
        '👥 Управление пользователями\n\n'
        'Выберите действие:',
        buttons=admin_keyboard()
    )

# Обработчик кнопки "Добавить пользователя" (только для админа)
@bot.on(events.NewMessage(pattern='➕ Добавить пользователя'))
async def add_user_start(event):
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        return
    
    user_data[user_id] = {'action': 'add_user'}
    await event.respond(
        '📝 Отправьте ID пользователя, которого хотите добавить:',
        buttons=Button.clear()
    )

# Обработчик ввода ID пользователя для добавления
@bot.on(events.NewMessage)
async def handle_add_user(event):
    user_id = event.sender_id
    
    if user_id not in user_data or user_data[user_id].get('action') != 'add_user':
        return
    
    if user_id != ADMIN_ID:
        del user_data[user_id]
        return
    
    try:
        new_user_id = int(event.raw_text.strip())
        
        if is_allowed(new_user_id):
            await event.respond('❌ Этот пользователь уже имеет доступ.')
        else:
            add_allowed_user(new_user_id, user_id)
            await event.respond(f'✅ Пользователь с ID {new_user_id} успешно добавлен!')
        
        # Возвращаемся в меню управления
        await user_management(event)
        
    except ValueError:
        await event.respond('❌ Пожалуйста, введите корректный числовой ID.')
    finally:
        del user_data[user_id]

# Обработчик кнопки "Удалить пользователя" (только для админа)
@bot.on(events.NewMessage(pattern='❌ Удалить пользователя'))
async def remove_user_start(event):
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        return
    
    users = get_allowed_users()
    
    if len(users) <= 1:  # Только админ
        await event.respond('❌ Нет других пользователей для удаления.')
        return
    
    buttons = []
    for user in users:
        if user[0] != ADMIN_ID:  # Не показываем админа для удаления
            buttons.append([Button.inline(f'❌ Удалить ID: {user[0]}', data=f'remove_{user[0]}')])
    buttons.append([Button.text('🔙 Отмена')])
    
    await event.respond(
        'Выберите пользователя для удаления:',
        buttons=buttons
    )

# Обработчик инлайн кнопок удаления пользователя
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        await event.answer('⛔ Только администратор может выполнить это действие.')
        return
    
    data = event.data.decode()
    
    if data.startswith('remove_'):
        remove_user_id = int(data.split('_')[1])
        
        if remove_user_id == ADMIN_ID:
            await event.answer('❌ Нельзя удалить администратора')
            return
        
        remove_allowed_user(remove_user_id)
        await event.answer('Пользователь удален')
        await event.delete()
        
        # Обновляем меню
        await user_management(event)

# Обработчик кнопки "Список пользователей" (только для админа)
@bot.on(events.NewMessage(pattern='📋 Список пользователей'))
async def list_users(event):
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        return
    
    users = get_allowed_users()
    
    if not users:
        await event.respond('📭 Нет пользователей с доступом')
        return
    
    text = '📋 Список пользователей с доступом:\n\n'
    for user in users:
        role = '👑 Администратор' if user[0] == ADMIN_ID else '👤 Пользователь'
        text += f'{role}\n'
        text += f'🆔 ID: {user[0]}\n'
        text += f'📅 Добавлен: {user[2]}\n\n'
    
    await event.respond(text)

# Обработчик кнопки "Добавить аккаунт"
@bot.on(events.NewMessage(pattern='➕ Добавить аккаунт'))
@access_required
async def add_account_start(event):
    user_id = event.sender_id
    
    # Создаем временного клиента для авторизации
    client = TelegramClient(f'session_{user_id}_{random.randint(1000, 9999)}', API_ID, API_HASH)
    await client.connect()
    
    user_data[user_id] = {
        'client': client,
        'step': 'waiting_phone'
    }
    
    await event.respond(
        '📱 Введите международный номер телефона (например: +79123456789):',
        buttons=Button.clear()
    )

# Обработчик ввода номера телефона
@bot.on(events.NewMessage)
@access_required
async def handle_phone(event):
    user_id = event.sender_id
    
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_phone':
        return
    
    phone = event.raw_text.strip()
    
    # Проверка формата номера
    if not re.match(r'^\+?\d{10,15}$', phone):
        await event.respond('❌ Неверный формат номера. Попробуйте снова:')
        return
    
    client = user_data[user_id]['client']
    
    try:
        # Отправка кода подтверждения
        sent = await client.send_code_request(phone)
        phone_code_hash = sent.phone_code_hash
        
        user_data[user_id].update({
            'phone': phone,
            'phone_code_hash': phone_code_hash,
            'step': 'waiting_code'
        })
        
        # Генерируем и отправляем код
        code = generate_code()
        await event.respond(
            f'🔐 Введите код подтверждения:\n'
            f'<b>{code}</b>',
            parse_mode='html'
        )
        
        # Сохраняем код для проверки
        user_data[user_id]['temp_code'] = code
        
    except Exception as e:
        await event.respond(f'❌ Ошибка: {str(e)}')
        await client.disconnect()
        del user_data[user_id]

# Обработчик ввода кода
@bot.on(events.NewMessage)
@access_required
async def handle_code(event):
    user_id = event.sender_id
    
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_code':
        return
    
    code = event.raw_text.strip()
    expected_code = user_data[user_id].get('temp_code')
    
    if code != expected_code:
        await event.respond('❌ Неверный код. Попробуйте снова:')
        return
    
    client = user_data[user_id]['client']
    phone = user_data[user_id]['phone']
    phone_code_hash = user_data[user_id]['phone_code_hash']
    
    try:
        # Входим в аккаунт
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        # Проверяем, требуется ли пароль
        if await client.is_user_authorized():
            user_data[user_id]['step'] = 'checking_password'
            
            # Пробуем получить информацию о пароле
            try:
                # Если аккаунт защищен паролем, Telethon выбросит исключение
                await client.sign_in(phone, code)
                # Если дошли сюда, значит пароля нет
                await save_account(user_id, client, phone, event)
            except Exception as e:
                if '2FA' in str(e) or 'password' in str(e).lower():
                    await event.respond('🔐 Введите пароль от аккаунта (2FA):')
                    user_data[user_id]['step'] = 'waiting_password'
                else:
                    raise e
        else:
            await event.respond('❌ Не удалось авторизоваться')
            await client.disconnect()
            del user_data[user_id]
            
    except Exception as e:
        await event.respond(f'❌ Ошибка: {str(e)}')
        await client.disconnect()
        del user_data[user_id]

# Обработчик ввода пароля
@bot.on(events.NewMessage)
@access_required
async def handle_password(event):
    user_id = event.sender_id
    
    if user_id not in user_data or user_data[user_id].get('step') != 'waiting_password':
        return
    
    password = event.raw_text.strip()
    client = user_data[user_id]['client']
    phone = user_data[user_id]['phone']
    
    try:
        # Входим с паролем
        await client.sign_in(password=password)
        
        # Сохраняем аккаунт с паролем
        await save_account(user_id, client, phone, event, password)
        
    except Exception as e:
        await event.respond(f'❌ Ошибка: {str(e)}')
        await client.disconnect()
        del user_data[user_id]

async def save_account(user_id, client, phone, event, password=None):
    # Сохраняем сессию
    session_string = client.session.save()
    
    # Добавляем в базу данных
    add_account(user_id, phone, session_string)
    
    is_admin = (user_id == ADMIN_ID)
    
    await event.respond(
        '✅ Аккаунт успешно добавлен!',
        buttons=main_keyboard(is_admin)
    )
    
    await client.disconnect()
    del user_data[user_id]

# Обработчик кнопки "Список аккаунтов"
@bot.on(events.NewMessage(pattern='📋 Список аккаунтов'))
@access_required
async def list_accounts(event):
    user_id = event.sender_id
    accounts = get_accounts(user_id)
    
    if not accounts:
        await event.respond('📭 У вас пока нет добавленных аккаунтов')
        return
    
    text = '📋 Ваши аккаунты:\n\n'
    for acc in accounts:
        text += f'📱 {acc[2]}\n'
        text += f'🆔 ID: {acc[0]}\n'
        text += f'📅 Добавлен: {acc[4]}\n\n'
    
    await event.respond(text)

# Обработчик кнопки "Переливаем воду"
@bot.on(events.NewMessage(pattern='💧 Переливаем воду'))
@access_required
async def water_menu(event):
    user_id = event.sender_id
    
    main_group = get_groups(user_id, 'main')
    water_groups = get_groups(user_id, 'water')
    
    text = '💧 Меню перелива воды\n\n'
    
    if main_group:
        text += f'🏠 Основная группа: {main_group[0][3]}\n'
    else:
        text += '🏠 Основная группа: не установлена\n'
    
    text += '\n💧 Группы с водой:\n'
    if water_groups:
        for group in water_groups:
            text += f'• {group[3]}\n'
    else:
        text += '• Не добавлено ни одной группы\n'
    
    await event.respond(
        text,
        buttons=[
            [Button.text('➕ Добавить/Изменить основную группу')],
            [Button.text('➕ Добавить группу с водой')],
            [Button.text('❌ Удалить группу с водой')],
            [Button.text('🔙 Назад в главное меню')]
        ]
    )

# Обработчик добавления основной группы
@bot.on(events.NewMessage(pattern='➕ Добавить/Изменить основную группу'))
@access_required
async def add_main_group(event):
    user_id = event.sender_id
    user_data[user_id] = {'action': 'add_main_group'}
    
    await event.respond(
        '📝 Отправьте ссылку на основную группу:',
        buttons=Button.clear()
    )

# Обработчик добавления группы с водой
@bot.on(events.NewMessage(pattern='➕ Добавить группу с водой'))
@access_required
async def add_water_group(event):
    user_id = event.sender_id
    user_data[user_id] = {'action': 'add_water_group'}
    
    await event.respond(
        '📝 Отправьте ссылку на группу с водой:',
        buttons=Button.clear()
    )

# Обработчик удаления группы с водой
@bot.on(events.NewMessage(pattern='❌ Удалить группу с водой'))
@access_required
async def delete_water_group(event):
    user_id = event.sender_id
    water_groups = get_groups(user_id, 'water')
    
    if not water_groups:
        await event.respond('❌ У вас нет добавленных групп с водой')
        return
    
    buttons = []
    for group in water_groups:
        buttons.append([Button.inline(f'❌ {group[3]}', data=f'delete_{group[0]}')])
    buttons.append([Button.text('🔙 Отмена')])
    
    await event.respond(
        'Выберите группу для удаления:',
        buttons=buttons
    )

# Обработчик инлайн кнопок удаления
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    
    if not is_allowed(user_id):
        await event.answer('⛔ У вас нет доступа к этому боту.')
        return
    
    data = event.data.decode()
    
    if data.startswith('delete_'):
        group_id = int(data.split('_')[1])
        delete_group(group_id)
        await event.answer('Группа удалена')
        await event.delete()
        
        # Обновляем меню
        await water_menu(event)

# Обработчик ввода ссылок на группы
@bot.on(events.NewMessage)
@access_required
async def handle_group_link(event):
    user_id = event.sender_id
    
    if user_id not in user_data or 'action' not in user_data[user_id]:
        return
    
    action = user_data[user_id]['action']
    link = event.raw_text.strip()
    
    # Простая проверка ссылки
    if not ('t.me/' in link or 'telegram.me/' in link):
        await event.respond('❌ Неверная ссылка на группу')
        return
    
    try:
        # Получаем информацию о группе
        if '+' in link or 'joinchat' in link:
            # Приватная группа
            group = await bot.get_entity(link)
        else:
            # Публичная группа
            username = link.split('/')[-1]
            group = await bot.get_entity(username)
        
        group_title = group.title
        group_link = link
        
        if action == 'add_main_group':
            save_group(user_id, 'main', group_link, group_title)
            await event.respond('✅ Основная группа сохранена')
        elif action == 'add_water_group':
            save_group(user_id, 'water', group_link, group_title)
            await event.respond('✅ Группа с водой сохранена')
        
        # Возвращаемся в меню
        await water_menu(event)
        
    except Exception as e:
        await event.respond(f'❌ Ошибка: {str(e)}')
    
    del user_data[user_id]

# Обработчик кнопки "Начать переливать воду"
@bot.on(events.NewMessage(pattern='🚰 Начать переливать воду'))
@access_required
async def start_pouring(event):
    await event.respond(
        '❓ Вы точно хотите начать переливать воду?',
        buttons=[
            [Button.text('✅ Да'), Button.text('❌ Нет')]
        ]
    )

# Обработчик подтверждения
@bot.on(events.NewMessage(pattern='✅ Да'))
@access_required
async def confirm_pouring(event):
    user_id = event.sender_id
    
    # Получаем группы
    main_group = get_groups(user_id, 'main')
    water_groups = get_groups(user_id, 'water')
    accounts = get_accounts(user_id)
    
    if not main_group:
        await event.respond('❌ Сначала добавьте основную группу')
        return
    
    if not water_groups:
        await event.respond('❌ Сначала добавьте группы с водой')
        return
    
    if not accounts:
        await event.respond('❌ Сначала добавьте аккаунты')
        return
    
    await event.respond('🔄 Начинаю переливать воду...', buttons=main_keyboard(user_id == ADMIN_ID))
    
    # Запускаем процесс перелива
    asyncio.create_task(pour_water(user_id, main_group[0], water_groups, accounts, event))

async def pour_water(user_id, main_group, water_groups, accounts, event):
    try:
        main_entity = await bot.get_entity(main_group[2])
    except:
        await event.respond('❌ Не удалось получить основную группу')
        return
    
    for water_group in water_groups:
        try:
            water_entity = await bot.get_entity(water_group[2])
            
            # Получаем участников из группы с водой
            participants = await bot.get_participants(water_entity)
            
            for participant in participants:
                if participant.bot or participant.deleted:
                    continue
                
                # Пробуем добавить участника из каждого аккаунта
                for account in accounts:
                    try:
                        # Создаем клиент для аккаунта
                        from telethon import TelegramClient
                        from telethon.sessions import StringSession
                        
                        client = TelegramClient(StringSession(account[3]), API_ID, API_HASH)
                        await client.connect()
                        
                        if not await client.is_user_authorized():
                            continue
                        
                        # Добавляем участника
                        try:
                            await client(InviteToChannelRequest(
                                main_entity,
                                [participant]
                            ))
                        except:
                            try:
                                await client(AddChatUserRequest(
                                    main_entity.id,
                                    participant,
                                    fwd_limit=0
                                ))
                            except:
                                pass
                        
                        await asyncio.sleep(2)  # Задержка 2 секунды
                        await client.disconnect()
                        break  # Если получилось, переходим к следующему участнику
                        
                    except FloodWaitError as e:
                        await event.respond(f'⚠️ Flood wait: {e.seconds} секунд')
                        await asyncio.sleep(e.seconds)
                    except UserPrivacyRestrictedError:
                        pass
                    except Exception as e:
                        logger.error(f"Error: {e}")
                    finally:
                        await client.disconnect()
                        
        except Exception as e:
            logger.error(f"Error with water group: {e}")
    
    await event.respond('✅ Переливание воды завершено!')

# Обработчик кнопки "Нет"
@bot.on(events.NewMessage(pattern='❌ Нет'))
@access_required
async def cancel_pouring(event):
    user_id = event.sender_id
    await event.respond('❌ Действие отменено', buttons=main_keyboard(user_id == ADMIN_ID))

# Обработчик кнопки "Назад"
@bot.on(events.NewMessage(pattern='🔙 Назад|🔙 Назад в главное меню'))
@access_required
async def back_to_main(event):
    user_id = event.sender_id
    await event.respond(
        'Главное меню:',
        buttons=main_keyboard(user_id == ADMIN_ID)
    )

# Запуск бота
async def main():
    logger.info("Бот запущен...")
    logger.info(f"Администратор ID: {ADMIN_ID}")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
