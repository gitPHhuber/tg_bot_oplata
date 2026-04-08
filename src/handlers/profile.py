from aiogram import F, Router
from aiogram.types import Message

from .. import messages
from ..config import settings
from ..db import DB
from ..services import format_dt_human, format_traffic, format_used
from ..tariffs import get_tariff
from ..vless_link import build_vless_link
from ..xui_client import XUIClient

router = Router(name="profile")


@router.message(F.text == messages.MENU_PROFILE)
async def show_profile(msg: Message, db: DB, xui: XUIClient) -> None:
    sub = await db.get_active_user_subscription(msg.from_user.id)
    if not sub or sub.is_expired:
        await msg.answer(messages.PROFILE_NONE)
        return

    tariff = get_tariff(sub.tariff_code)
    tariff_title = tariff.title if tariff else sub.tariff_code

    # Подтянем фактический трафик из xui (best-effort)
    used_str = "—"
    traffic_data = await xui.get_client_traffic(sub.xui_email)
    if traffic_data:
        used_bytes = (traffic_data.get("up", 0) or 0) + (traffic_data.get("down", 0) or 0)
        used_str = format_used(used_bytes)

    link = build_vless_link(sub.xui_uuid, remark=f"VPN-{sub.tariff_code}")
    await msg.answer(
        messages.PROFILE_ACTIVE.format(
            tariff_title=tariff_title,
            expires=format_dt_human(sub.expires_at),
            traffic=format_traffic(sub.traffic_gb),
            used=used_str,
            link=link,
        )
    )
