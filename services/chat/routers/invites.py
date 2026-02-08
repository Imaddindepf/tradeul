"""
Invite endpoints - Group invitations
"""

import json
import secrets
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
import structlog

from models.invite import InviteResponse, InviteLinkCreate, InviteLinkResponse, InviteLinkInfo
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


# =============================================================================
# INVITE LINKS - Shareable links to join groups
# =============================================================================

def generate_invite_code(length: int = 8) -> str:
    """Generate a short, URL-safe invite code."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@router.post("/invite-links/group/{group_id}", response_model=InviteLinkResponse)
async def create_invite_link(
    group_id: str,
    data: InviteLinkCreate = Body(default=InviteLinkCreate()),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Create a shareable invite link for a group.
    Only owner/admin can create links.
    """
    db = http_clients.timescale
    
    # Check permission
    role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if role not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owners and admins can create invite links")
    
    # Generate unique code
    code = generate_invite_code()
    
    # Calculate expiration
    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)
    
    # Create the invite link
    link = await db.fetchrow("""
        INSERT INTO chat_invite_links (group_id, code, name, created_by, max_uses, expires_at)
        VALUES ($1::uuid, $2, $3, $4, $5, $6)
        RETURNING 
            id::text, group_id::text, code, name, created_by, 
            max_uses, uses, expires_at, is_active, created_at
    """, group_id, code, data.name, user.user_id, data.max_uses, expires_at)
    
    if not link:
        raise HTTPException(status_code=500, detail="Failed to create invite link")
    
    # Get group name
    group_name = await db.fetchval("""
        SELECT name FROM chat_groups WHERE id = $1::uuid
    """, group_id)
    
    logger.info("invite_link_created", group_id=group_id, code=code, by=user.user_id)
    
    return {
        **dict(link),
        "group_name": group_name,
        "created_by_name": user.name or user.username
    }


@router.get("/invite-links/group/{group_id}", response_model=List[InviteLinkResponse])
async def list_invite_links(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List all invite links for a group.
    Only owner/admin can view.
    """
    db = http_clients.timescale
    
    # Check permission
    role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if role not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owners and admins can view invite links")
    
    # Get links with group info
    links = await db.fetch("""
        SELECT 
            l.id::text, l.group_id::text, l.code, l.name, l.created_by,
            l.max_uses, l.uses, l.expires_at, l.is_active, l.created_at,
            g.name as group_name
        FROM chat_invite_links l
        JOIN chat_groups g ON g.id = l.group_id
        WHERE l.group_id = $1::uuid
        ORDER BY l.created_at DESC
    """, group_id)
    
    return [dict(link) for link in links]


@router.delete("/invite-links/{code}")
async def revoke_invite_link(
    code: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Revoke (deactivate) an invite link.
    Only owner/admin of the group can revoke.
    """
    db = http_clients.timescale
    
    # Get link and check permission
    link = await db.fetchrow("""
        SELECT l.group_id::text, m.role
        FROM chat_invite_links l
        JOIN chat_members m ON m.group_id = l.group_id AND m.user_id = $2
        WHERE l.code = $1
    """, code, user.user_id)
    
    if not link:
        raise HTTPException(status_code=404, detail="Invite link not found or you're not a member")
    
    if link["role"] not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owners and admins can revoke invite links")
    
    # Deactivate the link
    await db.execute("""
        UPDATE chat_invite_links SET is_active = FALSE WHERE code = $1
    """, code)
    
    logger.info("invite_link_revoked", code=code, by=user.user_id)
    
    return {"message": "Invite link revoked"}


@router.get("/invite-links/{code}/info", response_model=InviteLinkInfo)
async def get_invite_link_info(code: str):
    """
    Get public info about an invite link.
    Used by the join page to show group details.
    No authentication required.
    """
    db = http_clients.timescale
    
    # Get link with group info
    link = await db.fetchrow("""
        SELECT 
            l.code, l.is_active, l.max_uses, l.uses, l.expires_at,
            g.name as group_name, g.icon as group_icon,
            (SELECT COUNT(*) FROM chat_members WHERE group_id = g.id) as member_count
        FROM chat_invite_links l
        JOIN chat_groups g ON g.id = l.group_id
        WHERE l.code = $1
    """, code)
    
    if not link:
        return InviteLinkInfo(
            code=code,
            group_name="",
            member_count=0,
            is_valid=False,
            error="Enlace de invitación no encontrado"
        )
    
    # Check if link is valid
    if not link["is_active"]:
        return InviteLinkInfo(
            code=code,
            group_name=link["group_name"],
            group_icon=link["group_icon"],
            member_count=link["member_count"],
            is_valid=False,
            error="Este enlace ha sido desactivado"
        )
    
    # Check expiration
    if link["expires_at"] and link["expires_at"] < datetime.now(timezone.utc):
        return InviteLinkInfo(
            code=code,
            group_name=link["group_name"],
            group_icon=link["group_icon"],
            member_count=link["member_count"],
            is_valid=False,
            error="Este enlace ha expirado"
        )
    
    # Check max uses
    if link["max_uses"] and link["uses"] >= link["max_uses"]:
        return InviteLinkInfo(
            code=code,
            group_name=link["group_name"],
            group_icon=link["group_icon"],
            member_count=link["member_count"],
            is_valid=False,
            error="Este enlace ha alcanzado el límite de usos"
        )
    
    return InviteLinkInfo(
        code=code,
        group_name=link["group_name"],
        group_icon=link["group_icon"],
        member_count=link["member_count"],
        is_valid=True
    )


@router.post("/invite-links/{code}/join")
async def join_via_invite_link(
    code: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Join a group using an invite link.
    Returns the group data on success.
    """
    db = http_clients.timescale
    
    # Get link with validation
    link = await db.fetchrow("""
        SELECT 
            l.id::text, l.group_id::text, l.is_active, l.max_uses, l.uses, l.expires_at,
            g.name as group_name
        FROM chat_invite_links l
        JOIN chat_groups g ON g.id = l.group_id
        WHERE l.code = $1
    """, code)
    
    if not link:
        raise HTTPException(status_code=404, detail="Enlace de invitación no encontrado")
    
    # Validate link
    if not link["is_active"]:
        raise HTTPException(status_code=400, detail="Este enlace ha sido desactivado")
    
    if link["expires_at"] and link["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Este enlace ha expirado")
    
    if link["max_uses"] and link["uses"] >= link["max_uses"]:
        raise HTTPException(status_code=400, detail="Este enlace ha alcanzado el límite de usos")
    
    group_id = link["group_id"]
    
    # Check if already a member
    is_member = await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM chat_members 
            WHERE group_id = $1::uuid AND user_id = $2
        )
    """, group_id, user.user_id)
    
    if is_member:
        # Return group data anyway
        group = await db.fetchrow("""
            SELECT 
                g.id::text, g.name, g.description, g.icon, g.is_dm, g.owner_id, g.created_at,
                (SELECT COUNT(*) FROM chat_members WHERE group_id = g.id) as member_count,
                0 as unread_count
            FROM chat_groups g
            WHERE g.id = $1::uuid
        """, group_id)
        return {"message": "Ya eres miembro de este grupo", "group": dict(group), "already_member": True}
    
    # Add as member
    display_name = user.name or user.username or "Usuario"
    await db.execute("""
        INSERT INTO chat_members (group_id, user_id, user_name, user_avatar, role)
        VALUES ($1::uuid, $2, $3, $4, 'member')
        ON CONFLICT (group_id, user_id) DO NOTHING
    """, group_id, user.user_id, display_name, user.avatar)
    
    # Increment uses counter
    await db.execute("""
        UPDATE chat_invite_links SET uses = uses + 1 WHERE code = $1
    """, code)
    
    # Create system message
    await create_system_message(group_id, f"{display_name} se ha unido al grupo mediante enlace de invitación")
    
    # Get group data to return
    group = await db.fetchrow("""
        SELECT 
            g.id::text, g.name, g.description, g.icon, g.is_dm, g.owner_id, g.created_at,
            (SELECT COUNT(*) FROM chat_members WHERE group_id = g.id) as member_count,
            0 as unread_count
        FROM chat_groups g
        WHERE g.id = $1::uuid
    """, group_id)
    
    logger.info("user_joined_via_link", group_id=group_id, user_id=user.user_id, code=code)
    
    return {"message": "Te has unido al grupo", "group": dict(group), "already_member": False}