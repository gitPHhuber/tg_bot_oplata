"""ЮKassa интеграция. SDK синхронный, оборачиваем в asyncio.to_thread.

Если PAYMENT_MODE=manual — все методы выкидывают исключение, ботом
управляет админ через /grant. Это режим разработки и MVP без юр.оформления.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from .config import settings
from .tariffs import Tariff

log = logging.getLogger(__name__)

# SDK импортится только в режиме yookassa, чтобы manual-режим работал без него
_yk_initialized = False


def _ensure_yookassa() -> None:
    global _yk_initialized
    if _yk_initialized:
        return
    if not settings.yookassa_shop_id or not settings.yookassa_secret:
        raise RuntimeError("YOOKASSA_SHOP_ID и YOOKASSA_SECRET не заданы в .env")
    from yookassa import Configuration  # noqa: WPS433

    Configuration.account_id = settings.yookassa_shop_id
    Configuration.secret_key = settings.yookassa_secret
    _yk_initialized = True
    log.info("yookassa: initialized for shop %s", settings.yookassa_shop_id)


@dataclass
class CreatedPayment:
    yk_id: str
    confirmation_url: str
    amount_rub: int


def _build_payload(tariff: Tariff, tg_id: int, method: str | None = None) -> dict:
    amount_str = f"{tariff.price_rub}.00"
    payload: dict = {
        "amount": {"value": amount_str, "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": settings.yookassa_return_url,
        },
        "description": settings.receipt_description,
        "metadata": {
            "tg_id": str(tg_id),
            "tariff": tariff.code,
        },
        "receipt": {
            "customer": {"email": settings.receipt_email},
            "items": [
                {
                    "description": settings.receipt_description,
                    "quantity": "1.00",
                    "amount": {"value": amount_str, "currency": "RUB"},
                    "vat_code": 1,  # без НДС (для СЗ — 1)
                    "payment_subject": "service",
                    "payment_mode": "full_payment",
                }
            ],
        },
    }
    # Форсируем метод → YooKassa сразу открывает экран этого метода,
    # без промежуточного выбора. None = универсальный checkout со всеми доступными.
    if method == "sbp":
        payload["payment_method_data"] = {"type": "sbp"}
    elif method == "card":
        payload["payment_method_data"] = {"type": "bank_card"}
    return payload


async def create_payment(tariff: Tariff, tg_id: int, method: str | None = None) -> CreatedPayment:
    if settings.payment_mode != "yookassa":
        raise RuntimeError("payment_mode != yookassa")
    _ensure_yookassa()

    from yookassa import Payment as YKPayment  # noqa: WPS433
    import uuid as uuid_lib

    payload = _build_payload(tariff, tg_id, method=method)
    idempotency_key = str(uuid_lib.uuid4())

    def _create() -> "YKPayment":
        return YKPayment.create(payload, idempotency_key)

    payment = await asyncio.to_thread(_create)
    return CreatedPayment(
        yk_id=payment.id,
        confirmation_url=payment.confirmation.confirmation_url,
        amount_rub=tariff.price_rub,
    )


async def get_payment_status(yk_id: str) -> Optional[str]:
    if settings.payment_mode != "yookassa":
        return None
    _ensure_yookassa()
    from yookassa import Payment as YKPayment  # noqa: WPS433

    def _find() -> "YKPayment":
        return YKPayment.find_one(yk_id)

    try:
        payment = await asyncio.to_thread(_find)
    except Exception as e:
        log.warning("yookassa: find_one(%s) failed: %s", yk_id, e)
        return None
    return payment.status  # pending | waiting_for_capture | succeeded | canceled
