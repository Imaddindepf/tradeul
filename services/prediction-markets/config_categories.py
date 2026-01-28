"""
Polymarket Categories Configuration
Use /api/v1/predictions/check-categories to discover new categories.
"""

INCLUDE_CATEGORIES = [
    # Geopolitics
    "geopolitics",
    "greenland",
    "ukraine",
    "iran",
    "china",
    "israel",
    "gaza",
    "syria",
    "yemen",
    "venezuela",
    "trade-war",
    "tariffs",
    "foreign-policy",
    # Politics
    "politics",
    "trump",
    "trump-cabinet",
    "elections",
    "global-elections",
    "us-presidential-election",
    "congress",
    "midterms",
    # Economy
    "economy",
    "finance",
    "fed",
    "fed-rates",
    "earnings",
    "business",
    "ipos",
    "acquisitions",
    "inflation",
    "gdp",
    # Crypto
    "crypto",
    "bitcoin",
    "crypto-prices",
    "airdrops",
    # Tech
    "tech",
    "ai",
    "openai",
    "big-tech",
    "elon-musk",
]

EXCLUDE_CATEGORIES = [
    "sports", "pop-culture", "mention-markets",
    "nfl", "nba", "mlb", "nhl", "soccer", "ufc", "boxing",
    "movies", "music", "celebrities", "taylor-swift", "mrbeast",
    "reality-tv", "grammys", "oscars",
]

EVENTS_PER_CATEGORY = 100
