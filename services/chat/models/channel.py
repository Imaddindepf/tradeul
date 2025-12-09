from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ChannelResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    is_default: bool
    sort_order: int
    created_at: datetime
    message_count: int = 0
    
    class Config:
        from_attributes = True

