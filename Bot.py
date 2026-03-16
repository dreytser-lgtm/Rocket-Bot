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

BOT_TOKEN = os.getenv("BOT_TOKEN", "8682396682:AAFJw9BgaIL8T1mPTYKP_iQzMARbv6iCEiw")
ALERT_CHAT_IDS = []
POLL_INTERVAL = 5
DB_FILE = "bot.db"
IL_TZ = pytz.timezone("Asia/Jerusalem")
OREF_ALERTS_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HEADERS = {"Referer": "https://www.oref.org.il/", "X-Requested-With": "XMLHttpRequest", "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
