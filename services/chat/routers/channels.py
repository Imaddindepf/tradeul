"""
Channel endpoints - Public chat channels
"""

from typing import List
from fastapi import APIRouter, HTTPException
import structlog

from models.channel import ChannelResponse
from http_clients import http_clients

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=List[ChannelResponse])
async def list_channels():
    """
    List all public channels.
    No auth required for listing.
    """
    db = http_clients.timescale
    
    channels = await db.fetch("""
        SELECT 
            c.id::text,
            c.name,
            c.description,
            c.icon,
            c.is_default,
            c.sort_order,
            c.created_at,
            COALESCE(
                (SELECT COUNT(*) FROM chat_messages m 
                 WHERE m.channel_id = c.id AND m.deleted_at IS NULL),
                0
            ) as message_count
        FROM chat_channels c
        ORDER BY c.sort_order ASC
    """)
    
    return channels


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str):
    """
    Get a single channel by ID or name
    """
    db = http_clients.timescale
    
    channel = await db.fetchrow("""
        SELECT 
            c.id::text,
            c.name,
            c.description,
            c.icon,
            c.is_default,
            c.sort_order,
            c.created_at,
            COALESCE(
                (SELECT COUNT(*) FROM chat_messages m 
                 WHERE m.channel_id = c.id AND m.deleted_at IS NULL),
                0
            ) as message_count
        FROM chat_channels c
        WHERE c.id::text = $1 OR c.name = $1
    """, channel_id)
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    return channel

