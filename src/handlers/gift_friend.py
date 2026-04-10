"""Подарок подписки другу — обычный юзер платит за подписку, ключ идёт другу.

Flow:
1. m:gift → ask for recipient (tg_id или @username)
2. После ввода — выбор тарифа
3. После выбора — создаётся ЮKassa payment с recipient_tg_id != null
4. После успешной оплаты (в buy.on_check_click / scheduler) — подписка
   создаётся для recipient_tg_id, ему шлётся ключ + отправителю — подтверждение
"""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import messages, payments
from ..config import settings
from ..db import DB
from ..keyboards import gift_tariffs_kb, main_inline_back_kb, pay_kb
from ..tariffs import Tariff, get_tariff

log = logging.getLogger(__name__)
router = Router(name="gift_friend")


class GiftStates(StatesGroup):
    waiting_recipient = State()
    waiting_tariff = State()


@router.callback_query(F.data == "m:gift")
async def cb_gift_start(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GiftStates.waiting_recipient)
    try:
        await cq.message.edit_text(
            messages.GIFT_FRIEND_PROMPT, reply_markup=main_inline_back_kb()
        )
    except Exception:
        await cq.message.answer(
            messages.GIFT_FRIEND_PROMPT, reply_markup=main_inline_back_kb()
        )
    await cq.answer()


@router.message(StateFilter(GiftStates.waiting_recipient), Command("cancel"))
@router.message(StateFilter(GiftStates.waiting_tariff), Command("cancel"))
async def gift_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отменено.", reply_markup=main_inline_back_kb())


@router.message(StateFilter(GiftStates.waiting_recipient))
async def gift_pick_recipient(
    msg: Message, state: FSMContext, db: DB, bot: Bot
) -> None:
    q = (msg.text or "").strip()
    target_id: int | None = None
    target_name: str | None = None
    user_row = None
    if q.isdigit():
        target_id = int(q)
        user_row = await db.get_user(target_id)
        if user_row:
            target_name = user_row[2] or (f"@{user_row[1]}" if user_row[1] else f"ID {target_id}")
    elif q.startswith("@"):
        row = await db.find_user_by_username(q)
        if row:
            target_id = int(row[0])
            target_name = row[2] or row[1] or f"ID {target_id}"
            user_row = row  # already confirmed user exists

    if target_id is None or not user_row:
        me = await bot.get_me()
        await msg.answer(
            messages.GIFT_FRIEND_NOT_FOUND.format(
                q=q, bot_link=f"@{me.username}"
            )
        )
        return

    if target_id == msg.from_user.id:
        await msg.answer(messages.GIFT_FRIEND_SELF, reply_markup=main_inline_back_kb())
        await state.clear()
        return

    await state.update_data(recipient_id=target_id, recipient_name=target_name or str(target_id))
    await state.set_state(GiftStates.waiting_tariff)
    await msg.answer(
        messages.GIFT_FRIEND_TARIFF.format(name=target_name or str(target_id), tg_id=target_id),
        reply_markup=gift_tariffs_kb(),
    )


@router.callback_query(F.data.startswith("gft:"))
async def cb_gift_pay(
    cq: CallbackQuery, state: FSMContext, db: DB
) -> None:
    code = cq.data.split(":", 1)[1]
    tariff = get_tariff(code)
    if not tariff:
        await cq.answer("Тариф не найден", show_alert=True)
        return
    if settings.payment_mode != "yookassa":
        await cq.answer(
            "Платежи временно недоступны. Обратись к админу.", show_alert=True
        )
        return

    data = await state.get_data()
    recipient_id = int(data.get("recipient_id", 0))
    recipient_name = data.get("recipient_name") or str(recipient_id)
    if not recipient_id:
        await cq.answer("Сессия устарела, нажми «🎁 Подарить другу» ещё раз", show_alert=True)
        await state.clear()
        return

    try:
        created = await payments.create_payment(tariff, cq.from_user.id)
    except Exception:
        log.exception("create_payment for gift failed")
        await cq.answer("Не удалось создать счёт, попробуй позже", show_alert=True)
        return

    await db.create_payment(
        tg_id=cq.from_user.id,
        yk_id=created.yk_id,
        tariff_code=tariff.code,
        amount_rub=tariff.price_rub,
        status="pending",
        recipient_tg_id=recipient_id,
    )
    await state.clear()

    await cq.message.edit_text(
        messages.GIFT_PAYMENT_CREATED.format(
            recipient_name=recipient_name,
            recipient_id=recipient_id,
            tariff_title=tariff.title,
            price=f"{tariff.price_rub}₽",
        ),
        reply_markup=pay_kb(created.confirmation_url, tariff.code),
    )
    await cq.answer()
