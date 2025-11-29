"""
Watchlist API Router
CRUD operations for Quote Monitor watchlists
"""

import json
import asyncpg
import structlog
from datetime import datetime
from typing import List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query, Depends

from shared.models.watchlist import (
    Watchlist, WatchlistCreate, WatchlistUpdate, WatchlistReorder,
    WatchlistTicker, WatchlistTickerCreate, WatchlistTickerUpdate,
    WatchlistColumn, QuoteMonitorState,
    WatchlistSection, WatchlistSectionCreate, WatchlistSectionUpdate,
    WatchlistSectionReorder, TickerMoveToSection
)
from shared.config.settings import settings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


def parse_columns(columns_data) -> List[WatchlistColumn]:
    """Parse columns from database (can be JSON string or list)"""
    if columns_data is None:
        return []
    if isinstance(columns_data, str):
        columns_data = json.loads(columns_data)
    return [WatchlistColumn(c) for c in columns_data]


def parse_tags(tags_data) -> List[str]:
    """Parse tags from database (can be JSON string or list)"""
    if tags_data is None:
        return []
    if isinstance(tags_data, str):
        tags_data = json.loads(tags_data)
    return tags_data

# Database connection pool
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


async def close_db_pool():
    """Close database connection pool"""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


# ============================================================================
# Watchlist CRUD
# ============================================================================

def parse_ticker(tr) -> WatchlistTicker:
    """Parse ticker row to WatchlistTicker model"""
    return WatchlistTicker(
        symbol=tr['symbol'],
        exchange=tr['exchange'],
        section_id=str(tr['section_id']) if tr.get('section_id') else None,
        added_at=tr['added_at'],
        notes=tr['notes'],
        alert_price_above=float(tr['alert_price_above']) if tr['alert_price_above'] else None,
        alert_price_below=float(tr['alert_price_below']) if tr['alert_price_below'] else None,
        alert_change_percent=float(tr['alert_change_percent']) if tr['alert_change_percent'] else None,
        position_size=float(tr['position_size']) if tr['position_size'] else None,
        weight=float(tr['weight']) if tr['weight'] else None,
        tags=parse_tags(tr['tags']),
        position=tr.get('position', 0) or 0
    )


@router.get("", response_model=List[Watchlist])
async def get_watchlists(user_id: str = Query(..., description="User ID from Clerk")):
    """Get all watchlists for a user with sections and tickers"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Get watchlists
            rows = await conn.fetch("""
                SELECT id, user_id, name, description, color, icon, 
                       is_synthetic_etf, columns, sort_by, sort_order, 
                       position, created_at, updated_at
                FROM watchlists 
                WHERE user_id = $1 
                ORDER BY position ASC
            """, user_id)
            
            watchlists = []
            for row in rows:
                watchlist_id = row['id']
                
                # Get sections for this watchlist
                section_rows = await conn.fetch("""
                    SELECT id, watchlist_id, name, color, icon, is_collapsed, 
                           position, created_at, updated_at
                    FROM watchlist_sections
                    WHERE watchlist_id = $1
                    ORDER BY position ASC
                """, watchlist_id)
                
                # Get ALL tickers for this watchlist
                ticker_rows = await conn.fetch("""
                    SELECT id, watchlist_id, symbol, exchange, section_id, notes,
                           alert_price_above, alert_price_below, alert_change_percent,
                           position_size, weight, tags, position, added_at
                    FROM watchlist_tickers
                    WHERE watchlist_id = $1
                    ORDER BY position ASC, added_at ASC
                """, watchlist_id)
                
                # Group tickers by section
                tickers_by_section = {}
                unsorted_tickers = []
                
                for tr in ticker_rows:
                    ticker = parse_ticker(tr)
                    if tr['section_id']:
                        section_id = str(tr['section_id'])
                        if section_id not in tickers_by_section:
                            tickers_by_section[section_id] = []
                        tickers_by_section[section_id].append(ticker)
                    else:
                        unsorted_tickers.append(ticker)
                
                # Build sections with their tickers
                sections = [
                    WatchlistSection(
                        id=str(sr['id']),
                        watchlist_id=str(sr['watchlist_id']),
                        name=sr['name'],
                        color=sr['color'],
                        icon=sr['icon'],
                        is_collapsed=sr['is_collapsed'],
                        position=sr['position'],
                        created_at=sr['created_at'],
                        updated_at=sr['updated_at'],
                        tickers=tickers_by_section.get(str(sr['id']), [])
                    )
                    for sr in section_rows
                ]
                
                watchlists.append(Watchlist(
                    id=str(row['id']),
                    user_id=row['user_id'],
                    name=row['name'],
                    description=row['description'],
                    color=row['color'],
                    icon=row['icon'],
                    is_synthetic_etf=row['is_synthetic_etf'],
                    columns=parse_columns(row['columns']),
                    sections=sections,
                    tickers=unsorted_tickers,  # Tickers without section
                    sort_by=row['sort_by'],
                    sort_order=row['sort_order'],
                    position=row['position'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                ))
            
            return watchlists
            
    except Exception as e:
        logger.error("get_watchlists_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Watchlist)
async def create_watchlist(
    data: WatchlistCreate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Create a new watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Get next position
            max_pos = await conn.fetchval(
                "SELECT COALESCE(MAX(position), -1) FROM watchlists WHERE user_id = $1",
                user_id
            )
            
            # Default columns if not provided
            columns = data.columns or [
                WatchlistColumn.TICKER,
                WatchlistColumn.LAST,
                WatchlistColumn.BID,
                WatchlistColumn.ASK,
                WatchlistColumn.CHANGE_PERCENT,
                WatchlistColumn.VOLUME,
                WatchlistColumn.LATENCY,
            ]
            
            columns_json = json.dumps([c.value for c in columns])
            
            row = await conn.fetchrow("""
                INSERT INTO watchlists (user_id, name, description, color, icon, 
                                        is_synthetic_etf, columns, position)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                RETURNING id, user_id, name, description, color, icon,
                          is_synthetic_etf, columns, sort_by, sort_order,
                          position, created_at, updated_at
            """, user_id, data.name, data.description, data.color, data.icon,
                data.is_synthetic_etf, columns_json, max_pos + 1)
            
            logger.info("watchlist_created", user_id=user_id, name=data.name)
            
            return Watchlist(
                id=str(row['id']),
                user_id=row['user_id'],
                name=row['name'],
                description=row['description'],
                color=row['color'],
                icon=row['icon'],
                is_synthetic_etf=row['is_synthetic_etf'],
                columns=parse_columns(row['columns']),
                sort_by=row['sort_by'],
                sort_order=row['sort_order'],
                position=row['position'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                tickers=[]
            )
            
    except Exception as e:
        logger.error("create_watchlist_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{watchlist_id}", response_model=Watchlist)
async def update_watchlist(
    watchlist_id: str,
    data: WatchlistUpdate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Update a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Build update query dynamically
            updates = []
            params = [watchlist_id, user_id]
            param_idx = 3
            
            if data.name is not None:
                updates.append(f"name = ${param_idx}")
                params.append(data.name)
                param_idx += 1
            
            if data.description is not None:
                updates.append(f"description = ${param_idx}")
                params.append(data.description)
                param_idx += 1
            
            if data.color is not None:
                updates.append(f"color = ${param_idx}")
                params.append(data.color)
                param_idx += 1
            
            if data.icon is not None:
                updates.append(f"icon = ${param_idx}")
                params.append(data.icon)
                param_idx += 1
            
            if data.is_synthetic_etf is not None:
                updates.append(f"is_synthetic_etf = ${param_idx}")
                params.append(data.is_synthetic_etf)
                param_idx += 1
            
            if data.columns is not None:
                updates.append(f"columns = ${param_idx}::jsonb")
                params.append(json.dumps([c.value for c in data.columns]))
                param_idx += 1
            
            if data.sort_by is not None:
                updates.append(f"sort_by = ${param_idx}")
                params.append(data.sort_by)
                param_idx += 1
            
            if data.sort_order is not None:
                updates.append(f"sort_order = ${param_idx}")
                params.append(data.sort_order)
                param_idx += 1
            
            if data.position is not None:
                updates.append(f"position = ${param_idx}")
                params.append(data.position)
                param_idx += 1
            
            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            query = f"""
                UPDATE watchlists 
                SET {', '.join(updates)}
                WHERE id = $1::uuid AND user_id = $2
                RETURNING id, user_id, name, description, color, icon,
                          is_synthetic_etf, columns, sort_by, sort_order,
                          position, created_at, updated_at
            """
            
            row = await conn.fetchrow(query, *params)
            
            if not row:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            # Get tickers
            ticker_rows = await conn.fetch("""
                SELECT symbol, exchange, notes, alert_price_above, alert_price_below,
                       alert_change_percent, position_size, weight, tags, added_at
                FROM watchlist_tickers
                WHERE watchlist_id = $1
                ORDER BY added_at ASC
            """, row['id'])
            
            tickers = [
                WatchlistTicker(
                    symbol=tr['symbol'],
                    exchange=tr['exchange'],
                    added_at=tr['added_at'],
                    notes=tr['notes'],
                    alert_price_above=float(tr['alert_price_above']) if tr['alert_price_above'] else None,
                    alert_price_below=float(tr['alert_price_below']) if tr['alert_price_below'] else None,
                    alert_change_percent=float(tr['alert_change_percent']) if tr['alert_change_percent'] else None,
                    position_size=float(tr['position_size']) if tr['position_size'] else None,
                    weight=float(tr['weight']) if tr['weight'] else None,
                    tags=parse_tags(tr['tags'])
                )
                for tr in ticker_rows
            ]
            
            return Watchlist(
                id=str(row['id']),
                user_id=row['user_id'],
                name=row['name'],
                description=row['description'],
                color=row['color'],
                icon=row['icon'],
                is_synthetic_etf=row['is_synthetic_etf'],
                columns=parse_columns(row['columns']),
                sort_by=row['sort_by'],
                sort_order=row['sort_order'],
                position=row['position'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                tickers=tickers
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_watchlist_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{watchlist_id}")
async def delete_watchlist(
    watchlist_id: str,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Delete a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM watchlists 
                WHERE id = $1::uuid AND user_id = $2
            """, watchlist_id, user_id)
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            logger.info("watchlist_deleted", watchlist_id=watchlist_id, user_id=user_id)
            return {"success": True}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_watchlist_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder")
async def reorder_watchlists(
    data: WatchlistReorder,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Reorder watchlist tabs"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                for idx, wl_id in enumerate(data.watchlist_ids):
                    await conn.execute("""
                        UPDATE watchlists 
                        SET position = $1
                        WHERE id = $2::uuid AND user_id = $3
                    """, idx, wl_id, user_id)
            
            logger.info("watchlists_reordered", user_id=user_id)
            return {"success": True}
            
    except Exception as e:
        logger.error("reorder_watchlists_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Watchlist Ticker CRUD
# ============================================================================

@router.post("/{watchlist_id}/tickers", response_model=WatchlistTicker)
async def add_ticker(
    watchlist_id: str,
    data: WatchlistTickerCreate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Add a ticker to a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid",
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=403, detail="Not authorized")
            
            tags_json = json.dumps(data.tags) if data.tags else '[]'
            
            # Insert ticker
            row = await conn.fetchrow("""
                INSERT INTO watchlist_tickers (watchlist_id, symbol, exchange, notes, weight, tags)
                VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (watchlist_id, symbol) DO UPDATE SET
                    notes = EXCLUDED.notes,
                    weight = EXCLUDED.weight,
                    tags = EXCLUDED.tags
                RETURNING symbol, exchange, notes, weight, tags, added_at
            """, watchlist_id, data.symbol.upper(), data.exchange, 
                data.notes, data.weight, tags_json)
            
            logger.info("ticker_added", watchlist_id=watchlist_id, symbol=data.symbol)
            
            return WatchlistTicker(
                symbol=row['symbol'],
                exchange=row['exchange'],
                added_at=row['added_at'],
                notes=row['notes'],
                weight=float(row['weight']) if row['weight'] else None,
                tags=parse_tags(row['tags'])
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("add_ticker_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{watchlist_id}/tickers/batch")
async def add_tickers_batch(
    watchlist_id: str,
    symbols: List[str],
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Add multiple tickers to a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid",
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=403, detail="Not authorized")
            
            # Insert tickers
            added = 0
            for symbol in symbols:
                try:
                    await conn.execute("""
                        INSERT INTO watchlist_tickers (watchlist_id, symbol)
                        VALUES ($1::uuid, $2)
                        ON CONFLICT (watchlist_id, symbol) DO NOTHING
                    """, watchlist_id, symbol.upper())
                    added += 1
                except Exception:
                    pass
            
            logger.info("tickers_batch_added", watchlist_id=watchlist_id, count=added)
            return {"success": True, "added": added}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("add_tickers_batch_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{watchlist_id}/tickers/{symbol}", response_model=WatchlistTicker)
async def update_ticker(
    watchlist_id: str,
    symbol: str,
    data: WatchlistTickerUpdate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Update a ticker in a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid",
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=403, detail="Not authorized")
            
            # Build update query
            updates = []
            params = [watchlist_id, symbol.upper()]
            param_idx = 3
            
            if data.notes is not None:
                updates.append(f"notes = ${param_idx}")
                params.append(data.notes)
                param_idx += 1
            
            if data.alert_price_above is not None:
                updates.append(f"alert_price_above = ${param_idx}")
                params.append(data.alert_price_above)
                param_idx += 1
            
            if data.alert_price_below is not None:
                updates.append(f"alert_price_below = ${param_idx}")
                params.append(data.alert_price_below)
                param_idx += 1
            
            if data.alert_change_percent is not None:
                updates.append(f"alert_change_percent = ${param_idx}")
                params.append(data.alert_change_percent)
                param_idx += 1
            
            if data.position_size is not None:
                updates.append(f"position_size = ${param_idx}")
                params.append(data.position_size)
                param_idx += 1
            
            if data.weight is not None:
                updates.append(f"weight = ${param_idx}")
                params.append(data.weight)
                param_idx += 1
            
            if data.tags is not None:
                updates.append(f"tags = ${param_idx}::jsonb")
                params.append(json.dumps(data.tags))
                param_idx += 1
            
            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            query = f"""
                UPDATE watchlist_tickers 
                SET {', '.join(updates)}
                WHERE watchlist_id = $1::uuid AND symbol = $2
                RETURNING symbol, exchange, notes, alert_price_above, alert_price_below,
                          alert_change_percent, position_size, weight, tags, added_at
            """
            
            row = await conn.fetchrow(query, *params)
            
            if not row:
                raise HTTPException(status_code=404, detail="Ticker not found")
            
            return WatchlistTicker(
                symbol=row['symbol'],
                exchange=row['exchange'],
                added_at=row['added_at'],
                notes=row['notes'],
                alert_price_above=float(row['alert_price_above']) if row['alert_price_above'] else None,
                alert_price_below=float(row['alert_price_below']) if row['alert_price_below'] else None,
                alert_change_percent=float(row['alert_change_percent']) if row['alert_change_percent'] else None,
                position_size=float(row['position_size']) if row['position_size'] else None,
                weight=float(row['weight']) if row['weight'] else None,
                tags=parse_tags(row['tags'])
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_ticker_error", error=str(e), watchlist_id=watchlist_id, symbol=symbol)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{watchlist_id}/tickers/{symbol}")
async def remove_ticker(
    watchlist_id: str,
    symbol: str,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Remove a ticker from a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid",
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=403, detail="Not authorized")
            
            result = await conn.execute("""
                DELETE FROM watchlist_tickers 
                WHERE watchlist_id = $1::uuid AND symbol = $2
            """, watchlist_id, symbol.upper())
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Ticker not found")
            
            logger.info("ticker_removed", watchlist_id=watchlist_id, symbol=symbol)
            return {"success": True}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("remove_ticker_error", error=str(e), watchlist_id=watchlist_id, symbol=symbol)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Quote Monitor State
# ============================================================================

@router.get("/state", response_model=QuoteMonitorState)
async def get_quote_monitor_state(user_id: str = Query(..., description="User ID from Clerk")):
    """Get full Quote Monitor state for a user"""
    watchlists = await get_watchlists(user_id)
    
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            settings_row = await conn.fetchrow("""
                SELECT active_watchlist_id, settings 
                FROM quote_monitor_settings 
                WHERE user_id = $1
            """, user_id)
            
            active_id = str(settings_row['active_watchlist_id']) if settings_row and settings_row['active_watchlist_id'] else None
            user_settings = settings_row['settings'] if settings_row else {}
            
            return QuoteMonitorState(
                user_id=user_id,
                watchlists=watchlists,
                active_watchlist_id=active_id,
                settings=user_settings
            )
            
    except Exception as e:
        logger.error("get_state_error", error=str(e), user_id=user_id)
        # Return default state if settings don't exist
        return QuoteMonitorState(
            user_id=user_id,
            watchlists=watchlists,
            active_watchlist_id=watchlists[0].id if watchlists else None,
            settings={}
        )


@router.put("/state/active/{watchlist_id}")
async def set_active_watchlist(
    watchlist_id: str,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Set the active watchlist for a user"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO quote_monitor_settings (user_id, active_watchlist_id)
                VALUES ($1, $2::uuid)
                ON CONFLICT (user_id) DO UPDATE SET 
                    active_watchlist_id = EXCLUDED.active_watchlist_id
            """, user_id, watchlist_id)
            
            return {"success": True}
            
    except Exception as e:
        logger.error("set_active_error", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Section CRUD
# ============================================================================

@router.get("/{watchlist_id}/sections", response_model=List[WatchlistSection])
async def get_sections(
    watchlist_id: str,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Get all sections for a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid", 
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            section_rows = await conn.fetch("""
                SELECT id, watchlist_id, name, color, icon, is_collapsed, 
                       position, created_at, updated_at
                FROM watchlist_sections
                WHERE watchlist_id = $1::uuid
                ORDER BY position ASC
            """, watchlist_id)
            
            sections = []
            for sr in section_rows:
                # Get tickers for this section
                ticker_rows = await conn.fetch("""
                    SELECT id, watchlist_id, symbol, exchange, section_id, notes,
                           alert_price_above, alert_price_below, alert_change_percent,
                           position_size, weight, tags, position, added_at
                    FROM watchlist_tickers
                    WHERE section_id = $1::uuid
                    ORDER BY position ASC, added_at ASC
                """, sr['id'])
                
                sections.append(WatchlistSection(
                    id=str(sr['id']),
                    watchlist_id=str(sr['watchlist_id']),
                    name=sr['name'],
                    color=sr['color'],
                    icon=sr['icon'],
                    is_collapsed=sr['is_collapsed'],
                    position=sr['position'],
                    created_at=sr['created_at'],
                    updated_at=sr['updated_at'],
                    tickers=[parse_ticker(tr) for tr in ticker_rows]
                ))
            
            return sections
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_sections_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{watchlist_id}/sections", response_model=WatchlistSection)
async def create_section(
    watchlist_id: str,
    data: WatchlistSectionCreate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Create a new section in a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid", 
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            # Get next position
            max_pos = await conn.fetchval("""
                SELECT COALESCE(MAX(position), -1) 
                FROM watchlist_sections 
                WHERE watchlist_id = $1::uuid
            """, watchlist_id)
            
            row = await conn.fetchrow("""
                INSERT INTO watchlist_sections (watchlist_id, name, color, icon, position)
                VALUES ($1::uuid, $2, $3, $4, $5)
                RETURNING id, watchlist_id, name, color, icon, is_collapsed, 
                          position, created_at, updated_at
            """, watchlist_id, data.name, data.color, data.icon, max_pos + 1)
            
            logger.info("section_created", watchlist_id=watchlist_id, name=data.name)
            
            return WatchlistSection(
                id=str(row['id']),
                watchlist_id=str(row['watchlist_id']),
                name=row['name'],
                color=row['color'],
                icon=row['icon'],
                is_collapsed=row['is_collapsed'],
                position=row['position'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                tickers=[]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_section_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{watchlist_id}/sections/{section_id}", response_model=WatchlistSection)
async def update_section(
    watchlist_id: str,
    section_id: str,
    data: WatchlistSectionUpdate,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Update a section"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid", 
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            # Build dynamic update query
            updates = []
            values = []
            idx = 1
            
            if data.name is not None:
                updates.append(f"name = ${idx}")
                values.append(data.name)
                idx += 1
            if data.color is not None:
                updates.append(f"color = ${idx}")
                values.append(data.color)
                idx += 1
            if data.icon is not None:
                updates.append(f"icon = ${idx}")
                values.append(data.icon)
                idx += 1
            if data.is_collapsed is not None:
                updates.append(f"is_collapsed = ${idx}")
                values.append(data.is_collapsed)
                idx += 1
            if data.position is not None:
                updates.append(f"position = ${idx}")
                values.append(data.position)
                idx += 1
            
            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            values.extend([section_id, watchlist_id])
            
            row = await conn.fetchrow(f"""
                UPDATE watchlist_sections
                SET {', '.join(updates)}, updated_at = NOW()
                WHERE id = ${idx}::uuid AND watchlist_id = ${idx + 1}::uuid
                RETURNING id, watchlist_id, name, color, icon, is_collapsed, 
                          position, created_at, updated_at
            """, *values)
            
            if not row:
                raise HTTPException(status_code=404, detail="Section not found")
            
            # Get tickers for this section
            ticker_rows = await conn.fetch("""
                SELECT id, watchlist_id, symbol, exchange, section_id, notes,
                       alert_price_above, alert_price_below, alert_change_percent,
                       position_size, weight, tags, position, added_at
                FROM watchlist_tickers
                WHERE section_id = $1::uuid
                ORDER BY position ASC, added_at ASC
            """, row['id'])
            
            logger.info("section_updated", section_id=section_id)
            
            return WatchlistSection(
                id=str(row['id']),
                watchlist_id=str(row['watchlist_id']),
                name=row['name'],
                color=row['color'],
                icon=row['icon'],
                is_collapsed=row['is_collapsed'],
                position=row['position'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                tickers=[parse_ticker(tr) for tr in ticker_rows]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_section_error", error=str(e), section_id=section_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{watchlist_id}/sections/{section_id}")
async def delete_section(
    watchlist_id: str,
    section_id: str,
    user_id: str = Query(..., description="User ID from Clerk"),
    move_tickers_to: Optional[str] = Query(None, description="Move tickers to another section (or null for unsorted)")
):
    """Delete a section. Tickers can be moved to another section or become unsorted."""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid", 
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            async with conn.transaction():
                # Move tickers to target section (or set to NULL for unsorted)
                if move_tickers_to:
                    await conn.execute("""
                        UPDATE watchlist_tickers
                        SET section_id = $1::uuid
                        WHERE section_id = $2::uuid
                    """, move_tickers_to, section_id)
                else:
                    await conn.execute("""
                        UPDATE watchlist_tickers
                        SET section_id = NULL
                        WHERE section_id = $1::uuid
                    """, section_id)
                
                # Delete the section
                result = await conn.execute("""
                    DELETE FROM watchlist_sections 
                    WHERE id = $1::uuid AND watchlist_id = $2::uuid
                """, section_id, watchlist_id)
                
                if result == "DELETE 0":
                    raise HTTPException(status_code=404, detail="Section not found")
            
            logger.info("section_deleted", section_id=section_id)
            return {"success": True}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_section_error", error=str(e), section_id=section_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{watchlist_id}/sections/reorder")
async def reorder_sections(
    watchlist_id: str,
    data: WatchlistSectionReorder,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Reorder sections within a watchlist"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid", 
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            async with conn.transaction():
                for idx, section_id in enumerate(data.section_ids):
                    await conn.execute("""
                        UPDATE watchlist_sections
                        SET position = $1
                        WHERE id = $2::uuid AND watchlist_id = $3::uuid
                    """, idx, section_id, watchlist_id)
            
            logger.info("sections_reordered", watchlist_id=watchlist_id)
            return {"success": True}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("reorder_sections_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{watchlist_id}/sections/{section_id}/tickers")
async def move_tickers_to_section(
    watchlist_id: str,
    section_id: str,
    data: TickerMoveToSection,
    user_id: str = Query(..., description="User ID from Clerk")
):
    """Move tickers to a section (use 'unsorted' as section_id to remove from section)"""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Verify ownership
            owner = await conn.fetchval(
                "SELECT user_id FROM watchlists WHERE id = $1::uuid", 
                watchlist_id
            )
            if owner != user_id:
                raise HTTPException(status_code=404, detail="Watchlist not found")
            
            target_section = None if section_id == 'unsorted' else section_id
            
            # Get next position in target section
            if target_section:
                max_pos = await conn.fetchval("""
                    SELECT COALESCE(MAX(position), -1) 
                    FROM watchlist_tickers 
                    WHERE section_id = $1::uuid
                """, target_section)
            else:
                max_pos = await conn.fetchval("""
                    SELECT COALESCE(MAX(position), -1) 
                    FROM watchlist_tickers 
                    WHERE watchlist_id = $1::uuid AND section_id IS NULL
                """, watchlist_id)
            
            async with conn.transaction():
                for idx, symbol in enumerate(data.symbols):
                    if target_section:
                        await conn.execute("""
                            UPDATE watchlist_tickers
                            SET section_id = $1::uuid, position = $2
                            WHERE watchlist_id = $3::uuid AND symbol = $4
                        """, target_section, max_pos + 1 + idx, watchlist_id, symbol.upper())
                    else:
                        await conn.execute("""
                            UPDATE watchlist_tickers
                            SET section_id = NULL, position = $1
                            WHERE watchlist_id = $2::uuid AND symbol = $3
                        """, max_pos + 1 + idx, watchlist_id, symbol.upper())
            
            logger.info("tickers_moved_to_section", 
                       watchlist_id=watchlist_id, 
                       section_id=section_id, 
                       count=len(data.symbols))
            return {"success": True, "moved": len(data.symbols)}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("move_tickers_error", error=str(e), watchlist_id=watchlist_id)
        raise HTTPException(status_code=500, detail=str(e))

