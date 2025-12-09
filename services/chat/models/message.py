from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    channel_id: Optional[str] = None
    group_id: Optional[str] = None
    content_type: str = "text"  # text, image, file, ticker
    reply_to_id: Optional[str] = None
    mentions: List[str] = []
    tickers: List[str] = []  # Tickers mentioned like $AAPL
    # Optional: client can send user info (from Clerk frontend)
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    channel_id: Optional[str]
    group_id: Optional[str]
    user_id: str
    user_name: str
    user_avatar: Optional[str]
    content: str
    content_type: str
    reply_to_id: Optional[str]
    mentions: List[str]
    tickers: List[str]
    ticker_prices: Optional[Dict[str, Dict]] = None  # {"AAPL": {"price": 150.25, "change": 2.5}}
    reactions: Dict[str, List[str]] = {}  # {"👍": ["user1", "user2"]}
    created_at: datetime
    edited_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)

