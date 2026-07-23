"""
Re-export de compatibilidad: los rosters viven en agents/tool_rosters.py
(los usa también el selector de producción, agents/_tool_selector.py).
"""
from agents.tool_rosters import ROSTERS, TOOL_DESCS, roster_tools, all_roster_tools  # noqa: F401
