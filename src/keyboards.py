"""Inline-клавиатуры. Все callback_data — короткие, чтобы влезть в 64 байта."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import messages
from .tariffs import TARIFFS, Tariff


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=messages.MENU_BUY)],
            [
                KeyboardButton(text=messages.MENU_PROFILE),
                KeyboardButton(text=messages.MENU_HOWTO),
            ],
            [KeyboardButton(text=messages.MENU_SUPPORT)],
        ],
        resize_keyboard=True,
    )


def tariffs_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in TARIFFS:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{t.title} — {t.price_rub}₽",
                    callback_data=f"buy:{t.code}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_kb(url: str, tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check:{tariff_code}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back")]]
    )
