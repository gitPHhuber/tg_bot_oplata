"""Точка входа.

Запуск:
    python -m src.main

Все настройки — в .env (см. .env.example).
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import settings
from .db import DB
from .handlers import admin_router, buy_router, profile_router, start_router
from .middlewares import DependenciesMiddleware
from .scheduler import setup_scheduler
from .xui_client import XUIClient


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # APScheduler шумный — приглушим до WARNING
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    log = logging.getLogger("vpn-bot")

    log.info("starting vpn-bot, payment_mode=%s", settings.payment_mode)

    db = DB(settings.db_path)
    await db.init()

    xui = XUIClient(
        base_url=settings.xui_url,
        web_path=settings.xui_path,
        username=settings.xui_user,
        password=settings.xui_pass,
        verify_ssl=settings.xui_verify_ssl,
    )
    await xui.login()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    log.info("authorized as @%s", me.username)
    admin_username = me.username or "admin"

    dp = Dispatcher()
    dp.update.middleware(DependenciesMiddleware(db, xui, admin_username))
    dp.include_router(start_router)
    dp.include_router(buy_router)
    dp.include_router(profile_router)
    dp.include_router(admin_router)

    scheduler = setup_scheduler(db, xui, bot)
    scheduler.start()
    log.info("scheduler started: poll=%ss, expire-check=%smin",
             settings.payment_poll_interval, settings.sub_check_interval)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await xui.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
