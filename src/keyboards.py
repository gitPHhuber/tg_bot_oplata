"""Inline-клавиатуры. Все callback_data — короткие, чтобы влезть в 64 байта."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from . import messages
from .tariffs import TARIFFS, Tariff


def renew_kb() -> InlineKeyboardMarkup:
    """Кнопки под уведомлением об истечении подписки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Продлить подписку", callback_data="m:buy")],
            [InlineKeyboardButton(text="🔐 Моя подписка", callback_data="m:profile")],
        ]
    )


def admin_reply_kb() -> ReplyKeyboardMarkup:
    """Reply-клавиатура только для админов с быстрыми кнопками админки."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=messages.MENU_ADMIN_STATS),
                KeyboardButton(text=messages.MENU_ADMIN_USERS),
                KeyboardButton(text=messages.MENU_ADMIN_SUBS),
            ],
            [
                KeyboardButton(text=messages.MENU_ADMIN_GIFT),
                KeyboardButton(text=messages.MENU_ADMIN_PANEL),
            ],
        ],
        resize_keyboard=True,
    )


def tariffs_kb(promo_label: str | None = None) -> InlineKeyboardMarkup:
    """Список тарифов. badge подсвечивает featured. Кнопка промо снизу."""
    rows: list[list[InlineKeyboardButton]] = []
    for t in TARIFFS:
        prefix = "⭐ " if t.featured else ""
        suffix = f"  {t.badge}" if t.badge else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{t.title} — {t.price_rub}₽{suffix}",
                    callback_data=f"buy:{t.code}",
                )
            ]
        )
    promo_btn_text = (
        f"🏷 Промокод: {promo_label}" if promo_label else "🏷 У меня есть промокод"
    )
    rows.append(
        [InlineKeyboardButton(text=promo_btn_text, callback_data="buy:promo")]
    )
    rows.append(
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="m:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


HAPP_IOS_URL = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"
HAPP_ANDROID_URL = "https://play.google.com/store/apps/details?id=com.happproxy"


def install_kb(sub_link: str) -> InlineKeyboardMarkup:
    """Клавиатура для one-tap импорта профиля в Happ.
    Telegram Bot API разрешает в url= только http/https/tg, поэтому кладём
    прямой HTTPS subscription-URL. На мобилке Happ перехватывает sub-URL
    через OS-intent и импортирует подписку."""
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(text="📥 Happ · iOS",     url=HAPP_IOS_URL),
            InlineKeyboardButton(text="📥 Happ · Android", url=HAPP_ANDROID_URL),
        ]
    )
    if sub_link:
        rows.append(
            [InlineKeyboardButton(text="🔗 Активировать профиль", url=sub_link)]
        )
    rows.append(
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="m:home")]
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


def payment_method_kb(tariff_code: str) -> InlineKeyboardMarkup:
    """Выбор способа оплаты после клика на тариф.
    card/sbp форсируют соответствующий экран YooKassa без промежуточного выбора."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 СБП — быстрый перевод из банка", callback_data=f"pay:{tariff_code}:sbp")],
            [InlineKeyboardButton(text="💳 Банковская карта", callback_data=f"pay:{tariff_code}:card")],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="m:buy")],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back")]]
    )


def main_inline_kb(
    channel_url: str = "",
    show_trial: bool = False,
) -> InlineKeyboardMarkup:
    """Главное inline-меню в стиле «бренд». Показывается под /start.
    show_trial=True показывает большую кнопку «🎣 Проба · 3 дня за 49₽»."""
    rows: list[list[InlineKeyboardButton]] = []
    if show_trial:
        rows.append(
            [InlineKeyboardButton(text="🎣 Проба · 3 дня за 49₽", callback_data="buy:trial_50")]
        )
    rows.append(
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="m:buy")]
    )
    rows.append(
        [InlineKeyboardButton(text="🎁 Подарить другу", callback_data="m:gift")]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🔐 Моя подписка",     callback_data="m:profile"),
            InlineKeyboardButton(text="📲 Как подключиться", callback_data="m:howto"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="m:ref")]
    )
    rows.append(
        [
            InlineKeyboardButton(text="💬 Поддержка", callback_data="m:support"),
            InlineKeyboardButton(text="🆘 Помощь",    callback_data="m:help"),
        ]
    )
    third_row: list[InlineKeyboardButton] = []
    if channel_url:
        third_row.append(InlineKeyboardButton(text="🌟 Наш канал", url=channel_url))
    third_row.append(InlineKeyboardButton(text="ℹ️ О нас", callback_data="m:about"))
    rows.append(third_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gift_tariffs_kb() -> InlineKeyboardMarkup:
    """Список тарифов в режиме подарка — callback другого префикса."""
    rows: list[list[InlineKeyboardButton]] = []
    for t in TARIFFS:
        prefix = "⭐ " if t.featured else ""
        suffix = f"  {t.badge}" if t.badge else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{t.title} — {t.price_rub}₽{suffix}",
                    callback_data=f"gft:{t.code}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="m:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb(has_active_sub: bool, sub_link: str = "") -> InlineKeyboardMarkup:
    """Действия в карточке моей подписки.
    sub_link (HTTPS subscription URL) — добавляет 3 кнопки one-tap импорта в Happ."""
    rows: list[list[InlineKeyboardButton]] = []
    if has_active_sub:
        if sub_link:
            rows.append(
                [
                    InlineKeyboardButton(text="📥 Happ · iOS",     url=HAPP_IOS_URL),
                    InlineKeyboardButton(text="📥 Happ · Android", url=HAPP_ANDROID_URL),
                ]
            )
            rows.append(
                [InlineKeyboardButton(text="🔗 Активировать профиль", url=sub_link)]
            )
        rows.append(
            [
                InlineKeyboardButton(text="📋 Скопировать ключ", callback_data="p:copy"),
                InlineKeyboardButton(text="📲 QR-код",            callback_data="p:qr"),
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="➕ Продлить", callback_data="m:buy")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="m:buy")]
        )
    rows.append(
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="m:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_inline_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="m:home")]
        ]
    )


def about_kb() -> InlineKeyboardMarkup:
    """Экран «О нас»: кнопки оферты и возврата.
    Если задан settings.offer_url — оферта открывается внешней ссылкой
    (teletype и т.п.); иначе — inline callback на старый текст."""
    from .config import settings
    if settings.offer_url:
        offer_btn = InlineKeyboardButton(text="📄 Договор оферты", url=settings.offer_url)
    else:
        offer_btn = InlineKeyboardButton(text="📄 Договор оферты", callback_data="m:offer")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [offer_btn],
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
