"""Реферальная программа."""
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import messages
from ..config import settings
from ..db import DB
from ..keyboards import main_inline_back_kb, referral_share_kb

router = Router(name="referral")


def _build_share_link(bot_username: str, tg_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{tg_id}"


def _build_share_url(link: str) -> str:
    """tg://msg_url=… — кнопка «Поделиться» открывает выбор чата с готовым текстом."""
    text = (
        "Я пользуюсь Atlas — быстрым VPN, и тебе советую. "
        "Жми по ссылке, регистрируйся:\n" + link
    )
    return f"https://t.me/share/url?url={quote_plus(link)}&text={quote_plus(text)}"


async def _render_referral_screen(target, tg_id: int, db: DB, bot) -> None:
    if not settings.referral_enabled:
        try:
            await target.edit_text(
                messages.REFERRAL_DISABLED, reply_markup=main_inline_back_kb()
            )
        except Exception:
            await target.answer(
                messages.REFERRAL_DISABLED, reply_markup=main_inline_back_kb()
            )
        return

    me = await bot.get_me()
    invited = await db.count_referrals(tg_id)
    paid = await db.count_paid_referrals(tg_id)
    earned = paid * settings.referral_bonus_days
    link = _build_share_link(me.username or "", tg_id)
    text = messages.REFERRAL_INFO.format(
        bonus_days=settings.referral_bonus_days,
        invited=invited,
        paid=paid,
        earned=earned,
        link=link,
    )
    kb = referral_share_kb(_build_share_url(link))
    try:
        await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data == "m:ref")
async def cb_referral(cq: CallbackQuery, db: DB, bot) -> None:
    await _render_referral_screen(cq.message, cq.from_user.id, db, bot)
    await cq.answer()


@router.message(F.text.in_({"🤝 Реферальная программа", "/ref"}))
async def show_referral(msg: Message, db: DB, bot) -> None:
    await _render_referral_screen(msg, msg.from_user.id, db, bot)
