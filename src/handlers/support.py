"""Поддержка через бота — без раскрытия username админа.

Поток:
1. Юзер жмёт «💬 Поддержка» → бот переводит его в FSM состояние SupportStates.waiting
2. Юзер пишет любое сообщение → бот копирует его всем админам, сохраняет mapping
   (admin_chat_id, admin_msg_id) → user_tg_id и выходит из FSM
3. Админ в личке боту делает reply на это сообщение → бот находит mapping и
   шлёт текст обратно юзеру
"""
import logging
from html import escape as html_escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import messages
from ..config import settings
from ..db import DB

log = logging.getLogger(__name__)
router = Router(name="support")


class SupportStates(StatesGroup):
    waiting = State()


@router.message(F.text == messages.MENU_SUPPORT)
async def support_entry(msg: Message, state: FSMContext) -> None:
    await state.set_state(SupportStates.waiting)
    await msg.answer(messages.SUPPORT_PROMPT)


@router.callback_query(F.data == "m:support")
async def cb_support_entry(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SupportStates.waiting)
    await cq.message.answer(messages.SUPPORT_PROMPT)
    await cq.answer()


@router.message(StateFilter(SupportStates.waiting), Command("cancel"))
async def support_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer(messages.SUPPORT_CANCELED)


@router.message(StateFilter(SupportStates.waiting))
async def support_relay_to_admins(
    msg: Message, state: FSMContext, db: DB, bot: Bot
) -> None:
    """Принимает любое сообщение от юзера в поддержке и копирует его всем админам."""
    await state.clear()

    user = msg.from_user
    user_link = (
        f'<a href="tg://user?id={user.id}">'
        f"{user.first_name or user.username or 'user'}</a>"
    )
    header = messages.SUPPORT_INCOMING_HEADER.format(
        user_link=user_link, tg_id=user.id
    )

    delivered = 0
    for admin_id in settings.admin_id_set:
        try:
            header_msg = await bot.send_message(admin_id, header)
            # Копия исходного сообщения (текст/фото/voice/что угодно).
            # copy_message сохраняет содержимое, но "обнуляет" автора —
            # это нам и нужно (важно сохранить anonymity полностью).
            copied = await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id,
            )
            # Сохраняем маппинг и для копии тела, и для заголовка — админ
            # может сделать reply на любое из двух сообщений.
            await db.save_support_thread(
                admin_chat_id=admin_id,
                admin_msg_id=copied.message_id,
                user_tg_id=user.id,
            )
            await db.save_support_thread(
                admin_chat_id=admin_id,
                admin_msg_id=header_msg.message_id,
                user_tg_id=user.id,
            )
            delivered += 1
        except Exception as e:
            log.warning("support: failed to deliver to admin %s: %s", admin_id, e)

    if delivered:
        await msg.answer(messages.SUPPORT_SENT)
    else:
        await msg.answer(messages.ERROR_GENERIC)


# --- ответ от админа ---
# Отдельный handler ловит ЛЮБОЕ сообщение от админа в личке, у которого есть
# reply_to_message. Если reply на сохранённое в БД сообщение — пересылаем юзеру.


def _is_admin_private_reply(msg: Message) -> bool:
    return (
        msg.chat.type == "private"
        and msg.from_user is not None
        and settings.is_admin(msg.from_user.id)
        and msg.reply_to_message is not None
    )


@router.message(F.func(_is_admin_private_reply))
async def admin_reply_to_user(msg: Message, db: DB, bot: Bot) -> None:
    log.info(
        "support: admin %s reply to msg=%s",
        msg.from_user.id, msg.reply_to_message.message_id,
    )
    user_tg_id = await db.find_support_user(
        admin_chat_id=msg.chat.id,
        admin_msg_id=msg.reply_to_message.message_id,
    )
    if user_tg_id is None:
        # Не наш тред — игнорим, а не отвечаем "не нашёл", чтобы не мешать
        # админу обычно общаться с reply вне поддержки.
        log.info("support: no mapping for msg=%s, skip", msg.reply_to_message.message_id)
        return

    text = msg.text or msg.caption or ""
    try:
        if text:
            await bot.send_message(
                user_tg_id,
                messages.SUPPORT_REPLY_TO_USER.format(text=html_escape(text)),
            )
        else:
            # Если нет текста (фото/voice/документ) — копируем как есть
            await bot.send_message(user_tg_id, "✉️ <b>Ответ от поддержки:</b>")
            await bot.copy_message(
                chat_id=user_tg_id,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id,
            )
        await msg.reply(
            messages.SUPPORT_REPLY_DELIVERED.format(tg_id=user_tg_id)
        )
    except TelegramBadRequest as e:
        log.warning("support: deliver reply to %s failed: %s", user_tg_id, e)
        await msg.reply(f"❌ Не удалось доставить: {e.message}")
