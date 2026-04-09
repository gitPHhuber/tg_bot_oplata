"""SQLite-хранилище. Async через aiosqlite, без ORM — простой repo-pattern."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id        INTEGER PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    created_at   TEXT NOT NULL,
    referrer_id  INTEGER          -- кто пригласил (NULL если зашёл сам)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id        INTEGER NOT NULL,
    xui_uuid     TEXT NOT NULL,
    xui_email    TEXT NOT NULL UNIQUE,
    tariff_code  TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    traffic_gb   INTEGER NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (tg_id) REFERENCES users(tg_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id        INTEGER NOT NULL,
    yk_id        TEXT UNIQUE,
    tariff_code  TEXT NOT NULL,
    amount_rub   INTEGER NOT NULL,
    status       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    sub_id       INTEGER,
    FOREIGN KEY (tg_id) REFERENCES users(tg_id),
    FOREIGN KEY (sub_id) REFERENCES subscriptions(id)
);

CREATE INDEX IF NOT EXISTS idx_subs_tg ON subscriptions(tg_id);
CREATE INDEX IF NOT EXISTS idx_subs_exp ON subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_pay_status ON payments(status);

CREATE TABLE IF NOT EXISTS support_threads (
    -- mapping: пересланное в чат админа сообщение → исходный user_tg_id
    admin_chat_id  INTEGER NOT NULL,
    admin_msg_id   INTEGER NOT NULL,
    user_tg_id     INTEGER NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (admin_chat_id, admin_msg_id)
);
CREATE INDEX IF NOT EXISTS idx_support_user ON support_threads(user_tg_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


@dataclass
class Subscription:
    id: int
    tg_id: int
    xui_uuid: str
    xui_email: str
    tariff_code: str
    started_at: str
    expires_at: str
    traffic_gb: int
    active: bool

    @property
    def expires_dt(self) -> datetime:
        return parse_iso(self.expires_at)

    @property
    def is_expired(self) -> bool:
        return self.expires_dt < datetime.now(timezone.utc)


@dataclass
class Payment:
    id: int
    tg_id: int
    yk_id: Optional[str]
    tariff_code: str
    amount_rub: int
    status: str
    created_at: str
    updated_at: str
    sub_id: Optional[int]


class DB:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as conn:
            # WAL — конкурентное чтение пока scheduler/handlers пишут.
            # NORMAL synchronous — чуть быстрее FULL, при крэше теряется максимум
            # последняя транзакция (для бота приемлемо).
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.executescript(SCHEMA)
            # Идемпотентные миграции для существующих БД, где CREATE TABLE
            # уже отработал без новых колонок.
            await self._migrate(conn)
            await conn.commit()

    async def _migrate(self, conn) -> None:
        """Безопасные ALTER'ы для добавления колонок, появившихся после первого
        релиза. SQLite-friendly: только ADD COLUMN, без изменения существующих."""
        cur = await conn.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in await cur.fetchall()}
        if "referrer_id" not in cols:
            await conn.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
        # индекс создаём ПОСЛЕ ALTER, чтобы он не падал на пустой схеме
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id)"
        )

    # ---------- users ----------
    async def upsert_user(self, tg_id: int, username: str | None, first_name: str | None) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """INSERT INTO users (tg_id, username, first_name, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(tg_id) DO UPDATE SET
                     username = excluded.username,
                     first_name = excluded.first_name""",
                (tg_id, username, first_name, now_iso()),
            )
            await conn.commit()

    async def count_users(self) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM users")
            row = await cur.fetchone()
            return row[0] if row else 0

    async def count_users_since(self, since_iso: str) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?", (since_iso,)
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def get_users_page(self, limit: int, offset: int) -> list[tuple]:
        """Возвращает строки (tg_id, username, first_name, created_at)."""
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT tg_id, username, first_name, created_at FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return list(await cur.fetchall())

    async def get_all_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute("SELECT tg_id FROM users")
            return [r[0] for r in await cur.fetchall()]

    async def find_user_by_username(self, username: str) -> Optional[tuple]:
        username = username.lstrip("@")
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT tg_id, username, first_name, created_at FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            )
            row = await cur.fetchone()
            return tuple(row) if row else None

    async def get_user(self, tg_id: int) -> Optional[tuple]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT tg_id, username, first_name, created_at FROM users WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cur.fetchone()
            return tuple(row) if row else None

    # ---------- referrals ----------
    async def set_referrer_if_empty(self, tg_id: int, referrer_id: int) -> bool:
        """Сохранить кто пригласил юзера. Только если у него ещё нет referrer'а
        и referrer != сам себе. Возвращает True если установлено."""
        if tg_id == referrer_id:
            return False
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT referrer_id FROM users WHERE tg_id = ?", (tg_id,)
            )
            row = await cur.fetchone()
            if row is None or row[0] is not None:
                return False
            # убеждаемся что referrer существует
            cur2 = await conn.execute(
                "SELECT 1 FROM users WHERE tg_id = ?", (referrer_id,)
            )
            if not await cur2.fetchone():
                return False
            await conn.execute(
                "UPDATE users SET referrer_id = ? WHERE tg_id = ?",
                (referrer_id, tg_id),
            )
            await conn.commit()
            return True

    async def get_referrer(self, tg_id: int) -> Optional[int]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT referrer_id FROM users WHERE tg_id = ?", (tg_id,)
            )
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None

    async def count_referrals(self, referrer_id: int) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (referrer_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def count_paid_referrals(self, referrer_id: int) -> int:
        """Сколько приведённых юзеров уже совершили хотя бы 1 успешный платёж."""
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                """SELECT COUNT(DISTINCT u.tg_id)
                   FROM users u
                   JOIN payments p ON p.tg_id = u.tg_id
                   WHERE u.referrer_id = ? AND p.status = 'succeeded'""",
                (referrer_id,),
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def is_first_activation(self, tg_id: int) -> bool:
        """True, если у юзера ещё нет ни одной активации (любого типа). Используется
        для триггера реферального бонуса — должен вызываться ДО create_payment."""
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM payments WHERE tg_id = ? AND status IN ('succeeded', 'manual')",
                (tg_id,),
            )
            row = await cur.fetchone()
            return (row[0] if row else 0) == 0

    # ---------- subscriptions ----------
    async def create_subscription(
        self,
        tg_id: int,
        xui_uuid: str,
        xui_email: str,
        tariff_code: str,
        expires_at: str,
        traffic_gb: int,
    ) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                """INSERT INTO subscriptions
                   (tg_id, xui_uuid, xui_email, tariff_code, started_at, expires_at, traffic_gb, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (tg_id, xui_uuid, xui_email, tariff_code, now_iso(), expires_at, traffic_gb),
            )
            await conn.commit()
            return cur.lastrowid or 0

    async def get_subscription(self, sub_id: int) -> Optional[Subscription]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
            row = await cur.fetchone()
            return _row_to_sub(row) if row else None

    async def get_user_subscriptions(self, tg_id: int) -> list[Subscription]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT * FROM subscriptions WHERE tg_id = ? ORDER BY id DESC",
                (tg_id,),
            )
            rows = await cur.fetchall()
            return [_row_to_sub(r) for r in rows]

    async def get_active_user_subscription(self, tg_id: int) -> Optional[Subscription]:
        """Самая свежая активная (не помеченная как inactive)."""
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT * FROM subscriptions WHERE tg_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
                (tg_id,),
            )
            row = await cur.fetchone()
            return _row_to_sub(row) if row else None

    async def get_expiring_subscriptions(self, before_iso: str) -> list[Subscription]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT * FROM subscriptions WHERE active = 1 AND expires_at <= ?",
                (before_iso,),
            )
            rows = await cur.fetchall()
            return [_row_to_sub(r) for r in rows]

    async def deactivate_subscription(self, sub_id: int) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute("UPDATE subscriptions SET active = 0 WHERE id = ?", (sub_id,))
            await conn.commit()

    async def extend_subscription(self, sub_id: int, new_expires_iso: str) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "UPDATE subscriptions SET expires_at = ?, active = 1 WHERE id = ?",
                (new_expires_iso, sub_id),
            )
            await conn.commit()

    async def list_active_subscriptions(self, limit: int, offset: int) -> list[Subscription]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT * FROM subscriptions WHERE active = 1 ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cur.fetchall()
            return [_row_to_sub(r) for r in rows]

    async def count_active_subscriptions(self) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE active = 1 AND expires_at > ?",
                (now_iso(),),
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def count_subscriptions_since(self, since_iso: str) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE started_at >= ?",
                (since_iso,),
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    # ---------- payments ----------
    async def create_payment(
        self,
        tg_id: int,
        yk_id: Optional[str],
        tariff_code: str,
        amount_rub: int,
        status: str,
    ) -> int:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                """INSERT INTO payments
                   (tg_id, yk_id, tariff_code, amount_rub, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (tg_id, yk_id, tariff_code, amount_rub, status, now_iso(), now_iso()),
            )
            await conn.commit()
            return cur.lastrowid or 0

    async def get_pending_payments(self) -> list[Payment]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute("SELECT * FROM payments WHERE status = 'pending'")
            rows = await cur.fetchall()
            return [_row_to_pay(r) for r in rows]

    async def update_payment_status(
        self, payment_id: int, status: str, sub_id: Optional[int] = None
    ) -> None:
        async with aiosqlite.connect(self.path) as conn:
            if sub_id is not None:
                await conn.execute(
                    "UPDATE payments SET status = ?, sub_id = ?, updated_at = ? WHERE id = ?",
                    (status, sub_id, now_iso(), payment_id),
                )
            else:
                await conn.execute(
                    "UPDATE payments SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now_iso(), payment_id),
                )
            await conn.commit()

    # ---------- support ----------
    async def save_support_thread(
        self, admin_chat_id: int, admin_msg_id: int, user_tg_id: int
    ) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """INSERT OR REPLACE INTO support_threads
                   (admin_chat_id, admin_msg_id, user_tg_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (admin_chat_id, admin_msg_id, user_tg_id, now_iso()),
            )
            await conn.commit()

    async def find_support_user(
        self, admin_chat_id: int, admin_msg_id: int
    ) -> Optional[int]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT user_tg_id FROM support_threads WHERE admin_chat_id = ? AND admin_msg_id = ?",
                (admin_chat_id, admin_msg_id),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else None

    async def count_payments(self) -> tuple[int, int]:
        """Возвращает (всего успешных, сумма выручки в рублях)."""
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM payments WHERE status = 'succeeded'"
            )
            row = await cur.fetchone()
            return (row[0], row[1]) if row else (0, 0)

    async def count_payments_since(self, since_iso: str) -> tuple[int, int]:
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM payments WHERE status = 'succeeded' AND created_at >= ?",
                (since_iso,),
            )
            row = await cur.fetchone()
            return (row[0], row[1]) if row else (0, 0)


# ---------- row mappers ----------
def _row_to_sub(row) -> Subscription:
    return Subscription(
        id=row[0],
        tg_id=row[1],
        xui_uuid=row[2],
        xui_email=row[3],
        tariff_code=row[4],
        started_at=row[5],
        expires_at=row[6],
        traffic_gb=row[7],
        active=bool(row[8]),
    )


def _row_to_pay(row) -> Payment:
    return Payment(
        id=row[0],
        tg_id=row[1],
        yk_id=row[2],
        tariff_code=row[3],
        amount_rub=row[4],
        status=row[5],
        created_at=row[6],
        updated_at=row[7],
        sub_id=row[8],
    )
