"""Фоновые задачи: polling платежей и истечение подписок."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import messages, payments
from .config import settings
from .db import DB
from .services import activate_subscription, deactivate_subscription, format_dt_human
from .tariffs import get_tariff
from .xui_client import XUIClient

log = logging.getLogger(__name__)


async def poll_pending_payments(db: DB, xui: XUIClient, bot: Bot) -> None:
    if settings.payment_mode != "yookassa":
        return
    pending = await db.get_pending_payments()
    if not pending:
        return
    log.debug("polling %d pending payments", len(pending))
    for p in pending:
        if not p.yk_id:
            continue
        status = await payments.get_payment_status(p.yk_id)
        if status is None:
            continue

        # таймаут pending: > 24 часов → отменяем
        created = datetime.fromisoformat(p.created_at)
        if status == "pending" and datetime.now(timezone.utc) - created > timedelta(hours=24):
            await db.update_payment_status(p.id, "canceled")
            log.info("payment %s timed out (>24h), canceled", p.id)
            continue

        if status == "succeeded":
            tariff = get_tariff(p.tariff_code)
            if not tariff:
                log.warning("payment %s: tariff %s not found", p.id, p.tariff_code)
                await db.update_payment_status(p.id, "canceled")
                continue
            try:
                sub, link = await activate_subscription(db, xui, p.tg_id, tariff)
            except Exception as e:
                log.exception("activate failed for payment %s: %s", p.id, e)
                continue
            await db.update_payment_status(p.id, "succeeded", sub.id)
            try:
                await bot.send_message(
                    p.tg_id,
                    messages.PAYMENT_SUCCESS.format(
                        tariff_title=tariff.title,
                        expires=format_dt_human(sub.expires_at),
                        link=link,
                    ),
                )
            except Exception as e:
                log.warning("notify user %s failed: %s", p.tg_id, e)
        elif status == "canceled":
            await db.update_payment_status(p.id, "canceled")


async def check_expiring_subscriptions(db: DB, xui: XUIClient, bot: Bot) -> None:
    """Уведомляем за 24 часа до истечения, отрубаем после."""
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    soon_iso = soon.isoformat()

    expiring = await db.get_expiring_subscriptions(soon_iso)
    for sub in expiring:
        if sub.is_expired:
            try:
                await deactivate_subscription(db, xui, sub)
                await bot.send_message(sub.tg_id, messages.NOTIFY_EXPIRED)
                log.info("sub %s expired and revoked", sub.id)
            except Exception as e:
                log.warning("expire sub %s failed: %s", sub.id, e)
        else:
            # Уведомление за 24ч (без флага «уже уведомлён» — отправится 1-2 раза, нестрашно)
            try:
                await bot.send_message(
                    sub.tg_id,
                    messages.NOTIFY_EXPIRING_SOON.format(
                        when=format_dt_human(sub.expires_at)
                    ),
                )
            except Exception as e:
                log.warning("notify expiring sub %s failed: %s", sub.id, e)


def setup_scheduler(db: DB, xui: XUIClient, bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        poll_pending_payments,
        "interval",
        seconds=settings.payment_poll_interval,
        kwargs={"db": db, "xui": xui, "bot": bot},
        id="poll_payments",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        check_expiring_subscriptions,
        "interval",
        minutes=settings.sub_check_interval,
        kwargs={"db": db, "xui": xui, "bot": bot},
        id="check_expiring",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
