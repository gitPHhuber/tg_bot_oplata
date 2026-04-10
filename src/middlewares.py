"""Middleware: инжектит общие зависимости + троттлинг."""
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .config import settings
from .db import DB
from .xui_client import XUIClient


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, db: DB, xui: XUIClient):
        super().__init__()
        self.db = db
        self.xui = xui

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["xui"] = self.xui
        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Простой rate-limit per user. Защищает от spam-кликов и от случайной
    дос-атаки самим клиентом (двойной тап и т.п.).

    Лимит: один колбэк/сообщение раз в `interval` секунд. Админы исключены.
    """

    def __init__(self, interval: float = 0.4):
        super().__init__()
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is not None and not settings.is_admin(from_user.id):
            now = time.monotonic()
            last = self._last.get(from_user.id, 0.0)
            if now - last < self.interval:
                # Ничего не делаем — глотаем событие
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except Exception:
                        pass
                return None
            self._last[from_user.id] = now
            # Prune old entries to prevent memory leak
            if len(self._last) > 5000:
                cutoff = now - 60
                self._last = {k: v for k, v in self._last.items() if v > cutoff}
        return await handler(event, data)
