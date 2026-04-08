import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import messages, payments
from ..config import settings
from ..db import DB
from ..keyboards import pay_kb, tariffs_kb
from ..services import activate_subscription
from ..tariffs import get_tariff
from ..xui_client import XUIClient

log = logging.getLogger(__name__)
router = Router(name="buy")


@router.message(F.text == messages.MENU_BUY)
async def show_tariffs(msg: Message) -> None:
    if settings.payment_mode == "manual":
        await msg.answer(
            "💳 Платёжный модуль пока не подключён.\n"
            "Чтобы получить доступ — напиши админу (см. «💬 Поддержка»)."
        )
        return
    await msg.answer(messages.TARIFF_LIST_HEADER, reply_markup=tariffs_kb())


@router.callback_query(F.data.startswith("buy:"))
async def on_buy_click(cq: CallbackQuery, db: DB) -> None:
    code = cq.data.split(":", 1)[1]
    tariff = get_tariff(code)
    if not tariff:
        await cq.answer("Тариф не найден", show_alert=True)
        return

    if settings.payment_mode != "yookassa":
        await cq.answer("Платежи отключены", show_alert=True)
        return

    try:
        created = await payments.create_payment(tariff, cq.from_user.id)
    except Exception as e:
        log.exception("create_payment failed")
        await cq.answer("Не удалось создать платёж, попробуй позже", show_alert=True)
        return

    await db.create_payment(
        tg_id=cq.from_user.id,
        yk_id=created.yk_id,
        tariff_code=tariff.code,
        amount_rub=tariff.price_rub,
        status="pending",
    )

    await cq.message.edit_text(
        messages.PAYMENT_CREATED.format(title=tariff.title, price=tariff.price_rub),
        reply_markup=pay_kb(created.confirmation_url, tariff.code),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("check:"))
async def on_check_click(cq: CallbackQuery, db: DB, xui: XUIClient, bot) -> None:
    """Юзер сам жмёт «проверить оплату» — гоним напрямую в ЮKassa."""
    pending = await db.get_pending_payments()
    user_pending = [p for p in pending if p.tg_id == cq.from_user.id]
    if not user_pending:
        await cq.answer("Активных платежей нет. Жми «Купить» снова.", show_alert=True)
        return

    payment = user_pending[-1]  # последний созданный
    if not payment.yk_id:
        await cq.answer("Внутренняя ошибка: нет ID платежа", show_alert=True)
        return

    status = await payments.get_payment_status(payment.yk_id)
    if status == "succeeded":
        tariff = get_tariff(payment.tariff_code)
        if not tariff:
            await cq.answer("Тариф удалён, обратись в поддержку", show_alert=True)
            return
        sub, link = await activate_subscription(db, xui, cq.from_user.id, tariff)
        await db.update_payment_status(payment.id, "succeeded", sub.id)
        await cq.message.edit_text(
            messages.PAYMENT_SUCCESS.format(
                tariff_title=tariff.title,
                expires=sub.expires_at[:16].replace("T", " ") + " UTC",
                link=link,
            )
        )
        return
    if status == "canceled":
        await db.update_payment_status(payment.id, "canceled")
        await cq.answer("Платёж отменён", show_alert=True)
        return

    await cq.answer("Платёж ещё не оплачен. Попробуй через 10-30 секунд после оплаты.", show_alert=True)


@router.callback_query(F.data == "cancel")
async def on_cancel(cq: CallbackQuery) -> None:
    await cq.message.edit_text("Отменено.")
    await cq.answer()
