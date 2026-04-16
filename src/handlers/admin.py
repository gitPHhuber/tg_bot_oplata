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


@router.message(Command("promo"))
async def cmd_promo(msg: Message, command: CommandObject, db: DB) -> None:
    """/promo создать <КОД> percent|fixed <значение> [max_uses=0] [days=0]
    /promo list — список всех промокодов
    /promo del <КОД> — отключить (через update enabled=0 — пока не реализовано, удалять можно вручную)
    """
    if not _is_admin(msg):
        await msg.answer(messages.ADMIN_ONLY)
        return
    if not command.args:
        await msg.answer(
            "<b>Промокоды</b>\n\n"
            "• Создать: <code>/promo create CODE percent 20 100 30</code>\n"
            "  (CODE, тип, значение, max_uses=100, истекает через 30 дней)\n"
            "  Можно опустить max_uses (=0=безлимит) и days (=0=бессрочно).\n"
            "• Тип: <code>percent</code> (1..100) или <code>fixed</code> (рубли)\n"
            "• Список: <code>/promo list</code>\n\n"
            "Пример:\n"
            "<code>/promo create WELCOME percent 20</code>\n"
            "<code>/promo create FIRST50 fixed 50 100 7</code>"
        )
        return
    parts = command.args.split()
    sub = parts[0].lower()
    if sub == "list":
        rows = await db.list_promocodes()
        if not rows:
            await msg.answer("Промокодов нет.")
            return
        lines = ["<b>Промокоды</b>\n"]
        for r in rows:
            (pid, code, kind, value, max_uses, used_count, exp, enabled) = r
            disp = f"-{value}%" if kind == "percent" else f"-{value}₽"
            limit = "∞" if not max_uses else f"{used_count}/{max_uses}"
            exp_str = f", до {exp[:10]}" if exp else ""
            on = "✅" if enabled else "❌"
            lines.append(f"{on} <code>{code}</code> · {disp} · {limit}{exp_str}")
        await msg.answer("\n".join(lines))
        return
    if sub == "create":
        if len(parts) < 4:
            await msg.answer(
                "Формат: <code>/promo create CODE percent|fixed VALUE [max_uses] [days]</code>"
            )
            return
        code = parts[1]
        kind = parts[2].lower()
        if kind not in ("percent", "fixed"):
            await msg.answer("Тип должен быть <code>percent</code> или <code>fixed</code>")
            return
        try:
            value = int(parts[3])
        except ValueError:
            await msg.answer("VALUE должно быть числом")
            return
        max_uses = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        days = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
        from datetime import datetime, timedelta, timezone
        expires_at = (
            (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            if days
            else None
        )
        try:
            pid = await db.create_promocode(
                code=code, kind=kind, value=value, max_uses=max_uses, expires_at=expires_at
            )
        except Exception as e:
            await msg.answer(f"❌ Ошибка: {e}")
            return
        disp = f"-{value}%" if kind == "percent" else f"-{value}₽"
        await msg.answer(
            f"✅ Промокод <code>{code.upper()}</code> создан (#{pid})\n"
            f"Скидка: <b>{disp}</b>\n"
            f"Лимит: {'∞' if not max_uses else max_uses}\n"
            f"Истекает: {expires_at or 'бессрочно'}"
        )
        return
    await msg.answer("Неизвестная подкоманда. Используй: create | list")


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
async def cmd_grant(msg: Message, command: CommandObject, db: DB, xui: XUIClient, xui_wl: XUIClient | None = None) -> None:
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
        sub, link = await activate_subscription(db, xui, tg_id, tariff, xui_wl=xui_wl)
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
async def cmd_revoke(msg: Message, command: CommandObject, db: DB, xui: XUIClient, xui_wl: XUIClient | None = None) -> None:
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
    await deactivate_subscription(db, xui, sub, xui_wl=xui_wl)
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
