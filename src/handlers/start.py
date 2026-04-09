from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import messages
from ..db import DB
from ..keyboards import main_menu_kb

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, db: DB) -> None:
    # Любое /start сбрасывает текущее FSM-состояние (например, выход из поддержки)
    await state.clear()
    await db.upsert_user(
        tg_id=msg.from_user.id,
        username=msg.from_user.username,
        first_name=msg.from_user.first_name,
    )
    name = msg.from_user.first_name or msg.from_user.username or "друг"
    await msg.answer(
        messages.WELCOME.format(name=name),
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == messages.MENU_HOWTO)
async def show_howto(msg: Message) -> None:
    await msg.answer(messages.HOWTO)
