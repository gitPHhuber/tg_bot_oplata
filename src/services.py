"""Бизнес-логика, общая для handlers и scheduler.

Тут только высокоуровневые операции — `activate_subscription`, чтобы они были
в одном месте, а не дублировались в каждом обработчике.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

from .config import settings
from .db import DB, Subscription
from .tariffs import Tariff
from .vless_link import build_vless_link
from .xui_client import XUIClient, days_from_now_unix_ms

log = logging.getLogger(__name__)


async def activate_gift_subscription(
    db: DB,
    xui: XUIClient,
    tg_id: int,
    days: int,
    traffic_gb: int = 0,
) -> tuple[Subscription, str]:
    """Подарок: подписка на N дней без привязки к существующему тарифу.
    Tariff_code сохраняется как 'gift_<days>d', чтобы потом отличать в статистике.
    """
    gift = Tariff(
        code=f"gift_{days}d",
        title=f"🎁 Подарок · {days} дн.",
        price_rub=0,
        days=days,
        traffic_gb=traffic_gb,
    )
    return await activate_subscription(db, xui, tg_id, gift)


async def activate_subscription(
    db: DB,
    xui: XUIClient,
    tg_id: int,
    tariff: Tariff,
) -> tuple[Subscription, str]:
    """Создать клиента в 3x-ui + запись в БД. Возвращает (subscription, vless-link)."""
    # уникальный email = идентификатор клиента в xray
    existing_subs = await db.get_user_subscriptions(tg_id)
    serial = len(existing_subs) + 1
    email = f"tg-{tg_id}-{serial}"

    expiry_ms = days_from_now_unix_ms(tariff.days)

    client_uuid = await xui.add_client(
        inbound_id=settings.xui_inbound_id,
        email=email,
        total_gb=tariff.traffic_gb,
        expiry_unix_ms=expiry_ms,
    )

    expires_iso = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).isoformat()
    sub_id = await db.create_subscription(
        tg_id=tg_id,
        xui_uuid=client_uuid,
        xui_email=email,
        tariff_code=tariff.code,
        expires_at=expires_iso,
        traffic_gb=tariff.traffic_gb,
    )
    sub = await db.get_subscription(sub_id)
    assert sub is not None
    link = build_vless_link(client_uuid, remark=f"VPN-{tariff.code}")
    log.info("activated sub %s for tg=%s tariff=%s", sub_id, tg_id, tariff.code)
    return sub, link


async def deactivate_subscription(
    db: DB,
    xui: XUIClient,
    sub: Subscription,
) -> None:
    """Удалить клиента в 3x-ui и пометить подписку неактивной."""
    try:
        await xui.delete_client(settings.xui_inbound_id, sub.xui_uuid)
    except Exception as e:
        log.warning("xui delete_client failed for sub %s: %s", sub.id, e)
    await db.deactivate_subscription(sub.id)


async def award_referral_bonus(
    db: DB,
    xui: XUIClient,
    referrer_id: int,
    days: int,
) -> tuple[Subscription, bool, str]:
    """Начислить реферреру бонус: продлить активную подписку на N дней,
    или создать новую gift-подписку (без лимита трафика).

    Возвращает (subscription, was_extended, vless_link).
    was_extended=True если продлили, False если создали новую.
    vless_link непустой только когда создали новую (продление не меняет ключ).
    """
    sub = await db.get_active_user_subscription(referrer_id)
    if sub and not sub.is_expired:
        updated = await extend_subscription(db, xui, sub, days)
        return updated, True, ""
    new_sub, link = await activate_gift_subscription(
        db, xui, referrer_id, days=days, traffic_gb=0
    )
    return new_sub, False, link


async def process_referral_after_activation(
    db: DB,
    xui: XUIClient,
    bot,  # aiogram.Bot — прямой импорт здесь не делаем, чтобы избежать циклов
    new_user_tg_id: int,
) -> None:
    """Вызывать ПОСЛЕ db.create_payment() при первой активации.
    Проверяет, есть ли у нового юзера referrer, и если да — начисляет бонус.

    Идемпотентен: если у юзера уже есть >1 активаций (то есть это не первая),
    функция тихо ничего не делает.
    """
    from . import messages  # local import чтобы не было циклов

    if not settings.referral_enabled:
        return
    referrer_id = await db.get_referrer(new_user_tg_id)
    if not referrer_id:
        return
    # Считаем активные/manual платежи юзера. Если != 1 — либо ещё нет записи
    # (рано вызвали), либо уже была обработка (повторный платёж).
    cnt = 0
    async with aiosqlite.connect(db.path) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM payments WHERE tg_id = ? AND status IN ('succeeded', 'manual')",
            (new_user_tg_id,),
        )
        row = await cur.fetchone()
        cnt = row[0] if row else 0
    if cnt != 1:
        return  # либо ещё нет записи (рано вызвали), либо уже была — повторный платёж

    days = settings.referral_bonus_days
    try:
        sub, extended, link = await award_referral_bonus(db, xui, referrer_id, days)
    except Exception as e:
        log.warning("referral bonus for %s failed: %s", referrer_id, e)
        return

    # Уведомляем реферрера
    if extended:
        outcome = messages.REFERRAL_BONUS_EXTENDED.format(
            expires=format_dt_human(sub.expires_at)
        )
    else:
        outcome = messages.REFERRAL_BONUS_NEW.format(
            expires=format_dt_human(sub.expires_at), link=link
        )
    text = messages.REFERRAL_BONUS_NOTIFY.format(
        friend_id=new_user_tg_id, days=days, outcome=outcome
    )
    try:
        await bot.send_message(referrer_id, text)
    except Exception as e:
        log.warning("notify referrer %s failed: %s", referrer_id, e)


async def extend_subscription(
    db: DB,
    xui: XUIClient,
    sub: Subscription,
    extra_days: int,
) -> Subscription:
    """Продлить подписку на N дней. Если истекла — отсчёт от сейчас, иначе от текущей expires."""
    now = datetime.now(timezone.utc)
    base = max(sub.expires_dt, now)
    new_expires = base + timedelta(days=extra_days)
    new_expires_ms = int(new_expires.timestamp() * 1000)
    new_expires_iso = new_expires.isoformat()

    await xui.update_client(
        inbound_id=settings.xui_inbound_id,
        client_uuid=sub.xui_uuid,
        email=sub.xui_email,
        total_gb=sub.traffic_gb,
        expiry_unix_ms=new_expires_ms,
        enable=True,
    )
    await db.extend_subscription(sub.id, new_expires_iso)
    updated = await db.get_subscription(sub.id)
    assert updated is not None
    log.info("extended sub %s: +%dd → %s", sub.id, extra_days, new_expires_iso)
    return updated


def format_traffic(gb: int) -> str:
    return "без лимита" if gb <= 0 else f"{gb} GB"


def format_used(used_bytes: int) -> str:
    if used_bytes < 1024 * 1024:
        return f"{used_bytes / 1024:.0f} KB"
    if used_bytes < 1024 * 1024 * 1024:
        return f"{used_bytes / (1024 * 1024):.1f} MB"
    return f"{used_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_dt_human(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    # Местное время оставим в UTC — без TZ-кручения, иначе в .env придётся хранить TZ
    return dt.strftime("%d.%m.%Y %H:%M UTC")
