"""Фоновые задачи: polling платежей и истечение подписок."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import messages, payments
from .config import settings
from .db import DB
from .keyboards import install_kb, renew_kb
from .services import (
    activate_subscription,
    deactivate_subscription,
    format_dt_human,
    process_referral_after_activation,
)
from .tariffs import get_tariff
from .vless_link import build_tap_link
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
            # Помечаем как processing, чтобы on_check_click не активировал параллельно
            await db.update_payment_status(p.id, "processing")
            # Кому активируем: если есть recipient — это gift, иначе самому покупателю
            beneficiary_id = p.recipient_tg_id or p.tg_id
            try:
                sub, link = await activate_subscription(db, xui, beneficiary_id, tariff)
            except Exception as e:
                log.exception("activate failed for payment %s: %s", p.id, e)
                # Откатываем статус обратно, чтобы следующий poll мог повторить
                await db.update_payment_status(p.id, "pending")
                continue
            await db.update_payment_status(p.id, "succeeded", sub.id)
            # Списываем промо если был использован
            if p.promo_id:
                try:
                    await db.use_promocode(p.promo_id, p.tg_id)
                except Exception:
                    pass

            if p.recipient_tg_id:
                # Это gift: уведомляем покупателя и получателя отдельно
                buyer = await db.get_user(p.tg_id)
                buyer_name = (
                    (buyer[2] if buyer else None)
                    or (f"@{buyer[1]}" if buyer and buyer[1] else "друг")
                )
                try:
                    await bot.send_message(
                        p.recipient_tg_id,
                        messages.GIFT_RECEIVED_FROM_FRIEND.format(
                            from_name=buyer_name,
                            tariff_title=tariff.title,
                            expires=format_dt_human(sub.expires_at),
                            link=link,
                        ),
                        reply_markup=install_kb(build_tap_link(sub.sub_id) or link),
                    )
                except Exception as e:
                    log.warning("notify gift recipient %s failed: %s", p.recipient_tg_id, e)
                try:
                    await bot.send_message(
                        p.tg_id,
                        messages.GIFT_DELIVERED_TO_BUYER.format(
                            recipient_id=p.recipient_tg_id,
                            tariff_title=tariff.title,
                            expires=format_dt_human(sub.expires_at),
                        ),
                    )
                except Exception as e:
                    log.warning("notify gift buyer %s failed: %s", p.tg_id, e)
            else:
                try:
                    await bot.send_message(
                        p.tg_id,
                        messages.PAYMENT_SUCCESS.format(
                            tariff_title=tariff.title,
                            expires=format_dt_human(sub.expires_at),
                            link=link,
                        ),
                        reply_markup=install_kb(build_tap_link(sub.sub_id) or link),
                    )
                except Exception as e:
                    log.warning("notify user %s failed: %s", p.tg_id, e)

            # Реферальный бонус — за beneficiary, не за плательщика (логично:
            # если пригласённый получил подарок — это его первая активация)
            await process_referral_after_activation(db, xui, bot, beneficiary_id)
        elif status == "canceled":
            await db.update_payment_status(p.id, "canceled")


async def check_expiring_subscriptions(db: DB, xui: XUIClient, bot: Bot) -> None:
    """Два прохода:
    1) Подписки, которые УЖЕ истекли → деактивировать + один NOTIFY_EXPIRED.
    2) Подписки, которые истекают в ближайшие 24ч И ещё не уведомлены →
       один NOTIFY_EXPIRING_SOON + mark_notified_expiring (больше не пишем).
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    soon_iso = (now + timedelta(hours=24)).isoformat()

    # 1. Истёкшие → деактивация (delete из xui + active=0 в БД)
    for sub in await db.get_expired_active(now_iso):
        try:
            await deactivate_subscription(db, xui, sub)
            await bot.send_message(sub.tg_id, messages.NOTIFY_EXPIRED, reply_markup=renew_kb())
            log.info("sub %s expired and revoked", sub.id)
        except Exception as e:
            log.warning("expire sub %s failed: %s", sub.id, e)

    # 2. Скоро истекающие → одно уведомление (без повторов)
    for sub in await db.get_expiring_unnotified(now_iso, soon_iso):
        try:
            await bot.send_message(
                sub.tg_id,
                messages.NOTIFY_EXPIRING_SOON.format(
                    when=format_dt_human(sub.expires_at)
                ),
                reply_markup=renew_kb(),
            )
            await db.mark_notified_expiring(sub.id)
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
