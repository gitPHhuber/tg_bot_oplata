"""Inline-клавиатуры. Все callback_data — короткие, чтобы влезть в 64 байта."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import messages
from .tariffs import TARIFFS, Tariff


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню. Админу показываем дополнительный ряд с быстрыми действиями
    + кнопкой 🛠 Админ-панель, открывающей inline-меню."""
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=messages.MENU_BUY)],
        [
            KeyboardButton(text=messages.MENU_PROFILE),
            KeyboardButton(text=messages.MENU_HOWTO),
        ],
        [KeyboardButton(text=messages.MENU_SUPPORT)],
    ]
    if is_admin:
        rows.append(
            [
                KeyboardButton(text=messages.MENU_ADMIN_STATS),
                KeyboardButton(text=messages.MENU_ADMIN_USERS),
                KeyboardButton(text=messages.MENU_ADMIN_SUBS),
            ]
        )
        rows.append(
            [
                KeyboardButton(text=messages.MENU_ADMIN_GIFT),
                KeyboardButton(text=messages.MENU_ADMIN_PANEL),
            ]
        )
    return ReplyKeyboardMarkup(
        keyboard=rows,
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


def main_inline_kb(channel_url: str = "") -> InlineKeyboardMarkup:
    """Главное inline-меню в стиле «бренд». Показывается под /start."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="m:buy")],
        [
            InlineKeyboardButton(text="🔐 Моя подписка",     callback_data="m:profile"),
            InlineKeyboardButton(text="📲 Как подключиться", callback_data="m:howto"),
        ],
        [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="m:ref")],
    ]
    third_row: list[InlineKeyboardButton] = []
    if channel_url:
        third_row.append(InlineKeyboardButton(text="🌟 Наш канал", url=channel_url))
    third_row.append(InlineKeyboardButton(text="ℹ️ О нас", callback_data="m:about"))
    rows.append(third_row)
    rows.append([InlineKeyboardButton(text="🆘 Помощь", callback_data="m:help")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_inline_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="m:home")]
        ]
    )


def about_kb() -> InlineKeyboardMarkup:
    """Экран «О нас»: кнопки оферты и возврата."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Договор оферты", callback_data="m:offer")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="m:home")],
        ]
    )


def offer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="m:about")],
        ]
    )


def referral_share_kb(share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=share_url)],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="m:home")],
        ]
    )


# ---------- админ-панель ----------

def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
                InlineKeyboardButton(text="🖥 Сервер",     callback_data="adm:server"),
            ],
            [
                InlineKeyboardButton(text="👥 Юзеры",      callback_data="adm:users:0"),
                InlineKeyboardButton(text="🔐 Подписки",   callback_data="adm:subs:0"),
            ],
            [
                InlineKeyboardButton(text="🔍 Найти юзера", callback_data="adm:find"),
                InlineKeyboardButton(text="🎁 Подарок",     callback_data="adm:gift"),
            ],
            [
                InlineKeyboardButton(text="📨 Сообщение",  callback_data="adm:senddm"),
                InlineKeyboardButton(text="📢 Рассылка",   callback_data="adm:bcast"),
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
