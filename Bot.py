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

# ========================

# НАСТРОЙКИ

# ========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8682396682:AAFJw9BgaIL8T1mPTYKP_iQzMARbv6iCEiw")

# ID каналов куда слать оповещения (добавь свой канал)

ALERT_CHAT_IDS: list[int] = [
# -1001234567890,
]

POLL_INTERVAL = 5  # секунд между проверками API
DB_FILE = "bot.db"
IL_TZ = pytz.timezone("Asia/Jerusalem")
OREF_ALERTS_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HEADERS = {
"Referer": "https://www.oref.org.il/",
"X-Requested-With": "XMLHttpRequest",
"Accept": "application/json",
"User-Agent": "Mozilla/5.0",
}

# ========================

# БАЗА ДАННЫХ (SQLite)

# ========================

def init_db():
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
chat_id INTEGER PRIMARY KEY,
lang TEXT DEFAULT 'ru',
subscribed INTEGER DEFAULT 1,
created_at TEXT DEFAULT (datetime('now'))
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS alert_history (
id INTEGER PRIMARY KEY AUTOINCREMENT,
alert_id TEXT,
source TEXT,
cities TEXT,
sent_at TEXT DEFAULT (datetime('now'))
)
""")
conn.commit()
conn.close()

def db_get_lang(chat_id: int) -> str:
conn = sqlite3.connect(DB_FILE)
row = conn.execute("SELECT lang FROM users WHERE chat_id=?", (chat_id,)).fetchone()
conn.close()
return row[0] if row else "ru"

def db_set_lang(chat_id: int, lang: str):
conn = sqlite3.connect(DB_FILE)
conn.execute("""
INSERT INTO users (chat_id, lang, subscribed) VALUES (?, ?, 1)
ON CONFLICT(chat_id) DO UPDATE SET lang=excluded.lang
""", (chat_id, lang))
conn.commit()
conn.close()

def db_subscribe(chat_id: int, lang: str = "ru"):
conn = sqlite3.connect(DB_FILE)
conn.execute("""
INSERT INTO users (chat_id, lang, subscribed) VALUES (?, ?, 1)
ON CONFLICT(chat_id) DO UPDATE SET subscribed=1
""", (chat_id, lang))
conn.commit()
conn.close()

def db_unsubscribe(chat_id: int):
conn = sqlite3.connect(DB_FILE)
conn.execute("UPDATE users SET subscribed=0 WHERE chat_id=?", (chat_id,))
conn.commit()
conn.close()

def db_get_subscribers() -> list[tuple[int, str]]:
"""Возвращает список (chat_id, lang) всех подписчиков."""
conn = sqlite3.connect(DB_FILE)
rows = conn.execute("SELECT chat_id, lang FROM users WHERE subscribed=1").fetchall()
conn.close()
return rows

def db_save_alert(alert_id: str, source: str, cities: list[str]):
conn = sqlite3.connect(DB_FILE)
conn.execute(
"INSERT INTO alert_history (alert_id, source, cities) VALUES (?, ?, ?)",
(alert_id, source, ", ".join(cities[:10]))
)
conn.commit()
conn.close()

# ========================

# ПЕРЕВОДЫ

# ========================

STRINGS = {
"ru": {
"start_msg": (
"🚨 <b>Бот оповещения о ракетных атаках</b>\n\n"
"Слежу за Пикуд ха-Ореф 24/7.\n"
"Оповещаю о ракетах из <b>Ирана 🇮🇷</b> и <b>Йемена 🇾🇪</b>.\n\n"
"Выберите язык / Choose language / בחר שפה:"
),
"lang_set": "✅ Язык: Русский",
"subscribed": "✅ Вы подписаны на оповещения.",
"unsubscribed": "🔕 Вы отписались от оповещений.\nЧтобы снова подписаться — /start",
"no_alerts": "✅ <b>Тревог нет.</b> Всё спокойно.",
"active_alerts_header": "🔴 <b>Активные тревоги:</b>\n",
"regions_label": "Районы",
"arrival_label": "Прибытие",
"alert_header": "🔴 <b>ТРЕВОГА!</b>",
"launch_detected": "🕐 Обнаружен пуск",
"flight_time": "⏱ Время полёта",
"expected_arrival": "🎯 Ожидаемое прибытие",
"shelter_now": "⚠️ <i>Немедленно укройтесь в убежище!</i>",
"allclear_header": "🟢 <b>ОТБОЙ</b>",
"intercepted": "✅ <b>Перехвачена!</b> Успешный перехват.",
"not_intercepted": "💥 <b>Данные о перехвате уточняются.</b>",
"threat_clear": "ℹ️ <b>Угроза миновала.</b>",
"follow_oref": "📻 <i>Следите за Пикуд ха-Ореф</i>",
"min": "мин",
"from_iran": "Иран 🇮🇷",
"from_yemen": "Йемен 🇾🇪",
"from_unknown": "Неизвестный источник ⚠️",
"help": "/start — подписаться\n/stop — отписаться\n/status — текущий статус\n/lang — сменить язык",
},
"en": {
"start_msg": (
"🚨 <b>Rocket Alert Bot — Israel</b>\n\n"
"Monitoring Pikud HaOref 24/7.\n"
"Alerts from <b>Iran 🇮🇷</b> and <b>Yemen 🇾🇪</b>.\n\n"
"Выберите язык / Choose language / בחר שפה:"
),
"lang_set": "✅ Language: English",
"subscribed": "✅ You are subscribed to alerts.",
"unsubscribed": "🔕 You unsubscribed.\nTo subscribe again — /start",
"no_alerts": "✅ <b>No alerts.</b> All clear.",
"active_alerts_header": "🔴 <b>Active alerts:</b>\n",
"regions_label": "Areas",
"arrival_label": "Arrival",
"alert_header": "🔴 <b>ALERT!</b>",
"launch_detected": "🕐 Launch detected",
"flight_time": "⏱ Flight time",
"expected_arrival": "🎯 Expected arrival",
"shelter_now": "⚠️ <i>Take shelter immediately!</i>",
"allclear_header": "🟢 <b>ALL CLEAR</b>",
"intercepted": "✅ <b>Intercepted!</b> Successful interception.",
"not_intercepted": "💥 <b>Interception data pending.</b>",
"threat_clear": "ℹ️ <b>Threat has passed.</b>",
"follow_oref": "📻 <i>Follow Pikud HaOref for updates</i>",
"min": "min",
"from_iran": "Iran 🇮🇷",
"from_yemen": "Yemen 🇾🇪",
"from_unknown": "Unknown source ⚠️",
"help": "/start — subscribe\n/stop — unsubscribe\n/status — current status\n/lang — change language",
},
"he": {
"start_msg": (
"🚨 <b>בוט התראות טילים – ישראל</b>\n\n"
"מעקב אחר פיקוד העורף 24/7.\n"
"התראות על טילים מ<b>איראן 🇮🇷</b> ומ<b>תימן 🇾🇪</b>.\n\n"
"Выберите язык / Choose language / בחר שפה:"
),
"lang_set": "✅ שפה: עברית",
"subscribed": "✅ נרשמת להתראות.",
"unsubscribed": "🔕 בוטלה הרשמתך.\nלהרשמה מחדש — /start",
"no_alerts": "✅ <b>אין התראות.</b> הכל שקט.",
"active_alerts_header": "🔴 <b>התראות פעילות:</b>\n",
"regions_label": "אזורים",
"arrival_label": "הגעה צפויה",
"alert_header": "🔴 <b>!התראה</b>",
"launch_detected": "🕐 זוהה שיגור",
"flight_time": "⏱ זמן טיסה",
"expected_arrival": "🎯 צפי הגעה",
"shelter_now": "⚠️ <i>!היכנסו מיד למרחב המוגן</i>",
"allclear_header": "🟢 <b>ביטול התראה</b>",
"intercepted": "✅ <b>!יורט בהצלחה</b>",
"not_intercepted": "💥 <b>בירור נתוני יירוט בתהליך.</b>",
"threat_clear": "ℹ️ <b>האיום חלף.</b>",
"follow_oref": "📻 <i>עקבו אחר פיקוד העורף</i>",
"min": "דק'",
"from_iran": "איראן 🇮🇷",
"from_yemen": "תימן 🇾🇪",
"from_unknown": "מקור לא ידוע ⚠️",
"help": "/start — הרשמה\n/stop — ביטול\n/status — סטטוס נוכחי\n/lang — שינוי שפה",
},
}

# ========================

# РЕГИОНЫ И ВРЕМЯ ПОЛЁТА

# ========================

IRAN_FLIGHT_TIMES = {
"צפון": 10, "גליל": 10, "נהריה": 10, "עכו": 11,
"חיפה": 11, "כרמל": 11,
"מרכז": 12, "תל אביב": 12, "גוש דן": 12,
"ירושלים": 12, "בית שמש": 12,
"שפלה": 13, "אשדוד": 13, "אשקלון": 13,
"דרום": 14, "באר שבע": 14, "נגב": 15,
"אילת": 18,
"default": 12,
}

YEMEN_FLIGHT_TIMES = {
"צפון": 17, "גליל": 17, "נהריה": 17, "עכו": 17,
"חיפה": 17, "כרמל": 17,
"מרכז": 18, "תל אביב": 18, "גוש דן": 18,
"ירושלים": 18, "בית שמש": 18,
"שפלה": 19, "אשדוד": 19, "אשקלון": 19,
"דרום": 16, "באר שבע": 16, "נגב": 15,
"אילת": 12,
"default": 18,
}

REGION_TRANSLATIONS = {
"צפון":     {"ru": "Север",       "en": "North",      "he": "צפון"},
"גליל":     {"ru": "Галилея",     "en": "Galilee",    "he": "גליל"},
"חיפה":     {"ru": "Хайфа",       "en": "Haifa",      "he": "חיפה"},
"עכו":      {"ru": "Акко",        "en": "Akko",       "he": "עכו"},
"נהריה":    {"ru": "Нагария",     "en": "Nahariya",   "he": "נהריה"},
"גוש דן":   {"ru": "Гуш Дан",    "en": "Gush Dan",   "he": "גוש דן"},
"תל אביב":  {"ru": "Тель-Авив",  "en": "Tel Aviv",   "he": "תל אביב"},
"מרכז":     {"ru": "Центр",       "en": "Center",     "he": "מרכז"},
"ירושלים":  {"ru": "Иерусалим",  "en": "Jerusalem",  "he": "ירושלים"},
"שפלה":     {"ru": "Шфела",       "en": "Shfela",     "he": "שפלה"},
"אשדוד":    {"ru": "Ашдод",       "en": "Ashdod",     "he": "אשדוד"},
"אשקלון":   {"ru": "Ашкелон",     "en": "Ashkelon",   "he": "אשקלון"},
"דרום":     {"ru": "Юг",          "en": "South",      "he": "דרום"},
"באר שבע":  {"ru": "Беэр-Шева",  "en": "Beer Sheva", "he": "באר שבע"},
"נגב":      {"ru": "Негев",       "en": "Negev",      "he": "נגב"},
"אילת":     {"ru": "Эйлат",       "en": "Eilat",      "he": "אילת"},
}

IRAN_KEYWORDS  = ["איראן", "iran", "שיגור בליסטי", "ballistic"]
YEMEN_KEYWORDS = ["תימן", "yemen", "חות'ים", "houthi"]

ALERT_CATEGORIES = {
1:   {"ru": "🚀 Ракетный обстрел",       "en": "🚀 Missile attack",    "he": "🚀 ירי טילים"},
2:   {"ru": "☢️ Угроза БПЛА",            "en": "☢️ UAV threat",        "he": "☢️ איום כטבם"},
6:   {"ru": "🚨 Теракт",                 "en": "🚨 Terror threat",     "he": "🚨 פיגוע"},
13:  {"ru": "🚀 Баллистическая ракета",  "en": "🚀 Ballistic missile", "he": "🚀 טיל בליסטי"},
101: {"ru": "🚀 Ракета (Иран/Йемен)",    "en": "🚀 Missile (Iran/Yemen)", "he": "🚀 טיל (איראן/תימן)"},
}

logging.basicConfig(
level=logging.INFO,
format="%(asctime)s %(levelname)s %(message)s",
handlers=[
logging.StreamHandler(),
logging.FileHandler("bot.log", encoding="utf-8"),
]
)
logger = logging.getLogger(**name**)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

seen_alert_ids: set  = set()
active_alerts:  dict = {}

# ========================

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ

# ========================

def lang_keyboard() -> InlineKeyboardMarkup:
return InlineKeyboardMarkup(inline_keyboard=[[
InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
InlineKeyboardButton(text="🇮🇱 עברית",   callback_data="lang_he"),
]])

def detect_source(data: dict) -> str:
combined = ((data.get("title") or "") + " " + (data.get("desc") or "")).lower()
if any(kw.lower() in combined for kw in IRAN_KEYWORDS):
return "iran"
if any(kw.lower() in combined for kw in YEMEN_KEYWORDS):
return "yemen"
if int(data.get("cat", 1)) in (13, 101):
return "iran"
return "unknown"

def get_flight_time(cities: list[str], source: str) -> int:
times = YEMEN_FLIGHT_TIMES if source == "yemen" else IRAN_FLIGHT_TIMES
for city in cities:
for region, mins in times.items():
if region != "default" and region in city:
return mins
return times["default"]

def translate_cities(cities: list[str], lang: str) -> list[str]:
result = []
for city in cities[:8]:
translated = city
for he_name, tr in REGION_TRANSLATIONS.items():
if he_name in city:
translated = tr.get(lang, city)
break
result.append(translated)
return result

def fmt_alert(data: dict, arrival: datetime, lang: str, source: str) -> str:
s       = STRINGS[lang]
cities  = data.get("data", [])
cat     = int(data.get("cat", 1))
atype   = ALERT_CATEGORIES.get(cat, ALERT_CATEGORIES[1])[lang]
tr_cities = translate_cities(cities, lang)
src_str = s["from_iran"] if source == "iran" else (
s["from_yemen"] if source == "yemen" else s["from_unknown"])
return (
f"{s['alert_header']}\n"
f"━━━━━━━━━━━━━━━\n"
f"{atype}\n"
f"🌍 {src_str}\n\n"
f"📍 <b>{s['regions_label']}:</b> {', '.join(tr_cities) or '—'}\n"
f"{s['launch_detected']}: {datetime.now(IL_TZ).strftime('%H:%M:%S')}\n"
f"{s['flight_time']}: ~{get_flight_time(cities, source)} {s['min']}\n"
f"{s['expected_arrival']}: <b>{arrival.strftime('%H:%M:%S')}</b>\n"
f"━━━━━━━━━━━━━━━\n"
f"{s['shelter_now']}"
)

def fmt_allclear(data: dict, lang: str) -> str:
s = STRINGS[lang]
tr_cities = translate_cities(data.get("data", []), lang)
return (
f"{s['allclear_header']}\n"
f"━━━━━━━━━━━━━━━\n"
f"📍 {', '.join(tr_cities) or '—'}\n\n"
f"{s['threat_clear']}\n"
f"━━━━━━━━━━━━━━━\n"
f"{s['follow_oref']}"
)

async def broadcast_alert(data: dict, arrival: datetime, source: str):
subscribers = db_get_subscribers()
targets = {row[0]: row[1] for row in subscribers}
for chat_id in ALERT_CHAT_IDS:
if chat_id not in targets:
targets[chat_id] = "ru"
for chat_id, lang in targets.items():
try:
await bot.send_message(chat_id, fmt_alert(data, arrival, lang, source), parse_mode="HTML")
except Exception as e:
logger.error(f"broadcast_alert → {chat_id}: {e}")

async def broadcast_allclear(data: dict):
subscribers = db_get_subscribers()
targets = {row[0]: row[1] for row in subscribers}
for chat_id in ALERT_CHAT_IDS:
if chat_id not in targets:
targets[chat_id] = "ru"
for chat_id, lang in targets.items():
try:
await bot.send_message(chat_id, fmt_allclear(data, lang), parse_mode="HTML")
except Exception as e:
logger.error(f"broadcast_allclear → {chat_id}: {e}")

# ========================

# МОНИТОРИНГ 24/7

# ========================

async def monitor_alerts():
logger.info("🟢 Мониторинг тревог запущен")
async with aiohttp.ClientSession() as session:
while True:
try:
data = await fetch_oref(session)
if data:
alert_id = str(data.get("id", ""))
cities   = data.get("data", [])
if alert_id and alert_id not in seen_alert_ids:
seen_alert_ids.add(alert_id)
source     = detect_source(data)
flight     = get_flight_time(cities, source)
arrival_il = (datetime.now(timezone.utc) + timedelta(minutes=flight)).astimezone(IL_TZ)

```
                    await broadcast_alert(data, arrival_il, source)
                    db_save_alert(alert_id, source, cities)
                    active_alerts[alert_id] = {"data": data, "source": source, "arrival": arrival_il}
                    logger.info(f"🚨 ТРЕВОГА id={alert_id} source={source} cities={cities[:3]}")
            else:
                now_il = datetime.now(IL_TZ)
                for aid, info in list(active_alerts.items()):
                    if now_il > info["arrival"]:
                        await broadcast_allclear(info["data"])
                        del active_alerts[aid]
                        logger.info(f"✅ Отбой id={aid}")
        except Exception as e:
            logger.error(f"monitor_alerts error: {e}")
        await asyncio.sleep(POLL_INTERVAL)
```

async def fetch_oref(session: aiohttp.ClientSession) -> dict | None:
try:
async with session.get(
OREF_ALERTS_URL, headers=OREF_HEADERS,
timeout=aiohttp.ClientTimeout(total=5), ssl=False
) as r:
if r.status == 200:
text = (await r.text(encoding="utf-8-sig")).strip()
if text:
return json.loads(text)
except Exception as e:
logger.debug(f"fetch_oref: {e}")
return None

# ========================

# КОМАНДЫ БОТА

# ========================

@dp.message(Command("start"))
async def cmd_start(message: Message):
await message.answer(STRINGS["ru"]["start_msg"], reply_markup=lang_keyboard(), parse_mode="HTML")

@dp.message(Command("lang"))
async def cmd_lang(message: Message):
await message.answer("Выберите язык / Choose language / בחר שפה:", reply_markup=lang_keyboard())

@dp.callback_query(F.data.startswith("lang_"))
async def cb_lang(cb: CallbackQuery):
lang    = cb.data.split("_")[1]
chat_id = cb.message.chat.id
db_set_lang(chat_id, lang)
db_subscribe(chat_id, lang)
s = STRINGS[lang]
await cb.message.edit_text(
f"{s['lang_set']}\n{s['subscribed']}\n\n<b>Команды:</b>\n{s['help']}",
parse_mode="HTML"
)
await cb.answer()

@dp.message(Command("stop"))
async def cmd_stop(message: Message):
db_unsubscribe(message.chat.id)
lang = db_get_lang(message.chat.id)
await message.answer(STRINGS[lang]["unsubscribed"])

@dp.message(Command("status"))
async def cmd_status(message: Message):
chat_id = message.chat.id
lang    = db_get_lang(chat_id)
s       = STRINGS[lang]
if not active_alerts:
await message.answer(s["no_alerts"], parse_mode="HTML")
return
lines = [s["active_alerts_header"]]
for info in active_alerts.values():
cities = translate_cities(info["data"].get("data", []), lang)
src    = s["from_iran"] if info["source"] == "iran" else (
s["from_yemen"] if info["source"] == "yemen" else s["from_unknown"])
lines.append(f"• {src}: {', '.join(cities[:3])}\n  {s['arrival_label']}: {info['arrival'].strftime('%H:%M:%S')}")
await message.answer("\n".join(lines), parse_mode="HTML")

# ========================

# ЗАПУСК

# ========================

async def main():
init_db()
asyncio.create_task(monitor_alerts())
logger.info("🤖 Бот запущен")
await dp.start_polling(bot)

if **name** == "**main**":
asyncio.run(main())
