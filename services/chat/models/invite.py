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

