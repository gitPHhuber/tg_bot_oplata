"""Расширенная админ-панель: inline-меню /admin со всеми разделами.

Содержит:
- /admin → главное меню
- 📊 Stats — статистика с разбивкой по периодам (день/неделя/месяц/всё)
- 🖥 Server — состояние сервера и сервисов
- 👥 Users — список юзеров с пагинацией
- 🔐 Active subs — список активных подписок с трафиком из xui
- 🔍 Find user — поиск по tg_id или @username
- ➕ Extend — продление чужой подписки
- 📨 Send DM — отправить сообщение конкретному юзеру
- 📢 Broadcast — рассылка всем

Пагинация: callback_data="adm:users:<page>" / "adm:subs:<page>".
Карточка юзера: "adm:user:<tg_id>" — список действий через subset кнопок.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from .. import messages
from ..config import settings
from ..db import DB
from ..keyboards import (
    admin_back_kb,
    admin_confirm_kb,
    admin_extend_days_kb,
    admin_grant_tariff_kb,
    admin_main_kb,
    admin_paginator_kb,
    admin_stats_period_kb,
    admin_user_card_kb,
)
from ..services import (
    activate_gift_subscription,
    activate_subscription,
    deactivate_subscription,
    extend_subscription,
    format_dt_human,
    format_traffic,
    format_used,
)
from ..tariffs import TARIFFS, get_tariff
from ..xui_client import XUIClient

log = logging.getLogger(__name__)
router = Router(name="admin_panel")

# постраничные размеры
USERS_PER_PAGE = 10
SUBS_PER_PAGE = 10


class AdminStates(StatesGroup):
    finding_user = State()
    sending_dm = State()
    sending_dm_text = State()
    broadcasting = State()
    broadcast_confirm = State()
    gifting_user = State()
    gifting_days = State()


class IsAdmin(BaseFilter):
    """Пропускает только сообщения/callback от админов из ADMIN_IDS."""

    async def __call__(self, event: TelegramObject) -> bool:
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return False
        return settings.is_admin(from_user.id)


# Применяем фильтр ко всему роутеру — все handlers ниже автоматически
# доступны только админам.
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ---------- Главное меню ----------

@router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())


# Кнопки reply-клавиатуры админа (см. keyboards.main_menu_kb)
@router.message(F.text == messages.MENU_ADMIN_PANEL)
async def menu_admin_panel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())


@router.message(F.text == messages.MENU_ADMIN_STATS)
async def menu_admin_stats(msg: Message) -> None:
    await msg.answer(
        "📊 <b>Статистика</b>\n\nВыбери период:",
        reply_markup=admin_stats_period_kb(),
    )


@router.message(F.text == messages.MENU_ADMIN_USERS)
async def menu_admin_users(msg: Message, db: DB) -> None:
    total = await db.count_users()
    total_pages = max((total + USERS_PER_PAGE - 1) // USERS_PER_PAGE, 1)
    rows = await db.get_users_page(USERS_PER_PAGE, 0)
    if not rows:
        txt = "👥 <b>Юзеры</b>\n\nПусто."
    else:
        lines = [f"👥 <b>Юзеры</b> ({total})\n"]
        for tg_id, username, first_name, _ in rows:
            uname = f"@{username}" if username else "—"
            name = first_name or "?"
            lines.append(f"<code>{tg_id}</code> · {name} · {uname}")
        lines.append("\n<i>Тапни /u_&lt;tg_id&gt; чтобы открыть карточку.</i>")
        txt = "\n".join(lines)
    await msg.answer(txt, reply_markup=admin_paginator_kb("adm:users", 0, total_pages))


@router.message(F.text == messages.MENU_ADMIN_SUBS)
async def menu_admin_subs(msg: Message, db: DB, xui: XUIClient) -> None:
    total = await db.count_active_subscriptions()
    total_pages = max((total + SUBS_PER_PAGE - 1) // SUBS_PER_PAGE, 1)
    subs = await db.list_active_subscriptions(SUBS_PER_PAGE, 0)
    stats = await xui.get_inbound_client_stats(settings.xui_inbound_id)
    by_email = {s.get("email"): s for s in stats}
    if not subs:
        txt = "🔐 <b>Активные подписки</b>\n\nПусто."
    else:
        lines = [f"🔐 <b>Активные подписки</b> ({total})\n"]
        for s in subs:
            cs = by_email.get(s.xui_email) or {}
            up = cs.get("up", 0) or 0
            down = cs.get("down", 0) or 0
            tariff = get_tariff(s.tariff_code)
            ttl = tariff.title if tariff else s.tariff_code
            limit = format_traffic(s.traffic_gb)
            lines.append(
                f"#{s.id} <code>{s.tg_id}</code>\n"
                f"  {ttl} · {limit} · до {s.expires_at[:10]}\n"
                f"  ⬆️ {format_used(up)} ⬇️ {format_used(down)} · Σ {format_used(up + down)}"
            )
        txt = "\n\n".join(lines)
    await msg.answer(txt, reply_markup=admin_paginator_kb("adm:subs", 0, total_pages))


@router.callback_query(F.data == "adm:home")
async def cb_home(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await cq.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())
    except TelegramBadRequest:
        await cq.message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())
    await cq.answer()


@router.callback_query(F.data == "adm:close")
async def cb_close(cq: CallbackQuery) -> None:
    try:
        await cq.message.delete()
    except TelegramBadRequest:
        pass
    await cq.answer()


@router.callback_query(F.data == "adm:noop")
async def cb_noop(cq: CallbackQuery) -> None:
    await cq.answer()


# ---------- 📊 Stats с разбивкой по периодам ----------

@router.callback_query(F.data == "adm:stats")
async def cb_stats_menu(cq: CallbackQuery) -> None:
    await cq.message.edit_text(
        "📊 <b>Статистика</b>\n\nВыбери период:",
        reply_markup=admin_stats_period_kb(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:stats:"))
async def cb_stats_period(cq: CallbackQuery, db: DB) -> None:
    period = cq.data.split(":")[2]
    now = datetime.now(timezone.utc)
    period_titles = {"1": "Сегодня (24ч)", "7": "Последние 7 дней", "30": "Последние 30 дней", "all": "За всё время"}
    if period == "all":
        since = None
    else:
        since = (now - timedelta(days=int(period))).isoformat()

    total_users = await db.count_users()
    active_subs = await db.count_active_subscriptions()
    total_paid, total_revenue = await db.count_payments()

    if since is None:
        new_users = total_users
        new_subs = await db.count_subscriptions_since("1970-01-01T00:00:00+00:00")
        period_paid, period_rev = total_paid, total_revenue
    else:
        new_users = await db.count_users_since(since)
        new_subs = await db.count_subscriptions_since(since)
        period_paid, period_rev = await db.count_payments_since(since)

    avg_check = period_rev // period_paid if period_paid else 0
    pending = len(await db.get_pending_payments())

    txt = (
        f"📊 <b>Статистика — {period_titles[period]}</b>\n\n"
        f"👥 Юзеры: <b>{new_users}</b> новых / <b>{total_users}</b> всего\n"
        f"🔐 Подписок выдано: <b>{new_subs}</b> (активных сейчас: <b>{active_subs}</b>)\n"
        f"💰 Оплат: <b>{period_paid}</b>\n"
        f"💵 Выручка: <b>{period_rev}₽</b>\n"
        f"🧾 Средний чек: <b>{avg_check}₽</b>\n"
        f"⏳ Pending платежей: <b>{pending}</b>\n\n"
        f"<i>Всего за всё время: {total_paid} оплат на {total_revenue}₽</i>"
    )
    try:
        await cq.message.edit_text(txt, reply_markup=admin_stats_period_kb())
    except TelegramBadRequest:
        pass
    await cq.answer()


# ---------- 🖥 Server status ----------

@router.callback_query(F.data == "adm:server")
async def cb_server(cq: CallbackQuery, xui: XUIClient) -> None:
    status = await xui.get_server_status()
    if not status:
        txt = "🖥 <b>Состояние сервера</b>\n\n⚠️ Не удалось получить данные от 3x-ui."
    else:
        cpu = status.get("cpu", 0)
        cpu_speed = status.get("cpuSpeedMhz", 0)
        cpu_cores = status.get("cpuCores", 0)
        mem = status.get("mem", {})
        mem_used = mem.get("current", 0)
        mem_total = mem.get("total", 1)
        mem_pct = mem_used / mem_total * 100 if mem_total else 0
        disk = status.get("disk", {})
        disk_used = disk.get("current", 0)
        disk_total = disk.get("total", 1)
        disk_pct = disk_used / disk_total * 100 if disk_total else 0
        uptime = status.get("uptime", 0)
        loads = status.get("loads", [0, 0, 0])
        xray_state = status.get("xray", {}).get("state", "unknown")
        xray_ver = status.get("xray", {}).get("version", "?")
        net = status.get("netTraffic", {})
        net_up = net.get("sent", 0)
        net_down = net.get("recv", 0)
        tcp = status.get("tcpCount", 0)
        udp = status.get("udpCount", 0)

        def _gb(b):
            return f"{b / (1024**3):.1f} GB" if b else "0"

        def _hms(seconds):
            d = seconds // 86400
            h = (seconds % 86400) // 3600
            m = (seconds % 3600) // 60
            return f"{d}d {h}h {m}m"

        txt = (
            "🖥 <b>Состояние сервера</b>\n\n"
            f"⏱ Аптайм: <b>{_hms(uptime)}</b>\n"
            f"⚙️ CPU: <b>{cpu:.1f}%</b> ({cpu_cores} ядра @ {cpu_speed} МГц)\n"
            f"📈 Load avg: {loads[0]:.2f} / {loads[1]:.2f} / {loads[2]:.2f}\n"
            f"🧠 RAM: <b>{_gb(mem_used)} / {_gb(mem_total)}</b> ({mem_pct:.0f}%)\n"
            f"💾 Диск: <b>{_gb(disk_used)} / {_gb(disk_total)}</b> ({disk_pct:.0f}%)\n\n"
            f"🟢 Xray: <b>{xray_state}</b> v{xray_ver}\n"
            f"🌐 TCP: <b>{tcp}</b> · UDP: <b>{udp}</b>\n"
            f"📤 Отправлено: <b>{_gb(net_up)}</b> · 📥 Получено: <b>{_gb(net_down)}</b>"
        )
    try:
        await cq.message.edit_text(txt, reply_markup=admin_back_kb())
    except TelegramBadRequest:
        pass
    await cq.answer()


# ---------- 👥 Users list (пагинация) ----------

@router.callback_query(F.data.startswith("adm:users:"))
async def cb_users(cq: CallbackQuery, db: DB) -> None:
    page = int(cq.data.split(":")[2])
    total = await db.count_users()
    total_pages = max((total + USERS_PER_PAGE - 1) // USERS_PER_PAGE, 1)
    page = max(0, min(page, total_pages - 1))
    rows = await db.get_users_page(USERS_PER_PAGE, page * USERS_PER_PAGE)
    if not rows:
        txt = "👥 <b>Юзеры</b>\n\nПусто."
    else:
        lines = [f"👥 <b>Юзеры</b> ({total})\n"]
        for tg_id, username, first_name, created in rows:
            uname = f"@{username}" if username else "—"
            name = first_name or "?"
            lines.append(
                f"<code>{tg_id}</code> · {name} · {uname}"
            )
        lines.append("\n<i>Тапни /u_&lt;tg_id&gt; чтобы открыть карточку.</i>")
        txt = "\n".join(lines)
    try:
        await cq.message.edit_text(
            txt, reply_markup=admin_paginator_kb("adm:users", page, total_pages)
        )
    except TelegramBadRequest:
        pass
    await cq.answer()


# Открыть карточку юзера через текстовую команду /u_<id>
@router.message(F.text.regexp(r"^/u_\d+$"))
async def cmd_user_short(msg: Message, db: DB, xui: XUIClient) -> None:
    tg_id = int(msg.text[3:])
    await _show_user_card(msg, tg_id, db, xui)


@router.callback_query(F.data.startswith("adm:user:"))
async def cb_user_card(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    tg_id = int(cq.data.split(":")[2])
    await _show_user_card(cq.message, tg_id, db, xui, edit=True)
    await cq.answer()


async def _show_user_card(target: Message, tg_id: int, db: DB, xui: XUIClient, edit: bool = False) -> None:
    user = await db.get_user(tg_id)
    if not user:
        text = f"❓ Юзер <code>{tg_id}</code> не найден в БД."
        kb = admin_back_kb()
        if edit:
            try:
                await target.edit_text(text, reply_markup=kb)
                return
            except TelegramBadRequest:
                pass
        await target.answer(text, reply_markup=kb)
        return

    _, username, first_name, created = user
    subs = await db.get_user_subscriptions(tg_id)
    active_subs = [s for s in subs if s.active and not s.is_expired]

    lines = [
        f"👤 <b>Карточка пользователя</b>",
        f"ID: <code>{tg_id}</code>",
        f"Имя: {first_name or '—'}",
        f"Username: @{username}" if username else "Username: —",
        f"Зарегистрирован: {format_dt_human(created)}",
        "",
        f"<b>Подписок всего:</b> {len(subs)}",
        f"<b>Активных:</b> {len(active_subs)}",
    ]
    if active_subs:
        lines.append("")
        for s in active_subs[:5]:
            traffic_data = await xui.get_client_traffic(s.xui_email)
            used = "—"
            if traffic_data:
                used_b = (traffic_data.get("up", 0) or 0) + (traffic_data.get("down", 0) or 0)
                used = format_used(used_b)
            tariff = get_tariff(s.tariff_code)
            ttl = tariff.title if tariff else s.tariff_code
            lines.append(
                f"🟢 #{s.id} · {ttl} · до {format_dt_human(s.expires_at)} · использовано {used}"
            )

    text = "\n".join(lines)
    kb = admin_user_card_kb(tg_id)
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await target.answer(text, reply_markup=kb)


# ---------- 🔐 Active subscriptions list ----------

@router.callback_query(F.data.startswith("adm:subs:"))
async def cb_subs(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    page = int(cq.data.split(":")[2])
    total = await db.count_active_subscriptions()
    total_pages = max((total + SUBS_PER_PAGE - 1) // SUBS_PER_PAGE, 1)
    page = max(0, min(page, total_pages - 1))
    subs = await db.list_active_subscriptions(SUBS_PER_PAGE, page * SUBS_PER_PAGE)

    # Один запрос за всеми клиентами с трафиком
    stats = await xui.get_inbound_client_stats(settings.xui_inbound_id)
    by_email = {s.get("email"): s for s in stats}

    if not subs:
        txt = "🔐 <b>Активные подписки</b>\n\nПусто."
    else:
        lines = [f"🔐 <b>Активные подписки</b> ({total})\n"]
        for s in subs:
            cs = by_email.get(s.xui_email) or {}
            up = cs.get("up", 0) or 0
            down = cs.get("down", 0) or 0
            total_used = up + down
            tariff = get_tariff(s.tariff_code)
            ttl = tariff.title if tariff else s.tariff_code
            limit = format_traffic(s.traffic_gb)
            lines.append(
                f"#{s.id} <code>{s.tg_id}</code>\n"
                f"  {ttl} · {limit} · до {s.expires_at[:10]}\n"
                f"  ⬆️ {format_used(up)} ⬇️ {format_used(down)} · Σ {format_used(total_used)}"
            )
        txt = "\n\n".join(lines)
    try:
        await cq.message.edit_text(
            txt, reply_markup=admin_paginator_kb("adm:subs", page, total_pages)
        )
    except TelegramBadRequest:
        pass
    await cq.answer()


# ---------- 🔍 Find user ----------

@router.callback_query(F.data == "adm:find")
async def cb_find_start(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.finding_user)
    await cq.message.edit_text(
        "🔍 <b>Найти юзера</b>\n\nПришли <code>tg_id</code> числом или <code>@username</code>.\n\n/cancel — отмена",
        reply_markup=admin_back_kb(),
    )
    await cq.answer()


@router.message(StateFilter(AdminStates.finding_user), Command("cancel"))
async def find_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отменено.", reply_markup=admin_main_kb())


@router.message(StateFilter(AdminStates.finding_user))
async def find_handle(msg: Message, state: FSMContext, db: DB, xui: XUIClient) -> None:
    await state.clear()
    q = (msg.text or "").strip()
    tg_id = None
    if q.isdigit():
        tg_id = int(q)
    elif q.startswith("@"):
        row = await db.find_user_by_username(q)
        if row:
            tg_id = int(row[0])
    if tg_id is None:
        await msg.answer(f"❓ Юзер «{q}» не найден.", reply_markup=admin_main_kb())
        return
    await _show_user_card(msg, tg_id, db, xui)


# ---------- ➕ Extend (через карточку юзера) ----------

@router.callback_query(F.data.startswith("adm:ext:"))
async def cb_extend_pick(cq: CallbackQuery, db: DB) -> None:
    tg_id = int(cq.data.split(":")[2])
    sub = await db.get_active_user_subscription(tg_id)
    if not sub:
        await cq.answer("Активной подписки нет — сначала выдай через ➕", show_alert=True)
        return
    await cq.message.edit_text(
        f"⏳ <b>Продлить подписку #{sub.id}</b>\n\n"
        f"Юзер <code>{tg_id}</code>, текущая до {format_dt_human(sub.expires_at)}\n"
        f"На сколько дней?",
        reply_markup=admin_extend_days_kb(sub.id),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:ex2:"))
async def cb_extend_apply(cq: CallbackQuery, db: DB, xui: XUIClient, bot: Bot) -> None:
    _, _, sub_id, days = cq.data.split(":")
    sub = await db.get_subscription(int(sub_id))
    if not sub:
        await cq.answer("Подписка не найдена", show_alert=True)
        return
    try:
        updated = await extend_subscription(db, xui, sub, int(days))
    except Exception as e:
        log.exception("extend failed")
        await cq.answer(f"Ошибка: {e}", show_alert=True)
        return
    try:
        await bot.send_message(
            sub.tg_id,
            f"🎁 Твоя подписка продлена на <b>{days} дней</b>!\nДействует до {format_dt_human(updated.expires_at)}",
        )
    except Exception:
        pass
    await cq.message.edit_text(
        f"✅ Подписка #{sub.id} продлена на {days} дней.\nНовая дата: {format_dt_human(updated.expires_at)}",
        reply_markup=admin_back_kb(),
    )
    await cq.answer("Готово")


# ---------- ❌ Revoke / ➕ Grant из карточки ----------

@router.callback_query(F.data.startswith("adm:rev:"))
async def cb_revoke_from_card(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    tg_id = int(cq.data.split(":")[2])
    sub = await db.get_active_user_subscription(tg_id)
    if not sub:
        await cq.answer("Активной подписки нет", show_alert=True)
        return
    await deactivate_subscription(db, xui, sub)
    await cq.answer(f"Отозвана #{sub.id}", show_alert=True)
    # Перерисуем карточку
    await _show_user_card(cq.message, tg_id, db, xui, edit=True)


@router.callback_query(F.data.startswith("adm:gr:"))
async def cb_grant_from_card(cq: CallbackQuery) -> None:
    tg_id = int(cq.data.split(":")[2])
    await cq.message.edit_text(
        f"➕ <b>Выдать подписку юзеру <code>{tg_id}</code></b>\n\nВыбери тариф:",
        reply_markup=admin_grant_tariff_kb(tg_id),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:gr2:"))
async def cb_grant_apply(cq: CallbackQuery, db: DB, xui: XUIClient, bot: Bot) -> None:
    _, _, tg_id, code = cq.data.split(":")
    tg_id = int(tg_id)
    tariff = get_tariff(code)
    if not tariff:
        await cq.answer("Тариф не найден", show_alert=True)
        return
    await db.upsert_user(tg_id=tg_id, username=None, first_name=None)
    try:
        sub, link = await activate_subscription(db, xui, tg_id, tariff)
    except Exception as e:
        log.exception("admin grant failed")
        await cq.answer(f"Ошибка: {e}", show_alert=True)
        return
    await db.create_payment(
        tg_id=tg_id, yk_id=None, tariff_code=tariff.code, amount_rub=0, status="manual"
    )
    try:
        await bot.send_message(
            tg_id,
            f"🎁 Тебе выдана подписка <b>{tariff.title}</b>!\n\nКлюч:\n<code>{link}</code>",
        )
    except Exception:
        pass
    await cq.message.edit_text(
        f"✅ Выдана подписка #{sub.id} юзеру <code>{tg_id}</code>: {tariff.title}\n\nКлюч:\n<code>{link}</code>",
        reply_markup=admin_back_kb(),
    )
    await cq.answer("Готово")


# ---------- 🎁 Gift (подарить подписку на N дней) ----------

# Кнопка из reply-клавиатуры
@router.message(F.text == messages.MENU_ADMIN_GIFT)
async def menu_gift_entry(msg: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.gifting_user)
    await msg.answer(
        "🎁 <b>Подарить ключ</b>\n\n"
        "Кому подарить? Пришли <code>tg_id</code> или <code>@username</code>.\n\n"
        "/cancel — отмена",
    )


# Кнопка из inline-меню
@router.callback_query(F.data == "adm:gift")
async def cb_gift_entry(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.gifting_user)
    await cq.message.edit_text(
        "🎁 <b>Подарить ключ</b>\n\n"
        "Кому подарить? Пришли <code>tg_id</code> или <code>@username</code>.\n\n"
        "/cancel — отмена",
        reply_markup=admin_back_kb(),
    )
    await cq.answer()


@router.message(StateFilter(AdminStates.gifting_user), Command("cancel"))
@router.message(StateFilter(AdminStates.gifting_days), Command("cancel"))
async def gift_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отменено.", reply_markup=admin_main_kb())


@router.message(StateFilter(AdminStates.gifting_user))
async def gift_pick_user(msg: Message, state: FSMContext, db: DB) -> None:
    q = (msg.text or "").strip()
    target_id: int | None = None
    if q.isdigit():
        target_id = int(q)
    elif q.startswith("@"):
        row = await db.find_user_by_username(q)
        if row:
            target_id = int(row[0])
        else:
            await msg.answer(
                f"❓ Юзер {q} не найден в БД (он должен хотя бы раз нажать /start). "
                f"Можно также просто прислать его tg_id."
            )
            return
    if target_id is None:
        await msg.answer("Нужен tg_id (число) или @username. /cancel — отмена")
        return

    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.gifting_days)
    await msg.answer(
        f"Получатель: <code>{target_id}</code>\n\n"
        f"На сколько дней дарим? Пришли число (например <b>3</b>, <b>7</b>, <b>30</b>).\n\n"
        f"Можно также через пробел указать лимит трафика в GB: <code>7 50</code> "
        f"(7 дней, 50 GB). Без второго числа — без лимита."
    )


@router.message(StateFilter(AdminStates.gifting_days))
async def gift_pick_days(
    msg: Message, state: FSMContext, db: DB, xui: XUIClient, bot: Bot
) -> None:
    parts = (msg.text or "").strip().split()
    if not parts or not parts[0].isdigit():
        await msg.answer("Нужно число дней. /cancel — отмена")
        return
    days = int(parts[0])
    traffic_gb = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if days <= 0 or days > 3650:
        await msg.answer("Дней должно быть от 1 до 3650. /cancel — отмена")
        return

    data = await state.get_data()
    await state.clear()
    target_id = int(data.get("target_id", 0))
    if not target_id:
        await msg.answer("Внутренняя ошибка, попробуй заново.", reply_markup=admin_main_kb())
        return

    # убеждаемся что юзер есть в БД
    await db.upsert_user(tg_id=target_id, username=None, first_name=None)

    try:
        sub, link = await activate_gift_subscription(
            db, xui, target_id, days=days, traffic_gb=traffic_gb
        )
    except Exception as e:
        log.exception("gift failed")
        await msg.answer(f"❌ Не удалось создать подписку: {e}", reply_markup=admin_main_kb())
        return

    # запишем как «manual» платёж с amount=0 для статистики
    await db.create_payment(
        tg_id=target_id,
        yk_id=None,
        tariff_code=sub.tariff_code,
        amount_rub=0,
        status="manual",
    )

    traffic_label = "без лимита" if traffic_gb == 0 else f"{traffic_gb} GB"
    # Сообщение получателю
    try:
        await bot.send_message(
            target_id,
            f"🎁 <b>Тебе подарили подписку!</b>\n\n"
            f"Срок: <b>{days} дн.</b>\n"
            f"Трафик: <b>{traffic_label}</b>\n"
            f"Действует до: <b>{format_dt_human(sub.expires_at)}</b>\n\n"
            f"<b>Ключ для подключения:</b>\n"
            f"<code>{link}</code>\n\n"
            f"Скопируй ссылку и добавь в Hiddify (см. «📲 Как подключиться»).",
        )
        delivered_note = "✅ Сообщение с ключом отправлено получателю."
    except Exception as e:
        log.warning("gift: notify user %s failed: %s", target_id, e)
        delivered_note = (
            f"⚠️ Не удалось отправить юзеру (он не запускал бот?): {e}\n"
            f"Перешли ему ключ вручную."
        )

    await msg.answer(
        f"🎁 <b>Подарок создан</b>\n\n"
        f"Получатель: <code>{target_id}</code>\n"
        f"Срок: <b>{days} дн.</b> · Трафик: <b>{traffic_label}</b>\n"
        f"До: {format_dt_human(sub.expires_at)}\n\n"
        f"{delivered_note}\n\n"
        f"<b>Ключ:</b>\n<code>{link}</code>",
        reply_markup=admin_main_kb(),
    )


# ---------- 📨 Send DM ----------

@router.callback_query(F.data == "adm:senddm")
async def cb_senddm_start(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.sending_dm)
    await cq.message.edit_text(
        "📨 <b>Личное сообщение</b>\n\nПришли tg_id получателя.\n\n/cancel — отмена",
        reply_markup=admin_back_kb(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:dm:"))
async def cb_dm_user_from_card(cq: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(cq.data.split(":")[2])
    await state.set_state(AdminStates.sending_dm_text)
    await state.update_data(target_id=tg_id)
    await cq.message.edit_text(
        f"📨 Сообщение юзеру <code>{tg_id}</code>\n\nПришли текст. /cancel — отмена",
        reply_markup=admin_back_kb(),
    )
    await cq.answer()


@router.message(StateFilter(AdminStates.sending_dm), Command("cancel"))
@router.message(StateFilter(AdminStates.sending_dm_text), Command("cancel"))
async def dm_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отменено.", reply_markup=admin_main_kb())


@router.message(StateFilter(AdminStates.sending_dm))
async def dm_target(msg: Message, state: FSMContext) -> None:
    q = (msg.text or "").strip()
    if not q.isdigit():
        await msg.answer("Нужен числовой tg_id. /cancel — отмена")
        return
    await state.update_data(target_id=int(q))
    await state.set_state(AdminStates.sending_dm_text)
    await msg.answer(f"Окей. Теперь пришли текст для <code>{q}</code>")


@router.message(StateFilter(AdminStates.sending_dm_text))
async def dm_send(msg: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    target = data.get("target_id")
    await state.clear()
    if not target:
        await msg.answer("Внутренняя ошибка", reply_markup=admin_main_kb())
        return
    try:
        await bot.send_message(int(target), msg.text or "(пусто)")
        await msg.answer(f"✅ Доставлено <code>{target}</code>", reply_markup=admin_main_kb())
    except Exception as e:
        await msg.answer(f"❌ Не доставлено: {e}", reply_markup=admin_main_kb())


# ---------- 📢 Broadcast ----------

@router.callback_query(F.data == "adm:bcast")
async def cb_bcast_start(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.broadcasting)
    await cq.message.edit_text(
        "📢 <b>Рассылка всем</b>\n\nПришли текст рассылки. Поддерживается HTML.\n\n/cancel — отмена",
        reply_markup=admin_back_kb(),
    )
    await cq.answer()


@router.message(StateFilter(AdminStates.broadcasting), Command("cancel"))
async def bcast_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отменено.", reply_markup=admin_main_kb())


@router.message(StateFilter(AdminStates.broadcasting))
async def bcast_preview(msg: Message, state: FSMContext, db: DB) -> None:
    await state.update_data(text=msg.html_text or msg.text or "")
    await state.set_state(AdminStates.broadcast_confirm)
    total = await db.count_users()
    await msg.answer(
        f"📢 <b>Превью рассылки</b> ({total} получателей)\n\n———\n{msg.html_text or msg.text}\n———\n\nОтправлять?",
        reply_markup=admin_confirm_kb("adm:bc:go", "adm:home"),
    )


@router.callback_query(F.data == "adm:bc:go", StateFilter(AdminStates.broadcast_confirm))
async def cb_bcast_go(cq: CallbackQuery, state: FSMContext, db: DB, bot: Bot) -> None:
    data = await state.get_data()
    text = data.get("text") or ""
    await state.clear()

    user_ids = await db.get_all_user_ids()
    sent = failed = 0
    progress_msg = await cq.message.edit_text(f"📤 Рассылка: 0 / {len(user_ids)}…")
    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception as e:
            failed += 1
            log.debug("broadcast to %s failed: %s", uid, e)
        # обновлять прогресс не чаще раза в 10 (избежим flood-limit)
        if i % 10 == 0 or i == len(user_ids):
            try:
                await progress_msg.edit_text(
                    f"📤 Рассылка: {i} / {len(user_ids)} (✅ {sent} / ❌ {failed})"
                )
            except TelegramBadRequest:
                pass
        await asyncio.sleep(0.05)  # 20 msg/sec — в пределах TG лимитов

    try:
        await progress_msg.edit_text(
            f"✅ Рассылка завершена\n\nДоставлено: <b>{sent}</b>\nОшибок: <b>{failed}</b>",
            reply_markup=admin_back_kb(),
        )
    except TelegramBadRequest:
        pass
    await cq.answer()
