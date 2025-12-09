"""
Group endpoints - Private groups with invitations
"""

import os
import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
import structlog
import httpx

from models.group import GroupCreate, GroupResponse, MemberResponse
from auth.dependencies import get_current_user, get_current_user_optional
from auth.models import AuthenticatedUser
from http_clients import http_clients

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/groups", tags=["groups"])

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")


async def get_clerk_username(user_id: str) -> str:
    """Get username from Clerk API."""
    if not CLERK_SECRET_KEY:
        return user_id.replace("user_", "")[:8]
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clerk.com/v1/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {CLERK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=5.0
            )
            
            if response.status_code == 200:
                data = response.json()
                # Priority: username > email prefix > first_name > id
                username = data.get("username")
                if username:
                    return username
                
                email = data.get("email_addresses", [{}])[0].get("email_address", "")
                if email:
                    return email.split("@")[0]
                
                first_name = data.get("first_name", "")
                if first_name:
                    return first_name
                
                return user_id.replace("user_", "")[:8]
    except Exception as e:
        logger.error("clerk_username_lookup_error", user_id=user_id, error=str(e))
    
    return user_id.replace("user_", "")[:8]


async def create_system_message(group_id: str, content: str):
    """Create a system message when someone joins/leaves the group."""
    db = http_clients.timescale
    redis = http_clients.redis
    
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


@router.post("", response_model=GroupResponse)
async def create_group(
    data: GroupCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Create a new private group.
    Creator becomes owner.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Create group
    group = await db.fetchrow("""
        INSERT INTO chat_groups (name, description, icon, owner_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id::text, name, description, icon, is_dm, owner_id, created_at
    """, data.name, data.description, data.icon, user.user_id)
    
    if not group:
        raise HTTPException(status_code=500, detail="Failed to create group")
    
    group_id = group["id"]
    
    # Add owner as first member
    await db.execute("""
        INSERT INTO chat_members (group_id, user_id, user_name, user_avatar, role)
        VALUES ($1::uuid, $2, $3, $4, 'owner')
    """, group_id, user.user_id, user.name or user.username, user.avatar)
    
    # Create invites for initial members and notify them
    group_data = {**dict(group), "member_count": 1, "unread_count": 0}
    
    # Get inviter's username once for all invites
    inviter_username = await get_clerk_username(user.user_id)
    
    for member_id in data.member_ids:
        if member_id != user.user_id:
            await db.execute("""
                INSERT INTO chat_invites (group_id, inviter_id, invitee_id)
                VALUES ($1::uuid, $2, $3)
                ON CONFLICT (group_id, invitee_id) DO NOTHING
            """, group_id, user.user_id, member_id)
            
            # Notify invited user via Pub/Sub
            await redis.publish(f"user:{member_id}", json.dumps({
                "type": "group_invite",
                "payload": {
                    "group": group_data,
                    "inviter_id": user.user_id,
                    "inviter_name": inviter_username
                }
            }, default=str))
    
    logger.info("group_created", group_id=group_id, owner=user.user_id)
    
    return group_data


@router.get("", response_model=List[GroupResponse])
async def list_my_groups(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List groups the current user is a member of.
    """
    db = http_clients.timescale
    
    groups = await db.fetch("""
        SELECT 
            g.id::text,
            g.name,
            g.description,
            g.icon,
            g.is_dm,
            g.owner_id,
            g.created_at,
            (SELECT COUNT(*) FROM chat_members WHERE group_id = g.id) as member_count,
            chat_unread_count($1, NULL, g.id) as unread_count
        FROM chat_groups g
        JOIN chat_members m ON m.group_id = g.id
        WHERE m.user_id = $1
        ORDER BY g.updated_at DESC
    """, user.user_id)
    
    return groups


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get a group by ID. Must be a member.
    """
    db = http_clients.timescale
    
    # Check membership
    is_member = await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM chat_members 
            WHERE group_id = $1::uuid AND user_id = $2
        )
    """, group_id, user.user_id)
    
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    
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
            chat_unread_count($2, NULL, g.id) as unread_count
        FROM chat_groups g
        WHERE g.id = $1::uuid
    """, group_id, user.user_id)
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return group


@router.get("/{group_id}/members", response_model=List[MemberResponse])
async def list_members(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List members of a group. Must be a member.
    """
    db = http_clients.timescale
    
    # Check membership
    is_member = await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM chat_members 
            WHERE group_id = $1::uuid AND user_id = $2
        )
    """, group_id, user.user_id)
    
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    
    members = await db.fetch("""
        SELECT 
            user_id,
            user_name,
            user_avatar,
            role,
            joined_at
        FROM chat_members
        WHERE group_id = $1::uuid
        ORDER BY 
            CASE role 
                WHEN 'owner' THEN 1 
                WHEN 'admin' THEN 2 
                ELSE 3 
            END,
            joined_at ASC
    """, group_id)
    
    return members


class InviteRequest(BaseModel):
    invitee_name: Optional[str] = None


@router.post("/{group_id}/invite/{invitee_id}")
async def invite_user(
    group_id: str,
    invitee_id: str,
    data: InviteRequest = Body(default=InviteRequest()),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Invite a user to a group. Must be owner or admin.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Check permission (must be owner or admin)
    role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if role not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owners and admins can invite")
    
    # Check if already a member
    is_member = await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM chat_members 
            WHERE group_id = $1::uuid AND user_id = $2
        )
    """, group_id, invitee_id)
    
    if is_member:
        raise HTTPException(status_code=400, detail="User is already a member")
    
    # Get group info for the notification
    group = await db.fetchrow("""
        SELECT id::text, name, description, icon, is_dm, owner_id
        FROM chat_groups WHERE id = $1::uuid
    """, group_id)
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Get invitee name - use provided or extract short id
    invitee_name = data.invitee_name or invitee_id.replace("user_", "")[:8]
    
    # Create invite with name
    await db.execute("""
        INSERT INTO chat_invites (group_id, inviter_id, invitee_id, invitee_name)
        VALUES ($1::uuid, $2, $3, $4)
        ON CONFLICT (group_id, invitee_id) 
        DO UPDATE SET 
            status = 'pending',
            inviter_id = $2,
            invitee_name = $4,
            created_at = NOW(),
            expires_at = NOW() + INTERVAL '7 days'
    """, group_id, user.user_id, invitee_id, invitee_name)
    
    # Get inviter's username from Clerk
    inviter_name = await get_clerk_username(user.user_id)
    
    # Publish invite notification to the invitee via Redis Pub/Sub
    invite_payload = json.dumps({
        "type": "group_invite",
        "payload": {
            "group": {
                "id": group["id"],
                "name": group["name"],
                "description": group["description"],
                "icon": group["icon"],
                "is_dm": group["is_dm"],
            },
            "inviter_id": user.user_id,
            "inviter_name": inviter_name,
        }
    })
    
    # Publish to the invitee's personal channel
    await redis.publish(f"user:{invitee_id}", invite_payload)
    
    logger.info("user_invited", group_id=group_id, inviter=user.user_id, invitee=invitee_id, invitee_name=invitee_name, published=True)
    
    return {"message": "Invitation sent"}


@router.delete("/{group_id}/members/{member_id}")
async def remove_member(
    group_id: str,
    member_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Remove a member from a group. 
    - Owner can remove anyone except self
    - Admin can remove members (not other admins)
    - Anyone can remove themselves
    """
    db = http_clients.timescale
    
    # Get current user's role
    user_role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if not user_role:
        raise HTTPException(status_code=403, detail="Not a member of this group")
    
    # Get target member's role
    target_role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    if not target_role:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Owner cannot be removed
    if target_role == 'owner':
        raise HTTPException(status_code=400, detail="Cannot remove owner")
    
    # Self-removal is always allowed
    is_self = member_id == user.user_id
    
    # Permission logic
    if not is_self:
        if user_role == 'owner':
            pass  # Owner can remove anyone
        elif user_role == 'admin':
            if target_role == 'admin':
                raise HTTPException(status_code=403, detail="Admins cannot remove other admins")
            # Admin can remove members
        else:
            raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get member name before removing
    member_name = await db.fetchval("""
        SELECT user_name FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    # Remove member
    await db.execute("""
        DELETE FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    # Create system message
    if is_self:
        await create_system_message(group_id, f"{member_name} ha salido del grupo")
    else:
        await create_system_message(group_id, f"{member_name} ha sido eliminado del grupo")
    
    logger.info("member_removed", group_id=group_id, member=member_id, by=user.user_id)
    
    return {"message": "Member removed"}


@router.post("/{group_id}/mark-read")
async def mark_as_read(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Mark a group as read (update last_read_at)
    """
    db = http_clients.timescale
    
    await db.execute("""
        UPDATE chat_members 
        SET last_read_at = NOW()
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    return {"message": "Marked as read"}


@router.post("/{group_id}/members/{member_id}/promote")
async def promote_member(
    group_id: str,
    member_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Promote a member to admin. Owner and admins can promote.
    """
    db = http_clients.timescale
    
    # Check if current user is owner or admin
    user_role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    if user_role not in ('owner', 'admin'):
        raise HTTPException(status_code=403, detail="Only owner and admins can promote members")
    
    # Check target is a member
    target_role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    if not target_role:
        raise HTTPException(status_code=404, detail="Member not found")
    if target_role == 'owner':
        raise HTTPException(status_code=400, detail="Cannot change owner role")
    if target_role == 'admin':
        raise HTTPException(status_code=400, detail="Already an admin")
    
    # Promote to admin
    await db.execute("""
        UPDATE chat_members 
        SET role = 'admin'
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    logger.info("member_promoted", group_id=group_id, member=member_id, by=user.user_id)
    
    return {"message": "Member promoted to admin"}


@router.post("/{group_id}/members/{member_id}/demote")
async def demote_member(
    group_id: str,
    member_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Demote an admin to member. Only owner can demote.
    """
    db = http_clients.timescale
    
    # Check if current user is owner
    is_owner = await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM chat_groups 
            WHERE id = $1::uuid AND owner_id = $2
        )
    """, group_id, user.user_id)
    
    if not is_owner:
        raise HTTPException(status_code=403, detail="Only owner can demote members")
    
    # Check target is admin
    target_role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    if not target_role:
        raise HTTPException(status_code=404, detail="Member not found")
    if target_role != 'admin':
        raise HTTPException(status_code=400, detail="Member is not an admin")
    
    # Demote to member
    await db.execute("""
        UPDATE chat_members 
        SET role = 'member'
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    logger.info("member_demoted", group_id=group_id, member=member_id, by=user.user_id)
    
    return {"message": "Admin demoted to member"}


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Delete a group. Must be owner.
    """
    db = http_clients.timescale
    
    # Check owner
    is_owner = await db.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM chat_groups 
            WHERE id = $1::uuid AND owner_id = $2
        )
    """, group_id, user.user_id)
    
    if not is_owner:
        raise HTTPException(status_code=403, detail="Only owner can delete group")
    
    # Delete (cascade will handle members, messages, invites)
    await db.execute("DELETE FROM chat_groups WHERE id = $1::uuid", group_id)
    
    logger.info("group_deleted", group_id=group_id, by=user.user_id)
    
    return {"message": "Group deleted"}

