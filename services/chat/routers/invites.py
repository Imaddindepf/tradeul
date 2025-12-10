"""
Invite endpoints - Group invitations
"""

import json
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
import structlog

from models.invite import InviteResponse
from auth.dependencies import get_current_user
from auth.models import AuthenticatedUser
from http_clients import http_clients


class AcceptInviteRequest(BaseModel):
    user_name: Optional[str] = None

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/invites", tags=["invites"])


async def create_system_message(group_id: str, content: str):
    """Create a system message when someone joins/leaves the group."""
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Insert system message
    message = await db.fetchrow("""
        INSERT INTO chat_messages (
            group_id, user_id, user_name, content, content_type
        )
        VALUES ($1::uuid, 'system', 'Sistema', $2, 'system')
        RETURNING 
            id::text, channel_id::text, group_id::text,
            user_id, user_name, user_avatar,
            content, content_type, reply_to_id::text,
            mentions, tickers, ticker_prices, reactions,
            created_at, edited_at
    """, group_id, content)
    
    if message:
        # Publish via Redis Pub/Sub
        message_payload = json.dumps({
            **dict(message),
            "created_at": message["created_at"].isoformat(),
            "edited_at": None,
            "reactions": {},
            "ticker_prices": None,
        })
        
        await redis.publish(f"chat:group:{group_id}", json.dumps({
            "type": "new_message",
            "payload": json.loads(message_payload)
        }))


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
    
    # Get inviter names from Clerk
    from .groups import get_clerk_username
    result = []
    for inv in invites:
        inv_dict = dict(inv)
        inviter_name = await get_clerk_username(inv["inviter_id"])
        inv_dict["inviter_name"] = inviter_name
        logger.info("invite_with_name", inviter_id=inv["inviter_id"], inviter_name=inviter_name, group_name=inv["group_name"])
        result.append(inv_dict)
    
    return result


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



@router.post("/group/{group_id}/accept")
async def accept_invite_by_group(
    group_id: str,
    data: AcceptInviteRequest = Body(default=AcceptInviteRequest()),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Accept an invitation by group_id and join the group.
    Returns the group data.
    """
    db = http_clients.timescale
    
    # Get pending invite for this user and group
    invite = await db.fetchrow("""
        SELECT id::text, invitee_id, status, expires_at
        FROM chat_invites
        WHERE group_id = $1::uuid AND invitee_id = $2 AND status = 'pending'
    """, group_id, user.user_id)
    
    if not invite:
        raise HTTPException(status_code=404, detail="No pending invitation found")
    
    # Check if expired
    if invite["expires_at"] < datetime.now(timezone.utc):
        await db.execute("""
            UPDATE chat_invites SET status = 'expired' WHERE id = $1::uuid
        """, invite["id"])
        raise HTTPException(status_code=400, detail="Invitation expired")
    
    # Get user display name - prioritize from request body
    display_name = data.user_name or user.name or user.username or "Usuario"
    
    # Add as member
    await db.execute("""
        INSERT INTO chat_members (group_id, user_id, user_name, user_avatar, role)
        VALUES ($1::uuid, $2, $3, $4, 'member')
        ON CONFLICT (group_id, user_id) DO NOTHING
    """, group_id, user.user_id, display_name, user.avatar)
    
    # Update invite status
    await db.execute("""
        UPDATE chat_invites 
        SET status = 'accepted', responded_at = NOW()
        WHERE id = $1::uuid
    """, invite["id"])
    
    # Create system message announcing the join
    await create_system_message(group_id, f"{display_name} se ha unido al grupo")
    
    # Get group data to return
    group = await db.fetchrow("""
        SELECT 
            g.id::text,
            g.name,
            g.description,
            g.icon,
            g.is_dm,
            g.owner_id,
            g.created_at,
            (SELECT COUNT(*) FROM chat_members WHERE group_id = g.id) as member_count,
            0 as unread_count
        FROM chat_groups g
        WHERE g.id = $1::uuid
    """, group_id)
    
    logger.info("invite_accepted_by_group", group_id=group_id, user_id=user.user_id)
    
    return dict(group)


@router.post("/group/{group_id}/decline")
async def decline_invite_by_group(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Decline an invitation by group_id.
    """
    db = http_clients.timescale
    
    # Get pending invite
    invite = await db.fetchrow("""
        SELECT id::text, status FROM chat_invites 
        WHERE group_id = $1::uuid AND invitee_id = $2 AND status = 'pending'
    """, group_id, user.user_id)
    
    if not invite:
        raise HTTPException(status_code=404, detail="No pending invitation found")
    
    # Update status
    await db.execute("""
        UPDATE chat_invites 
        SET status = 'declined', responded_at = NOW()
        WHERE id = $1::uuid
    """, invite["id"])
    
    logger.info("invite_declined_by_group", group_id=group_id, user_id=user.user_id)
    
    return {"message": "Invitation declined"}


@router.get("/group/{group_id}/pending")
async def list_pending_invites(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List pending invitations for a group. Only owner/admin can see.
    """
    db = http_clients.timescale
    
    # Check if user is owner or admin
    role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if role not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owners and admins can view pending invites")
    
    # Get pending invites with invitee info
    invites = await db.fetch("""
        SELECT 
            i.id::text,
            i.invitee_id,
            i.invitee_name,
            i.inviter_id,
            i.created_at,
            i.expires_at
        FROM chat_invites i
        WHERE i.group_id = $1::uuid 
            AND i.status = 'pending'
            AND i.expires_at > NOW()
        ORDER BY i.created_at DESC
    """, group_id)
    
    return [dict(inv) for inv in invites]


@router.delete("/group/{group_id}/pending/{invitee_id}")
async def cancel_invite(
    group_id: str,
    invitee_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Cancel a pending invitation. Only owner/admin can cancel.
    """
    db = http_clients.timescale
    
    # Check if user is owner or admin
    role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if role not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owners and admins can cancel invites")
    
    # Delete the invite
    result = await db.execute("""
        DELETE FROM chat_invites 
        WHERE group_id = $1::uuid AND invitee_id = $2 AND status = 'pending'
    """, group_id, invitee_id)
    
    logger.info("invite_cancelled", group_id=group_id, invitee=invitee_id, by=user.user_id)
    
    return {"message": "Invitation cancelled"}
