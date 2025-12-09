"""
Message endpoints - Send and receive messages
"""

import json
import re
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
import structlog

from models.message import MessageCreate, MessageResponse, MessageUpdate
from auth.dependencies import get_current_user, get_current_user_optional
from auth.models import AuthenticatedUser
from http_clients import http_clients

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/messages", tags=["messages"])

# Regex for ticker mentions like $AAPL
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')


def extract_tickers(content: str) -> List[str]:
    """Extract tickers from message content"""
    matches = TICKER_PATTERN.findall(content)
    return list(set(matches))  # Unique tickers


@router.post("", response_model=MessageResponse)
async def send_message(
    data: MessageCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Send a message to a channel or group.
    Automatically extracts tickers and fetches prices.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Validate target
    if not data.channel_id and not data.group_id:
        raise HTTPException(status_code=400, detail="Must specify channel_id or group_id")
    if data.channel_id and data.group_id:
        raise HTTPException(status_code=400, detail="Cannot specify both channel_id and group_id")
    
    # If group, check membership
    if data.group_id:
        is_member = await db.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM chat_members 
                WHERE group_id = $1::uuid AND user_id = $2
            )
        """, data.group_id, user.user_id)
        
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this group")
    
    # Extract tickers from content
    tickers = extract_tickers(data.content)
    
    # Fetch ticker prices if any
    ticker_prices = {}
    if tickers and http_clients.polygon:
        for ticker in tickers[:5]:  # Limit to 5 tickers per message
            price_data = await http_clients.get_ticker_price(ticker)
            if price_data:
                ticker_prices[ticker] = price_data
    
    # Insert message
    message = await db.fetchrow("""
        INSERT INTO chat_messages (
            channel_id, group_id, user_id, user_name, user_avatar,
            content, content_type, reply_to_id, mentions, tickers, ticker_prices
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::uuid, $9, $10, $11)
        RETURNING 
            id::text, channel_id::text, group_id::text,
            user_id, user_name, user_avatar,
            content, content_type, reply_to_id::text,
            mentions, tickers, ticker_prices, reactions,
            created_at, edited_at
    """,
        data.channel_id if data.channel_id else None,
        data.group_id if data.group_id else None,
        user.user_id,
        user.name or user.username or "Anonymous",
        user.avatar,
        data.content,
        data.content_type,
        data.reply_to_id if data.reply_to_id else None,
        data.mentions or [],
        tickers,
        json.dumps(ticker_prices) if ticker_prices else None
    )
    
    if not message:
        raise HTTPException(status_code=500, detail="Failed to send message")
    
    # Publish to Redis for real-time delivery
    stream_key = f"stream:chat:{'channel:' + data.channel_id if data.channel_id else 'group:' + data.group_id}"
    
    await redis.xadd(stream_key, {
        "type": "new_message",
        "payload": json.dumps({
            **dict(message),
            "created_at": message["created_at"].isoformat(),
            "edited_at": message["edited_at"].isoformat() if message["edited_at"] else None,
        })
    })
    
    logger.info("message_sent", 
        message_id=message["id"],
        channel_id=data.channel_id,
        group_id=data.group_id,
        user_id=user.user_id,
        tickers=tickers
    )
    
    return message


@router.get("/channel/{channel_id}", response_model=List[MessageResponse])
async def get_channel_messages(
    channel_id: str,
    before: Optional[str] = Query(None, description="Get messages before this ID"),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Get messages from a public channel.
    No auth required for public channels.
    """
    db = http_clients.timescale
    
    # Verify channel exists
    exists = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM chat_channels WHERE id = $1::uuid)",
        channel_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    # Build query
    if before:
        messages = await db.fetch("""
            SELECT 
                id::text, channel_id::text, group_id::text,
                user_id, user_name, user_avatar,
                content, content_type, reply_to_id::text,
                mentions, tickers, ticker_prices, reactions,
                created_at, edited_at
            FROM chat_messages
            WHERE channel_id = $1::uuid 
                AND deleted_at IS NULL
                AND created_at < (SELECT created_at FROM chat_messages WHERE id = $2::uuid)
            ORDER BY created_at DESC
            LIMIT $3
        """, channel_id, before, limit)
    else:
        messages = await db.fetch("""
            SELECT 
                id::text, channel_id::text, group_id::text,
                user_id, user_name, user_avatar,
                content, content_type, reply_to_id::text,
                mentions, tickers, ticker_prices, reactions,
                created_at, edited_at
            FROM chat_messages
            WHERE channel_id = $1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT $2
        """, channel_id, limit)
    
    # Return in chronological order
    return list(reversed(messages))


@router.get("/group/{group_id}", response_model=List[MessageResponse])
async def get_group_messages(
    group_id: str,
    before: Optional[str] = Query(None, description="Get messages before this ID"),
    limit: int = Query(50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get messages from a private group.
    Must be a member.
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
    
    # Build query
    if before:
        messages = await db.fetch("""
            SELECT 
                id::text, channel_id::text, group_id::text,
                user_id, user_name, user_avatar,
                content, content_type, reply_to_id::text,
                mentions, tickers, ticker_prices, reactions,
                created_at, edited_at
            FROM chat_messages
            WHERE group_id = $1::uuid 
                AND deleted_at IS NULL
                AND created_at < (SELECT created_at FROM chat_messages WHERE id = $2::uuid)
            ORDER BY created_at DESC
            LIMIT $3
        """, group_id, before, limit)
    else:
        messages = await db.fetch("""
            SELECT 
                id::text, channel_id::text, group_id::text,
                user_id, user_name, user_avatar,
                content, content_type, reply_to_id::text,
                mentions, tickers, ticker_prices, reactions,
                created_at, edited_at
            FROM chat_messages
            WHERE group_id = $1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT $2
        """, group_id, limit)
    
    return list(reversed(messages))


@router.patch("/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: str,
    data: MessageUpdate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Edit a message. Can only edit own messages.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Verify ownership
    original = await db.fetchrow("""
        SELECT user_id, channel_id::text, group_id::text
        FROM chat_messages
        WHERE id = $1::uuid AND deleted_at IS NULL
    """, message_id)
    
    if not original:
        raise HTTPException(status_code=404, detail="Message not found")
    if original["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Can only edit own messages")
    
    # Extract tickers from new content
    tickers = extract_tickers(data.content)
    
    # Update
    message = await db.fetchrow("""
        UPDATE chat_messages
        SET content = $2, tickers = $3, edited_at = NOW()
        WHERE id = $1::uuid
        RETURNING 
            id::text, channel_id::text, group_id::text,
            user_id, user_name, user_avatar,
            content, content_type, reply_to_id::text,
            mentions, tickers, ticker_prices, reactions,
            created_at, edited_at
    """, message_id, data.content, tickers)
    
    # Notify via Redis
    target = f"channel:{original['channel_id']}" if original['channel_id'] else f"group:{original['group_id']}"
    await redis.xadd(f"stream:chat:{target}", {
        "type": "message_edited",
        "payload": json.dumps({
            "id": message_id,
            "content": data.content,
            "edited_at": message["edited_at"].isoformat()
        })
    })
    
    return message


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Soft-delete a message. Can only delete own messages.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Verify ownership
    original = await db.fetchrow("""
        SELECT user_id, channel_id::text, group_id::text
        FROM chat_messages
        WHERE id = $1::uuid AND deleted_at IS NULL
    """, message_id)
    
    if not original:
        raise HTTPException(status_code=404, detail="Message not found")
    if original["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Can only delete own messages")
    
    # Soft delete
    await db.execute("""
        UPDATE chat_messages SET deleted_at = NOW() WHERE id = $1::uuid
    """, message_id)
    
    # Notify
    target = f"channel:{original['channel_id']}" if original['channel_id'] else f"group:{original['group_id']}"
    await redis.xadd(f"stream:chat:{target}", {
        "type": "message_deleted",
        "payload": json.dumps({"id": message_id})
    })
    
    logger.info("message_deleted", message_id=message_id, user_id=user.user_id)
    
    return {"message": "Message deleted"}


@router.post("/{message_id}/react/{emoji}")
async def add_reaction(
    message_id: str,
    emoji: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Add a reaction to a message.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    # Verify message exists
    original = await db.fetchrow("""
        SELECT reactions, channel_id::text, group_id::text
        FROM chat_messages
        WHERE id = $1::uuid AND deleted_at IS NULL
    """, message_id)
    
    if not original:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Update reactions
    reactions = original["reactions"] or {}
    if emoji not in reactions:
        reactions[emoji] = []
    if user.user_id not in reactions[emoji]:
        reactions[emoji].append(user.user_id)
    
    await db.execute("""
        UPDATE chat_messages SET reactions = $2 WHERE id = $1::uuid
    """, message_id, json.dumps(reactions))
    
    # Notify
    target = f"channel:{original['channel_id']}" if original['channel_id'] else f"group:{original['group_id']}"
    await redis.xadd(f"stream:chat:{target}", {
        "type": "reaction_added",
        "payload": json.dumps({
            "message_id": message_id,
            "emoji": emoji,
            "user_id": user.user_id
        })
    })
    
    return {"message": "Reaction added"}


@router.delete("/{message_id}/react/{emoji}")
async def remove_reaction(
    message_id: str,
    emoji: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Remove a reaction from a message.
    """
    db = http_clients.timescale
    redis = http_clients.redis
    
    original = await db.fetchrow("""
        SELECT reactions, channel_id::text, group_id::text
        FROM chat_messages
        WHERE id = $1::uuid AND deleted_at IS NULL
    """, message_id)
    
    if not original:
        raise HTTPException(status_code=404, detail="Message not found")
    
    reactions = original["reactions"] or {}
    if emoji in reactions and user.user_id in reactions[emoji]:
        reactions[emoji].remove(user.user_id)
        if not reactions[emoji]:
            del reactions[emoji]
    
    await db.execute("""
        UPDATE chat_messages SET reactions = $2 WHERE id = $1::uuid
    """, message_id, json.dumps(reactions))
    
    # Notify
    target = f"channel:{original['channel_id']}" if original['channel_id'] else f"group:{original['group_id']}"
    await redis.xadd(f"stream:chat:{target}", {
        "type": "reaction_removed",
        "payload": json.dumps({
            "message_id": message_id,
            "emoji": emoji,
            "user_id": user.user_id
        })
    })
    
    return {"message": "Reaction removed"}

