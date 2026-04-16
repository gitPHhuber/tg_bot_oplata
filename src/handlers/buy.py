import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import messages, payments
from ..config import settings
from ..db import DB
from ..keyboards import install_kb, main_inline_back_kb, pay_kb, payment_method_kb, tariffs_kb
from ..services import activate_subscription, format_dt_human, process_referral_after_activation
from ..vless_link import build_tap_link
from ..tariffs import get_tariff
from ..xui_client import XUIClient

log = logging.getLogger(__name__)
router = Router(name="buy")


class BuyStates(StatesGroup):
    entering_promo = State()


def _promo_label(kind: str, value: int) -> str:
    return f"-{value}%" if kind == "percent" else f"-{value}₽"


async def _get_active_promo(state: FSMContext) -> tuple[str, int, str] | None:
    """Возвращает (kind, value, code) если в state есть применённый промо."""
    data = await state.get_data()
    code = data.get("promo_code")
    kind = data.get("promo_kind")
    value = data.get("promo_value")
    if code and kind and value is not None:
        return kind, int(value), code
    return None


async def _show_tariff_screen(target, state: FSMContext, edit: bool = False) -> None:
    promo = await _get_active_promo(state)
    label = _promo_label(promo[0], promo[1]) if promo else None
    text = messages.TARIFF_LIST_HEADER
    if promo:
        text += f"\n\n🏷 Применён промо <b>{promo[2]}</b>: {label}"
    kb = tariffs_kb(promo_label=label)
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=kb)


@router.message(F.text == messages.MENU_BUY)
async def show_tariffs(msg: Message, state: FSMContext) -> None:
    if settings.payment_mode == "manual":
        await msg.answer(
            "💳 Платёжный модуль пока не подключён.\n"
            "Чтобы получить доступ — напиши в поддержку."
        )
        return
    await _show_tariff_screen(msg, state)


@router.callback_query(F.data == "m:buy")
async def cb_show_tariffs(cq: CallbackQuery, state: FSMContext) -> None:
    if settings.payment_mode == "manual":
        await cq.answer(
            "Платёжный модуль пока не подключён. Напиши в поддержку.",
            show_alert=True,
        )
        return
    await _show_tariff_screen(cq.message, state, edit=True)
    await cq.answer()


# ----- Промокод -----

@router.callback_query(F.data == "buy:promo")
async def cb_promo_start(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyStates.entering_promo)
    await cq.message.answer(messages.PROMO_PROMPT)
    await cq.answer()


@router.message(StateFilter(BuyStates.entering_promo), Command("cancel"))
async def promo_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отменено.")


@router.message(StateFilter(BuyStates.entering_promo))
async def promo_apply(msg: Message, state: FSMContext, db: DB) -> None:
    code = (msg.text or "").strip().upper()
    promo = await db.get_promocode(code)
    if not promo:
        await state.clear()
        await msg.answer(messages.PROMO_INVALID, reply_markup=main_inline_back_kb())
        return
    pid, pcode, kind, value, max_uses, used_count, expires_at, enabled = promo
    if not enabled:
        await state.clear()
        await msg.answer(messages.PROMO_DISABLED, reply_markup=main_inline_back_kb())
        return
    if max_uses and used_count >= max_uses:
        await state.clear()
        await msg.answer(messages.PROMO_USED_OUT, reply_markup=main_inline_back_kb())
        return
    if expires_at:
        from datetime import datetime, timezone
        if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            await state.clear()
            await msg.answer(messages.PROMO_EXPIRED, reply_markup=main_inline_back_kb())
            return
    if await db.is_promo_used_by(pid, msg.from_user.id):
        await state.clear()
        await msg.answer(messages.PROMO_USED_BY_YOU, reply_markup=main_inline_back_kb())
        return

    # Сохраним в state до момента покупки
    await state.update_data(promo_code=pcode, promo_kind=kind, promo_value=value, promo_id=pid)
    await state.set_state(None)
    await msg.answer(
        messages.PROMO_APPLIED.format(label=_promo_label(kind, value))
    )
    await _show_tariff_screen(msg, state)


def _apply_promo_to_price(price: int, kind: str, value: int) -> int:
    if kind == "percent":
        return max(1, int(round(price * (100 - value) / 100)))
    return max(1, price - value)


@router.callback_query(F.data.startswith("buy:") & ~F.data.in_({"buy:promo"}))
async def on_buy_click(cq: CallbackQuery, state: FSMContext, db: DB) -> None:
    """Первый шаг: выбор тарифа → показываем выбор способа оплаты."""
    code = cq.data.split(":", 1)[1]
    tariff = get_tariff(code)
    if not tariff:
        await cq.answer("Тариф не найден", show_alert=True)
        return

    if settings.payment_mode != "yookassa":
        await cq.answer("Платежи отключены", show_alert=True)
        return

    # Проба за 49₽ — одна на юзера
    if tariff.code == "trial_50":
        if not await db.is_trial_available(cq.from_user.id):
            await cq.answer(
                "🎣 Проба за 49₽ доступна только один раз. Выбери другой тариф.",
                show_alert=True,
            )
            return

    # Считаем финальную цену (с учётом промо) — только для показа, платёж создаём на следующем шаге
    promo = await _get_active_promo(state)
    final_price = tariff.price_rub
    if promo:
        final_price = _apply_promo_to_price(tariff.price_rub, promo[0], promo[1])
    price_line = (
        f"{final_price}₽ <s>{tariff.price_rub}₽</s>"
        if promo and final_price != tariff.price_rub
        else f"{final_price}₽"
    )

    await cq.message.edit_text(
        messages.CHOOSE_PAYMENT_METHOD.format(title=tariff.title, price=price_line),
        reply_markup=payment_method_kb(tariff.code),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("pay:"))
async def on_pay_method_click(cq: CallbackQuery, state: FSMContext, db: DB) -> None:
    """Второй шаг: юзер выбрал СБП/карту — создаём платёж с нужным методом."""
    parts = cq.data.split(":")
    if len(parts) != 3:
        await cq.answer("Некорректные данные", show_alert=True)
        return
    _, code, method = parts
    if method not in ("sbp", "card"):
        await cq.answer("Неизвестный способ оплаты", show_alert=True)
        return

    tariff = get_tariff(code)
    if not tariff:
        await cq.answer("Тариф не найден", show_alert=True)
        return
    if settings.payment_mode != "yookassa":
        await cq.answer("Платежи отключены", show_alert=True)
        return
    if tariff.code == "trial_50" and not await db.is_trial_available(cq.from_user.id):
        await cq.answer("🎣 Проба уже использована", show_alert=True)
        return

    # Применяем промо
    promo = await _get_active_promo(state)
    promo_id: int | None = None
    final_price = tariff.price_rub
    if promo:
        kind, value, _pcode = promo
        final_price = _apply_promo_to_price(tariff.price_rub, kind, value)
        data = await state.get_data()
        promo_id = data.get("promo_id")

    try:
        from ..tariffs import Tariff as _T
        priced = _T(
            code=tariff.code,
            title=tariff.title,
            price_rub=final_price,
            days=tariff.days,
            traffic_gb=tariff.traffic_gb,
            limit_ip=tariff.limit_ip,
            whitelist=tariff.whitelist,
            allowlist_exit=tariff.allowlist_exit,
        )
        created = await payments.create_payment(priced, cq.from_user.id, method=method)
    except Exception:
        log.exception("create_payment failed")
        await cq.answer("Не удалось создать платёж, попробуй позже", show_alert=True)
        return

    await db.create_payment(
        tg_id=cq.from_user.id,
        yk_id=created.yk_id,
        tariff_code=tariff.code,
        amount_rub=final_price,
        status="pending",
        promo_id=promo_id,
    )

    price_line = (
        f"{final_price}₽ <s>{tariff.price_rub}₽</s>"
        if promo and final_price != tariff.price_rub
        else f"{final_price}₽"
    )
    method_label = "🇷🇺 СБП" if method == "sbp" else "💳 Картой"
    await cq.message.edit_text(
        messages.PAYMENT_CREATED.format(title=tariff.title, price=price_line) +
        f"\n\nСпособ: <b>{method_label}</b>",
        reply_markup=pay_kb(created.confirmation_url, tariff.code),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("check:"))
async def on_check_click(cq: CallbackQuery, state: FSMContext, db: DB, xui: XUIClient, bot, xui_wl: XUIClient | None = None) -> None:
    """Юзер сам жмёт «проверить оплату» — гоним напрямую в ЮKassa."""
    pending = await db.get_pending_payments()
    user_pending = [p for p in pending if p.tg_id == cq.from_user.id]
    if not user_pending:
        await cq.answer("Активных платежей нет. Создай новый через «🛒 Купить подписку».", show_alert=True)
        return

    payment = user_pending[-1]  # последний созданный
    if not payment.yk_id:
        await cq.answer("Внутренняя ошибка: нет ID платежа", show_alert=True)
        return

    status = await payments.get_payment_status(payment.yk_id)
    if status == "succeeded":
        # Re-read to guard against race with scheduler
        fresh_payments = await db.get_pending_payments()
        fresh = next((pp for pp in fresh_payments if pp.id == payment.id and pp.status == "pending"), None)
        if not fresh:
            await cq.answer("Платёж уже обработан", show_alert=True)
            return
        tariff = get_tariff(payment.tariff_code)
        if not tariff:
            await cq.answer("Тариф удалён, обратись в поддержку", show_alert=True)
            return
        beneficiary_id = payment.recipient_tg_id or cq.from_user.id
        sub, link = await activate_subscription(db, xui, beneficiary_id, tariff, xui_wl=xui_wl)
        await db.update_payment_status(payment.id, "succeeded", sub.id)
        # Списываем промо если был использован
        if payment.promo_id:
            try:
                await db.use_promocode(payment.promo_id, cq.from_user.id)
            except Exception:
                pass
        # Очищаем промо из state — повторное использование одним юзером невозможно
        await state.update_data(promo_code=None, promo_kind=None, promo_value=None, promo_id=None)

        if payment.recipient_tg_id:
            # gift flow: получателю шлём ключ, покупателю — подтверждение
            buyer = await db.get_user(cq.from_user.id)
            buyer_name = (
                (buyer[2] if buyer else None)
                or (f"@{buyer[1]}" if buyer and buyer[1] else "друг")
            )
            try:
                await bot.send_message(
                    payment.recipient_tg_id,
                    messages.GIFT_RECEIVED_FROM_FRIEND.format(
                        from_name=buyer_name,
                        tariff_title=tariff.title,
                        expires=format_dt_human(sub.expires_at),
                        link=link,
                    ),
                    reply_markup=install_kb(await build_tap_link(sub.sub_id, wl=tariff.allowlist_exit) or link),
                )
            except Exception as e:
                log.warning("notify gift recipient %s failed: %s", payment.recipient_tg_id, e)
            await cq.message.edit_text(
                messages.GIFT_DELIVERED_TO_BUYER.format(
                    recipient_id=payment.recipient_tg_id,
                    tariff_title=tariff.title,
                    expires=format_dt_human(sub.expires_at),
                )
            )
        else:
            await cq.message.edit_text(
                messages.PAYMENT_SUCCESS.format(
                    tariff_title=tariff.title,
                    expires=format_dt_human(sub.expires_at),
                    link=link,
                ),
                reply_markup=install_kb(await build_tap_link(sub.sub_id, wl=tariff.allowlist_exit) or link),
            )
        await process_referral_after_activation(db, xui, bot, beneficiary_id, xui_wl=xui_wl)
        return
    if status == "canceled":
        await db.update_payment_status(payment.id, "canceled")
        await cq.answer("Платёж отменён или просрочен. Создай новый через «🛒 Купить подписку».", show_alert=True)
        return

    await cq.answer("Платёж ещё не оплачен. Попробуй через 10-30 секунд после оплаты.", show_alert=True)


@router.callback_query(F.data == "cancel")
async def on_cancel(cq: CallbackQuery) -> None:
    await cq.message.edit_text("Отменено.", reply_markup=main_inline_back_kb())
    await cq.answer()
