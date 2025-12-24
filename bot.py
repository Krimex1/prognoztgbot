import os
import asyncio
import logging
import sqlite3
import time
import re
from typing import List, Dict, Optional, Tuple, Any

import aiohttp # Используем для парсинга курсов валют
import ccxt.async_support as ccxt
import google.generativeai as genai
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    CallbackQuery,
)
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

# ==============================================================================
# CONFIGURATION
# ==============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN") # ← ВСТАВЬ СВОЙ TOKEN
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GOOGLE_GEMINI_API_KEY")
DB_FILE = "crypto_ai_analyst.db"

RSI_PERIOD = 14
SMA_PERIOD = 20
AI_CACHE_TTL = 60  # кэш AI-ответов на 60 секунд
FIAT_CACHE_TTL = 3600  # кэш курсов валют на 1 час (обновляем реже, они стабильнее крипты)
ALERT_CHECK_DELAY = 60  # интервал фонового сканера, сек

# Список монет
COINS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
    "TON/USDT", "NOT/USDT", "TRX/USDT", "XRP/USDT",
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "HMSTR/USDT",
    "LTC/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT",
    "LINK/USDT", "ATOM/USDT", "NEAR/USDT", "MATIC/USDT",
    "UNI/USDT", "APT/USDT", "ARB/USDT", "OP/USDT",
    "VET/USDT", "RNDR/USDT", "IMX/USDT", "STX/USDT",
    "SUI/USDT", "TIA/USDT", "SEI/USDT", "FTM/USDT",
    "INJ/USDT", "LDO/USDT", "RUNE/USDT", "AR/USDT"
]

CURRENCY_SYMBOLS = {"USD": "$", "RUB": "₽", "EUR": "€"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("CryptoAIAnalyst")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Кэш для курсов фиата и AI-ответов
# По умолчанию ставим заглушки, они обновятся при первом запросе
fiat_cache: Dict[str, Any] = {"RUB": 100.0, "EUR": 0.95, "ts": 0.0}
ai_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

# Конфигурация Gemini
if GEMINI_KEY and not GEMINI_KEY.startswith("ВАШ_"):
    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel("gemini-2.5-flash")
else:
    gemini_model = None

# ==============================================================================
# DATABASE (sqlite3)
# ==============================================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                currency TEXT DEFAULT 'USD',
                analysis_mode TEXT DEFAULT 'AI',
                alert_percent REAL DEFAULT 3.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subs (
                user_id INTEGER,
                coin TEXT,
                PRIMARY KEY (user_id, coin)
            )
        """)
    conn.close()

def get_user(user_id: int) -> dict:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        with conn:
            conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.close()
        return {"user_id": user_id, "currency": "USD", "analysis_mode": "AI", "alert_percent": 3.0}
    data = dict(row)
    conn.close()
    return data

def update_user(user_id: int, column: str, value: Any):
    conn = sqlite3.connect(DB_FILE)
    with conn:
        conn.execute(f"UPDATE users SET {column} = ? WHERE user_id = ?", (value, user_id))
    conn.close()

def toggle_sub(user_id: int, coin: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM subs WHERE user_id = ? AND coin = ?", (user_id, coin))
    exists = cur.fetchone()
    with conn:
        if exists:
            conn.execute("DELETE FROM subs WHERE user_id = ? AND coin = ?", (user_id, coin))
            conn.close()
            return False
        conn.execute("INSERT INTO subs (user_id, coin) VALUES (?, ?)", (user_id, coin))
    conn.close()
    return True

def get_subs(user_id: int) -> List[str]:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT coin FROM subs WHERE user_id = ?", (user_id,))
    res = [r[0] for r in cur.fetchall()]
    conn.close()
    return res

def get_subscribers(coin: str) -> List[dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT u.user_id, u.currency, u.alert_percent
        FROM subs s
        JOIN users u ON u.user_id = s.user_id
        WHERE s.coin = ?
    """, (coin,))
    res = [dict(r) for r in cur.fetchall()]
    conn.close()
    return res

# ==============================================================================
# MARKET DATA & TECH ANALYSIS
# ==============================================================================

async def get_fiat_rates() -> Dict[str, float]:
    """
    Парсит актуальные курсы валют с открытого API.
    """
    now = time.time()
    # Если кэш свежий, возвращаем его
    if now - fiat_cache["ts"] < FIAT_CACHE_TTL:
        return fiat_cache

    try:
        async with aiohttp.ClientSession() as session:
            # Используем бесплатный и надежный API для курсов относительно USD
            async with session.get('https://api.exchangerate-api.com/v4/latest/USD') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates = data.get('rates', {})
                    # Обновляем кэш (USD -> RUB, USD -> EUR)
                    if 'RUB' in rates:
                        fiat_cache["RUB"] = rates['RUB']
                    if 'EUR' in rates:
                        fiat_cache["EUR"] = rates['EUR']
                    fiat_cache["ts"] = now
                    logger.info(f"Fiat rates updated: USD/RUB={fiat_cache['RUB']}, USD/EUR={fiat_cache['EUR']}")
                else:
                    logger.error("Failed to fetch fiat rates: Status not 200")
    except Exception as e:
        logger.error(f"Fiat update error: {e}")

    return fiat_cache

def convert_price_usd(price_usd: float, currency: str, rates: Dict[str, float]) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    if currency == "USD":
        value = price_usd
    elif currency == "RUB":
        value = price_usd * rates["RUB"]
    elif currency == "EUR":
        value = price_usd * rates["EUR"]
    else:
        value = price_usd

    if value < 1:
        return f"{symbol}{value:.4f}"
    if value < 100:
        return f"{symbol}{value:.2f}"
    return f"{symbol}{value:,.0f}".replace(",", " ")

def calc_rsi(prices: List[float], period: int = RSI_PERIOD) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [abs(d) if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(prices) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_sma(prices: List[float], period: int = SMA_PERIOD) -> Optional[float]:
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

# ==============================================================================
# GEMINI AI INTEGRATION
# ==============================================================================

async def get_ai_analysis(
    coin: str,
    price_usd: float,
    rsi: Optional[float],
    change_24h: float,
    volume_usdt: float,
    distance_from_high_pct: float,
    mode_label: str,
) -> Optional[str]:
    if gemini_model is None:
        return None

    try:
        # Подготовка строки RSI заранее
        rsi_str = f"{rsi:.2f}" if rsi is not None else "нет данных"
        
        base_prompt = (
            f"Монета: {coin}\n"
            f"Текущая цена (USDT): {price_usd:.4f}\n"
            f"RSI(14): {rsi_str}\n"
            f"Изменение за 24ч (%): {change_24h:.2f}\n"
            f"Объем за 24ч (USDT): {volume_usdt:.0f}\n"
            f"Отдаление от локального максимума 24ч (%): {distance_from_high_pct:.2f}\n"
            f"Режим анализа: {mode_label}\n\n"
            "Сформируй короткий вывод в 3-6 предложениях."
        )

        system_prompt = (
            "Ты — опытный крипто-трейдер с циничным, но профессиональным стилем речи. "
            "Твоя задача — проанализировать технические данные монеты и дать краткий, "
            "жесткий и понятный вердикт на русском языке. Не используй сложные термины "
            "без объяснения. Скажи прямо: покупать, продавать или ждать. Используй эмодзи."
        )

        # ИСПРАВЛЕНО: Убраны артефакты
        # Мы просто склеиваем инструкции в один текст
        full_prompt = f"{system_prompt}\n\n{base_prompt}"
        
        # И отправляем как простую строку
        response = await gemini_model.generate_content_async(full_prompt)
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        return None
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None

# ==============================================================================
# KEYBOARDS
# ==============================================================================

def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🧠 AI Прогноз"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔔 Подписки"), KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def settings_kb(user: dict) -> InlineKeyboardMarkup:
    curr = user["currency"]
    mode = user["analysis_mode"]
    alert = user["alert_percent"]
    
    kb = [
        [
            InlineKeyboardButton(
                text=f"{'✅ ' if curr=='USD' else ''}🇺🇸 USD", callback_data="set_curr_USD"
            ),
            InlineKeyboardButton(
                text=f"{'✅ ' if curr=='RUB' else ''}🇷🇺 RUB", callback_data="set_curr_RUB"
            ),
            InlineKeyboardButton(
                text=f"{'✅ ' if curr=='EUR' else ''}🇪🇺 EUR", callback_data="set_curr_EUR"
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"Чувствительность: {alert:.1f}%", callback_data="cycle_alert"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Режим: {'🧊 Алгоритм' if mode=='ALG' else '🧠 AI'}",
                callback_data="toggle_mode",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def coins_kb(page: int, mode: str, user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    per_page = 10
    start = page * per_page
    end = start + per_page
    coins_page = COINS[start:end]
    subs = get_subs(user_id) if (user_id and mode == "subs") else []

    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []

    for coin in coins_page:
        ticker = coin.split("/")[0]
        if mode == "ai":
            text = f"🧠 {ticker}"
            cb = f"ai_{coin}_{page}"
        elif mode == "stats":
            text = f"📊 {ticker}"
            cb = f"st_{coin}_{page}"
        else:  # subs
            sub_mark = "✅" if coin in subs else "☑️"
            text = f"{sub_mark} {ticker}"
            cb = f"sub_{coin}_{page}"

        row.append(InlineKeyboardButton(text=text, callback_data=cb))
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    nav_row: List[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"pg_{mode}_{page-1}"))
    if end < len(COINS):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"pg_{mode}_{page+1}"))
    if nav_row:
        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)

# ==============================================================================
# HANDLERS
# ==============================================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer(
        "🧠 Crypto AI Analyst\n\n"
        "Я анализирую рынок, зову на помощь Gemini и говорю простым языком.\n"
        "Нажми кнопку AI Прогноз или напиши сумму, например: 100 TON",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

@dp.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: types.Message):
    user = get_user(message.from_user.id)
    await message.answer(
        "⚙️ Настройки профиля:", parse_mode="HTML", reply_markup=settings_kb(user)
    )

@dp.callback_query(F.data.startswith("set_curr_"))
async def cb_set_curr(call: CallbackQuery):
    _, _, code = call.data.split("_")
    update_user(call.from_user.id, "currency", code)
    await call.message.edit_reply_markup(reply_markup=settings_kb(get_user(call.from_user.id)))
    await call.answer(f"Валюта отображения: {code}")

@dp.callback_query(F.data == "cycle_alert")
async def cb_cycle_alert(call: CallbackQuery):
    user = get_user(call.from_user.id)
    options = [1.0, 3.0, 5.0]
    try:
        idx = options.index(float(user["alert_percent"]))
        new_val = options[(idx + 1) % len(options)]
    except ValueError:
        new_val = 3.0
    update_user(call.from_user.id, "alert_percent", new_val)
    await call.message.edit_reply_markup(reply_markup=settings_kb(get_user(call.from_user.id)))
    await call.answer(f"Чувствительность: {new_val:.1f}%")

@dp.callback_query(F.data == "toggle_mode")
async def cb_toggle_mode(call: CallbackQuery):
    user = get_user(call.from_user.id)
    new_mode = "ALG" if user["analysis_mode"] == "AI" else "AI"
    update_user(call.from_user.id, "analysis_mode", new_mode)
    await call.message.edit_reply_markup(reply_markup=settings_kb(get_user(call.from_user.id)))
    await call.answer(f"Режим: {'AI' if new_mode=='AI' else 'Алгоритмический'}")

# --- Меню выбора монет ---

@dp.message(F.text == "🧠 AI Прогноз")
async def menu_ai(message: types.Message):
    await message.answer(
        "Выбери монету для анализа:", reply_markup=coins_kb(0, "ai"), parse_mode="HTML"
    )

@dp.message(F.text == "📊 Статистика")
async def menu_stats(message: types.Message):
    await message.answer(
        "Выбери монету для статистики за 24ч:",
        reply_markup=coins_kb(0, "stats"),
        parse_mode="HTML",
    )

@dp.message(F.text == "🔔 Подписки")
async def menu_subs(message: types.Message):
    await message.answer(
        "Нажми на монету, чтобы подписаться/отписаться от сигналов:",
        reply_markup=coins_kb(0, "subs", message.from_user.id),
        parse_mode="HTML",
    )

@dp.callback_query(F.data.startswith("pg_"))
async def cb_page(call: CallbackQuery):
    _, mode, page = call.data.split("_")
    page_i = int(page)
    uid = call.from_user.id
    await call.message.edit_reply_markup(
        reply_markup=coins_kb(page_i, mode, uid if mode == "subs" else None)
    )
    await call.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def cb_sub(call: CallbackQuery):
    _, coin, page = call.data.split("_")
    added = toggle_sub(call.from_user.id, coin)
    text = "Подписка включена" if added else "Подписка отключена"
    await call.message.edit_reply_markup(
        reply_markup=coins_kb(int(page), "subs", call.from_user.id)
    )
    await call.answer(text)

# --- Статистика ---

@dp.callback_query(F.data.startswith("st_"))
async def cb_stats(call: CallbackQuery):
    coin = call.data.split("_")[1]
    user = get_user(call.from_user.id)
    await call.message.edit_text(f"📊 Собираю статистику по {coin}...", parse_mode="HTML")

    exchange = ccxt.binance()
    try:
        ticker = await exchange.fetch_ticker(coin)
        price = ticker["last"]
        change_pct = ticker.get("percentage", 0.0) or 0.0
        open_price = ticker.get("open", price - 1e-8)
        abs_change = price - open_price
        high = ticker.get("high", price)
        low = ticker.get("low", price)
        vol = ticker.get("quoteVolume", 0.0)

        rates = await get_fiat_rates()
        price_str = convert_price_usd(price, user["currency"], rates)

        liq_warning = ""
        if vol < 1_000_000:
            liq_warning = "\n⚠️ Мало ликвидности. Спреды могут быть высокими."

        sign = "+" if change_pct >= 0 else ""
        msg = (
            f"📊 Статистика за 24ч: {coin}\n\n"
            f"💰 Цена: {price_str}\n"
            f"📈 Изменение: {sign}{change_pct:.2f}% ({abs_change:+.4f} USDT)\n\n"
            f"🔝 High 24h: {high:.4f}\n"
            f"🔻 Low 24h: {low:.4f}\n"
            f"💸 Объем: {vol:,.0f} USDT{liq_warning}"
        )
        await call.message.edit_text(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Stats error {coin}: {e}")
        await call.message.edit_text("⚠️ Не удалось получить статистику, попробуйте позже.")
    finally:
        await exchange.close()

# --- AI ПРОГНОЗ (Gemini + кэш) ---

@dp.callback_query(F.data.startswith("ai_"))
async def cb_ai(call: CallbackQuery):
    coin = call.data.split("_")[1]
    user = get_user(call.from_user.id)
    currency = user["currency"]
    mode = user["analysis_mode"]

    await call.message.edit_text(f"🧠 Анализирую {coin}...", parse_mode="HTML")

    # Проверяем кэш
    cache_key = (coin, currency)
    now = time.time()
    if cache_key in ai_cache and now - ai_cache[cache_key]["ts"] < AI_CACHE_TTL:
        cached = ai_cache[cache_key]["text"]
        await call.message.edit_text(cached, parse_mode="HTML")
        await call.answer("Ответ из кэша")
        return

    exchange = ccxt.binance()
    try:
        ticker = await exchange.fetch_ticker(coin)
        ohlcv = await exchange.fetch_ohlcv(coin, timeframe="1h", limit=50)
        closes = [c[4] for c in ohlcv]

        price = ticker["last"]
        rsi = calc_rsi(closes)
        change_24 = ticker.get("percentage", 0.0) or 0.0
        high24 = ticker.get("high", price)
        dist_from_high = ((high24 - price) / high24 * 100) if high24 else 0.0
        vol = ticker.get("quoteVolume", 0.0)

        rates = await get_fiat_rates()
        price_str = convert_price_usd(price, currency, rates)

        # Попытка AI-анализа
        ai_text = None
        if mode == "AI":
            ai_text_raw = await get_ai_analysis(
                coin=coin,
                price_usd=price,
                rsi=rsi,
                change_24h=change_24,
                volume_usdt=vol,
                distance_from_high_pct=dist_from_high,
                mode_label="AI",
            )
            if ai_text_raw:
                ai_text = (
                    f"🧠 AI-прогноз по {coin}\n\n"
                    f"💰 Цена: {price_str}\n"
                    f"RSI(14): {int(rsi) if rsi else '-'} | Изм.24ч: {change_24:.2f}%\n\n"
                    f"{ai_text_raw}"
                )

        # Фоллбек: алгоритмический анализ
        if not ai_text:
            bar = "🌤 Норма"
            if rsi is not None:
                if rsi < 30:
                    bar = "🥶 Сильная перепроданность"
                    comment = (
                        "Цена неоправданно низкая. Толпа сливает монету, "
                        "но для терпеливых это может быть хорошая точка входа."
                    )
                    verdict = "🟢 ПОКУПАТЬ / ДОКУПАТЬ"
                elif rsi > 70:
                    bar = "🌋 Перегрев"
                    comment = (
                        "Ажиотаж зашкаливает. Новички залетают на хаях, "
                        "коррекция вниз выглядит очень вероятной."
                    )
                    verdict = "🔴 ФИКСИРОВАТЬ ПРИБЫЛЬ / ЖДАТЬ"
                else:
                    bar = "🌤 Баланс"
                    comment = (
                        "Рынок спокоен, явного перекоса нет. Можно просто держать позицию "
                        "и ждать более сильного сигнала."
                    )
                    verdict = "⚪️ ДЕРЖАТЬ"
            else:
                comment = "Недостаточно данных для RSI, ориентируемся по цене и динамике."
                verdict = "⚪️ НЕЙТРАЛЬНО"

            ai_text = (
                f"🧠 Прогноз по {coin}\n\n"
                f"💰 Цена: {price_str}\n"
                f"🌡 Градусник рынка: {bar}\n\n"
                f"🗣 {comment}\n\n"
                f"⚖️ Вердикт: {verdict}"
            )

        # Сохраняем в кэш и отправляем
        ai_cache[cache_key] = {"text": ai_text, "ts": now}
        await call.message.edit_text(ai_text, parse_mode="HTML")
        await call.answer()
    except Exception as e:
        logger.error(f"AI analyse error {coin}: {e}")
        await call.message.edit_text(
            "⚠️ Не получилось получить данные для анализа, попробуй позже."
        )
    finally:
        await exchange.close()

# --- Калькулятор: 100 TON, 0.5 BTC и т.п. ---

@dp.message(F.text.regexp(r"^(\d+(\.\d+)?)\s+([A-Za-z]+)$"))
async def converter_handler(message: types.Message):
    m = re.match(r"^(\d+(\.\d+)?)\s+([A-Za-z]+)$", message.text.strip())
    if not m:
        return

    amount = float(m.group(1).replace(",", "."))
    symbol = m.group(3).upper()
    pair = f"{symbol}/USDT"

    exchange = ccxt.binance()
    try:
        ticker = await exchange.fetch_ticker(pair)
        price_usd = ticker["last"]
        total_usd = amount * price_usd

        rates = await get_fiat_rates()
        total_rub = total_usd * rates["RUB"]
        total_eur = total_usd * rates["EUR"]

        msg = (
            f"🧮 Конвертация {amount} {symbol}\n\n"
            f"≈ {total_usd:,.2f} USD\n"
            f"≈ {total_rub:,.2f} RUB\n"
            f"≈ {total_eur:,.2f} EUR"
        )
        await message.answer(msg.replace(",", " "), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Converter error {symbol}: {e}")
        await message.answer("⚠️ Не удалось найти такую пару на бирже.")
    finally:
        await exchange.close()

# ==============================================================================
# BACKGROUND MONITOR (Простые алерты по %)
# ==============================================================================

async def background_monitor():
    logger.info("Background monitor started...")
    exchange = ccxt.binance({'enableRateLimit': True})
    last_prices: Dict[str, float] = {}

    while True:
        for coin in COINS:
            try:
                ticker = await exchange.fetch_ticker(coin)
                price = ticker["last"]

                # Флаг: нужно ли обновлять опорную цену?
                # Обновляем только если отправили алерт или это первый запуск для монеты
                should_update_anchor = False

                if coin not in last_prices:
                    should_update_anchor = True
                else:
                    old = last_prices[coin]
                    if old > 0:
                        change_pct = (price - old) / old * 100
                        subs = get_subscribers(coin)

                        # Проверяем всех подписчиков
                        for u in subs:
                            threshold = u["alert_percent"]
                            if abs(change_pct) >= threshold:
                                rates = await get_fiat_rates()
                                p_str = convert_price_usd(price, u["currency"], rates)
                                arrow = "🚀" if change_pct > 0 else "🔻"
                                text = (
                                    f"🚨 Движение по {coin}\n"
                                    f"{arrow} {change_pct:.2f}% (от {old:.4f})\n"
                                    f"Текущая цена: {p_str}"
                                )
                                try:
                                    await bot.send_message(
                                        u["user_id"], text, parse_mode="HTML"
                                    )
                                    await asyncio.sleep(0.05)
                                except (TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest):
                                    pass

                        # Если хотя бы одному юзеру отправили — сбрасываем "якорь"
                        should_update_anchor = True

                # Обновляем цену только если было событие или инициализация
                if should_update_anchor:
                    last_prices[coin] = price

            except Exception as e:
                logger.error(f"Monitor error {coin}: {e}")

            await asyncio.sleep(1.0)

        await asyncio.sleep(ALERT_CHECK_DELAY)

    await exchange.close()

# ==============================================================================
# ENTRY POINT
# ==============================================================================

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(background_monitor())

    try:
        logger.info("Bot started polling...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
