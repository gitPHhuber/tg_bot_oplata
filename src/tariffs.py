from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str                # short id used in callback_data
    title: str               # человекочитаемое название
    price_rub: int           # цена в рублях (целое)
    days: int                # длительность подписки в днях
    traffic_gb: int = 0      # 0 = безлимит (FUP прописан в оферте)
    limit_ip: int = 3        # сколько одновременных подключений с одного профиля
    # True = тариф с умной маршрутизацией: банковские приложения и
    # госсервисы РФ работают напрямую, остальной трафик — через защищённое
    # соединение. Включается за счёт отдельного inbound с split-tunnel routing.
    whitelist: bool = False
    # True = тариф, рассчитанный на сети с ограниченным доступом
    # (мобильные операторы в режиме allowlist). Клиент создаётся в отдельной
    # 3x-ui панели (relay) с inbound, совместимым с таким режимом.
    allowlist_exit: bool = False
    badge: str = ""          # пометка справа от цены: "🔥 популярно" / "💎 −45%"
    featured: bool = False


# Ценовая воронка: 49 (hook) → 249 (workhorse) → 449 (upsell) → 2990 (anchor).
# Безлимит трафика во всех — декларируется на витрине; реальные пороги — через FUP.
# whitelist=True включает split-tunnel routing для банков и госсервисов РФ.
TARIFFS: list[Tariff] = [
    Tariff(
        code="trial_50",
        title="🎁 Тестовые 3 дня",
        price_rub=49,
        days=3,
        limit_ip=3,
        badge="первый раз",
    ),
    Tariff(
        code="std_m",
        title="⚡ Базовый · 30 дней",
        price_rub=249,
        days=30,
        limit_ip=3,
        badge="🔥 популярно",
        featured=True,
    ),
    Tariff(
        code="pro_m",
        title="💎 Расширенный · 30 дней",
        price_rub=449,
        days=30,
        limit_ip=10,
        whitelist=True,
    ),
    Tariff(
        code="pro_y",
        title="🏆 Расширенный · год",
        price_rub=2990,
        days=365,
        limit_ip=10,
        whitelist=True,
        badge="💎 −45%",
    ),
    Tariff(
        code="wl_m",
        title="🛡 Максимальный доступ · 30 дней",
        price_rub=699,
        days=30,
        limit_ip=3,
        allowlist_exit=True,
        badge="для сетей с ограничениями",
    ),
]


_TARIFF_MAP: dict[str, Tariff] = {t.code: t for t in TARIFFS}


def get_tariff(code: str) -> Tariff | None:
    return _TARIFF_MAP.get(code)
