"""Async-клиент для 3x-ui панели.

Авторизация cookie-based: POST /login → сессионный cookie сохраняется
в aiohttp.CookieJar. При 401/таймауте — переавтологин.

Все методы безопасны для конкурентного вызова — создание клиентов защищено
asyncio.Lock, чтобы исключить race при одновременных оплатах.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

log = logging.getLogger(__name__)


class XUIError(RuntimeError):
    pass


class XUIClient:
    def __init__(
        self,
        base_url: str,
        web_path: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.web_path = web_path.strip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

        self._session: Optional[aiohttp.ClientSession] = None
        self._auth_lock = asyncio.Lock()
        self._client_lock = asyncio.Lock()  # сериализуем create/delete клиентов

    @property
    def panel_url(self) -> str:
        return f"{self.base_url}/{self.web_path}"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx: ssl.SSLContext | bool = True
            if not self.verify_ssl:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> None:
        async with self._auth_lock:
            session = await self._ensure_session()
            url = f"{self.panel_url}/login"
            data = {"username": self.username, "password": self.password}
            async with session.post(url, data=data) as r:
                payload = await r.json(content_type=None)
                if not payload.get("success"):
                    raise XUIError(f"login failed: {payload.get('msg')}")
            log.info("xui: logged in as %s", self.username)

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """JSON-запрос с авто-релогином при потере сессии.

        На ЛЮБОЙ non-JSON ответ (пустое тело, HTML, redirect) — re-login
        и повтор. Раньше проверяли "login" in text, но пустой ответ
        (протухший cookie) это не ловил.
        """
        session = await self._ensure_session()
        url = f"{self.panel_url}{path}"
        for attempt in range(2):
            async with session.request(method, url, **kwargs) as r:
                text = await r.text()
                # Non-2xx — скорее всего сессия протухла
                if r.status >= 400 and attempt == 0:
                    log.warning("xui: got %s on %s, re-login", r.status, path)
                    await self.login()
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    if attempt == 0:
                        log.warning("xui: non-json on %s (len=%d), re-login", path, len(text))
                        await self.login()
                        continue
                    raise XUIError(f"non-json response: {text[:200]}")
                if not data.get("success"):
                    msg = (data.get("msg") or "").lower()
                    if "login" in msg or "session" in msg or "auth" in msg:
                        if attempt == 0:
                            await self.login()
                            continue
                    raise XUIError(f"api error: {data.get('msg')}")
                return data
        raise XUIError("max retries exceeded")

    async def list_inbounds(self) -> list[dict]:
        data = await self._request("GET", "/panel/api/inbounds/list")
        return data.get("obj", []) or []

    async def get_inbound(self, inbound_id: int) -> dict:
        for ib in await self.list_inbounds():
            if ib.get("id") == inbound_id:
                return ib
        raise XUIError(f"inbound id={inbound_id} not found")

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        total_gb: int,
        expiry_unix_ms: int,
        flow: str = "",
        limit_ip: int = 2,
        sub_id: str = "",
    ) -> str:
        """Добавить клиента в существующий VLESS-инбаунд. Возвращает UUID.
        sub_id — токен для subscription-URL (Happ one-tap). Пусто = клиент
        без sub-URL, только vless://.

        flow="" (default) для chain relay→exit: на inbound клиента Vision
        НЕ нужен (payload ломается Happ'ом при двойном Vision). Vision
        остаётся только в outbound to-exit, там он нужен для user2 на
        exit-сервере. Исторически стоял vision — убрано 2026-04-16."""
        async with self._client_lock:
            client_uuid = str(uuid_lib.uuid4())
            total_bytes = 0 if total_gb <= 0 else total_gb * 1024 * 1024 * 1024
            settings_obj = {
                "clients": [
                    {
                        "id": client_uuid,
                        "flow": flow,
                        "email": email,
                        "limitIp": limit_ip,
                        "totalGB": total_bytes,
                        "expiryTime": expiry_unix_ms,
                        "enable": True,
                        "tgId": "",
                        "subId": sub_id,
                        "reset": 0,
                    }
                ]
            }
            body = {
                "id": inbound_id,
                "settings": json.dumps(settings_obj),
            }
            await self._request(
                "POST",
                "/panel/api/inbounds/addClient",
                json=body,
                headers={"Accept": "application/json"},
            )
            log.info("xui: created client %s in inbound %s", email, inbound_id)
            return client_uuid

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        async with self._client_lock:
            await self._request(
                "POST",
                f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
            )
            log.info("xui: deleted client %s", client_uuid)

    async def update_client(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str,
        total_gb: int,
        expiry_unix_ms: int,
        enable: bool = True,
        flow: str = "",
        limit_ip: int = 2,
        sub_id: str = "",
    ) -> None:
        async with self._client_lock:
            total_bytes = 0 if total_gb <= 0 else total_gb * 1024 * 1024 * 1024
            settings_obj = {
                "clients": [
                    {
                        "id": client_uuid,
                        "flow": flow,
                        "email": email,
                        "limitIp": limit_ip,
                        "totalGB": total_bytes,
                        "expiryTime": expiry_unix_ms,
                        "enable": enable,
                        "tgId": "",
                        "subId": sub_id,
                        "reset": 0,
                    }
                ]
            }
            body = {"id": inbound_id, "settings": json.dumps(settings_obj)}
            await self._request(
                "POST",
                f"/panel/api/inbounds/updateClient/{client_uuid}",
                json=body,
            )

    async def get_client_traffic(self, email: str) -> dict | None:
        """Возвращает {up, down, total, expiryTime, enable, ...} или None."""
        try:
            data = await self._request(
                "GET", f"/panel/api/inbounds/getClientTraffics/{email}"
            )
        except XUIError:
            return None
        return data.get("obj")

    async def get_inbound_client_stats(self, inbound_id: int) -> list[dict]:
        """Возвращает массив clientStats из инбаунда — содержит email, up, down,
        enable, expiryTime для всех клиентов одним запросом (быстрее, чем
        get_client_traffic в цикле).
        """
        ib = await self.get_inbound(inbound_id)
        return ib.get("clientStats") or []

    async def get_server_status(self) -> dict:
        """Системные метрики самой панели: uptime, memory, cpu, xray status."""
        try:
            data = await self._request("POST", "/server/status")
        except XUIError as e:
            log.warning("get_server_status failed: %s", e)
            return {}
        return data.get("obj") or {}


def days_from_now_unix_ms(days: int) -> int:
    """Срок подписки в формате unix-ms (как ждёт xray expiryTime)."""
    from datetime import timedelta
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp() * 1000)
