import json
from pathlib import Path

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    PreCheckoutQuery,
    LabeledPrice,
    Update,
)
from aiogram.filters import Command

# --------- КОНФИГ ---------
TOKEN = "YOUR_BOT_TOKEN"          # Вынеси в env на Vercel
ADMIN_CHANNEL = -1003371815477

PRICE_MAIN = 300
PRICE_EXTRA = 50

TITLE_MAIN = "Все локации"
TITLE_EXTRA = "Доп. актив"

DESC_MAIN = "Основной товар за 300⭐"
DESC_EXTRA = "Дополнительный товар за 50⭐"

BUYERS_FILE = "buyers.json"  # На Vercel НЕ ПЕРСИСТЕНТНО, только для тестов локально

# --------- GLOBAL OBJECTS (важно для серверлесс) ---------
app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()


# --------- UTILS (как у тебя, чуть аккуратнее) ---------
BUYERS_PATH = Path(BUYERS_FILE)


def load_buyers():
    if not BUYERS_PATH.exists():
        return []
    try:
        with BUYERS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_buyers(data):
    # На Vercel это НЕ гарантировано между запросами, смотри комментарий ниже
    with BUYERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def user_has_main(user_id: int) -> bool:
    buyers = load_buyers()
    return user_id in buyers


def add_main_buyer(user_id: int):
    buyers = load_buyers()
    if user_id not in buyers:
        buyers.append(user_id)
        save_buyers(buyers)


# --------- KEYBOARD ---------
def main_keyboard(user_id: int):
    btns = [
        [
            InlineKeyboardButton(
                text=f"Купить «{TITLE_MAIN}» за {PRICE_MAIN}⭐",
                callback_data="buy_main",
            )
        ]
    ]

    if user_has_main(user_id):
        btns.append(
            [
                InlineKeyboardButton(
                    text=f"Купить «{TITLE_EXTRA}» за {PRICE_EXTRA}⭐",
                    callback_data="buy_extra",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=btns)


# --------- HANDLERS (те же, только без polling) ---------
@dp.message(Command("start"))
async def start_handler(msg: Message):
    await msg.answer(
        "Добро пожаловать! Здесь доступны покупки.",
        reply_markup=main_keyboard(msg.from_user.id),
    )


@dp.callback_query(F.data == "buy_main")
async def buy_main_handler(callback):
    prices = [LabeledPrice(label=TITLE_MAIN, amount=PRICE_MAIN)]
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=TITLE_MAIN,
        description=DESC_MAIN,
        currency="XTR",
        prices=prices,
        payload="main_purchase",
    )
    await callback.answer()


@dp.callback_query(F.data == "buy_extra")
async def buy_extra_handler(callback):
    if not user_has_main(callback.from_user.id):
        await callback.answer(
            "Доступ к покупкам за 50⭐ только после покупки за 300⭐.",
            show_alert=True,
        )
        return

    prices = [LabeledPrice(label=TITLE_EXTRA, amount=PRICE_EXTRA)]
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=TITLE_EXTRA,
        description=DESC_EXTRA,
        currency="XTR",
        prices=prices,
        payload="extra_purchase",
    )
    await callback.answer()


@dp.pre_checkout_query()
async def checkout_handler(pre: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre.id, ok=True)


@dp.message(F.successful_payment)
async def payment_success(msg: Message):
    payload = msg.successful_payment.invoice_payload
    user = msg.from_user

    if payload == "main_purchase":
        add_main_buyer(user.id)
        title = TITLE_MAIN
        price = PRICE_MAIN
    elif payload == "extra_purchase":
        title = TITLE_EXTRA
        price = PRICE_EXTRA
    else:
        return

    text_user = f"Товар «{title}» активирован!"
    text_admin = (
        "📩 Новый заказ!\n"
        f"Покупатель: @{user.username or 'нет username'}\n"
        f"ID: {user.id}\n"
        f"Товар: {title}\n"
        f"Оплата: {price}⭐"
    )

    await msg.answer(text_user)
    await bot.send_message(ADMIN_CHANNEL, text_admin)
    await msg.answer("Меню обновлено:", reply_markup=main_keyboard(user.id))


# --------- FASTAPI WEBHOOK ENDPOINT ---------
@app.post("/")
async def telegram_webhook(request: Request):
    data = await request.json()
    # Для aiogram 3.x с pydantic v2:
    try:
        update = Update.model_validate(data)
    except AttributeError:
        # fallback если старая версия
        update = Update(**data)

    # Отдаём апдейт в диспетчер
    await dp.feed_update(bot, update)  # официальный способ из доки :contentReference[oaicite:3]{index=3}
    return {"ok": True}
