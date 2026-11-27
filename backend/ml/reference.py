"""Static reference data shared by the ML pipeline, the seed script and the API.

Everything here is *sample* market data used to make the synthetic dataset
realistic. Replace it with real market data before using the platform for real.
"""

from __future__ import annotations

SOURCES: tuple[str, ...] = ("website", "facebook_ads", "newspaper", "direct")
PROPERTY_TYPES: tuple[str, ...] = ("apartment", "villa", "plot", "commercial")

# Relative price level of each micro-market (1.0 = city average). Sample values.
LOCATION_PRICE_INDEX: dict[str, float] = {
    "Aundh": 1.30,
    "Baner": 1.25,
    "Kothrud": 1.20,
    "Kharadi": 1.15,
    "Hinjewadi": 1.00,
    "Wakad": 0.95,
    "Hadapsar": 0.90,
    "Wagholi": 0.70,
}

# Typical ticket size (INR) per property type at city-average price level.
TYPE_BASE_PRICE: dict[str, float] = {
    "apartment": 8_000_000,
    "villa": 20_000_000,
    "plot": 6_000_000,
    "commercial": 15_000_000,
}

UNKNOWN = "unknown"


def market_price(location: str | None, property_type: str | None) -> float:
    """Reference market price (INR) for a location / property type pair.

    Unknown locations or types fall back to the city average / apartment price so
    that feature engineering never fails on missing data.
    """
    base = TYPE_BASE_PRICE.get(property_type or "", TYPE_BASE_PRICE["apartment"])
    index = LOCATION_PRICE_INDEX.get(location or "", 1.0)
    return base * index
