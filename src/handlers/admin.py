"""Админ-команды. Доступны только tg_id из ADMIN_IDS."""
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import messages
from ..config import settings
from ..db import DB
from ..services import activate_subscription, deactivate_subscription, format_dt_human
from ..tariffs import TARIFFS, get_tariff
from ..xui_client import XUIClient

log = logging.getLogger(__name__)
router = Router(name="admin")


def _is_admin(msg: Message) -> bool:
    return settings.is_admin(msg.from_user.id)


# /admin перенесён в handlers/admin_panel.py — там полноценная inline-админка.
# Старые CLI-команды /stats /grant /revoke /userinfo оставлены как
# быстрый доступ из любого места без открытия меню.


@router.message(Command("stats"))
async def cmd_stats(msg: Message, db: DB) -> None:
    if not _is_admin(msg):
        await msg.answer(messages.ADMIN_ONLY)
        return
    users = await db.count_users()
    paid_count, revenue = await db.count_payments()
    pending = len(await db.get_pending_payments())
    # активных подписок — посчитаем через expiring(future)
    from datetime import datetime, timedelta, timezone

    far_future = (datetime.now(timezone.utc) + timedelta(days=365 * 10)).isoformat()
    active = [s for s in await db.get_expiring_subscriptions(far_future) if not s.is_expired]
    await msg.answer(
        messages.ADMIN_STATS.format(
            users=users,
            paid_count=paid_count,
            revenue=revenue,
            active_subs=len(active),
            pending=pending,
        )
    )


@router.message(Command("grant"))
async def cmd_grant(msg: Message, command: CommandObject, db: DB, xui: XUIClient) -> None:
    """/grant <tg_id> <tariff_code> — выдать подписку вручную."""
    if not _is_admin(msg):
        await msg.answer(messages.ADMIN_ONLY)
        return
    if not command.args:
        await msg.answer("Использование: <code>/grant &lt;tg_id&gt; &lt;tariff_code&gt;</code>")
        return
    parts = command.args.split()
    if len(parts) != 2:
        await msg.answer("Использование: <code>/grant &lt;tg_id&gt; &lt;tariff_code&gt;</code>")
        return
    try:
        tg_id = int(parts[0])
    except ValueError:
        await msg.answer("tg_id должен быть числом")
        return
    tariff = get_tariff(parts[1])
    if not tariff:
        codes = ", ".join(t.code for t in TARIFFS)
        await msg.answer(f"Тариф не найден. Доступные: {codes}")
        return

    # Убеждаемся, что юзер есть в БД (на случай если он не запускал /start)
    await db.upsert_user(tg_id=tg_id, username=None, first_name=None)

    try:
        sub, link = await activate_subscription(db, xui, tg_id, tariff)
    except Exception as e:
        log.exception("grant failed")
        await msg.answer(f"❌ Ошибка: {e}")
        return

    await db.create_payment(
        tg_id=tg_id,
        yk_id=None,
        tariff_code=tariff.code,
        amount_rub=0,
        status="manual",
    )

    await msg.answer(
        messages.ADMIN_GRANTED.format(
            tg_id=tg_id, tariff_title=tariff.title, link=link
        )
    )


@router.message(Command("revoke"))
async def cmd_revoke(msg: Message, command: CommandObject, db: DB, xui: XUIClient) -> None:
    if not _is_admin(msg):
        await msg.answer(messages.ADMIN_ONLY)
        return
    if not command.args:
        await msg.answer("Использование: <code>/revoke &lt;tg_id&gt;</code>")
        return
    try:
        tg_id = int(command.args.strip())
    except ValueError:
        await msg.answer("tg_id должен быть числом")
        return
    sub = await db.get_active_user_subscription(tg_id)
    if not sub:
        await msg.answer("Активной подписки нет.")
        return
    await deactivate_subscription(db, xui, sub)
    await msg.answer(messages.ADMIN_REVOKED.format(tg_id=tg_id))


@router.message(Command("userinfo"))
async def cmd_userinfo(msg: Message, command: CommandObject, db: DB) -> None:
    if not _is_admin(msg):
        await msg.answer(messages.ADMIN_ONLY)
        return
    if not command.args:
        await msg.answer("Использование: <code>/userinfo &lt;tg_id&gt;</code>")
        return
    try:
        tg_id = int(command.args.strip())
    except ValueError:
        await msg.answer("tg_id должен быть числом")
        return
    subs = await db.get_user_subscriptions(tg_id)
    if not subs:
        await msg.answer(f"User {tg_id}: подписок нет.")
        return
    lines = [f"<b>User {tg_id}</b>", f"Всего подписок: {len(subs)}", ""]
    for s in subs[:10]:
        status = "🟢" if s.active and not s.is_expired else "⚪️"
        lines.append(
            f"{status} #{s.id} {s.tariff_code} — до {format_dt_human(s.expires_at)}"
        )
    await msg.answer("\n".join(lines))
