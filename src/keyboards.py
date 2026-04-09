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


# ---------- админ-панель ----------

def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Stats", callback_data="adm:stats"),
                InlineKeyboardButton(text="🖥 Server", callback_data="adm:server"),
            ],
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users:0"),
                InlineKeyboardButton(text="🔐 Active subs", callback_data="adm:subs:0"),
            ],
            [
                InlineKeyboardButton(text="🔍 Find user", callback_data="adm:find"),
                InlineKeyboardButton(text="➕ Extend sub", callback_data="adm:extend"),
            ],
            [
                InlineKeyboardButton(text="📨 Send DM", callback_data="adm:senddm"),
                InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:bcast"),
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:close")],
        ]
    )


def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В админку", callback_data="adm:home")]
        ]
    )


def admin_stats_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data="adm:stats:1"),
                InlineKeyboardButton(text="7 дней",   callback_data="adm:stats:7"),
                InlineKeyboardButton(text="30 дней",  callback_data="adm:stats:30"),
                InlineKeyboardButton(text="Всё",      callback_data="adm:stats:all"),
            ],
            [InlineKeyboardButton(text="◀️ В админку", callback_data="adm:home")],
        ]
    )


def admin_paginator_kb(prefix: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page-1}")
        )
    nav_row.append(
        InlineKeyboardButton(text=f"{page+1}/{max(total_pages,1)}", callback_data="adm:noop")
    )
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page+1}")
        )
    rows.append(nav_row)
    rows.append(
        [InlineKeyboardButton(text="◀️ В админку", callback_data="adm:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_confirm_kb(yes_data: str, no_data: str = "adm:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да",  callback_data=yes_data),
                InlineKeyboardButton(text="❌ Нет", callback_data=no_data),
            ]
        ]
    )


def admin_user_card_kb(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Дать", callback_data=f"adm:gr:{tg_id}"),
                InlineKeyboardButton(text="⏳ Продлить", callback_data=f"adm:ext:{tg_id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Отозвать", callback_data=f"adm:rev:{tg_id}"),
                InlineKeyboardButton(text="📨 Написать", callback_data=f"adm:dm:{tg_id}"),
            ],
            [InlineKeyboardButton(text="◀️ В админку", callback_data="adm:home")],
        ]
    )


def admin_grant_tariff_kb(tg_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с выбором тарифа для админского /grant через UI."""
    from .tariffs import TARIFFS

    rows = [
        [
            InlineKeyboardButton(
                text=f"{t.title}",
                callback_data=f"adm:gr2:{tg_id}:{t.code}",
            )
        ]
        for t in TARIFFS
    ]
    rows.append(
        [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm:user:{tg_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_extend_days_kb(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="+7 дн",  callback_data=f"adm:ex2:{sub_id}:7"),
                InlineKeyboardButton(text="+14 дн", callback_data=f"adm:ex2:{sub_id}:14"),
                InlineKeyboardButton(text="+30 дн", callback_data=f"adm:ex2:{sub_id}:30"),
                InlineKeyboardButton(text="+90 дн", callback_data=f"adm:ex2:{sub_id}:90"),
            ],
            [InlineKeyboardButton(text="◀️ В админку", callback_data="adm:home")],
        ]
    )
