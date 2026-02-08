from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class InviteResponse(BaseModel):
    id: str
    group_id: str
    group_name: Optional[str]
    inviter_id: str
    inviter_name: Optional[str]
    invitee_id: str
    status: str  # 'pending', 'accepted', 'declined', 'expired'
    created_at: datetime
    expires_at: datetime
    responded_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class InviteLinkCreate(BaseModel):
    """Request to create an invite link."""
    name: Optional[str] = None  # Optional name for the link
    max_uses: Optional[int] = None  # None = unlimited
    expires_in_days: Optional[int] = None  # None = never expires


class InviteLinkResponse(BaseModel):
    """Response for an invite link."""
    id: str
    group_id: str
    group_name: Optional[str] = None
    code: str
    name: Optional[str] = None
    created_by: str
    created_by_name: Optional[str] = None
    max_uses: Optional[int] = None
    uses: int = 0
    expires_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime
    
    class Config:
        from_attributes = True


class InviteLinkInfo(BaseModel):
    """Public info about an invite link (for join page)."""
    code: str
    group_name: str
    group_icon: Optional[str] = None
    member_count: int
    is_valid: bool = True
    error: Optional[str] = None

