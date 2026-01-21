"""
Category Configuration Models
Defines the taxonomy for filtering and grouping prediction markets
"""

from typing import Optional, List, Dict, Set
from pydantic import BaseModel, Field
from enum import Enum


class RelevanceType(str, Enum):
    """Tag relevance classification"""
    WHITELIST = "whitelist"  # Always include events with this tag
    BLACKLIST = "blacklist"  # Always exclude events with this tag
    NEUTRAL = "neutral"      # Consider but don't force include/exclude
    PENDING = "pending"      # New tag, needs review


class TagConfig(BaseModel):
    """Configuration for a single tag"""
    slug: str
    label: str
    relevance: RelevanceType = RelevanceType.NEUTRAL
    category: Optional[str] = None
    subcategory: Optional[str] = None
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    auto_classified: bool = False


class SubcategoryConfig(BaseModel):
    """Subcategory definition with keyword patterns"""
    id: str
    name: str
    keywords: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    priority: int = Field(default=0, description="Display order priority")


class CategoryConfig(BaseModel):
    """Category definition with subcategories"""
    id: str
    name: str
    description: Optional[str] = None
    subcategories: Dict[str, SubcategoryConfig] = Field(default_factory=dict)
    priority: int = Field(default=0, description="Display order priority")


# Default category taxonomy
DEFAULT_CATEGORIES: Dict[str, CategoryConfig] = {
    "geopolitics": CategoryConfig(
        id="geopolitics",
        name="Geopolitics & Conflict",
        priority=1,
        subcategories={
            "leadership": SubcategoryConfig(
                id="leadership",
                name="Leadership Changes",
                keywords=[
                    "out by", "out as", "out before",
                    "leader", "president", "prime minister",
                    "regime", "falls", "resigns", "resignation",
                    "removed", "impeach",
                    "supreme leader", "khamenei", "putin", "xi jinping",
                    "maduro", "netanyahu", "zelensky", "erdogan"
                ],
                priority=1
            ),
            "conflict": SubcategoryConfig(
                id="conflict",
                name="Conflict-Related",
                keywords=[
                    "strike on", "strike by", "strikes",
                    "invasion", "invade", "military clash",
                    "ceasefire", "war", "attack", "forces enter",
                    "capture", "occupy", "blockade"
                ],
                priority=2
            ),
            "diplomacy": SubcategoryConfig(
                id="diplomacy",
                name="Diplomacy & Relations",
                keywords=[
                    "normalize relations", "treaty", "agreement",
                    "sanctions", "embargo", "recognize",
                    "leave nato", "join nato", "alliance"
                ],
                priority=3
            ),
            "elections": SubcategoryConfig(
                id="elections",
                name="Elections",
                keywords=[
                    "presidential election", "nominee", "nomination",
                    "democratic", "republican", "election winner",
                    "prime minister election", "parliament"
                ],
                priority=4
            )
        }
    ),
    "macro": CategoryConfig(
        id="macro",
        name="Macro & Economy",
        priority=2,
        subcategories={
            "fed": SubcategoryConfig(
                id="fed",
                name="Federal Reserve",
                keywords=[
                    "fed", "rate cut", "rate hike",
                    "fomc", "powell", "federal reserve",
                    "interest rate"
                ],
                priority=1
            ),
            "indicators": SubcategoryConfig(
                id="indicators",
                name="Economic Indicators",
                keywords=[
                    "gdp", "inflation", "cpi", "ppi",
                    "recession", "unemployment", "jobs",
                    "deficit", "debt ceiling"
                ],
                priority=2
            ),
            "fiscal": SubcategoryConfig(
                id="fiscal",
                name="Fiscal Policy",
                keywords=[
                    "tariff", "tax", "spending",
                    "budget", "doge", "government spending"
                ],
                priority=3
            )
        }
    ),
    "corporate": CategoryConfig(
        id="corporate",
        name="Corporate & M&A",
        priority=3,
        subcategories={
            "ipo": SubcategoryConfig(
                id="ipo",
                name="IPO Markets",
                keywords=[
                    "ipo", "goes public", "public offering",
                    "direct listing", "spac"
                ],
                priority=1
            ),
            "ma": SubcategoryConfig(
                id="ma",
                name="Mergers & Acquisitions",
                keywords=[
                    "acquire", "acquisition", "merger",
                    "buyout", "takeover", "deal"
                ],
                priority=2
            ),
            "earnings": SubcategoryConfig(
                id="earnings",
                name="Earnings & Results",
                keywords=[
                    "earnings", "revenue", "profit",
                    "beat", "miss", "guidance"
                ],
                priority=3
            ),
            "companies": SubcategoryConfig(
                id="companies",
                name="Company Events",
                keywords=[
                    "microstrategy", "tesla", "apple", "google",
                    "microsoft", "amazon", "nvidia", "meta",
                    "spacex", "twitter", "sells", "buys",
                    "stock price", "market cap"
                ],
                priority=4
            )
        }
    ),
    "crypto": CategoryConfig(
        id="crypto",
        name="Crypto Markets",
        priority=4,
        subcategories={
            "price": SubcategoryConfig(
                id="price",
                name="Price Targets",
                keywords=[
                    "bitcoin", "btc", "ethereum", "eth",
                    "price", "ath", "all time high"
                ],
                priority=1
            ),
            "regulation": SubcategoryConfig(
                id="regulation",
                name="Regulation & Policy",
                keywords=[
                    "etf", "sec", "crypto regulation",
                    "ban", "legal", "stablecoin"
                ],
                priority=2
            ),
            "defi": SubcategoryConfig(
                id="defi",
                name="DeFi & Projects",
                keywords=[
                    "airdrop", "token launch", "protocol",
                    "defi", "nft", "dao"
                ],
                priority=3
            )
        }
    ),
    "tech": CategoryConfig(
        id="tech",
        name="Technology",
        priority=5,
        subcategories={
            "ai": SubcategoryConfig(
                id="ai",
                name="AI & Machine Learning",
                keywords=[
                    "ai", "artificial intelligence", "chatgpt",
                    "openai", "anthropic", "llm", "gpt"
                ],
                priority=1
            ),
            "products": SubcategoryConfig(
                id="products",
                name="Product Launches",
                keywords=[
                    "launch", "release", "announce",
                    "fsd", "self driving", "robot"
                ],
                priority=2
            )
        }
    )
}


# Default blacklist tags (sports, entertainment, etc.)
DEFAULT_BLACKLIST_TAGS: Set[str] = {
    # Sports
    "sports", "nfl", "nba", "mlb", "nhl", "soccer", "football",
    "basketball", "baseball", "hockey", "tennis", "golf", "mma", "ufc",
    "wrestling", "boxing", "racing", "f1", "nascar", "olympics",
    "super-bowl", "world-series", "stanley-cup", "champions-league",
    "mvp", "rookie", "playoffs", "championship",
    # Entertainment
    "music", "movies", "tv", "celebrities", "taylor-swift", "kardashian",
    "oscars", "grammy", "emmy", "awards", "streaming", "netflix",
    "gta", "video-games", "gaming", "esports", "twitch",
    "pop-culture", "entertainment", "celebrity",
    # Other non-financial
    "weather", "science", "space-exploration", "aliens", "ufo",
    "reality-tv", "dating", "bachelor", "survivor"
}


# Default whitelist tags (always include)
DEFAULT_WHITELIST_TAGS: Set[str] = {
    "finance", "economy", "business", "stocks", "stock-market",
    "fed", "interest-rates", "inflation", "recession", "gdp",
    "tariff", "trade-war", "ipo", "merger", "acquisition",
    "crypto", "bitcoin", "ethereum", "defi",
    "geopolitics", "military", "war", "conflict", "sanctions",
    "government", "policy", "regulation"
}
