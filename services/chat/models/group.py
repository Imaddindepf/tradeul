from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    member_ids: List[str] = []  # User IDs to invite initially


class GroupResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    is_dm: bool
    owner_id: str
    created_at: datetime
    member_count: int = 0
    unread_count: int = 0
    
    class Config:
        from_attributes = True


class MemberResponse(BaseModel):
    user_id: str
    user_name: str
    user_avatar: Optional[str]
    role: str  # 'owner', 'admin', 'member'
    joined_at: datetime
    
    class Config:
        from_attributes = True

