"""Middleware: инжектит общие зависимости (db, xui, admin_username) в handler kwargs."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from .db import DB
from .xui_client import XUIClient


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, db: DB, xui: XUIClient, admin_username: str):
        super().__init__()
        self.db = db
        self.xui = xui
        self.admin_username = admin_username

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["xui"] = self.xui
        data["admin_username"] = self.admin_username
        return await handler(event, data)
