from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str            # short id used in callback_data
    title: str           # человекочитаемое название
    price_rub: int       # цена в рублях (целое)
    days: int            # длительность подписки в днях
    traffic_gb: int      # лимит трафика; 0 = без лимита
    badge: str = ""      # пометка справа от цены: "🔥 ХИТ" / "💎 ВЫГОДНО -50%"
    featured: bool = False


# Тарифы. Меняй здесь — больше нигде дублирования нет.
TARIFFS: list[Tariff] = [
    Tariff("m_50",  "1 месяц / 50 GB",       150,  30,  50),
    Tariff("m_200", "1 месяц / 200 GB",      250,  30, 200,  badge="🔥 ХИТ", featured=True),
    Tariff("m_unl", "1 месяц / без лимита",  350,  30,   0),
    Tariff("q_unl", "3 месяца / без лимита", 900,  90,   0,  badge="−14%"),
    Tariff("y_unl", "1 год / без лимита",   3000, 365,   0,  badge="💎 −29%"),
]


def get_tariff(code: str) -> Tariff | None:
    return next((t for t in TARIFFS if t.code == code), None)
