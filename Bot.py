import asyncio
import aiohttp
import logging
import json
import os
import sqlite3
import pytz
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv(“BOT_TOKEN”, “8682396682:AAFJw9BgaIL8T1mPTYKP_iQzMARbv6iCEiw”)
ALERT_CHAT_IDS = []
POLL_INTERVAL = 5
DB_FILE = “bot.db”
IL_TZ = pytz.timezone(“Asia/Jerusalem”)
OREF_ALERTS_URL = “https://www.oref.org.il/WarningMessages/alert/alerts.json”
OREF_HEADERS = {
“Referer”: “https://www.oref.org.il/”,
“X-Requested-With”: “XMLHttpRequest”,
“Accept”: “application/json”,
“User-Agent”: “Mozilla/5.0”,
}

STRINGS = {
“ru”: {
“start_msg”: “🚨 <b>Бот оповещения о ракетных атаках</b>\n\nСлежу за Пикуд ха-Ореф 24/7.\nОповещаю о ракетах из <b>Ирана</b> и <b>Йемена</b>.\n\nВыберите язык / Choose language:”,
“lang_set”: “✅ Язык: Русский\n✅ Вы подписаны на оповещения.\n\n/stop — отписаться\n/status — текущий статус\n/lang — сменить язык”,
“subscribed”: “✅ Вы подписаны на оповещения.”,
“unsubscribed”: “🔕 Вы отписались.\nЧтобы снова подписаться — /start”,
“no_alerts”: “✅ <b>Тревог нет.</b> Всё спокойно.”,
“active_alerts_header”: “🔴 <b>Активные тревоги:</b>\n”,
“regions_label”: “Районы”,
“arrival_label”: “Прибытие”,
“alert_header”: “🔴 <b>ТРЕВОГА!</b>”,
“launch_detected”: “🕐 Обнаружен пуск”,
“flight_time”: “⏱ Время полёта”,
“expected_arrival”: “🎯 Ожидаемое прибытие”,
“shelter_now”: “⚠️ <i>Немедленно укройтесь в убежище!</i>”,
“allclear_header”: “🟢 <b>ОТБОЙ</b>”,
“threat_clear”: “ℹ️ <b>Угроза миновала.</b>”,
“follow_oref”: “📻 <i>Следите за Пикуд ха-Ореф</i>”,
“min”: “мин”,
“from_iran”: “Иран 🇮🇷”,
“from_yemen”: “Йемен 🇾🇪”,
“from_unknown”: “Неизвестный источник”,
},
“en”: {
“start_msg”: “🚨 <b>Rocket Alert Bot — Israel</b>\n\nMonitoring Pikud HaOref 24/7.\nAlerts from <b>Iran</b> and <b>Yemen</b>.\n\nВыберите язык / Choose language:”,
“lang_set”: “✅ Language: English\n✅ You are subscribed.\n\n/stop — unsubscribe\n/status — current status\n/lang — change language”,
“subscribed”: “✅ You are subscribed to alerts.”,
“unsubscribed”: “🔕 You unsubscribed.\nTo subscribe again — /start”,
“no_alerts”: “✅ <b>No alerts.</b> All clear.”,
“active_alerts_header”: “🔴 <b>Active alerts:</b>\n”,
“regions_label”: “Areas”,
“arrival_label”: “Arrival”,
“alert_header”: “🔴 <b>ALERT!</b>”,
“launch_detected”: “🕐 Launch detected”,
“flight_time”: “⏱ Flight time”,
“expected_arrival”: “🎯 Expected arrival”,
“shelter_now”: “⚠️ <i>Take shelter immediately!</i>”,
“allclear_header”: “🟢 <b>ALL CLEAR</b>”,
“threat_clear”: “ℹ️ <b>Threat has passed.</b>”,
“follow_oref”: “📻 <i>Follow Pikud HaOref</i>”,
“min”: “min”,
“from_iran”: “Iran 🇮🇷”,
“from_yemen”: “Yemen 🇾🇪”,
“from_unknown”: “Unknown source”,
},
}

IRAN_FLIGHT_TIMES = {
“North”: 10, “Haifa”: 11, “Center”: 12,
“Tel Aviv”: 12, “Jerusalem”: 12,
“South”: 14, “Negev”: 15, “Eilat”: 18,
“default”: 12,
}

YEMEN_FLIGHT_TIMES = {
“North”: 17, “Haifa”: 17, “Center”: 18,
“Tel Aviv”: 18, “Jerusalem”: 18,
“South”: 16, “Negev”: 15, “Eilat”: 12,
“default”: 18,
}

IRAN_KEYWORDS = [“iran”, “ballistic”]
YEMEN_KEYWORDS = [“yemen”, “houthi”]

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s %(levelname)s %(message)s”,
handlers=[
logging.StreamHandler(),
logging.FileHandler(“bot.log”, encoding=“utf-8”),
]
)
logger = logging.getLogger(**name**)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
seen_alert_ids = set()
active_alerts = {}

def init_db():
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute(”””
CREATE TABLE IF NOT EXISTS users (
chat_id INTEGER PRIMARY KEY,
lang TEXT DEFAULT ‘ru’,
subscribed INTEGER DEFAULT 1
)
“””)
c.execute(”””
CREATE TABLE IF NOT EXISTS alert_history (
id INTEGER PRIMARY KEY AUTOINCREMENT,
alert_id TEXT,
source TEXT,
cities TEXT,
sent_at TEXT DEFAULT (datetime(‘now’))
)
“””)
conn.commit()
conn.close()

def db_get_lang(chat_id):
conn = sqlite3.connect(DB_FILE)
row = conn.execute(“SELECT lang FROM users WHERE chat_id=?”, (chat_id,)).fetchone()
conn.close()
return row[0] if row else “ru”

def db_set_lang(chat_id, lang):
conn = sqlite3.connect(DB_FILE)
conn.execute(”””
INSERT INTO users (chat_id, lang, subscribed) VALUES (?, ?, 1)
ON CONFLICT(chat_id) DO UPDATE SET lang=excluded.lang
“””, (chat_id, lang))
conn.commit()
conn.close()

def db_subscribe(chat_id, lang=“ru”):
conn = sqlite3.connect(DB_FILE)
conn.execute(”””
INSERT INTO users (chat_id, lang, subscribed) VALUES (?, ?, 1)
ON CONFLICT(chat_id) DO UPDATE SET subscribed=1
“””, (chat_id, lang))
conn.commit()
conn.close()

def db_unsubscribe(chat_id):
conn = sqlite3.connect(DB_FILE)
conn.execute(“UPDATE users SET subscribed=0 WHERE chat_id=?”, (chat_id,))
conn.commit()
conn.close()

def db_get_subscribers():
conn = sqlite3.connect(DB_FILE)
rows = conn.execute(“SELECT chat_id, lang FROM users WHERE subscribed=1”).fetchall()
conn.close()
return rows

def db_save_alert(alert_id, source, cities):
conn = sqlite3.connect(DB_FILE)
conn.execute(
“INSERT INTO alert_history (alert_id, source, cities) VALUES (?, ?, ?)”,
(alert_id, source, “, “.join(cities[:10]))
)
conn.commit()
conn.close()

def lang_keyboard():
return InlineKeyboardMarkup(inline_keyboard=[[
InlineKeyboardButton(text=“🇷🇺 Русский”, callback_data=“lang_ru”),
InlineKeyboardButton(text=“🇬🇧 English”, callback_data=“lang_en”),
]])

def detect_source(data):
combined = ((data.get(“title”) or “”) + “ “ + (data.get(“desc”) or “”)).lower()
if any(kw in combined for kw in IRAN_KEYWORDS):
return “iran”
if any(kw in combined for kw in YEMEN_KEYWORDS):
return “yemen”
if int(data.get(“cat”, 1)) in (13, 101):
return “iran”
return “unknown”

def get_flight_time(cities, source):
times = YEMEN_FLIGHT_TIMES if source == “yemen” else IRAN_FLIGHT_TIMES
return times[“default”]

def fmt_alert(data, arrival, lang, source):
s = STRINGS[lang]
cities = data.get(“data”, [])
cities_str = “, “.join(cities[:8]) if cities else “-”
src_str = s[“from_iran”] if source == “iran” else (
s[“from_yemen”] if source == “yemen” else s[“from_unknown”])
flight = get_flight_time(cities, source)
return (
f”{s[‘alert_header’]}\n”
f”━━━━━━━━━━━━━━━\n”
f”🌍 {src_str}\n\n”
f”📍 <b>{s[‘regions_label’]}:</b> {cities_str}\n”
f”{s[‘launch_detected’]}: {datetime.now(IL_TZ).strftime(’%H:%M:%S’)}\n”
f”{s[‘flight_time’]}: ~{flight} {s[‘min’]}\n”
f”{s[‘expected_arrival’]}: <b>{arrival.strftime(’%H:%M:%S’)}</b>\n”
f”━━━━━━━━━━━━━━━\n”
f”{s[‘shelter_now’]}”
)

def fmt_allclear(data, lang):
s = STRINGS[lang]
cities = data.get(“data”, [])
cities_str = “, “.join(cities[:8]) if cities else “-”
return (
f”{s[‘allclear_header’]}\n”
f”━━━━━━━━━━━━━━━\n”
f”📍 {cities_str}\n\n”
f”{s[‘threat_clear’]}\n”
f”━━━━━━━━━━━━━━━\n”
f”{s[‘follow_oref’]}”
)

async def broadcast_alert(data, arrival, source):
subscribers = db_get_subscribers()
targets = {row[0]: row[1] for row in subscribers}
for chat_id in ALERT_CHAT_IDS:
if chat_id not in targets:
targets[chat_id] = “ru”
for chat_id, lang in targets.items():
try:
await bot.send_message(chat_id, fmt_alert(data, arrival, lang, source), parse_mode=“HTML”)
except Exception as e:
logger.error(f”broadcast_alert error {chat_id}: {e}”)

async def broadcast_allclear(data):
subscribers = db_get_subscribers()
targets = {row[0]: row[1] for row in subscribers}
for chat_id in ALERT_CHAT_IDS:
if chat_id not in targets:
targets[chat_id] = “ru”
for chat_id, lang in targets.items():
try:
await bot.send_message(chat_id, fmt_allclear(data, lang), parse_mode=“HTML”)
except Exception as e:
logger.error(f”broadcast_allclear error {chat_id}: {e}”)

async def fetch_oref(session):
try:
async with session.get(
OREF_ALERTS_URL, headers=OREF_HEADERS,
timeout=aiohttp.ClientTimeout(total=5), ssl=False
) as r:
if r.status == 200:
text = (await r.text(encoding=“utf-8-sig”)).strip()
if text:
return json.loads(text)
except Exception as e:
logger.debug(f”fetch_oref: {e}”)
return None

async def monitor_alerts():
logger.info(“Monitoring started”)
async with aiohttp.ClientSession() as session:
while True:
try:
data = await fetch_oref(session)
if data:
alert_id = str(data.get(“id”, “”))
cities = data.get(“data”, [])
if alert_id and alert_id not in seen_alert_ids:
seen_alert_ids.add(alert_id)
source = detect_source(data)
flight = get_flight_time(cities, source)
arrival_il = (datetime.now(timezone.utc) + timedelta(minutes=flight)).astimezone(IL_TZ)
await broadcast_alert(data, arrival_il, source)
db_save_alert(alert_id, source, cities)
active_alerts[alert_id] = {“data”: data, “source”: source, “arrival”: arrival_il}
logger.info(f”ALERT id={alert_id} source={source}”)
else:
now_il = datetime.now(IL_TZ)
for aid, info in list(active_alerts.items()):
if now_il > info[“arrival”]:
await broadcast_allclear(info[“data”])
del active_alerts[aid]
logger.info(f”ALL CLEAR id={aid}”)
except Exception as e:
logger.error(f”monitor error: {e}”)
await asyncio.sleep(POLL_INTERVAL)

@dp.message(Command(“start”))
async def cmd_start(message: Message):
await message.answer(STRINGS[“ru”][“start_msg”], reply_markup=lang_keyboard(), parse_mode=“HTML”)

@dp.message(Command(“lang”))
async def cmd_lang(message: Message):
await message.answer(“Выберите язык / Choose language:”, reply_markup=lang_keyboard())

@dp.callback_query(F.data.startswith(“lang_”))
async def cb_lang(cb: CallbackQuery):
lang = cb.data.split(”_”)[1]
chat_id = cb.message.chat.id
db_set_lang(chat_id, lang)
db_subscribe(chat_id, lang)
s = STRINGS[lang]
await cb.message.edit_text(s[“lang_set”], parse_mode=“HTML”)
await cb.answer()

@dp.message(Command(“stop”))
async def cmd_stop(message: Message):
db_unsubscribe(message.chat.id)
lang = db_get_lang(message.chat.id)
await message.answer(STRINGS[lang][“unsubscribed”])

@dp.message(Command(“status”))
async def cmd_status(message: Message):
chat_id = message.chat.id
lang = db_get_lang(chat_id)
s = STRINGS[lang]
if not active_alerts:
await message.answer(s[“no_alerts”], parse_mode=“HTML”)
return
lines = [s[“active_alerts_header”]]
for info in active_alerts.values():
cities = info[“data”].get(“data”, [])
src = s[“from_iran”] if info[“source”] == “iran” else (
s[“from_yemen”] if info[“source”] == “yemen” else s[“from_unknown”])
lines.append(f”• {src}: {’, ‘.join(cities[:3])}\n  {s[‘arrival_label’]}: {info[‘arrival’].strftime(’%H:%M:%S’)}”)
await message.answer(”\n”.join(lines), parse_mode=“HTML”)

async def main():
init_db()
asyncio.create_task(monitor_alerts())
logger.info(“Bot started”)
await dp.start_polling(bot)

if **name** == “**main**”:
asyncio.run(main())
