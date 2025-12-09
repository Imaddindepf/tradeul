"""
Group endpoints - Private groups with invitations
"""

import json
from typing import List
from fastapi import APIRouter, HTTPException, Depends
import structlog

from models.group import GroupCreate, GroupResponse, MemberResponse
from auth.dependencies import get_current_user, get_current_user_optional
from auth.models import AuthenticatedUser
from http_clients import http_clients

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/groups", tags=["groups"])


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
    
    # Create invites for initial members
    for member_id in data.member_ids:
        if member_id != user.user_id:
            await db.execute("""
                INSERT INTO chat_invites (group_id, inviter_id, invitee_id)
                VALUES ($1::uuid, $2, $3)
                ON CONFLICT (group_id, invitee_id) DO NOTHING
            """, group_id, user.user_id, member_id)
    
    logger.info("group_created", group_id=group_id, owner=user.user_id)
    
    return {**dict(group), "member_count": 1, "unread_count": 0}


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


@router.post("/{group_id}/invite/{invitee_id}")
async def invite_user(
    group_id: str,
    invitee_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Invite a user to a group. Must be owner or admin.
    """
    db = http_clients.timescale
    
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
    
    # Create invite
    await db.execute("""
        INSERT INTO chat_invites (group_id, inviter_id, invitee_id)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (group_id, invitee_id) 
        DO UPDATE SET 
            status = 'pending',
            inviter_id = $2,
            created_at = NOW(),
            expires_at = NOW() + INTERVAL '7 days'
    """, group_id, user.user_id, invitee_id)
    
    logger.info("user_invited", group_id=group_id, inviter=user.user_id, invitee=invitee_id)
    
    return {"message": "Invitation sent"}


@router.delete("/{group_id}/members/{member_id}")
async def remove_member(
    group_id: str,
    member_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Remove a member from a group. Must be owner/admin or self.
    """
    db = http_clients.timescale
    
    # Check permission
    role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, user.user_id)
    
    # Can remove self or if owner/admin
    can_remove = (member_id == user.user_id) or (role in ('owner', 'admin'))
    
    if not can_remove:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Owner cannot be removed (must delete group)
    target_role = await db.fetchval("""
        SELECT role FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
    if target_role == 'owner':
        raise HTTPException(status_code=400, detail="Cannot remove owner")
    
    # Remove
    await db.execute("""
        DELETE FROM chat_members 
        WHERE group_id = $1::uuid AND user_id = $2
    """, group_id, member_id)
    
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

