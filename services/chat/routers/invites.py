"""
Invite endpoints - Group invitations
"""

from typing import List
from fastapi import APIRouter, HTTPException, Depends
import structlog

from models.invite import InviteResponse
from auth.dependencies import get_current_user
from auth.models import AuthenticatedUser
from http_clients import http_clients

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/invites", tags=["invites"])


@router.get("", response_model=List[InviteResponse])
async def list_my_invites(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List pending invitations for the current user.
    """
    db = http_clients.timescale
    
    invites = await db.fetch("""
        SELECT 
            i.id::text,
            i.group_id::text,
            g.name as group_name,
            i.inviter_id,
            NULL as inviter_name,  -- Would need user service lookup
            i.invitee_id,
            i.status,
            i.created_at,
            i.expires_at,
            i.responded_at
        FROM chat_invites i
        JOIN chat_groups g ON g.id = i.group_id
        WHERE i.invitee_id = $1 
            AND i.status = 'pending'
            AND i.expires_at > NOW()
        ORDER BY i.created_at DESC
    """, user.user_id)
    
    return invites


@router.post("/{invite_id}/accept")
async def accept_invite(
    invite_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Accept an invitation and join the group.
    """
    db = http_clients.timescale
    
    # Get and validate invite
    invite = await db.fetchrow("""
        SELECT group_id::text, invitee_id, status, expires_at
        FROM chat_invites
        WHERE id = $1::uuid
    """, invite_id)
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite["invitee_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Not your invitation")
    if invite["status"] != 'pending':
        raise HTTPException(status_code=400, detail="Invitation already responded to")
    
    # Check if expired
    from datetime import datetime, timezone
    if invite["expires_at"] < datetime.now(timezone.utc):
        await db.execute("""
            UPDATE chat_invites SET status = 'expired' WHERE id = $1::uuid
        """, invite_id)
        raise HTTPException(status_code=400, detail="Invitation expired")
    
    # Add as member
    await db.execute("""
        INSERT INTO chat_members (group_id, user_id, user_name, user_avatar, role)
        VALUES ($1::uuid, $2, $3, $4, 'member')
        ON CONFLICT (group_id, user_id) DO NOTHING
    """, invite["group_id"], user.user_id, user.name or user.username, user.avatar)
    
    # Update invite status
    await db.execute("""
        UPDATE chat_invites 
        SET status = 'accepted', responded_at = NOW()
        WHERE id = $1::uuid
    """, invite_id)
    
    logger.info("invite_accepted", invite_id=invite_id, user_id=user.user_id, group_id=invite["group_id"])
    
    return {"message": "Invitation accepted", "group_id": invite["group_id"]}


@router.post("/{invite_id}/decline")
async def decline_invite(
    invite_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Decline an invitation.
    """
    db = http_clients.timescale
    
    # Validate
    invite = await db.fetchrow("""
        SELECT invitee_id, status FROM chat_invites WHERE id = $1::uuid
    """, invite_id)
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite["invitee_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Not your invitation")
    if invite["status"] != 'pending':
        raise HTTPException(status_code=400, detail="Invitation already responded to")
    
    # Update status
    await db.execute("""
        UPDATE chat_invites 
        SET status = 'declined', responded_at = NOW()
        WHERE id = $1::uuid
    """, invite_id)
    
    logger.info("invite_declined", invite_id=invite_id, user_id=user.user_id)
    
    return {"message": "Invitation declined"}

