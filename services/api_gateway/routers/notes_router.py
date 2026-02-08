"""
User Notes API Router
CRUD operations for user notes with TipTap/ProseMirror JSON content
"""

import json
import asyncpg
import structlog
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from shared.config.settings import settings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


# ============================================================================
# Pydantic Models
# ============================================================================

class NoteContent(BaseModel):
    """TipTap/ProseMirror document structure"""
    type: str = "doc"
    content: List[dict] = Field(default_factory=list)


class Note(BaseModel):
    """Note response model"""
    id: str
    user_id: str
    title: str
    content: dict  # ProseMirror JSON
    content_text: Optional[str] = None
    position: int = 0
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    """Create note request"""
    title: str = "Untitled"
    content: Optional[dict] = Field(default_factory=lambda: {"type": "doc", "content": []})
    position: Optional[int] = None


class NoteUpdate(BaseModel):
    """Update note request"""
    title: Optional[str] = None
    content: Optional[dict] = None
    position: Optional[int] = None
    is_pinned: Optional[bool] = None


class NotesReorder(BaseModel):
    """Reorder notes request"""
    note_ids: List[str]


# ============================================================================
# Database Pool
# ============================================================================

_db_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=2,
            max_size=10
        )
    return _db_pool


def extract_text_from_content(content: dict) -> str:
    """Extract plain text from ProseMirror JSON for search"""
    texts = []
    
    def walk(node):
        if isinstance(node, dict):
            if node.get('type') == 'text':
                texts.append(node.get('text', ''))
            for child in node.get('content', []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    
    walk(content)
    return ' '.join(texts)


def row_to_note(row) -> Note:
    """Convert database row to Note model"""
    content = row['content']
    if isinstance(content, str):
        content = json.loads(content)
    
    return Note(
        id=str(row['id']),
        user_id=row['user_id'],
        title=row['title'],
        content=content,
        content_text=row['content_text'],
        position=row['position'] or 0,
        is_pinned=row['is_pinned'] or False,
        created_at=row['created_at'],
        updated_at=row['updated_at']
    )


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.get("", response_model=List[Note])
async def get_notes(user_id: str = Query(..., description="User ID from Clerk")):
    """Get all notes for a user"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, user_id, title, content, content_text, 
                       position, is_pinned, created_at, updated_at
                FROM user_notes
                WHERE user_id = $1
                ORDER BY is_pinned DESC, position ASC, created_at DESC
            """, user_id)
            
            return [row_to_note(row) for row in rows]
            
    except Exception as e:
        logger.error("get_notes_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Note)
async def create_note(
    data: NoteCreate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Create a new note"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Get next position
            if data.position is None:
                max_pos = await conn.fetchval(
                    "SELECT COALESCE(MAX(position), -1) FROM user_notes WHERE user_id = $1",
                    user_id
                )
                position = max_pos + 1
            else:
                position = data.position
            
            # Extract text for search
            content_text = extract_text_from_content(data.content) if data.content else ""
            
            row = await conn.fetchrow("""
                INSERT INTO user_notes (user_id, title, content, content_text, position)
                VALUES ($1, $2, $3::jsonb, $4, $5)
                RETURNING id, user_id, title, content, content_text, 
                          position, is_pinned, created_at, updated_at
            """, user_id, data.title, json.dumps(data.content), content_text, position)
            
            logger.info("note_created", user_id=user_id, note_id=str(row['id']))
            return row_to_note(row)
            
    except Exception as e:
        logger.error("create_note_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{note_id}", response_model=Note)
async def get_note(
    note_id: str,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Get a specific note"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_id, title, content, content_text,
                       position, is_pinned, created_at, updated_at
                FROM user_notes
                WHERE id = $1::uuid AND user_id = $2
            """, note_id, user_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Note not found")
            
            return row_to_note(row)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_note_error", error=str(e), note_id=note_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{note_id}", response_model=Note)
async def update_note(
    note_id: str,
    data: NoteUpdate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Update a note"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Build dynamic update query
            updates = ["updated_at = NOW()"]
            params = [note_id, user_id]
            param_idx = 3
            
            if data.title is not None:
                updates.append(f"title = ${param_idx}")
                params.append(data.title)
                param_idx += 1
            
            if data.content is not None:
                updates.append(f"content = ${param_idx}::jsonb")
                params.append(json.dumps(data.content))
                param_idx += 1
                
                # Update search text
                content_text = extract_text_from_content(data.content)
                updates.append(f"content_text = ${param_idx}")
                params.append(content_text)
                param_idx += 1
            
            if data.position is not None:
                updates.append(f"position = ${param_idx}")
                params.append(data.position)
                param_idx += 1
            
            if data.is_pinned is not None:
                updates.append(f"is_pinned = ${param_idx}")
                params.append(data.is_pinned)
                param_idx += 1
            
            query = f"""
                UPDATE user_notes
                SET {', '.join(updates)}
                WHERE id = $1::uuid AND user_id = $2
                RETURNING id, user_id, title, content, content_text,
                          position, is_pinned, created_at, updated_at
            """
            
            row = await conn.fetchrow(query, *params)
            
            if not row:
                raise HTTPException(status_code=404, detail="Note not found")
            
            return row_to_note(row)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_note_error", error=str(e), note_id=note_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Delete a note"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM user_notes
                WHERE id = $1::uuid AND user_id = $2
            """, note_id, user_id)
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Note not found")
            
            logger.info("note_deleted", note_id=note_id, user_id=user_id)
            return {"success": True}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_note_error", error=str(e), note_id=note_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder")
async def reorder_notes(
    data: NotesReorder,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Reorder notes"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                for idx, note_id in enumerate(data.note_ids):
                    await conn.execute("""
                        UPDATE user_notes
                        SET position = $1
                        WHERE id = $2::uuid AND user_id = $3
                    """, idx, note_id, user_id)
            
            logger.info("notes_reordered", user_id=user_id)
            return {"success": True}
            
    except Exception as e:
        logger.error("reorder_notes_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))
