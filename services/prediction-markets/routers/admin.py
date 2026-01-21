"""
Admin API Router for Prediction Markets
Provides endpoints for managing categories, keywords, and tag rules
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# Request/Response Models
class KeywordRequest(BaseModel):
    category_id: str
    subcategory_id: str
    keyword: str


class TagRuleRequest(BaseModel):
    tag_slug: str
    rule_type: str  # "whitelist" or "blacklist"
    target_category_id: Optional[str] = None


class ConfigValueRequest(BaseModel):
    key: str
    value: str


class SuccessResponse(BaseModel):
    success: bool
    message: str


# Dependency injection for config_manager
_config_manager = None


def get_config_manager():
    if _config_manager is None:
        raise HTTPException(status_code=503, detail="Config manager not initialized")
    return _config_manager


def set_config_manager(manager):
    global _config_manager
    _config_manager = manager


@router.get("/keywords", response_model=List[dict])
async def list_keywords():
    """List all keywords from database"""
    return await get_config_manager().get_all_keywords()


@router.post("/keywords", response_model=SuccessResponse)
async def add_keyword(request: KeywordRequest):
    """Add a new keyword for classification"""
    manager = get_config_manager()
    success = await manager.add_keyword(
        request.category_id, request.subcategory_id, request.keyword
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add keyword")
    return SuccessResponse(success=True, message=f"Keyword '{request.keyword}' added")


@router.get("/tag-rules", response_model=List[dict])
async def list_tag_rules():
    """List all tag rules from database"""
    return await get_config_manager().get_all_tag_rules()


@router.post("/tag-rules", response_model=SuccessResponse)
async def add_tag_rule(request: TagRuleRequest):
    """Add or update a tag rule"""
    if request.rule_type not in ("whitelist", "blacklist"):
        raise HTTPException(status_code=400, detail="Invalid rule_type")
    
    success = await get_config_manager().add_tag_rule(
        request.tag_slug, request.rule_type, request.target_category_id
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add tag rule")
    return SuccessResponse(success=True, message=f"Tag rule for '{request.tag_slug}' added")


@router.delete("/tag-rules/{tag_slug}", response_model=SuccessResponse)
async def remove_tag_rule(tag_slug: str):
    """Remove a tag rule (deactivate)"""
    success = await get_config_manager().remove_tag_rule(tag_slug)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove tag rule")
    return SuccessResponse(success=True, message=f"Tag rule '{tag_slug}' removed")


@router.get("/config")
async def get_config():
    """Get current configuration status"""
    config = await get_config_manager().get_config()
    return {
        "is_from_db": config.is_from_db,
        "loaded_at": config.loaded_at.isoformat() if config.loaded_at else None,
        "categories_count": len(config.categories),
        "whitelist_count": len(config.whitelist_tags),
        "blacklist_count": len(config.blacklist_tags),
        "config_values": config.config_values,
    }


@router.post("/config", response_model=SuccessResponse)
async def update_config_value(request: ConfigValueRequest):
    """Update a configuration value"""
    success = await get_config_manager().update_config_value(request.key, request.value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update config")
    return SuccessResponse(success=True, message=f"Config '{request.key}' updated")


@router.post("/reload", response_model=SuccessResponse)
async def reload_config():
    """Force reload configuration from database"""
    config = await get_config_manager().get_config(force_reload=True)
    return SuccessResponse(
        success=True,
        message=f"Reloaded from {'database' if config.is_from_db else 'defaults'}"
    )


@router.get("/categories")
async def list_categories():
    """List all categories and subcategories"""
    config = await get_config_manager().get_config()
    result = []
    for cat_id, cat in sorted(config.categories.items(), key=lambda x: x[1].priority):
        cat_data = {
            "id": cat_id,
            "name": cat.name,
            "priority": cat.priority,
            "subcategories": [
                {"id": sub_id, "name": sub.name, "keywords_count": len(sub.keywords)}
                for sub_id, sub in sorted(cat.subcategories.items(), key=lambda x: x[1].priority)
            ]
        }
        result.append(cat_data)
    return result
