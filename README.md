<div align="center">

# 🤖 Crypto AI Analyst Bot

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Gemini](https://img.shields.io/badge/Google-Gemini_2.5-4285F4.svg?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

**Умный Telegram-бот для анализа криптовалют с использованием AI**

[Возможности](#-возможности) • [Установка](#-установка) • [Использование](#-использование) • [Технологии](#-технологии)

![Demo](https://img.shields.io/badge/Status-Active-success?style=flat-square)
![Maintained](https://img.shields.io/badge/Maintained-Yes-green?style=flat-square)

</div>

---

## 🎯 О проекте

Crypto AI Analyst — это профессиональный Telegram-бот для анализа криптовалютного рынка. Использует Google Gemini AI для глубокого анализа и предоставляет понятные рекомендации на русском языке.

### ✨ Ключевые преимущества

- 🧠 **AI-анализ** от Google Gemini 2.5 Flash
- 📊 **Технические индикаторы**: RSI, SMA, объёмы
- 🔔 **Умные алерты** с настраиваемыми порогами
- 💱 **Мультивалютность**: USD, RUB, EUR
- ⚡ **Кэширование** для быстрых ответов
- 🎨 **Удобный интерфейс** с inline-кнопками

## 🚀 Возможности

<table>
<tr>
<td width="50%">

### 🧠 AI Прогнозы
- Анализ рыночной ситуации
- Рекомендации: покупать/продавать/держать
- Понятное объяснение на русском
- Учёт RSI, объёмов, трендов

</td>
<td width="50%">

### 📈 Технический анализ
- RSI (14) — индекс относительной силы
- SMA (20) — скользящая средняя
- Расстояние от локальных экстремумов
- Анализ объёмов торговли

</td>
</tr>
<tr>
<td width="50%">

### 🔔 Система уведомлений
- Подписки на избранные монеты
- Настраиваемые пороги (1%, 3%, 5%)
- Фоновый мониторинг каждые 60 сек
- Мгновенные push-уведомления

</td>
<td width="50%">

### 💰 Дополнительно
- Быстрая конвертация (100 TON → USD/RUB/EUR)
- Статистика за 24 часа
- Поддержка 36+ популярных монет
- Два режима: AI и алгоритмический

</td>
</tr>
</table>

## 📦 Установка

### Требования

```bash
Python 3.9+
pip (package manager)
```

### Быстрый старт

1. **Клонируйте репозиторий**
```bash
git clone https://github.com/Krimex1/prognoztgbot.git
cd prognoztgbot
```

2. **Установите зависимости**
```bash
pip install -r requirements.txt
```

3. **Настройте переменные окружения**
```bash
cp .env.example .env
# Отредактируйте .env и добавьте свои ключи:
# BOT_TOKEN=your_telegram_bot_token
# GEMINI_API_KEY=your_gemini_api_key
```

4. **Запустите бота**
```bash
python bot.py
```

### Получение API ключей

| Сервис | Где получить | Бесплатно |
|--------|--------------|-----------|  
| **Telegram Bot** | [@BotFather](https://t.me/BotFather) | ✅ Да |
| **Google Gemini** | [Google AI Studio](https://makersuite.google.com/app/apikey) | ✅ Да (лимиты) |

## 💡 Использование

### Команды бота

| Команда/Кнопка | Описание |
|----------------|----------|
| `/start` | Запуск бота и показ главного меню |
| 🧠 **AI Прогноз** | Получить AI-анализ выбранной монеты |
| 📊 **Статистика** | Подробная статистика за 24 часа |
| 🔔 **Подписки** | Управление уведомлениями |
| ⚙️ **Настройки** | Валюта, режим анализа, чувствительность |

### Быстрая конвертация

Просто отправьте сообщение в формате:
```
100 TON
0.5 BTC
1000 PEPE
```

Бот автоматически конвертирует в USD, RUB и EUR.

## 🎨 Поддерживаемые монеты

<details>
<summary>📋 Полный список (36 монет)</summary>

```
BTC/USDT   ETH/USDT   BNB/USDT   SOL/USDT
TON/USDT   NOT/USDT   TRX/USDT   XRP/USDT
DOGE/USDT  SHIB/USDT  PEPE/USDT  HMSTR/USDT
LTC/USDT   ADA/USDT   AVAX/USDT  DOT/USDT
LINK/USDT  ATOM/USDT  NEAR/USDT  MATIC/USDT
UNI/USDT   APT/USDT   ARB/USDT   OP/USDT
VET/USDT   RNDR/USDT  IMX/USDT   STX/USDT
SUI/USDT   TIA/USDT   SEI/USDT   FTM/USDT
INJ/USDT   LDO/USDT   RUNE/USDT  AR/USDT
```
</details>

## 🛠 Технологии

<div align="center">

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Aiogram](https://img.shields.io/badge/Aiogram-3.13-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![CCXT](https://img.shields.io/badge/CCXT-4.4-black?style=for-the-badge)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)

</div>

### Основные библиотеки

- **[aiogram](https://github.com/aiogram/aiogram)** `3.13.1` — современный Telegram Bot API framework
- **[ccxt](https://github.com/ccxt/ccxt)** `4.4.27` — работа с биржами (Binance)
- **[google-generativeai](https://ai.google.dev/)** `0.8.3` — Google Gemini API
- **[aiohttp](https://docs.aiohttp.org/)** `3.10.10` — асинхронные HTTP-запросы

