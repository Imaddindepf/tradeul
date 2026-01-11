"""
Workflow Nodes Registry
Combines all node types into a single registry.
"""
from typing import Dict, Type
from nodes.base import NodeBase, NodeCategory, NodeResult, serialize_dataframe, deserialize_dataframe
from nodes.sources import SOURCE_NODES
from nodes.transforms import TRANSFORM_NODES
from nodes.enrichers import ENRICH_NODES
from nodes.actions import ACTION_NODES

# Combined registry of all nodes
NODE_REGISTRY: Dict[str, Type[NodeBase]] = {
    **SOURCE_NODES,
    **TRANSFORM_NODES,
    **ENRICH_NODES,
    **ACTION_NODES,
}

# Category mapping for frontend
NODE_CATEGORIES = {
    "source": list(SOURCE_NODES.keys()),
    "transform": list(TRANSFORM_NODES.keys()),
    "enrich": list(ENRICH_NODES.keys()),
    "action": list(ACTION_NODES.keys()),
}

# Node metadata for frontend
NODE_METADATA = {}
for name, node_class in NODE_REGISTRY.items():
    NODE_METADATA[name] = {
        "name": name,
        "category": node_class.category.value,
        "description": node_class.description,
        "config_schema": node_class.config_schema,
    }


def get_node_class(node_type: str) -> Type[NodeBase]:
    """Get node class by type name."""
    return NODE_REGISTRY.get(node_type)


def list_nodes_by_category(category: str = None):
    """List available nodes, optionally filtered by category."""
    if category:
        return NODE_CATEGORIES.get(category, [])
    return NODE_CATEGORIES


__all__ = [
    "NODE_REGISTRY",
    "NODE_CATEGORIES", 
    "NODE_METADATA",
    "NodeBase",
    "NodeCategory",
    "NodeResult",
    "get_node_class",
    "list_nodes_by_category",
    "serialize_dataframe",
    "deserialize_dataframe",
]
