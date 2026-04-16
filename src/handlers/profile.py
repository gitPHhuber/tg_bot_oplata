from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import messages
from ..db import DB
from ..keyboards import main_inline_back_kb, profile_kb
from ..services import format_dt_human
from ..tariffs import get_tariff
from ..ui import (
    days_left,
    days_left_str,
    format_bytes,
    make_qr_png,
    progress_bar,
    status_emoji_for_days,
)
from ..vless_link import build_primary_link, build_tap_link
from ..xui_client import XUIClient

router = Router(name="profile")


def _tariff_title(code: str) -> str:
    t = get_tariff(code)
    if t:
        return t.title
    if code.startswith("gift_"):
        return "🎁 Подарок"
    return code


async def _build_profile_view(tg_id: int, db: DB, xui: XUIClient) -> tuple[str, str | None, str | None, bool]:
    """Возвращает (text, raw_link, tap_link, has_active_sub).
    raw_link — HTTPS sub-URL (для p:copy/QR и fallback копипаста в Happ).
    tap_link — landing connect.html URL, открывает Happ на мобилке одним тапом.
    В text уже подставлен tap_link (если доступен), чтобы тап по ссылке шёл в Happ."""
    sub = await db.get_active_user_subscription(tg_id)

    # История подписок (последние 5)
    all_subs = await db.get_user_subscriptions(tg_id)
    if all_subs:
        history_lines = []
        for s in all_subs[:5]:
            marker = "🟢" if s.active and not s.is_expired else "✓"
            history_lines.append(
                messages.PROFILE_HISTORY_LINE.format(
                    date=s.started_at[:10],
                    tariff_title=_tariff_title(s.tariff_code),
                    marker=marker,
                )
            )
        history_str = "\n".join(history_lines)
    else:
        history_str = messages.PROFILE_HISTORY_EMPTY

    if not sub or sub.is_expired:
        text = messages.PROFILE_NONE
        if all_subs:
            text += "\n\n<b>📜 История</b>\n" + history_str
        return text, None, None, False

    # Трафик из xui (best-effort)
    used_bytes = 0
    traffic_data = await xui.get_client_traffic(sub.xui_email)
    traffic_unavailable = traffic_data is None
    if traffic_data:
        used_bytes = (traffic_data.get("up", 0) or 0) + (traffic_data.get("down", 0) or 0)

    if sub.traffic_gb > 0:
        total_bytes = sub.traffic_gb * 1024 * 1024 * 1024
        bar = progress_bar(used_bytes, total_bytes, width=18)
        total_str = f"{sub.traffic_gb} GB"
    else:
        bar = "♾  без лимита"
        total_str = "♾"

    dl = days_left(sub.expires_at)
    link = build_primary_link(sub.sub_id, sub.xui_uuid, remark=f"Atlas-{sub.tariff_code}")
    tap_link = await build_tap_link(sub.sub_id) or link
    used_str = "⚠️ данные временно недоступны" if traffic_unavailable else format_bytes(used_bytes)
    text = messages.PROFILE_ACTIVE.format(
        tariff_title=_tariff_title(sub.tariff_code),
        status_emoji=status_emoji_for_days(dl),
        days_left_str=days_left_str(sub.expires_at),
        expires=format_dt_human(sub.expires_at),
        used_str=used_str,
        total_str=total_str,
        progress_bar=bar,
        history=history_str,
        link=tap_link,
    )
    return text, link, tap_link, True


@router.callback_query(F.data == "m:profile")
async def cb_show_profile(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    text, link, tap_link, has_active = await _build_profile_view(cq.from_user.id, db, xui)
    kb = profile_kb(has_active_sub=has_active, sub_link=tap_link if has_active else "")
    try:
        await cq.message.edit_text(text, reply_markup=kb)
    except Exception:
        await cq.message.answer(text, reply_markup=kb)
    await cq.answer()


# Старый текстовый триггер (на случай если юзер пришёл с reply-кнопки)
@router.message(F.text == messages.MENU_PROFILE)
async def show_profile(msg: Message, db: DB, xui: XUIClient) -> None:
    text, link, tap_link, has_active = await _build_profile_view(msg.from_user.id, db, xui)
    await msg.answer(text, reply_markup=profile_kb(has_active_sub=has_active, sub_link=tap_link if has_active else ""))


@router.callback_query(F.data == "p:copy")
async def cb_copy_key(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    """Отправляем ключ отдельным сообщением без форматирования —
    в TG на мобиле такое сообщение копируется целиком одним тапом."""
    _text, link, _tap, has_active = await _build_profile_view(cq.from_user.id, db, xui)
    if not has_active or not link:
        await cq.answer("Нет активной подписки", show_alert=True)
        return
    await cq.message.answer(link, parse_mode=None)
    await cq.answer("Ключ отправлен ниже — нажми на него, чтобы скопировать")


@router.callback_query(F.data == "p:qr")
async def cb_qr_key(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    _text, link, _tap, has_active = await _build_profile_view(cq.from_user.id, db, xui)
    if not has_active or not link:
        await cq.answer("Нет активной подписки", show_alert=True)
        return
    png = make_qr_png(link)
    photo = BufferedInputFile(png, filename="atlas-key.png")
    await cq.message.answer_photo(
        photo=photo,
        caption=(
            "📲 <b>QR-код твоего ключа</b>\n\n"
            "<b>iPhone:</b>\n"
            "• <b>Streisand</b> (бесплатно) → «+» → «QR-код»\n"
            "• <b>Shadowrocket</b> → сканер в левом верхнем углу\n"
            "• <b>Hiddify</b> → «+» → «Сканировать QR»\n\n"
            "<b>Android:</b>\n"
            "• <b>Hiddify</b> → «+» → «Сканировать QR»\n"
            "• <b>v2rayNG</b> → «+» → «Импорт из QR-кода»\n"
            "• <b>NekoBox</b> → «+» → «QR-код»\n\n"
            "<b>ПК / ноутбук:</b>\n"
            "• Отсканируй QR камерой телефона с экрана ноутбука"
        ),
        reply_markup=main_inline_back_kb(),
    )
    await cq.answer()
