"""
ZEON Bot — Telegram игровой бот
pip install pyTelegramBotAPI
python bot.py
"""

import telebot
import sqlite3
import random
import threading
import time
import re
import json
import os
import string
from datetime import datetime, timedelta
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    LabeledPrice, ShippingAddress
)

# ═══════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═══════════════════════════════════════════════════════
BOT_TOKEN   = "СЮДА_ВАШ_ТОКЕН"    # токен от @BotFather
ADMIN_IDS   = [123456789]           # ← ваши Telegram ID
CURRENCY    = "ZEON"
C_ICON      = "💎"
BONUS_BASE  = 2500
BONUS_CD    = 24 * 3600
ROULETTE_WAIT = 20
CLAN_PRICE  = 25_000
STAT_PRICE  = 80   # галеоны

RED_NUMBERS   = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
BLACK_NUMBERS = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}

STAR_PACKAGES_DEFAULT = [
    (50,   100_000,  False),
    (100,  200_000,  False),
    (250,  525_000,  False),
    (500,  1_150_000,False),
    (1000, 2_300_000,False),
    (2500, 6_250_000,False),
    (100,  0,        True),   # VIP (True = vip пакет)
]

VIP_DAYS = 30

# ═══════════════════════════════════════════════════════
#  БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════
DB = "zeon.db"

def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as d:
        d.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT DEFAULT '',
            first_name  TEXT DEFAULT '',
            balance     INTEGER DEFAULT 0,
            galeons     INTEGER DEFAULT 0,
            last_bonus  INTEGER DEFAULT 0,
            language    TEXT DEFAULT 'ru',
            clan_id     INTEGER DEFAULT 0,
            vip_until   INTEGER DEFAULT 0,
            banned      INTEGER DEFAULT 0,
            stat_block      INTEGER DEFAULT 8,
            stat_endurance  INTEGER DEFAULT 8,
            stat_health     INTEGER DEFAULT 8,
            stat_intuition  INTEGER DEFAULT 8,
            stat_strength   INTEGER DEFAULT 8,
            stat_speed      INTEGER DEFAULT 8,
            stat_charisma   INTEGER DEFAULT 8
        );
        CREATE TABLE IF NOT EXISTS clans (
            clan_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT UNIQUE,
            owner_id  INTEGER,
            deputy_id INTEGER DEFAULT 0,
            treasury  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS transfers (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id  INTEGER, to_id INTEGER, amount INTEGER,
            ts       INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS roulette_log (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, result INTEGER,
            ts      INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS mines_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER, chat_id INTEGER,
            bet INTEGER, mines_count INTEGER,
            field TEXT, opened TEXT DEFAULT '[]',
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS promo_codes (
            code       TEXT PRIMARY KEY,
            amount     INTEGER,
            uses_left  INTEGER,
            used_by    TEXT DEFAULT '[]',
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS required_subs (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS star_packages (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            stars    INTEGER,
            zeon     INTEGER,
            is_vip   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS crash_sessions (
            session_id TEXT PRIMARY KEY,
            chat_id    INTEGER,
            bets       TEXT DEFAULT '{}',
            crashed_at REAL DEFAULT 0,
            active     INTEGER DEFAULT 1,
            started    INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS blackjack_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER, chat_id INTEGER,
            bet INTEGER, player_hand TEXT, dealer_hand TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS lottery_sessions (
            chat_id  INTEGER PRIMARY KEY,
            tickets  TEXT DEFAULT '{}',
            draw_at  INTEGER DEFAULT 0,
            active   INTEGER DEFAULT 0
        );
        """)
    # Заполнить пакеты звёзд если пусто
    with db() as d:
        if not d.execute("SELECT 1 FROM star_packages LIMIT 1").fetchone():
            for stars, zeon, vip in STAR_PACKAGES_DEFAULT:
                d.execute("INSERT INTO star_packages(stars,zeon,is_vip) VALUES(?,?,?)",
                          (stars, zeon, 1 if vip else 0))

def get_packages():
    with db() as d:
        return [dict(r) for r in d.execute("SELECT * FROM star_packages ORDER BY stars").fetchall()]

def get_user(uid, username="", first_name=""):
    with db() as d:
        r = d.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if not r:
            d.execute("INSERT INTO users(user_id,username,first_name) VALUES(?,?,?)",
                      (uid, username, first_name))
            r = d.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return dict(r)

def eu(msg):  # ensure_user из сообщения
    return get_user(msg.from_user.id,
                    msg.from_user.username or "",
                    msg.from_user.first_name or "")

def add_balance(uid, delta):
    with db() as d:
        d.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (delta, uid))

def is_vip(u):
    return int(time.time()) < u.get("vip_until", 0)

def grant_vip(uid, days=VIP_DAYS):
    now = int(time.time())
    with db() as d:
        row = d.execute("SELECT vip_until FROM users WHERE user_id=?", (uid,)).fetchone()
        current = row["vip_until"] if row and row["vip_until"] > now else now
        new_until = current + days * 86400
        d.execute("UPDATE users SET vip_until=? WHERE user_id=?", (new_until, uid))

def fmt(n): return f"{int(n):,}".replace(",", " ")

def is_group(msg): return msg.chat.type in ("group", "supergroup")

def number_color(n):
    if n == 0: return "🟢"
    return "🔴" if n in RED_NUMBERS else "⚫"

# ═══════════════════════════════════════════════════════
#  ПРОВЕРКА ПОДПИСОК
# ═══════════════════════════════════════════════════════
def check_subs(bot_inst, user_id):
    """Возвращает список каналов, на которые не подписан пользователь"""
    with db() as d:
        channels = [r["channel"] for r in d.execute("SELECT channel FROM required_subs").fetchall()]
    not_subbed = []
    for ch in channels:
        try:
            member = bot_inst.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                not_subbed.append(ch)
        except Exception:
            pass
    return not_subbed

def subs_keyboard(channels):
    kb = InlineKeyboardMarkup()
    for ch in channels:
        kb.row(InlineKeyboardButton(f"Подписаться {ch}", url=f"https://t.me/{ch.lstrip('@')}"))
    kb.row(InlineKeyboardButton("✅ Я подписался", callback_data="check_subs"))
    return kb

# ═══════════════════════════════════════════════════════
#  РУЛЕТКА
# ═══════════════════════════════════════════════════════
roulette_sessions = {}
rl = threading.Lock()

class Bet:
    def __init__(self, uid, uname, amount, btype):
        self.uid, self.uname, self.amount, self.btype = uid, uname, amount, btype

def parse_bet(text):
    text = text.strip()
    m = re.match(r'^(\d+)\s+(.+)$', text, re.IGNORECASE)
    if not m: return None
    amount = int(m.group(1))
    bt = m.group(2).strip().lower()
    if amount <= 0: return None
    if bt in ("ч","чёрное","черное","black"): return amount,"black",bt
    if bt in ("к","красное","red"):           return amount,"red",bt
    if bt in ("0","зеро","zero"):             return amount,"zero",bt
    if bt in ("чет","чётное","even"):         return amount,"even",bt
    if bt in ("нечет","нечётное","odd"):      return amount,"odd",bt
    r2 = re.match(r'^(\d+)-(\d+)$', bt)
    if r2:
        lo,hi = int(r2.group(1)),int(r2.group(2))
        if 0<=lo<=36 and 0<=hi<=36 and lo<hi:
            return amount,(lo,hi),f"{lo}-{hi}"
    if re.match(r'^\d+$',bt):
        n=int(bt)
        if 0<=n<=36: return amount,n,bt
    return None

def bet_label(bt):
    if bt=="red":   return "🔴 Красное"
    if bt=="black": return "⚫ Черное"
    if bt=="zero":  return "🟢 Зеро"
    if bt=="even":  return "Чётное"
    if bt=="odd":   return "Нечётное"
    if isinstance(bt,int): return f"Число {bt}"
    if isinstance(bt,tuple): return f"{bt[0]}-{bt[1]}"
    return str(bt)

def calc_payout(bt, result):
    color = "red" if result in RED_NUMBERS else ("black" if result in BLACK_NUMBERS else "zero")
    if bt=="red":   return 2 if color=="red" else 0
    if bt=="black": return 2 if color=="black" else 0
    if bt=="zero":  return 36 if result==0 else 0
    if bt=="even":  return 2 if result!=0 and result%2==0 else 0
    if bt=="odd":   return 2 if result!=0 and result%2==1 else 0
    if isinstance(bt,int): return 36 if result==bt else 0
    if isinstance(bt,tuple):
        lo,hi=bt; cnt=hi-lo+1
        return max(2,36//cnt) if lo<=result<=hi else 0
    return 0

def spin_roulette(chat_id):
    with rl:
        session = roulette_sessions.get(chat_id)
        if not session or not session["bets"]:
            roulette_sessions.pop(chat_id,None); return
        bets = session["bets"][:]
        last = {b.uid:b for b in bets}
        session["last_bets"] = last
        session["bets"] = []
        session["timer"] = None

    result = random.randint(0,36)
    with db() as d:
        d.execute("INSERT INTO roulette_log(chat_id,result) VALUES(?,?)", (chat_id,result))

    lines=[f"🎰 Рулетка: {result}{number_color(result)}\n"]
    for b in bets:
        mult = calc_payout(b.btype, result)
        if mult>0:
            won=b.amount*mult; net=won-b.amount
            add_balance(b.uid, net)
            lines.append(f"@{b.uname} ставка {fmt(b.amount)} выиграл {fmt(won)} на {bet_label(b.btype)}")
        else:
            lines.append(f"@{b.uname} ставка {fmt(b.amount)} — проигрыш на {bet_label(b.btype)}")

    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🔁 Повторить", callback_data=f"repeat_{chat_id}"),
        InlineKeyboardButton("×2 Удвоить",   callback_data=f"double_{chat_id}")
    )
    bot.send_message(chat_id, "\n".join(lines), reply_markup=kb)

def start_rl_timer(chat_id):
    def run():
        time.sleep(ROULETTE_WAIT)
        with rl:
            s = roulette_sessions.get(chat_id)
            if not s or s.get("cancelled"): return
        spin_roulette(chat_id)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t

# ═══════════════════════════════════════════════════════
#  КРАШ / АВИАТОР
# ═══════════════════════════════════════════════════════
crash_sessions = {}  # chat_id → {bets:{uid:(uname,amount)}, timer, active}
crash_lock = threading.Lock()

def generate_crash_mult():
    """
    Генерирует точку краша от 1.00 до 10.00x.
    Распределение:
      1.00–1.49x : ~38% (очень часто)
      1.50–1.99x : ~24% (часто)
      2.00–2.99x : ~18% (умеренно)
      3.00–4.99x : ~12% (редко)
      5.00–7.49x : ~5%  (очень редко)
      7.50–10.00x: ~3%  (крайне редко)
    House edge ~8% для баланса экономики.
    """
    r = random.random()
    if r < 0.38:   return round(random.uniform(1.00, 1.49), 2)
    elif r < 0.62: return round(random.uniform(1.50, 1.99), 2)
    elif r < 0.80: return round(random.uniform(2.00, 2.99), 2)
    elif r < 0.92: return round(random.uniform(3.00, 4.99), 2)
    elif r < 0.97: return round(random.uniform(5.00, 7.49), 2)
    else:          return round(random.uniform(7.50, 10.00), 2)

# ═══════════════════════════════════════════════════════
#  БЛЭКДЖЕК
# ═══════════════════════════════════════════════════════
CARDS = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
SUITS = ['♠','♥','♦','♣']

def new_deck():
    deck = [f"{v}{s}" for v in CARDS for s in SUITS]
    random.shuffle(deck)
    return deck

def card_value(card):
    v = card[:-1]
    if v in ('J','Q','K'): return 10
    if v == 'A': return 11
    return int(v)

def hand_value(hand):
    total = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[:-1]=='A')
    while total > 21 and aces:
        total -= 10; aces -= 1
    return total

def bj_kb(session_id):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("➕ Ещё", callback_data=f"bj_hit_{session_id}"),
        InlineKeyboardButton("✋ Стоп", callback_data=f"bj_stand_{session_id}"),
        InlineKeyboardButton("×2 Двойник", callback_data=f"bj_double_{session_id}")
    )
    return kb

def bj_text(ph, dh, show_dealer=False):
    pv = hand_value(ph)
    dv = hand_value(dh) if show_dealer else card_value(dh[0])
    dealer_str = f"{' '.join(dh)} ({hand_value(dh)})" if show_dealer else f"{dh[0]} [?]"
    return (f"🃏 Блэкджек\n\n"
            f"Дилер: {dealer_str}\n"
            f"Вы: {' '.join(ph)} ({pv})")

# ═══════════════════════════════════════════════════════
#  СКАЧКИ
# ═══════════════════════════════════════════════════════
HORSES = ["🐴","🏇","🦄","🐎","🎠"]
HORSE_NAMES = ["Буря","Ветер","Гром","Молния","Звёзда"]

# ═══════════════════════════════════════════════════════
#  ЛОТЕРЕЯ
# ═══════════════════════════════════════════════════════
lottery_timers = {}

def start_lottery(chat_id, bot_inst):
    draw_time = int(time.time()) + 300  # 5 минут
    with db() as d:
        d.execute("""INSERT OR REPLACE INTO lottery_sessions(chat_id,tickets,draw_at,active)
                     VALUES(?,?,?,1)""", (chat_id, '{}', draw_time))

    def run():
        time.sleep(300)
        draw_lottery(chat_id, bot_inst)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    lottery_timers[chat_id] = t
    return draw_time

def draw_lottery(chat_id, bot_inst):
    with db() as d:
        row = d.execute("SELECT * FROM lottery_sessions WHERE chat_id=?", (chat_id,)).fetchone()
        if not row or not row["active"]: return
        tickets = json.loads(row["tickets"])
        d.execute("UPDATE lottery_sessions SET active=0 WHERE chat_id=?", (chat_id,))

    if not tickets:
        bot_inst.send_message(chat_id, "🎟 Лотерея завершена без участников.")
        return

    # Победитель
    all_tickets = []
    for uid, cnt in tickets.items():
        all_tickets.extend([uid]*int(cnt))
    winner_uid = int(random.choice(all_tickets))

    jackpot = sum(tickets.values()) * 100
    add_balance(winner_uid, jackpot)

    with db() as d:
        u = d.execute("SELECT username,first_name FROM users WHERE user_id=?", (winner_uid,)).fetchone()
    name = f"@{u['username']}" if u and u["username"] else str(winner_uid)
    bot_inst.send_message(chat_id,
        f"🎟 Лотерея завершена!\n🏆 Победитель: {name}\n💰 Джекпот: {fmt(jackpot)} {CURRENCY}!"
    )

# ═══════════════════════════════════════════════════════
#  МИНЫ
# ═══════════════════════════════════════════════════════
def mines_kb(sid, field_size, opened, mines_set, revealed=False):
    kb = InlineKeyboardMarkup()
    row = []
    for i in range(field_size):
        if i in opened:
            btn = InlineKeyboardButton("💎", callback_data="noop")
        elif revealed and i in mines_set:
            btn = InlineKeyboardButton("💣", callback_data="noop")
        elif revealed:
            btn = InlineKeyboardButton("·", callback_data="noop")
        else:
            btn = InlineKeyboardButton("❓", callback_data=f"mx_{sid}_{i}")
        row.append(btn)
        if len(row)==5: kb.row(*row); row=[]
    if row: kb.row(*row)
    if not revealed:
        kb.row(InlineKeyboardButton("💰 Забрать", callback_data=f"mc_{sid}"))
    return kb

def create_mines(size=25, count=5):
    pos = list(range(size)); random.shuffle(pos)
    return set(pos[:count])

# ═══════════════════════════════════════════════════════
#  ADMIN STATE MACHINE
# ═══════════════════════════════════════════════════════
admin_states = {}  # uid → {"state":..., "data":{}}

def set_admin_state(uid, state, **data):
    admin_states[uid] = {"state": state, "data": data}

def get_admin_state(uid):
    return admin_states.get(uid, None)

def clear_admin_state(uid):
    admin_states.pop(uid, None)

# ═══════════════════════════════════════════════════════
#  ИНИЦИАЛИЗАЦИЯ БОТА
# ═══════════════════════════════════════════════════════
init_db()
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# ═══════════════════════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════════════════
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("👤 Профиль"), KeyboardButton("🔮 Хогвартс"))
    kb.row(KeyboardButton("📋 Команды"), KeyboardButton("🛒 Донат"))
    kb.row(KeyboardButton("🏆 Турниры"))
    kb.row(KeyboardButton("💬 Чаты"), KeyboardButton("🏰 Кланы"))
    kb.row(KeyboardButton("🎮 Игры"), KeyboardButton("🎁 Бонус"))
    kb.row(KeyboardButton("📜 Политика"), KeyboardButton("🌐 Язык"))
    return kb

def group_only(msg):
    if not is_group(msg):
        bot.reply_to(msg, "🎮 Эта игра доступна только в групповом чате!")
        return False
    return True

def not_banned(msg):
    u = eu(msg)
    if u.get("banned"):
        bot.reply_to(msg, "🚫 Вы заблокированы.")
        return False
    return True

def check_sub_gate(msg):
    """Возвращает False и отправляет сообщение если нет подписок"""
    missing = check_subs(bot, msg.from_user.id)
    if missing:
        bot.reply_to(msg,
            "⚠️ Для игры необходимо подписаться на каналы:",
            reply_markup=subs_keyboard(missing))
        return False
    return True

# ═══════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    u = eu(msg)
    now = int(time.time())
    diff = now - u["last_bonus"]
    if diff >= BONUS_CD:
        mult = 3 if is_vip(u) else 1
        bonus = BONUS_BASE * mult
        add_balance(u["user_id"], bonus)
        with db() as d:
            d.execute("UPDATE users SET last_bonus=? WHERE user_id=?", (now, u["user_id"]))
        vip_tag = " (VIP ×3)" if mult==3 else ""
        text = (f"👋 Добро пожаловать! {CURRENCY} — игровой бот.\n\n"
                f"Вам начислено: {fmt(bonus)} {CURRENCY}{vip_tag}\n"
                f"Следующий бонус через 24:00")
    else:
        rem = BONUS_CD - diff
        h,m = rem//3600,(rem%3600)//60
        text = (f"👋 Добро пожаловать в {CURRENCY}!\n\n"
                f"До следующего бонуса: {h:02d}:{m:02d}")
    bot.send_message(msg.chat.id, text, reply_markup=main_menu())

# ═══════════════════════════════════════════════════════
#  БОНУС
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip()=="🎁 Бонус")
def btn_bonus(msg):
    u = eu(msg)
    now = int(time.time())
    diff = now - u["last_bonus"]
    if diff >= BONUS_CD:
        mult = 3 if is_vip(u) else 1
        bonus = BONUS_BASE * mult
        add_balance(u["user_id"], bonus)
        with db() as d:
            d.execute("UPDATE users SET last_bonus=? WHERE user_id=?", (now, u["user_id"]))
        vip_tag = " (VIP ×3!) 👑" if mult==3 else ""
        bot.send_message(msg.chat.id,
            f"🎁 Вам начислено: {fmt(bonus)} {CURRENCY}{vip_tag}\n"
            f"Следующий бонус через 24:00")
    else:
        rem = BONUS_CD - diff
        h,m = rem//3600,(rem%3600)//60
        bot.send_message(msg.chat.id, f"⏳ Следующий бонус через {h:02d}:{m:02d}")

# ═══════════════════════════════════════════════════════
#  ПРОФИЛЬ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip() in ("👤 Профиль","/профиль","б","баланс"))
def btn_profile(msg):
    u = eu(msg)
    if msg.text.strip() in ("б","баланс"):
        bot.reply_to(msg, f"💰 Баланс: {fmt(u['balance'])} {CURRENCY}")
        return
    clan_name = "—"
    if u["clan_id"]:
        with db() as d:
            row = d.execute("SELECT name FROM clans WHERE clan_id=?", (u["clan_id"],)).fetchone()
            if row: clan_name = row["name"]
    vip_str = ""
    if is_vip(u):
        exp = datetime.fromtimestamp(u["vip_until"]).strftime("%d.%m.%Y")
        vip_str = f"\n👑 VIP до {exp}"
    stats_sum = sum(u[k] for k in ("stat_block","stat_endurance","stat_health",
                                    "stat_intuition","stat_strength","stat_speed","stat_charisma"))
    text = (f"🆔 {u['user_id']}\n"
            f"{C_ICON} Баланс: {fmt(u['balance'])} {CURRENCY}\n"
            f"🌕 {u['galeons']} галеонов\n"
            f"⚔️ Характеристики: {stats_sum}\n"
            f"🏰 Клан: {clan_name}{vip_str}")
    bot.send_message(msg.chat.id, text)

# ═══════════════════════════════════════════════════════
#  ХОГВАРТС
# ═══════════════════════════════════════════════════════
STATS = {"Блок":"stat_block","Выносливость":"stat_endurance","Здоровье":"stat_health",
         "Интуиция":"stat_intuition","Сила":"stat_strength","Скорость":"stat_speed","Харизма":"stat_charisma"}

@bot.message_handler(func=lambda m: m.text and m.text.strip()=="🔮 Хогвартс")
def btn_hogwarts(msg):
    u = eu(msg)
    lines = ["Твои характеристики\n"] + [f"{n}: {u[k]}" for n,k in STATS.items()]
    lines += [f"\nПрокачка за {STAT_PRICE} 🌕 каждая\nБаланс: {u['galeons']} 🌕"]
    kb = InlineKeyboardMarkup()
    for name, key in STATS.items():
        kb.row(
            InlineKeyboardButton(name, callback_data="noop"),
            InlineKeyboardButton(str(u[key]), callback_data="noop"),
            InlineKeyboardButton(f"+1 за {STAT_PRICE}🌕", callback_data=f"upg_{key}")
        )
    bot.send_message(msg.chat.id, "\n".join(lines), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("upg_"))
def cb_upgrade(call):
    key = call.data[4:]
    u = get_user(call.from_user.id)
    if u["galeons"] < STAT_PRICE:
        bot.answer_callback_query(call.id, f"Нужно {STAT_PRICE} галеонов!"); return
    with db() as d:
        d.execute(f"UPDATE users SET {key}={key}+1, galeons=galeons-{STAT_PRICE} WHERE user_id=?", (u["user_id"],))
    bot.answer_callback_query(call.id, "✅ Прокачано!")

# ═══════════════════════════════════════════════════════
#  КОМАНДЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip()=="📋 Команды")
def btn_commands(msg):
    text = (
        f"📋 Команды {CURRENCY}\n\n"
        f"б / баланс — баланс\n"
        f"н [сумма] — перевод (ответ на сообщение)\n"
        f"н [id] [сумма] — перевод по ID\n"
        f"/профиль — профиль\n"
        f"/история — история переводов\n"
        f"/дуэль — дуэль (ответ на сообщение)\n"
        f"/top [n] — топ игроков\n"
        f"промо [КОД] — активировать промокод\n\n"
        f"🎮 Игры (только в чате):\n"
        f"[сумма] ч/к/число/диапазон — рулетка\n"
        f"го — запустить рулетку\n"
        f"ставки — текущие ставки\n"
        f"лог — история рулетки\n\n"
        f"краш [ставка] [автостоп] — авиатор (пример: краш 500 2.5)\n\n"
        f"бж [сумма] — блэкджек\n\n"
        f"скачки [сумма] [1-5] — скачки\n\n"
        f"мины [сумма] [мин] — минное поле\n\n"
        f"монетка [сумма] орёл/решка — монетка\n\n"
        f"кости [сумма] [1-6] — кости\n\n"
        f"джокер [сумма] — джокер\n\n"
        f"лото [сумма] — лотерея\n\n"
        f"🏰 казна / казна [сумма] — казна клана"
    )
    bot.send_message(msg.chat.id, text)

# ═══════════════════════════════════════════════════════
#  ДОНАТ / ПОКУПКА ЗВЁЗДАМИ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip()=="🛒 Донат")
def btn_donate(msg):
    packages = get_packages()
    kb = InlineKeyboardMarkup()
    for p in packages:
        if p["is_vip"]:
            label = f"⭐ {p['stars']} — 👑 VIP на {VIP_DAYS} дней"
        else:
            label = f"⭐ {p['stars']} — {fmt(p['zeon'])} {CURRENCY}"
        kb.row(InlineKeyboardButton(label, callback_data=f"buy_{p['id']}"))
    bot.send_message(msg.chat.id,
        f"🛒 Пополнение {CURRENCY} за звёзды Telegram ⭐\n\n"
        f"VIP даёт: ×3 ежедневный бонус на {VIP_DAYS} дней!",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def cb_buy(call):
    pkg_id = int(call.data[4:])
    with db() as d:
        p = d.execute("SELECT * FROM star_packages WHERE id=?", (pkg_id,)).fetchone()
    if not p:
        bot.answer_callback_query(call.id, "Пакет не найден."); return

    if p["is_vip"]:
        title = f"👑 VIP на {VIP_DAYS} дней"
        desc  = f"VIP статус: ×3 ежедневный бонус в течение {VIP_DAYS} дней"
    else:
        title = f"{fmt(p['zeon'])} {CURRENCY}"
        desc  = f"Пополнение баланса на {fmt(p['zeon'])} {CURRENCY}"

    bot.answer_callback_query(call.id)
    try:
        bot.send_invoice(
            chat_id=call.from_user.id,
            title=title,
            description=desc,
            payload=f"pkg_{pkg_id}_{call.from_user.id}",
            provider_token="",  # Telegram Stars не требует токена
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=p["stars"])]
        )
    except Exception as e:
        bot.send_message(call.message.chat.id,
            f"⚠️ Для покупки напишите боту в личку: @{bot.get_me().username}\n"
            f"Или используйте /start в личном чате.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=["successful_payment"])
def successful_payment(msg):
    payload = msg.successful_payment.invoice_payload
    parts = payload.split("_")
    pkg_id = int(parts[1])
    uid = msg.from_user.id

    with db() as d:
        p = d.execute("SELECT * FROM star_packages WHERE id=?", (pkg_id,)).fetchone()
    if not p:
        bot.send_message(msg.chat.id, "Ошибка: пакет не найден. Обратитесь к администратору.")
        return

    if p["is_vip"]:
        grant_vip(uid, VIP_DAYS)
        bot.send_message(msg.chat.id,
            f"👑 VIP активирован на {VIP_DAYS} дней!\n"
            f"Ваш ежедневный бонус увеличен в 3 раза!")
    else:
        add_balance(uid, p["zeon"])
        bot.send_message(msg.chat.id,
            f"✅ Успешная покупка!\n"
            f"Зачислено: {fmt(p['zeon'])} {CURRENCY} {C_ICON}")

# ═══════════════════════════════════════════════════════
#  TOP
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=["top"])
def cmd_top(msg):
    parts = msg.text.split()
    limit = min(int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 10, 50)
    with db() as d:
        rows = d.execute(
            "SELECT user_id,username,first_name,balance FROM users WHERE banned=0 ORDER BY balance DESC LIMIT ?",
            (limit,)
        ).fetchall()
    lines = [f"🏆 Топ {limit} игроков\n"]
    for i,r in enumerate(rows,1):
        name = f"@{r['username']}" if r["username"] else r["first_name"] or str(r["user_id"])
        lines.append(f"{i}. {name} — {C_ICON} {fmt(r['balance'])}")
    bot.send_message(msg.chat.id, "\n".join(lines))

# ═══════════════════════════════════════════════════════
#  ПЕРЕВОДЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^н\s+\d+$', m.text.strip(), re.I))
def cmd_transfer_reply(msg):
    if not msg.reply_to_message:
        bot.reply_to(msg, "Ответьте на сообщение получателя."); return
    target = msg.reply_to_message.from_user
    if target.id == msg.from_user.id:
        bot.reply_to(msg, "Нельзя переводить себе."); return
    amount = int(msg.text.strip().split()[1])
    u = eu(msg)
    if u["balance"] < amount:
        bot.reply_to(msg, f"Недостаточно {CURRENCY}."); return
    get_user(target.id, target.username or "", target.first_name or "")
    with db() as d:
        d.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, msg.from_user.id))
        d.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, target.id))
        d.execute("INSERT INTO transfers(from_id,to_id,amount) VALUES(?,?,?)",
                  (msg.from_user.id, target.id, amount))
    tname = f"@{target.username}" if target.username else target.first_name
    bot.reply_to(msg, f"✅ Переведено {fmt(amount)} {CURRENCY} → {tname}")

@bot.message_handler(func=lambda m: m.text and re.match(r'^н\s+\d+\s+\d+$', m.text.strip(), re.I))
def cmd_transfer_id(msg):
    parts = msg.text.strip().split()
    tid, amount = int(parts[1]), int(parts[2])
    u = eu(msg)
    if u["balance"] < amount:
        bot.reply_to(msg, f"Недостаточно {CURRENCY}."); return
    with db() as d:
        target = d.execute("SELECT * FROM users WHERE user_id=?", (tid,)).fetchone()
    if not target:
        bot.reply_to(msg, "Пользователь не найден."); return
    with db() as d:
        d.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, msg.from_user.id))
        d.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, tid))
        d.execute("INSERT INTO transfers(from_id,to_id,amount) VALUES(?,?,?)",
                  (msg.from_user.id, tid, amount))
    tname = f"@{target['username']}" if target["username"] else str(tid)
    bot.reply_to(msg, f"✅ Переведено {fmt(amount)} {CURRENCY} → {tname}")

@bot.message_handler(commands=["история"])
def cmd_history(msg):
    uid = msg.from_user.id
    with db() as d:
        rows = d.execute(
            "SELECT * FROM transfers WHERE from_id=? OR to_id=? ORDER BY ts DESC LIMIT 10",
            (uid, uid)
        ).fetchall()
    if not rows:
        bot.reply_to(msg, "История пуста."); return
    lines = ["📜 Последние переводы:\n"]
    for r in rows:
        direction = "→ отправлено" if r["from_id"]==uid else "← получено"
        other = r["to_id"] if r["from_id"]==uid else r["from_id"]
        ts = datetime.fromtimestamp(r["ts"]).strftime("%d.%m %H:%M")
        lines.append(f"{ts} {direction} {fmt(r['amount'])} {CURRENCY} (ID {other})")
    bot.send_message(msg.chat.id, "\n".join(lines))

# ═══════════════════════════════════════════════════════
#  ДУЭЛЬ
# ═══════════════════════════════════════════════════════
duels = {}

@bot.message_handler(commands=["дуэль"])
def cmd_duel(msg):
    if not group_only(msg) or not check_sub_gate(msg): return
    if not msg.reply_to_message:
        bot.reply_to(msg, "Ответьте на сообщение соперника."); return
    target = msg.reply_to_message.from_user
    if target.id == msg.from_user.id:
        bot.reply_to(msg, "Нельзя вызвать себя!"); return
    uc = eu(msg)
    parts = msg.text.split()
    amount = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 100
    if uc["balance"] < amount:
        bot.reply_to(msg, f"Нужно {fmt(amount)} {CURRENCY}."); return
    cname = f"@{msg.from_user.username}" if msg.from_user.username else msg.from_user.first_name
    tname = f"@{target.username}" if target.username else target.first_name
    duels[msg.chat.id] = {"challenger":msg.from_user.id,"target":target.id,
                           "amount":amount,"cname":cname,"tname":tname}
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅ Принять", callback_data=f"da_{msg.chat.id}"),
           InlineKeyboardButton("❌ Отказать", callback_data=f"dd_{msg.chat.id}"))
    bot.send_message(msg.chat.id,
        f"⚔️ {cname} вызывает {tname} на дуэль!\nСтавка: {fmt(amount)} {CURRENCY}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("da_") or c.data.startswith("dd_"))
def cb_duel(call):
    action = call.data[:2]
    cid = int(call.data[3:])
    duel = duels.get(cid)
    if not duel:
        bot.answer_callback_query(call.id, "Дуэль не найдена."); return
    if call.from_user.id != duel["target"]:
        bot.answer_callback_query(call.id, "Не ваша дуэль!"); return
    if action=="dd":
        duels.pop(cid,None)
        bot.edit_message_text("❌ Дуэль отклонена.", cid, call.message.message_id); return
    uc = get_user(duel["challenger"]); ut = get_user(duel["target"])
    amount = duel["amount"]
    if uc["balance"]<amount or ut["balance"]<amount:
        bot.answer_callback_query(call.id, "Не хватает монет!"); return
    cp = uc["stat_strength"]+uc["stat_speed"]+uc["stat_intuition"]
    tp = ut["stat_strength"]+ut["stat_speed"]+ut["stat_intuition"]
    winner = duel["challenger"] if random.randint(1,cp+tp)<=cp else duel["target"]
    loser  = duel["target"] if winner==duel["challenger"] else duel["challenger"]
    wname  = duel["cname"] if winner==duel["challenger"] else duel["tname"]
    with db() as d:
        d.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount,loser))
        d.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount,winner))
    duels.pop(cid,None)
    bot.edit_message_text(
        f"⚔️ Дуэль!\n🏆 Победитель: {wname}\n💰 +{fmt(amount)} {CURRENCY}", cid, call.message.message_id)

# ═══════════════════════════════════════════════════════
#  ПРОМОКОДЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^промо\s+\S+$', m.text.strip(), re.I))
def cmd_promo(msg):
    code = msg.text.strip().split()[1].upper()
    uid = msg.from_user.id
    with db() as d:
        row = d.execute("SELECT * FROM promo_codes WHERE code=?", (code,)).fetchone()
    if not row:
        bot.reply_to(msg, "❌ Промокод не найден."); return
    used_by = json.loads(row["used_by"])
    if uid in used_by:
        bot.reply_to(msg, "❌ Вы уже использовали этот промокод."); return
    if row["uses_left"] <= 0:
        bot.reply_to(msg, "❌ Промокод исчерпан."); return
    used_by.append(uid)
    with db() as d:
        d.execute("UPDATE promo_codes SET uses_left=uses_left-1, used_by=? WHERE code=?",
                  (json.dumps(used_by), code))
    add_balance(uid, row["amount"])
    bot.reply_to(msg, f"✅ Промокод активирован! +{fmt(row['amount'])} {CURRENCY}")

# ═══════════════════════════════════════════════════════
#  КЛАНЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip()=="🏰 Кланы")
def btn_clans(msg):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🆕 Создать клан", callback_data="clan_create"))
    kb.row(InlineKeyboardButton("🔍 Поиск клана", callback_data="clan_search"))
    kb.row(InlineKeyboardButton("📜 Список кланов", callback_data="clan_list_0"))
    kb.row(InlineKeyboardButton("🏆 Топ кланов", callback_data="clan_top"))
    bot.send_message(msg.chat.id, "🏰 Кланы", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data=="clan_create")
def cb_clan_create(call):
    u = get_user(call.from_user.id)
    if u["clan_id"]:
        bot.answer_callback_query(call.id,"Вы уже в клане!"); return
    if u["balance"]<CLAN_PRICE:
        bot.answer_callback_query(call.id,f"Нужно {fmt(CLAN_PRICE)} {CURRENCY}"); return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"Введите название нового клана:")
    bot.register_next_step_handler(call.message, step_clan_name, call.from_user.id)

def step_clan_name(msg, cid):
    name=msg.text.strip()
    if not 3<=len(name)<=30:
        bot.send_message(msg.chat.id,"Название 3–30 символов."); return
    with db() as d:
        if d.execute("SELECT 1 FROM clans WHERE name=?", (name,)).fetchone():
            bot.send_message(msg.chat.id,"Клан с таким именем уже есть."); return
        d.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (CLAN_PRICE,cid))
        d.execute("INSERT INTO clans(name,owner_id) VALUES(?,?)", (name,cid))
        clan=d.execute("SELECT clan_id FROM clans WHERE name=?",(name,)).fetchone()
        d.execute("UPDATE users SET clan_id=? WHERE user_id=?", (clan["clan_id"],cid))
    bot.send_message(msg.chat.id,f"✅ Клан «{name}» создан!")

@bot.callback_query_handler(func=lambda c: c.data=="clan_top")
def cb_clan_top(call):
    with db() as d:
        rows=d.execute(
            "SELECT c.name,c.treasury,(SELECT COUNT(*) FROM users u WHERE u.clan_id=c.clan_id) m "
            "FROM clans c ORDER BY treasury DESC LIMIT 10"
        ).fetchall()
    lines=["🏆 Топ кланов\n"]
    for i,r in enumerate(rows,1):
        lines.append(f"{i}. {r['name']} | 👥{r['m']} | {C_ICON}{fmt(r['treasury'])}")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"\n".join(lines))

@bot.callback_query_handler(func=lambda c: c.data.startswith("clan_list_"))
def cb_clan_list(call):
    page=int(call.data.split("_")[2]); per=6
    with db() as d:
        total=d.execute("SELECT COUNT(*) c FROM clans").fetchone()["c"]
        rows=d.execute(
            "SELECT c.clan_id,c.name,c.treasury,(SELECT COUNT(*) FROM users u WHERE u.clan_id=c.clan_id) m "
            "FROM clans c ORDER BY clan_id LIMIT ? OFFSET ?", (per,page*per)
        ).fetchall()
    kb=InlineKeyboardMarkup()
    for r in rows:
        kb.row(InlineKeyboardButton(
            f"{r['name']} | {fmt(r['treasury'])} | {r['m']}👥",
            callback_data=f"clan_join_{r['clan_id']}"))
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("◀",callback_data=f"clan_list_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{max(1,(total//per)+1)}",callback_data="noop"))
    if (page+1)*per<total: nav.append(InlineKeyboardButton("▶",callback_data=f"clan_list_{page+1}"))
    if nav: kb.row(*nav)
    bot.answer_callback_query(call.id)
    try: bot.edit_message_reply_markup(call.message.chat.id,call.message.message_id,reply_markup=kb)
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("clan_join_"))
def cb_clan_join(call):
    cid=int(call.data.split("_")[2])
    with db() as d:
        clan=d.execute("SELECT * FROM clans WHERE clan_id=?",(cid,)).fetchone()
    if not clan:
        bot.answer_callback_query(call.id,"Клан не найден."); return
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✅ Вступить",callback_data=f"cc_{cid}"),
           InlineKeyboardButton("❌ Отмена",callback_data="noop"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
        f"🏰 {clan['name']}\n{C_ICON} Казна: {fmt(clan['treasury'])}\n\nВступить?",reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cc_"))
def cb_clan_confirm(call):
    cid=int(call.data[3:])
    with db() as d:
        d.execute("UPDATE users SET clan_id=? WHERE user_id=?",(cid,call.from_user.id))
    bot.answer_callback_query(call.id,"✅ Вступили!")
    bot.edit_message_text("✅ Вы в клане!",call.message.chat.id,call.message.message_id)

@bot.message_handler(func=lambda m: m.text and re.match(r'^казна(\s+\d+)?$',m.text.strip(),re.I))
def cmd_treasury(msg):
    u=eu(msg)
    if not u["clan_id"]:
        bot.reply_to(msg,"Вы не в клане."); return
    parts=msg.text.strip().split()
    if len(parts)==1:
        with db() as d:
            clan=d.execute("SELECT * FROM clans WHERE clan_id=?",(u["clan_id"],)).fetchone()
        bot.reply_to(msg,f"🏰 {clan['name']}\n{C_ICON} Казна: {fmt(clan['treasury'])} {CURRENCY}")
    else:
        amount=int(parts[1])
        if u["balance"]<amount:
            bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
        with db() as d:
            d.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(amount,u["user_id"]))
            d.execute("UPDATE clans SET treasury=treasury+? WHERE clan_id=?",(amount,u["clan_id"]))
        bot.reply_to(msg,f"✅ Пополнено казны клана: +{fmt(amount)} {CURRENCY}")

# ═══════════════════════════════════════════════════════
#  ЛОГ / СТАВКИ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() in ("лог","log"))
def cmd_log(msg):
    with db() as d:
        rows=d.execute("SELECT result FROM roulette_log WHERE chat_id=? ORDER BY ts DESC LIMIT 10",
                       (msg.chat.id,)).fetchall()
    if not rows:
        bot.reply_to(msg,"История пуста."); return
    bot.reply_to(msg,"\n".join(f"{r['result']}{number_color(r['result'])}" for r in rows))

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower()=="ставки" and is_group(m))
def cmd_bets(msg):
    s=roulette_sessions.get(msg.chat.id)
    if not s or not s.get("bets"):
        bot.reply_to(msg,"Нет активных ставок."); return
    lines=["📋 Текущие ставки:\n"]
    for b in s["bets"]:
        lines.append(f"@{b.uname} — {fmt(b.amount)} на {bet_label(b.btype)}")
    bot.reply_to(msg,"\n".join(lines))

# ═══════════════════════════════════════════════════════
#  ГО — запуск рулетки
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip().lower()=="го" and is_group(m))
def cmd_go(msg):
    with rl:
        s=roulette_sessions.get(msg.chat.id)
        if not s or not s.get("bets"):
            bot.reply_to(msg,"Нет ставок для запуска."); return
        s["cancelled"]=True
    spin_roulette(msg.chat.id)

# ═══════════════════════════════════════════════════════
#  ПОВТОРИТЬ / УДВОИТЬ
# ═══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data.startswith("repeat_") or c.data.startswith("double_"))
def cb_repeat(call):
    action=call.data.split("_")[0]; cid=int(call.data.split("_")[1])
    with rl:
        s=roulette_sessions.get(cid)
        last=s.get("last_bets",{}) if s else {}
    lb=last.get(call.from_user.id)
    if not lb:
        bot.answer_callback_query(call.id,"Нет ставки для повтора."); return
    amount=lb.amount*2 if action=="double" else lb.amount
    u=get_user(call.from_user.id)
    if u["balance"]<amount:
        bot.answer_callback_query(call.id,f"Недостаточно {CURRENCY}!"); return
    add_balance(call.from_user.id,-amount)
    uname=call.from_user.username or call.from_user.first_name or str(call.from_user.id)
    bet=Bet(call.from_user.id,uname,amount,lb.btype)
    with rl:
        if cid not in roulette_sessions:
            roulette_sessions[cid]={"bets":[],"timer":None,"last_bets":{},"cancelled":False}
        s=roulette_sessions[cid]; s["bets"].append(bet)
        is_first=s["timer"] is None
        if is_first:
            s["cancelled"]=False; s["timer"]=start_rl_timer(cid)
    bot.answer_callback_query(call.id,"✅ Ставка принята!")
    if is_first:
        bot.send_message(cid,
            f"🎰 @{uname} {fmt(amount)} на {bet_label(lb.btype)}\n"
            f"⏳ {ROULETTE_WAIT} сек. Пишите «го» для старта.")

# ═══════════════════════════════════════════════════════
#  СТАВКИ РУЛЕТКИ В ЧАТЕ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: is_group(m) and m.text and re.match(r'^\d+\s+\S', m.text.strip()))
def handle_bet(msg):
    parsed=parse_bet(msg.text.strip())
    if not parsed: return
    if not not_banned(msg) or not check_sub_gate(msg): return
    amount,btype,raw=parsed
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}. Баланс: {fmt(u['balance'])}"); return
    add_balance(u["user_id"],-amount)
    uname=msg.from_user.username or msg.from_user.first_name or str(msg.from_user.id)
    bet=Bet(msg.from_user.id,uname,amount,btype)
    with rl:
        if msg.chat.id not in roulette_sessions:
            roulette_sessions[msg.chat.id]={"bets":[],"timer":None,"last_bets":{},"cancelled":False}
        s=roulette_sessions[msg.chat.id]; s["bets"].append(bet)
        is_first=s["timer"] is None
        if is_first:
            s["cancelled"]=False; s["timer"]=start_rl_timer(msg.chat.id)
    conf=f"✅ @{uname} {fmt(amount)} {CURRENCY} на {bet_label(btype)}"
    if is_first: conf+=f"\n⏳ {ROULETTE_WAIT} сек. Пишите «го» для немедленного старта."
    bot.reply_to(msg,conf)

# ═══════════════════════════════════════════════════════
#  КРАШ / АВИАТОР
#  Формат: краш [ставка] [автостоп]
#  Пример: краш 1000 2.5  → вывод при достижении ×2.5
#  Если краш упал ДО автостопа — проигрыш
#  Если краш упал НА или ПОСЛЕ автостопа — победа
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(
    r'^краш\s+\d+(\s+[\d.]+)?$', m.text.strip(), re.I) and is_group(m))
def game_crash(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    parts = msg.text.strip().split()
    amount = int(parts[1])
    # автостоп — множитель для авто-вывода, по умолчанию 2.0
    try:
        autostop = round(float(parts[2]), 2) if len(parts) > 2 else 2.0
    except ValueError:
        autostop = 2.0
    autostop = max(1.01, min(autostop, 10.0))  # ограничиваем 1.01–10x

    u = eu(msg)
    if u["balance"] < amount:
        bot.reply_to(msg, f"Недостаточно {CURRENCY}. Баланс: {fmt(u['balance'])}"); return
    if amount < 10:
        bot.reply_to(msg, "Минимальная ставка 10."); return

    add_balance(u["user_id"], -amount)
    uname = msg.from_user.username or msg.from_user.first_name or str(msg.from_user.id)
    cid = msg.chat.id; uid = msg.from_user.id

    with crash_lock:
        if cid not in crash_sessions:
            # Первая ставка — запускаем раунд
            crash_sessions[cid] = {
                "bets": {}, "timer": None, "active": True,
                "started": False, "crashed_at": 0
            }
            t = threading.Thread(target=lambda: run_crash_game(cid), daemon=True)
            t.start()
            crash_sessions[cid]["timer"] = t
            bot.send_message(cid,
                f"✈️ Краш-раунд открыт! Ставки принимаются 10 секунд.\n"
                f"Формат: краш [ставка] [автостоп]\n"
                f"Пример: краш 500 2.5")
        s = crash_sessions[cid]
        if s.get("started"):
            add_balance(uid, amount)  # возврат — раунд уже идёт
            bot.reply_to(msg, "⚠️ Раунд уже начался! Дождитесь следующего."); return
        s["bets"][uid] = (uname, amount, autostop)

    bot.reply_to(msg,
        f"✈️ Ставка: {fmt(amount)} {CURRENCY} | Автостоп: ×{autostop}\n"
        f"Жди старта раунда...")

def run_crash_game(chat_id):
    """Ждёт 10 секунд, потом крутит краш и выводит результат."""
    time.sleep(10)
    with crash_lock:
        s = crash_sessions.get(chat_id)
        if not s or not s["active"] or not s["bets"]:
            crash_sessions.pop(chat_id, None); return
        s["started"] = True
        bets = dict(s["bets"])

    crash_point = generate_crash_mult()
    s["crashed_at"] = crash_point

    # Анимация взлёта
    milestones = [1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0]
    shown = []
    for tick in milestones:
        if tick >= crash_point: break
        shown.append(f"×{tick:.1f}")
        time.sleep(0.6)

    growth_str = " → ".join(shown) if shown else "×1.0"
    bot.send_message(chat_id,
        f"✈️ {growth_str}\n💥 КРАШ на ×{crash_point}!")

    lines = []
    for uid, (uname, amount, autostop) in bets.items():
        if autostop <= crash_point:
            # Автостоп сработал ДО краша — победа
            won = int(amount * autostop)
            add_balance(uid, won)
            net = won - amount
            lines.append(
                f"✅ @{uname} автостоп ×{autostop} | +{fmt(net)} {CURRENCY} (итого {fmt(won)})")
        else:
            # Краш случился раньше автостопа — проигрыш
            lines.append(
                f"💸 @{uname} хотел ×{autostop}, краш на ×{crash_point} | -{fmt(amount)} {CURRENCY}")

    if lines:
        bot.send_message(chat_id, "\n".join(lines))
    bot.send_message(chat_id, "Следующий раунд: напишите «краш [ставка] [автостоп]»")
    with crash_lock:
        crash_sessions.pop(chat_id, None)

# ═══════════════════════════════════════════════════════
#  БЛЭКДЖЕК
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^(бж|блэкджек)\s+\d+$',m.text.strip(),re.I) and is_group(m))
def game_bj(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    amount=int(msg.text.strip().split()[1])
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    add_balance(u["user_id"],-amount)
    deck=new_deck()
    ph=[deck.pop(),deck.pop()]
    dh=[deck.pop(),deck.pop()]
    sid=f"bj_{msg.from_user.id}_{msg.chat.id}_{int(time.time())}"
    with db() as d:
        d.execute("INSERT INTO blackjack_sessions(session_id,user_id,chat_id,bet,player_hand,dealer_hand) VALUES(?,?,?,?,?,?)",
                  (sid,msg.from_user.id,msg.chat.id,amount,json.dumps(ph),json.dumps(dh)))
    pv=hand_value(ph)
    if pv==21:
        win=int(amount*2.5)
        add_balance(msg.from_user.id,win)
        with db() as d: d.execute("UPDATE blackjack_sessions SET active=0 WHERE session_id=?",(sid,))
        bot.reply_to(msg,f"🃏 Блэкджек! Натуральный 21!\nВаши карты: {' '.join(ph)}\n🎉 Выигрыш: {fmt(win)} {CURRENCY}")
        return
    bot.reply_to(msg,bj_text(ph,dh),reply_markup=bj_kb(sid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("bj_"))
def cb_bj(call):
    parts=call.data.split("_")
    action=parts[1]; sid="_".join(parts[2:])
    with db() as d:
        row=d.execute("SELECT * FROM blackjack_sessions WHERE session_id=?",(sid,)).fetchone()
    if not row or not row["active"]:
        bot.answer_callback_query(call.id,"Игра завершена."); return
    if call.from_user.id!=row["user_id"]:
        bot.answer_callback_query(call.id,"Не ваша игра!"); return
    ph=json.loads(row["player_hand"]); dh=json.loads(row["dealer_hand"])
    deck=new_deck()
    while any(c in ph+dh for c in deck): deck=new_deck()

    if action=="hit":
        ph.append(deck.pop())
        pv=hand_value(ph)
        if pv>21:
            with db() as d: d.execute("UPDATE blackjack_sessions SET active=0,player_hand=? WHERE session_id=?",(json.dumps(ph),sid))
            bot.edit_message_text(
                f"🃏 Блэкджек\nВаши карты: {' '.join(ph)} ({pv})\n💥 Перебор! -{fmt(row['bet'])} {CURRENCY}",
                call.message.chat.id,call.message.message_id)
            bot.answer_callback_query(call.id); return
        with db() as d: d.execute("UPDATE blackjack_sessions SET player_hand=? WHERE session_id=?",(json.dumps(ph),sid))
        bot.edit_message_text(bj_text(ph,dh),call.message.chat.id,call.message.message_id,reply_markup=bj_kb(sid))

    elif action=="stand" or action=="double":
        if action=="double":
            u=get_user(call.from_user.id)
            if u["balance"]>=row["bet"]:
                add_balance(call.from_user.id,-row["bet"])
                amount=row["bet"]*2
                with db() as d: d.execute("UPDATE blackjack_sessions SET bet=? WHERE session_id=?",(amount,sid))
            else: amount=row["bet"]
        else: amount=row["bet"]

        # Дилер добирает до 17
        while hand_value(dh)<17:
            dh.append(deck.pop())
        pv=hand_value(ph); dv=hand_value(dh)
        with db() as d: d.execute("UPDATE blackjack_sessions SET active=0 WHERE session_id=?",(sid,))

        result_text=bj_text(ph,dh,show_dealer=True)+"\n\n"
        if pv>21: result_text+=f"💥 Перебор! -{fmt(amount)} {CURRENCY}"
        elif dv>21 or pv>dv:
            win=amount*2; add_balance(call.from_user.id,win)
            result_text+=f"🏆 Вы победили! +{fmt(win)} {CURRENCY}"
        elif pv==dv:
            add_balance(call.from_user.id,amount)
            result_text+=f"🤝 Ничья! Ставка возвращена"
        else: result_text+=f"😞 Дилер победил! -{fmt(amount)} {CURRENCY}"
        bot.edit_message_text(result_text,call.message.chat.id,call.message.message_id)
    bot.answer_callback_query(call.id)

# ═══════════════════════════════════════════════════════
#  КОЛЕСО ФОРТУНЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^колесо\s+\d+$',m.text.strip(),re.I) and is_group(m))
def game_wheel(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    amount=int(msg.text.strip().split()[1])
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    add_balance(u["user_id"],-amount)
    mult,label=spin_wheel()
    if mult<1:
        lose=int(amount*(1-mult))
        add_balance(u["user_id"],-lose)
        bot.reply_to(msg,f"🎡 Колесо: {label}\nПотеряли {fmt(int(amount*mult))} {CURRENCY}")
    else:
        win=int(amount*mult)
        add_balance(u["user_id"],win)
        bot.reply_to(msg,f"🎡 Колесо: {label}\n+{fmt(win)} {CURRENCY}!")

# ═══════════════════════════════════════════════════════
#  СКАЧКИ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^скачки\s+\d+\s+[1-5]$',m.text.strip(),re.I) and is_group(m))
def game_horses(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    parts=msg.text.strip().split()
    amount,guess=int(parts[1]),int(parts[2])
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    add_balance(u["user_id"],-amount)
    winner=random.randint(1,5)
    lines=[f"🏁 Скачки!\n"]
    positions=list(range(1,6)); random.shuffle(positions)
    race_str=""
    for i,pos in enumerate(sorted(range(5),key=lambda x: positions[x]),1):
        horse_n=pos+1
        finish="🏆" if horse_n==winner else ""
        race_str+=f"{HORSES[pos]} Конь {horse_n} {finish}\n"
    if winner==guess:
        win=amount*4; add_balance(u["user_id"],win)
        result=f"🏆 Победил Конь {winner}!\nВы выиграли {fmt(win)} {CURRENCY}!"
    else:
        result=f"🏆 Победил Конь {winner}. Вы ставили на {guess}. -{fmt(amount)} {CURRENCY}"
    bot.reply_to(msg,race_str+result)

# ═══════════════════════════════════════════════════════
#  ЛОТЕРЕЯ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^лото\s+\d+$',m.text.strip(),re.I) and is_group(m))
def game_lotto(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    amount=int(msg.text.strip().split()[1])
    if amount<100:
        bot.reply_to(msg,"Минимальная ставка в лотерее 100."); return
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    add_balance(u["user_id"],-amount)
    tickets_count=amount//100
    cid=msg.chat.id; uid=msg.from_user.id
    with db() as d:
        row=d.execute("SELECT * FROM lottery_sessions WHERE chat_id=?",(cid,)).fetchone()
        if not row or not row["active"]:
            draw_time=start_lottery(cid,bot)
            d.execute("INSERT OR REPLACE INTO lottery_sessions(chat_id,tickets,draw_at,active) VALUES(?,?,?,1)",
                      (cid,'{}',draw_time))
            row=d.execute("SELECT * FROM lottery_sessions WHERE chat_id=?",(cid,)).fetchone()
        tickets=json.loads(row["tickets"])
        tickets[str(uid)]=tickets.get(str(uid),0)+tickets_count
        d.execute("UPDATE lottery_sessions SET tickets=? WHERE chat_id=?",(json.dumps(tickets),cid))
    uname=msg.from_user.username or msg.from_user.first_name
    total_pool=sum(tickets.values())*100
    bot.reply_to(msg,
        f"🎟 @{uname} купил {tickets_count} билет(ов)!\n"
        f"Всего в банке: {fmt(total_pool)} {CURRENCY}\n"
        f"Розыгрыш через 5 минут после первой ставки!")

# ═══════════════════════════════════════════════════════
#  МИНЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^мины\s+\d+(\s+\d+)?$',m.text.strip(),re.I) and is_group(m))
def game_mines(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    parts=msg.text.strip().split()
    amount=int(parts[1]); mc=int(parts[2]) if len(parts)>2 else 5
    mc=max(1,min(mc,20))
    u=eu(msg)
    if u["balance"]<amount or amount<10:
        bot.reply_to(msg,f"Минимум 10, ваш баланс: {fmt(u['balance'])}"); return
    add_balance(u["user_id"],-amount)
    mines=create_mines(25,mc)
    sid=f"m_{msg.from_user.id}_{msg.chat.id}_{int(time.time())}"
    with db() as d:
        d.execute("INSERT INTO mines_sessions(session_id,user_id,chat_id,bet,mines_count,field) VALUES(?,?,?,?,?,?)",
                  (sid,msg.from_user.id,msg.chat.id,amount,mc,json.dumps(list(mines))))
    mult=round(25/(25-mc),2)
    bot.reply_to(msg,
        f"💣 Мины! Ставка: {fmt(amount)} {CURRENCY}, мин: {mc}\n"
        f"Открывайте клетки. Множитель за клетку: ×{mult}",
        reply_markup=mines_kb(sid,25,set(),mines))

@bot.callback_query_handler(func=lambda c: c.data.startswith("mx_"))
def cb_mines_open(call):
    parts=call.data.split("_",2); _,sid,cell=parts[0],parts[1]+"_"+parts[2].split("_")[0] if len(parts)>2 else (None,None,None)
    # fix parse
    raw=call.data[3:]; idx=raw.rfind("_"); sid=raw[:idx]; cell=int(raw[idx+1:])
    with db() as d:
        row=d.execute("SELECT * FROM mines_sessions WHERE session_id=?",(sid,)).fetchone()
    if not row or not row["active"]:
        bot.answer_callback_query(call.id,"Сессия завершена."); return
    if call.from_user.id!=row["user_id"]:
        bot.answer_callback_query(call.id,"Не ваша игра!"); return
    mines=set(json.loads(row["field"])); opened=set(json.loads(row["opened"]))
    opened.add(cell)
    if cell in mines:
        with db() as d: d.execute("UPDATE mines_sessions SET active=0 WHERE session_id=?",(sid,))
        bot.edit_message_text(f"💥 Мина! -{fmt(row['bet'])} {CURRENCY}",
            call.message.chat.id,call.message.message_id,
            reply_markup=mines_kb(sid,25,opened,mines,revealed=True))
        bot.answer_callback_query(call.id,"💥 Взрыв!")
    else:
        with db() as d: d.execute("UPDATE mines_sessions SET opened=? WHERE session_id=?",(json.dumps(list(opened)),sid))
        safe=len(opened); mult=round((25/(25-row["mines_count"]))**safe,2)
        win=int(row["bet"]*mult)
        bot.edit_message_text(f"💎 Открыто: {safe} | Выигрыш: {fmt(win)} {CURRENCY} (×{mult})",
            call.message.chat.id,call.message.message_id,
            reply_markup=mines_kb(sid,25,opened,mines))
        bot.answer_callback_query(call.id,f"✅ Безопасно! Выигрыш: {fmt(win)}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("mc_"))
def cb_mines_cash(call):
    sid=call.data[3:]
    with db() as d:
        row=d.execute("SELECT * FROM mines_sessions WHERE session_id=?",(sid,)).fetchone()
    if not row or not row["active"]:
        bot.answer_callback_query(call.id,"Сессия завершена."); return
    if call.from_user.id!=row["user_id"]:
        bot.answer_callback_query(call.id,"Не ваша игра!"); return
    opened=set(json.loads(row["opened"])); safe=len(opened)
    if safe==0:
        add_balance(row["user_id"],row["bet"])
        with db() as d: d.execute("UPDATE mines_sessions SET active=0 WHERE session_id=?",(sid,))
        bot.edit_message_text("Ставка возвращена.",call.message.chat.id,call.message.message_id)
        bot.answer_callback_query(call.id); return
    mult=round((25/(25-row["mines_count"]))**safe,2); win=int(row["bet"]*mult)
    add_balance(row["user_id"],win)
    with db() as d: d.execute("UPDATE mines_sessions SET active=0 WHERE session_id=?",(sid,))
    bot.edit_message_text(f"💰 Забрали {fmt(win)} {CURRENCY} (×{mult}, {safe} клеток)!",
        call.message.chat.id,call.message.message_id)
    bot.answer_callback_query(call.id,f"💰 +{fmt(win)} {CURRENCY}")

# ═══════════════════════════════════════════════════════
#  МОНЕТКА / КОСТИ / ДЖОКЕР
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and re.match(r'^монетка\s+\d+\s+(орёл|орел|решка)$',m.text.strip(),re.I) and is_group(m))
def game_coin(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    parts=msg.text.strip().split(); amount=int(parts[1]); guess=parts[2].lower()
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    result=random.choice(["орёл","решка"])
    won=guess in("орёл","орел") and result=="орёл" or guess=="решка" and result=="решка"
    icon="🦅" if result=="орёл" else "🌀"
    if won:
        add_balance(u["user_id"],amount); bot.reply_to(msg,f"{icon} {result.capitalize()}! +{fmt(amount*2)} {CURRENCY}!")
    else:
        add_balance(u["user_id"],-amount); bot.reply_to(msg,f"{icon} {result.capitalize()}! -{fmt(amount)} {CURRENCY}")

@bot.message_handler(func=lambda m: m.text and re.match(r'^кости\s+\d+\s+[1-6]$',m.text.strip(),re.I) and is_group(m))
def game_dice(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    parts=msg.text.strip().split(); amount=int(parts[1]); guess=int(parts[2])
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    # Отправляем анимированный кубик Telegram
    dice_msg=bot.send_dice(msg.chat.id, emoji="🎲")
    result=dice_msg.dice.value
    # Небольшая пауза чтобы анимация успела прокрутиться
    time.sleep(4)
    if result==guess:
        win=amount*5; add_balance(u["user_id"],win)
        bot.send_message(msg.chat.id,
            f"🎲 Выпало {result}!\n"
            f"@{u['username'] or msg.from_user.first_name} угадал! +{fmt(win)} {CURRENCY} 🎉")
    else:
        add_balance(u["user_id"],-amount)
        bot.send_message(msg.chat.id,
            f"🎲 Выпало {result}.\n"
            f"@{u['username'] or msg.from_user.first_name} ставил на {guess}. -{fmt(amount)} {CURRENCY}")

@bot.message_handler(func=lambda m: m.text and re.match(r'^джокер\s+\d+$',m.text.strip(),re.I) and is_group(m))
def game_joker(msg):
    if not not_banned(msg) or not check_sub_gate(msg): return
    amount=int(msg.text.strip().split()[1])
    u=eu(msg)
    if u["balance"]<amount:
        bot.reply_to(msg,f"Недостаточно {CURRENCY}."); return
    add_balance(u["user_id"],-amount)
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🔴 Красная",callback_data=f"jr_{u['user_id']}_{amount}"),
           InlineKeyboardButton("⚫ Чёрная", callback_data=f"jb_{u['user_id']}_{amount}"))
    bot.reply_to(msg,f"🃏 Джокер! Ставка: {fmt(amount)} {CURRENCY}\nУгадайте масть:",reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("jr_") or c.data.startswith("jb_"))
def cb_joker(call):
    guess="red" if call.data.startswith("jr_") else "black"
    _,uid,amount=[call.data.split("_")[0]]+call.data.split("_")[1:]
    uid=int(uid); amount=int(amount)
    if call.from_user.id!=uid:
        bot.answer_callback_query(call.id,"Не ваша игра!"); return
    suits=["♠️ Пики","♣️ Трефы","♥️ Червы","♦️ Бубны"]
    card=random.choice(suits)
    real="red" if "Червы" in card or "Бубны" in card else "black"
    if guess==real:
        win=amount*2; add_balance(uid,win)
        bot.edit_message_text(f"🃏 {card}\n✅ Угадали! +{fmt(win)} {CURRENCY}",
            call.message.chat.id,call.message.message_id)
    else:
        bot.edit_message_text(f"🃏 {card}\n❌ Не угадали. -{fmt(amount)} {CURRENCY}",
            call.message.chat.id,call.message.message_id)
    bot.answer_callback_query(call.id)

# ═══════════════════════════════════════════════════════
#  МЕНЮ ИГРЫ
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip()=="🎮 Игры")
def btn_games(msg):
    text=(
        "🎮 Игры (только в групповом чате)\n\n"
        "🎰 Рулетка: [сумма] ч/к/число/диапазон\n"
        "✈️ Авиатор: краш [ставка] [автостоп×]\n"
        "   Пример: краш 500 2.5\n"
        "🃏 Блэкджек: бж [сумма]\n"
        "🏇 Скачки: скачки [сумма] [1-5]\n"
        "💣 Мины: мины [сумма] [кол-во мин]\n"
        "🎟 Лотерея: лото [сумма]\n"
        "🪙 Монетка: монетка [сумма] орёл/решка\n"
        "🎲 Кости: кости [сумма] [1-6]\n"
        "🃏 Джокер: джокер [сумма]"
    )
    bot.send_message(msg.chat.id,text)

# ═══════════════════════════════════════════════════════
#  ПОДПИСКА — check callback
# ═══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data=="check_subs")
def cb_check_subs(call):
    missing=check_subs(bot,call.from_user.id)
    if missing:
        bot.answer_callback_query(call.id,"Вы ещё не подписались на все каналы!")
    else:
        bot.answer_callback_query(call.id,"✅ Спасибо! Теперь можете играть.")
        try: bot.delete_message(call.message.chat.id,call.message.message_id)
        except: pass

# ═══════════════════════════════════════════════════════
#  ЯЗЫК
# ═══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text and m.text.strip()=="🌐 Язык")
def btn_lang(msg):
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("🇺🇦 Українська",callback_data="lang_uk"),
           InlineKeyboardButton("🇬🇧 English",callback_data="lang_en"),
           InlineKeyboardButton("🇷🇺 Русский",callback_data="lang_ru"))
    bot.send_message(msg.chat.id,"Выберите язык:",reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang_"))
def cb_lang(call):
    lang=call.data[5:]
    with db() as d: d.execute("UPDATE users SET language=? WHERE user_id=?",(lang,call.from_user.id))
    names={"ru":"Русский","uk":"Українська","en":"English"}
    bot.answer_callback_query(call.id,f"✅ Язык: {names.get(lang,lang)}")
    bot.edit_message_text(f"✅ Язык изменён: {names.get(lang,lang)}",call.message.chat.id,call.message.message_id)

@bot.message_handler(func=lambda m: m.text and m.text.strip()=="📜 Политика")
def btn_policy(msg):
    bot.send_message(msg.chat.id,
        f"📜 Политика конфиденциальности {CURRENCY}\n\n"
        "Бот хранит Telegram ID, username и игровую историю. "
        "Данные не передаются третьим лицам. Баланс {CURRENCY} — игровая валюта без реальной стоимости.")

@bot.message_handler(func=lambda m: m.text and m.text.strip() in("🏆 Турниры","💬 Чаты"))
def btn_misc(msg):
    if "Турниры" in msg.text:
        bot.send_message(msg.chat.id,"🏆 Турниры — скоро! Следите за анонсами.")
    else:
        bot.send_message(msg.chat.id,f"💬 Чаты {CURRENCY}\n\nКанал: @zeon_channel\nЧат: @zeon_chat")

# ═══════════════════════════════════════════════════════
#  ══════════════════ АДМИН-ПАНЕЛЬ ══════════════════════
# ═══════════════════════════════════════════════════════
def admin_main_kb():
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📢 Рассылка",    callback_data="adm_broadcast"),
           InlineKeyboardButton("🎟 Промокоды",   callback_data="adm_promos"))
    kb.row(InlineKeyboardButton("👁 Подписки",    callback_data="adm_subs"),
           InlineKeyboardButton("💰 Цены ZEON",   callback_data="adm_prices"))
    kb.row(InlineKeyboardButton("👤 Игрок",       callback_data="adm_user"),
           InlineKeyboardButton("💎 Выдать/забрать",callback_data="adm_give"))
    kb.row(InlineKeyboardButton("🚫 Бан/Разбан",  callback_data="adm_ban"),
           InlineKeyboardButton("📊 Статистика",  callback_data="adm_stats"))
    kb.row(InlineKeyboardButton("🎁 ВИП выдать",  callback_data="adm_vip"))
    return kb

@bot.message_handler(commands=["admin"])
def cmd_admin(msg):
    if msg.from_user.id not in ADMIN_IDS:
        return
    bot.send_message(msg.chat.id,"🛠 Панель администратора",reply_markup=admin_main_kb())

# ─── СТАТИСТИКА ────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data=="adm_stats" and c.from_user.id in ADMIN_IDS)
def adm_stats(call):
    with db() as d:
        users=d.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        banned=d.execute("SELECT COUNT(*) c FROM users WHERE banned=1").fetchone()["c"]
        vips=d.execute("SELECT COUNT(*) c FROM users WHERE vip_until>?",(int(time.time()),)).fetchone()["c"]
        clans=d.execute("SELECT COUNT(*) c FROM clans").fetchone()["c"]
        transfers=d.execute("SELECT COUNT(*) c FROM transfers").fetchone()["c"]
        total_bal=d.execute("SELECT SUM(balance) s FROM users").fetchone()["s"] or 0
    text=(f"📊 Статистика бота\n\n"
          f"👥 Пользователей: {users}\n"
          f"🚫 Забанено: {banned}\n"
          f"👑 VIP: {vips}\n"
          f"🏰 Кланов: {clans}\n"
          f"💸 Переводов: {transfers}\n"
          f"{C_ICON} Всего в обороте: {fmt(total_bal)}")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,text,reply_markup=admin_main_kb())

# ─── ПРОМОКОДЫ ─────────────────────────────────────────
def promos_kb():
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("➕ Создать промокод",callback_data="adm_promo_create"))
    kb.row(InlineKeyboardButton("📋 Список промокодов",callback_data="adm_promo_list"))
    kb.row(InlineKeyboardButton("❌ Удалить промокод",callback_data="adm_promo_del"))
    kb.row(InlineKeyboardButton("◀ Назад",callback_data="adm_back"))
    return kb

@bot.callback_query_handler(func=lambda c: c.data=="adm_promos" and c.from_user.id in ADMIN_IDS)
def adm_promos(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"🎟 Управление промокодами",reply_markup=promos_kb())

@bot.callback_query_handler(func=lambda c: c.data=="adm_promo_create" and c.from_user.id in ADMIN_IDS)
def adm_promo_create(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"promo_code")
    bot.send_message(call.message.chat.id,"Введите название промокода (латиница):")

@bot.callback_query_handler(func=lambda c: c.data=="adm_promo_list" and c.from_user.id in ADMIN_IDS)
def adm_promo_list(call):
    with db() as d:
        rows=d.execute("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 20").fetchall()
    if not rows:
        bot.answer_callback_query(call.id,"Промокодов нет."); return
    lines=["🎟 Промокоды:\n"]
    for r in rows:
        used=len(json.loads(r["used_by"]))
        lines.append(f"• {r['code']} | {fmt(r['amount'])} {CURRENCY} | "
                     f"осталось: {r['uses_left']} | использовано: {used}")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"\n".join(lines))

@bot.callback_query_handler(func=lambda c: c.data=="adm_promo_del" and c.from_user.id in ADMIN_IDS)
def adm_promo_del(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"promo_del")
    bot.send_message(call.message.chat.id,"Введите код для удаления:")

# ─── РАССЫЛКА ──────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data=="adm_broadcast" and c.from_user.id in ADMIN_IDS)
def adm_broadcast(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"broadcast")
    bot.send_message(call.message.chat.id,"Введите текст рассылки (будет отправлен всем пользователям):")

# ─── ПОДПИСКИ ──────────────────────────────────────────
def subs_admin_kb():
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("➕ Добавить канал",  callback_data="adm_sub_add"))
    kb.row(InlineKeyboardButton("📋 Список каналов",  callback_data="adm_sub_list"))
    kb.row(InlineKeyboardButton("❌ Удалить канал",   callback_data="adm_sub_del"))
    kb.row(InlineKeyboardButton("◀ Назад",           callback_data="adm_back"))
    return kb

@bot.callback_query_handler(func=lambda c: c.data=="adm_subs" and c.from_user.id in ADMIN_IDS)
def adm_subs(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"👁 Обязательные подписки",reply_markup=subs_admin_kb())

@bot.callback_query_handler(func=lambda c: c.data=="adm_sub_add" and c.from_user.id in ADMIN_IDS)
def adm_sub_add(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"sub_add")
    bot.send_message(call.message.chat.id,"Введите @username канала:")

@bot.callback_query_handler(func=lambda c: c.data=="adm_sub_list" and c.from_user.id in ADMIN_IDS)
def adm_sub_list(call):
    with db() as d:
        rows=d.execute("SELECT channel FROM required_subs").fetchall()
    if not rows:
        bot.answer_callback_query(call.id,"Каналов нет."); return
    text="Обязательные подписки:\n"+"\n".join(f"• {r['channel']}" for r in rows)
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,text)

@bot.callback_query_handler(func=lambda c: c.data=="adm_sub_del" and c.from_user.id in ADMIN_IDS)
def adm_sub_del(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"sub_del")
    bot.send_message(call.message.chat.id,"Введите @username канала для удаления:")

# ─── ЦЕНЫ ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data=="adm_prices" and c.from_user.id in ADMIN_IDS)
def adm_prices(call):
    pkgs=get_packages()
    lines=["💰 Текущие пакеты звёзд:\n"]
    for p in pkgs:
        if p["is_vip"]:
            lines.append(f"ID{p['id']}: ⭐{p['stars']} → 👑 VIP")
        else:
            lines.append(f"ID{p['id']}: ⭐{p['stars']} → {fmt(p['zeon'])} {CURRENCY}")
    kb=InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("✏️ Изменить пакет",callback_data="adm_price_edit"))
    kb.row(InlineKeyboardButton("➕ Добавить пакет",callback_data="adm_price_add"))
    kb.row(InlineKeyboardButton("◀ Назад",callback_data="adm_back"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"\n".join(lines),reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data=="adm_price_edit" and c.from_user.id in ADMIN_IDS)
def adm_price_edit(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"price_edit")
    bot.send_message(call.message.chat.id,"Введите: ID пакета новые_звёзды новый_ZEON\nПример: 1 50 150000")

@bot.callback_query_handler(func=lambda c: c.data=="adm_price_add" and c.from_user.id in ADMIN_IDS)
def adm_price_add(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"price_add")
    bot.send_message(call.message.chat.id,"Введите: звёзды ZEON\nПример: 100 200000\nДля VIP: 100 vip")

# ─── ИГРОК ─────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data=="adm_user" and c.from_user.id in ADMIN_IDS)
def adm_user(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"find_user")
    bot.send_message(call.message.chat.id,"Введите ID или @username пользователя:")

@bot.callback_query_handler(func=lambda c: c.data=="adm_give" and c.from_user.id in ADMIN_IDS)
def adm_give(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"give_coins")
    bot.send_message(call.message.chat.id,"Введите: ID сумма (отрицательная — забрать)\nПример: 123456 50000")

@bot.callback_query_handler(func=lambda c: c.data=="adm_ban" and c.from_user.id in ADMIN_IDS)
def adm_ban(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"ban_user")
    bot.send_message(call.message.chat.id,"Введите ID пользователя (- перед ID для разбана):\nПример: 123456 (бан) или -123456 (разбан)")

@bot.callback_query_handler(func=lambda c: c.data=="adm_vip" and c.from_user.id in ADMIN_IDS)
def adm_vip_give(call):
    bot.answer_callback_query(call.id)
    set_admin_state(call.from_user.id,"give_vip")
    bot.send_message(call.message.chat.id,f"Введите: ID [дней]\nПример: 123456 30")

@bot.callback_query_handler(func=lambda c: c.data=="adm_back" and c.from_user.id in ADMIN_IDS)
def adm_back(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,"🛠 Панель администратора",reply_markup=admin_main_kb())

# ─── ОБРАБОТКА СОСТОЯНИЙ АДМИНА ────────────────────────
@bot.message_handler(func=lambda m: m.from_user.id in ADMIN_IDS and get_admin_state(m.from_user.id) is not None)
def handle_admin_input(msg):
    uid=msg.from_user.id
    state=get_admin_state(uid)
    if not state: return
    s=state["state"]; d_=state["data"]

    # ПРОМОКОД — шаги
    if s=="promo_code":
        code=msg.text.strip().upper()
        if not re.match(r'^[A-Z0-9_]{2,20}$',code):
            bot.reply_to(msg,"Код: латиница, цифры, _, 2-20 символов."); return
        set_admin_state(uid,"promo_amount",code=code)
        bot.reply_to(msg,f"Код: {code}\nВведите сумму {CURRENCY}:")

    elif s=="promo_amount":
        if not msg.text.strip().isdigit():
            bot.reply_to(msg,"Введите число."); return
        set_admin_state(uid,"promo_uses",code=d_["code"],amount=int(msg.text.strip()))
        bot.reply_to(msg,"Введите количество использований:")

    elif s=="promo_uses":
        if not msg.text.strip().isdigit():
            bot.reply_to(msg,"Введите число."); return
        uses=int(msg.text.strip())
        code=d_["code"]; amount=d_["amount"]
        with db() as conn:
            try:
                conn.execute("INSERT INTO promo_codes(code,amount,uses_left) VALUES(?,?,?)",(code,amount,uses))
                bot.reply_to(msg,f"✅ Промокод {code} создан!\nСумма: {fmt(amount)} {CURRENCY}, использований: {uses}")
            except: bot.reply_to(msg,"Промокод уже существует.")
        clear_admin_state(uid)

    elif s=="promo_del":
        code=msg.text.strip().upper()
        with db() as conn: conn.execute("DELETE FROM promo_codes WHERE code=?",(code,))
        bot.reply_to(msg,f"✅ Промокод {code} удалён.")
        clear_admin_state(uid)

    # РАССЫЛКА
    elif s=="broadcast":
        text=msg.text.strip()
        with db() as conn:
            uids=[r["user_id"] for r in conn.execute("SELECT user_id FROM users WHERE banned=0").fetchall()]
        ok=0; fail=0
        bot.reply_to(msg,f"⏳ Рассылка {len(uids)} пользователям...")
        for recv_uid in uids:
            try: bot.send_message(recv_uid,f"📢 {text}"); ok+=1
            except: fail+=1
            time.sleep(0.05)
        bot.reply_to(msg,f"✅ Рассылка завершена!\nОтправлено: {ok}, ошибок: {fail}")
        clear_admin_state(uid)

    # ПОДПИСКИ
    elif s=="sub_add":
        ch=msg.text.strip()
        if not ch.startswith("@"): ch="@"+ch
        with db() as conn:
            try: conn.execute("INSERT INTO required_subs(channel) VALUES(?)",(ch,))
            except: bot.reply_to(msg,"Канал уже добавлен."); clear_admin_state(uid); return
        bot.reply_to(msg,f"✅ Канал {ch} добавлен как обязательный.")
        clear_admin_state(uid)

    elif s=="sub_del":
        ch=msg.text.strip()
        if not ch.startswith("@"): ch="@"+ch
        with db() as conn: conn.execute("DELETE FROM required_subs WHERE channel=?",(ch,))
        bot.reply_to(msg,f"✅ Канал {ch} удалён.")
        clear_admin_state(uid)

    # ЦЕНЫ
    elif s=="price_edit":
        parts=msg.text.strip().split()
        if len(parts)<3:
            bot.reply_to(msg,"Формат: ID звёзды ZEON"); return
        pkg_id,stars=int(parts[0]),int(parts[1])
        is_vip=parts[2].lower()=="vip"
        zeon=0 if is_vip else int(parts[2])
        with db() as conn:
            conn.execute("UPDATE star_packages SET stars=?,zeon=?,is_vip=? WHERE id=?",(stars,zeon,1 if is_vip else 0,pkg_id))
        bot.reply_to(msg,f"✅ Пакет ID{pkg_id} обновлён.")
        clear_admin_state(uid)

    elif s=="price_add":
        parts=msg.text.strip().split()
        if len(parts)<2:
            bot.reply_to(msg,"Формат: звёзды ZEON"); return
        stars=int(parts[0])
        is_vip=parts[1].lower()=="vip"
        zeon=0 if is_vip else int(parts[1])
        with db() as conn:
            conn.execute("INSERT INTO star_packages(stars,zeon,is_vip) VALUES(?,?,?)",(stars,zeon,1 if is_vip else 0))
        bot.reply_to(msg,f"✅ Пакет ⭐{stars} добавлен.")
        clear_admin_state(uid)

    # ПОИСК ИГРОКА
    elif s=="find_user":
        q=msg.text.strip()
        with db() as conn:
            if q.lstrip("-").isdigit():
                row=conn.execute("SELECT * FROM users WHERE user_id=?",(int(q),)).fetchone()
            else:
                q2=q.lstrip("@")
                row=conn.execute("SELECT * FROM users WHERE username=?",(q2,)).fetchone()
        if not row:
            bot.reply_to(msg,"Пользователь не найден."); clear_admin_state(uid); return
        r=dict(row)
        vip_str=f"\n👑 VIP до {datetime.fromtimestamp(r['vip_until']).strftime('%d.%m.%Y')}" if r["vip_until"]>int(time.time()) else ""
        text=(f"👤 ID: {r['user_id']}\n"
              f"Username: @{r['username']}\n"
              f"{C_ICON} Баланс: {fmt(r['balance'])} {CURRENCY}\n"
              f"🚫 Бан: {'да' if r['banned'] else 'нет'}{vip_str}")
        kb=InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton(f"💎 Выдать монеты",callback_data=f"ag_{r['user_id']}"),
               InlineKeyboardButton(f"🚫 {'Разбан' if r['banned'] else 'Бан'}",
                                    callback_data=f"ab_{r['user_id']}"))
        kb.row(InlineKeyboardButton(f"👑 VIP 30д",callback_data=f"av_{r['user_id']}"))
        bot.reply_to(msg,text,reply_markup=kb)
        clear_admin_state(uid)

    # ВЫДАТЬ МОНЕТЫ
    elif s=="give_coins":
        parts=msg.text.strip().split()
        if len(parts)<2:
            bot.reply_to(msg,"Формат: ID сумма"); return
        target_uid=int(parts[0]); amount=int(parts[1])
        add_balance(target_uid,amount)
        sign="+" if amount>0 else ""
        bot.reply_to(msg,f"✅ {sign}{fmt(amount)} {CURRENCY} → ID{target_uid}")
        clear_admin_state(uid)

    # БАН
    elif s=="ban_user":
        q=msg.text.strip()
        unban=q.startswith("-")
        target_uid=int(q.lstrip("-"))
        with db() as conn:
            conn.execute("UPDATE users SET banned=? WHERE user_id=?",(0 if unban else 1,target_uid))
        action="разбан" if unban else "бан"
        bot.reply_to(msg,f"✅ {action.capitalize()} для ID{target_uid}")
        clear_admin_state(uid)

    # VIP
    elif s=="give_vip":
        parts=msg.text.strip().split()
        target_uid=int(parts[0]); days=int(parts[1]) if len(parts)>1 else VIP_DAYS
        grant_vip(target_uid,days)
        bot.reply_to(msg,f"✅ VIP на {days} дней выдан ID{target_uid}")
        clear_admin_state(uid)

# Inline-кнопки быстрого управления игроком из find_user
@bot.callback_query_handler(func=lambda c: c.data.startswith("ag_") or c.data.startswith("ab_") or c.data.startswith("av_"))
def cb_quick_admin(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id,"Нет доступа."); return
    action=call.data[:2]; target_uid=int(call.data[3:])
    if action=="ag":
        set_admin_state(call.from_user.id,"give_coins",target=target_uid)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,f"Введите сумму для ID{target_uid} (отрицательная — забрать):")
    elif action=="ab":
        with db() as d:
            row=d.execute("SELECT banned FROM users WHERE user_id=?",(target_uid,)).fetchone()
            new_ban=0 if row and row["banned"] else 1
            d.execute("UPDATE users SET banned=? WHERE user_id=?",(new_ban,target_uid))
        status="разбанен" if not new_ban else "забанен"
        bot.answer_callback_query(call.id,f"ID{target_uid} {status}!")
    elif action=="av":
        grant_vip(target_uid,VIP_DAYS)
        bot.answer_callback_query(call.id,f"VIP выдан ID{target_uid}!")

# ═══════════════════════════════════════════════════════
#  ЗАГЛУШКИ
# ═══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data=="noop")
def cb_noop(call):
    bot.answer_callback_query(call.id)

# ═══════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════
if __name__=="__main__":
    print(f"🚀 {CURRENCY} Bot запущен!")
    print(f"Аватарку загрузите через @BotFather → /setuserpic")
    bot.infinity_polling(skip_pending=True, timeout=30)
