import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import messages
from ..config import settings
from ..db import DB
from ..keyboards import (
    about_kb,
    admin_reply_kb,
    main_inline_back_kb,
    main_inline_kb,
    offer_kb,
)
from ..services import (
    activate_gift_subscription,
    format_dt_human,
    process_referral_after_activation,
)

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
    users_count = await db.count_users()
    trial_ok = await db.is_trial_available(msg.from_user.id)

    # Reply-клавиатура — только для админа (юзеры идут чисто через inline)
    if is_admin:
        await msg.answer(
            messages.WELCOME.format(name=name, users_count=users_count),
            reply_markup=admin_reply_kb(),
        )
    else:
        await msg.answer(
            messages.WELCOME.format(name=name, users_count=users_count),
        )

    # Inline главное меню — основной интерфейс
    await msg.answer(
        "Выбери действие 👇",
        reply_markup=main_inline_kb(
            channel_url=settings.channel_url,
            show_trial=trial_ok,
        ),
    )


# ===== Free trial =====

@router.callback_query(F.data == "m:trial")
async def cb_trial(cq: CallbackQuery, db: DB, xui, bot) -> None:
    if not await db.is_trial_available(cq.from_user.id):
        await cq.answer(messages.TRIAL_OFFERED_ALREADY, show_alert=True)
        return
    try:
        sub, link = await activate_gift_subscription(
            db, xui, cq.from_user.id, days=3, traffic_gb=0
        )
    except Exception as e:
        log.exception("trial activation failed")
        await cq.answer(f"Ошибка: {e}", show_alert=True)
        return
    await db.mark_trial_used(cq.from_user.id)
    # Записать как manual-платёж 0₽ для статистики/реферальной механики
    await db.create_payment(
        tg_id=cq.from_user.id,
        yk_id=None,
        tariff_code=sub.tariff_code,
        amount_rub=0,
        status="manual",
    )
    # Триггер реферального бонуса (это первая активация)
    await process_referral_after_activation(db, xui, bot, cq.from_user.id)
    text = messages.TRIAL_GRANTED.format(
        expires=format_dt_human(sub.expires_at), link=link
    )
    try:
        await cq.message.edit_text(text, reply_markup=main_inline_back_kb())
    except Exception:
        await cq.message.answer(text, reply_markup=main_inline_back_kb())
    await cq.answer("Подписка активирована 🎉")


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
        await cq.message.edit_text(
            text, reply_markup=about_kb(), disable_web_page_preview=True
        )
    except Exception:
        await cq.message.answer(
            text, reply_markup=about_kb(), disable_web_page_preview=True
        )
    await cq.answer()


@router.callback_query(F.data == "m:offer")
async def cb_offer(cq: CallbackQuery) -> None:
    try:
        await cq.message.edit_text(
            settings.offer_text, reply_markup=offer_kb(), disable_web_page_preview=True
        )
    except Exception:
        await cq.message.answer(
            settings.offer_text, reply_markup=offer_kb(), disable_web_page_preview=True
        )
    await cq.answer()


HELP_TEXT = (
    "🆘 <b>Помощь</b>\n\n"
    "• «🔐 Моя подписка» — ключ, срок и трафик\n"
    "• «📲 Как подключиться» — пошаговая инструкция\n"
    "• «🛒 Купить подписку» — тарифы и оплата\n"
    "• «🤝 Реферальная программа» — приглашай друзей и получай дни в подарок\n\n"
    "Не работает ключ или есть вопрос — напиши нам через раздел поддержки в боте."
)


@router.callback_query(F.data == "m:help")
async def cb_help(cq: CallbackQuery) -> None:
    try:
        await cq.message.edit_text(HELP_TEXT, reply_markup=main_inline_back_kb())
    except Exception:
        await cq.message.answer(HELP_TEXT, reply_markup=main_inline_back_kb())
    await cq.answer()


# Алиасы для команд из меню @BotFather (/setcommands)
@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(HELP_TEXT, reply_markup=main_inline_back_kb())


@router.message(Command("buy"))
async def cmd_buy(msg: Message) -> None:
    # Просто эмулируем кнопку «Купить подписку»
    await msg.answer(
        "🛒 Открой главное меню и нажми «Купить подписку».\n"
        "Или просто отправь /start.",
        reply_markup=main_inline_back_kb(),
    )


@router.message(Command("profile"))
async def cmd_profile(msg: Message) -> None:
    await msg.answer(
        "🔐 Открой главное меню и нажми «Моя подписка».\n"
        "Или просто отправь /start.",
        reply_markup=main_inline_back_kb(),
    )


# ----- старые reply-кнопки (оставлены, чтобы работало и текстом) -----

@router.message(F.text == messages.MENU_HOWTO)
async def show_howto(msg: Message) -> None:
    await msg.answer(messages.HOWTO)
