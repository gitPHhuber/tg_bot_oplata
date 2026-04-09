from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import messages
from ..config import settings
from ..db import DB
from ..keyboards import main_inline_back_kb
from ..services import format_dt_human, format_traffic, format_used
from ..tariffs import get_tariff
from ..vless_link import build_vless_link
from ..xui_client import XUIClient

router = Router(name="profile")


async def _build_profile_text(tg_id: int, db: DB, xui: XUIClient) -> str:
    sub = await db.get_active_user_subscription(tg_id)
    if not sub or sub.is_expired:
        return messages.PROFILE_NONE

    tariff = get_tariff(sub.tariff_code)
    if tariff:
        tariff_title = tariff.title
    elif sub.tariff_code.startswith("gift_"):
        tariff_title = f"🎁 Подарок"
    else:
        tariff_title = sub.tariff_code

    # Подтянем фактический трафик из xui (best-effort)
    used_str = "—"
    traffic_data = await xui.get_client_traffic(sub.xui_email)
    if traffic_data:
        used_bytes = (traffic_data.get("up", 0) or 0) + (traffic_data.get("down", 0) or 0)
        used_str = format_used(used_bytes)

    link = build_vless_link(sub.xui_uuid, remark=f"Atlas-{sub.tariff_code}")
    return messages.PROFILE_ACTIVE.format(
        tariff_title=tariff_title,
        expires=format_dt_human(sub.expires_at),
        traffic=format_traffic(sub.traffic_gb),
        used=used_str,
        link=link,
    )


@router.message(F.text == messages.MENU_PROFILE)
async def show_profile(msg: Message, db: DB, xui: XUIClient) -> None:
    text = await _build_profile_text(msg.from_user.id, db, xui)
    await msg.answer(text)


@router.callback_query(F.data == "m:profile")
async def cb_show_profile(cq: CallbackQuery, db: DB, xui: XUIClient) -> None:
    text = await _build_profile_text(cq.from_user.id, db, xui)
    try:
        await cq.message.edit_text(text, reply_markup=main_inline_back_kb())
    except Exception:
        await cq.message.answer(text, reply_markup=main_inline_back_kb())
    await cq.answer()
