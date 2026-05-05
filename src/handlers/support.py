"""Поддержка вынесена в отдельный бот @AtlasGoSupport_Bot.

Кнопка «💬 Поддержка» в этом боте — это просто шорткат: бот шлёт
сообщение с inline-кнопкой URL, которая открывает диалог с
support-ботом и автоматически прокидывает `?start=vpn` (источник
для админского заголовка).

Старая FSM-обработка (юзер пишет → копия всем админам в этом же
боте) удалена. Записи `support_thread` в БД больше не пишутся; old
rows просто остаются висеть, миграция их не сносит — мало ли админ
захочет их посмотреть.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import messages

log = logging.getLogger(__name__)
router = Router(name="support")


SUPPORT_BOT_DEEPLINK = "https://t.me/AtlasGoSupport_Bot?start=vpn"


def _support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Открыть @AtlasGoSupport_Bot", url=SUPPORT_BOT_DEEPLINK),
        ]]
    )


@router.message(F.text == messages.MENU_SUPPORT)
async def support_entry(msg: Message) -> None:
    await msg.answer(messages.SUPPORT_REDIRECT, reply_markup=_support_keyboard())


@router.callback_query(F.data == "m:support")
async def cb_support_entry(cq: CallbackQuery) -> None:
    await cq.message.answer(messages.SUPPORT_REDIRECT, reply_markup=_support_keyboard())
    await cq.answer()
