from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str                # short id used in callback_data
    title: str               # человекочитаемое название
    price_rub: int           # цена в рублях (целое)
    days: int                # длительность подписки в днях
    traffic_gb: int = 0      # 0 = безлимит (FUP прописан в оферте)
    limit_ip: int = 3        # сколько одновременных подключений с одного профиля
    whitelist: bool = False  # True = Pro split-tunnel (РФ-домены direct, xui_inbound_id_pro)
    # True = тариф «Обход белых списков» для allowlist-регионов (Дагестан и пр.).
    # Клиент создаётся в отдельной 3x-ui панели (relay), inbound с Reality
    # SNI-spoof под CDN Одноклассников. Проходит через мобильный ТСПУ-allowlist.
    allowlist_exit: bool = False
    badge: str = ""          # пометка справа от цены: "🔥 популярно" / "💎 −45%"
    featured: bool = False


# Ценовая воронка: 49 (hook) → 249 (workhorse) → 449 (upsell) → 2990 (anchor).
# Безлимит трафика во всех — декларируется на витрине; реальные пороги — через FUP.
# whitelist=True включается на уровне 3x-ui pro-inbound с split-tunnel routing.
TARIFFS: list[Tariff] = [
    Tariff(
        code="trial_50",
        title="🎣 Проба · 3 дня",
        price_rub=49,
        days=3,
        limit_ip=3,
        badge="первый раз",
    ),
    Tariff(
        code="std_m",
        title="⚡ Стандарт · 30 дней",
        price_rub=249,
        days=30,
        limit_ip=3,
        badge="🔥 популярно",
        featured=True,
    ),
    Tariff(
        code="pro_m",
        title="💎 Pro · 30 дней",
        price_rub=449,
        days=30,
        limit_ip=10,
        whitelist=True,
    ),
    Tariff(
        code="pro_y",
        title="🏆 Pro · Год",
        price_rub=2990,
        days=365,
        limit_ip=10,
        whitelist=True,
        badge="💎 −45%",
    ),
    Tariff(
        code="wl_m",
        title="🛡 Обход белых списков · 30 дней",
        price_rub=749,
        days=30,
        limit_ip=3,
        allowlist_exit=True,
        badge="для шатдауна",
    ),
]


_TARIFF_MAP: dict[str, Tariff] = {t.code: t for t in TARIFFS}


def get_tariff(code: str) -> Tariff | None:
    return _TARIFF_MAP.get(code)
