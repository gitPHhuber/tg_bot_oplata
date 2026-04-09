import logging

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import messages
from ..config import settings
from ..db import DB
from ..keyboards import main_inline_back_kb, main_inline_kb, main_menu_kb

log = logging.getLogger(__name__)
router = Router(name="start")


def _parse_ref_payload(payload: str | None) -> int | None:
    """Принимает payload из /start и пытается извлечь tg_id реферрера.
    Допустимые форматы: 'ref_12345', 'ref12345', '12345' (на крайний случай)."""
    if not payload:
        return None
    s = payload.strip().lower()
    if s.startswith("ref_"):
        s = s[4:]
    elif s.startswith("ref"):
        s = s[3:]
    return int(s) if s.isdigit() else None


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def cmd_start(
    msg: Message, command: CommandObject, state: FSMContext, db: DB
) -> None:
    # Любое /start сбрасывает текущее FSM (например, выход из поддержки)
    await state.clear()

    await db.upsert_user(
        tg_id=msg.from_user.id,
        username=msg.from_user.username,
        first_name=msg.from_user.first_name,
    )

    # Реферальная связка: только если пришёл с deep-link и ещё не привязан
    ref_id = _parse_ref_payload(command.args if command else None)
    if ref_id and settings.referral_enabled:
        ok = await db.set_referrer_if_empty(msg.from_user.id, ref_id)
        if ok:
            await msg.answer(
                messages.REFERRAL_LINKED.format(referrer_id=ref_id)
            )

    name = msg.from_user.first_name or msg.from_user.username or "друг"
    is_admin = settings.is_admin(msg.from_user.id)
    # Reply-клавиатура — для быстрого доступа (особенно админу)
    await msg.answer(
        messages.WELCOME.format(name=name),
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    # Inline главное меню — основной интерфейс
    await msg.answer(
        "Выбери действие 👇",
        reply_markup=main_inline_kb(channel_url=settings.channel_url),
    )


# ===== inline-меню роутинг =====

@router.callback_query(F.data == "m:home")
async def cb_home(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await cq.message.edit_text(
            "Выбери действие 👇",
            reply_markup=main_inline_kb(channel_url=settings.channel_url),
        )
    except Exception:
        await cq.message.answer(
            "Выбери действие 👇",
            reply_markup=main_inline_kb(channel_url=settings.channel_url),
        )
    await cq.answer()


@router.callback_query(F.data == "m:howto")
async def cb_howto(cq: CallbackQuery) -> None:
    try:
        await cq.message.edit_text(messages.HOWTO, reply_markup=main_inline_back_kb())
    except Exception:
        await cq.message.answer(messages.HOWTO, reply_markup=main_inline_back_kb())
    await cq.answer()


@router.callback_query(F.data == "m:about")
async def cb_about(cq: CallbackQuery) -> None:
    text = messages.ABOUT_HEADER + settings.about_text
    try:
        await cq.message.edit_text(text, reply_markup=main_inline_back_kb())
    except Exception:
        await cq.message.answer(text, reply_markup=main_inline_back_kb())
    await cq.answer()


@router.callback_query(F.data == "m:help")
async def cb_help(cq: CallbackQuery) -> None:
    text = (
        "🆘 <b>Помощь</b>\n\n"
        "• Выбери в меню «🔐 Моя подписка» — там твой ключ и срок\n"
        "• «📲 Как подключиться» — пошаговая инструкция\n"
        "• Не работает ключ или хочешь задать вопрос — нажми кнопку поддержки на reply-клавиатуре"
    )
    try:
        await cq.message.edit_text(text, reply_markup=main_inline_back_kb())
    except Exception:
        await cq.message.answer(text, reply_markup=main_inline_back_kb())
    await cq.answer()


# ----- старые reply-кнопки (оставлены, чтобы работало и текстом) -----

@router.message(F.text == messages.MENU_HOWTO)
async def show_howto(msg: Message) -> None:
    await msg.answer(messages.HOWTO)
