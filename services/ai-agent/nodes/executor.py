"""
Workflow Executor - Executes workflow graphs using modular nodes.
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import asyncio
from dataclasses import dataclass
from collections import defaultdict
import structlog

from nodes import NODE_REGISTRY, get_node_class, serialize_dataframe, deserialize_dataframe
from nodes.base import NodeResult

logger = structlog.get_logger()


@dataclass
class WorkflowNode:
    """Parsed workflow node."""
    id: str
    type: str
    config: Dict[str, Any]
    position: Dict[str, float]
    label: str


@dataclass
class WorkflowEdge:
    """Parsed workflow edge."""
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None


class WorkflowExecutor:
    """
    Executes workflow graphs using the modular node system.
    """
    
    def __init__(self, context: Dict[str, Any]):
        """
        Initialize executor with shared context.
        
        Args:
            context: Shared context containing llm_client, scanner, etc.
        """
        self.context = context
        self.logger = logger.bind(component="workflow_executor")
    
    async def execute(
        self,
        workflow: Dict[str, Any],
        on_node_start: Optional[callable] = None,
        on_node_complete: Optional[callable] = None,
        on_error: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow and return results.
        
        Args:
            workflow: Workflow definition with nodes and edges
            on_node_start: Callback when node starts (node_id)
            on_node_complete: Callback when node completes (node_id, result, time_ms)
            on_error: Callback on error (node_id, error)
            
        Returns:
            Dict with nodeResults and metadata
        """
        try:
            # Parse workflow
            nodes = self._parse_nodes(workflow.get("nodes", []))
            edges = self._parse_edges(workflow.get("edges", []))
            
            if not nodes:
                return {"success": False, "error": "No nodes in workflow"}
            
            # Build execution order (topological sort)
            execution_order = self._topological_sort(nodes, edges)
            
            self.logger.info("workflow_execution_start", 
                           node_count=len(nodes),
                           edge_count=len(edges),
                           order=[n.id for n in execution_order])
            
            # Execute nodes in order
            results: Dict[str, Dict[str, Any]] = {}
            node_outputs: Dict[str, pd.DataFrame] = {}
            
            for node in execution_order:
                import time
                start_time = time.time()
                
                if on_node_start:
                    await on_node_start(node.id)
                
                try:
                    # Get input data from connected nodes
                    input_data = self._get_node_input(node.id, edges, node_outputs)
                    
                    # Create and execute node
                    node_class = get_node_class(node.type)
                    
                    if not node_class:
                        # Unknown node type - pass through data
                        self.logger.warning("unknown_node_type", node_type=node.type)
                        result = NodeResult(
                            success=True,
                            data=input_data,
                            metadata={"passthrough": True}
                        )
                    else:
                        # Instantiate and execute
                        node_instance = node_class(node.config, self.context)
                        result = await node_instance.execute(input_data)
                    
                    exec_time = int((time.time() - start_time) * 1000)
                    
                    # Store output for downstream nodes
                    if result.success and result.data is not None:
                        node_outputs[node.id] = result.data
                    
                    # Build result dict
                    result_dict = {
                        "nodeId": node.id,
                        "status": "success" if result.success else "error",
                        "executionTime": exec_time,
                        "data": result.to_dict() if result.success else None,
                        "error": result.error
                    }
                    results[node.id] = result_dict
                    
                    if on_node_complete:
                        await on_node_complete(node.id, result_dict, exec_time)
                    
                    self.logger.info("node_executed",
                                   node_id=node.id,
                                   node_type=node.type,
                                   success=result.success,
                                   exec_time_ms=exec_time,
                                   output_rows=len(result.data) if result.data is not None else 0)
                    
                except Exception as e:
                    exec_time = int((time.time() - start_time) * 1000)
                    error_msg = str(e)
                    
                    self.logger.error("node_execution_error",
                                    node_id=node.id,
                                    error=error_msg)
                    
                    result_dict = {
                        "nodeId": node.id,
                        "status": "error",
                        "executionTime": exec_time,
                        "error": error_msg
                    }
                    results[node.id] = result_dict
                    
                    if on_error:
                        await on_error(node.id, error_msg)
            
            # Calculate totals
            total_time = sum(r.get("executionTime", 0) for r in results.values())
            success_count = sum(1 for r in results.values() if r.get("status") == "success")
            
            return {
                "success": True,
                "nodeResults": results,
                "metadata": {
                    "totalTime": total_time,
                    "nodeCount": len(nodes),
                    "successCount": success_count,
                    "errorCount": len(nodes) - success_count
                }
            }
            
        except Exception as e:
            self.logger.error("workflow_execution_error", error=str(e))
            return {"success": False, "error": str(e)}
    
    def _parse_nodes(self, raw_nodes: List[Dict]) -> List[WorkflowNode]:
        """Parse raw node dicts into WorkflowNode objects."""
        nodes = []
        for raw in raw_nodes:
            node = WorkflowNode(
                id=raw.get("id", ""),
                type=raw.get("type", ""),
                config=raw.get("data", {}).get("config", {}),
                position=raw.get("position", {"x": 0, "y": 0}),
                label=raw.get("data", {}).get("label", "")
            )
            nodes.append(node)
        return nodes
    
    def _parse_edges(self, raw_edges: List[Dict]) -> List[WorkflowEdge]:
        """Parse raw edge dicts into WorkflowEdge objects."""
        edges = []
        for raw in raw_edges:
            edge = WorkflowEdge(
                id=raw.get("id", ""),
                source=raw.get("source", ""),
                target=raw.get("target", ""),
                source_handle=raw.get("sourceHandle"),
                target_handle=raw.get("targetHandle")
            )
            edges.append(edge)
        return edges
    
    def _topological_sort(
        self, 
        nodes: List[WorkflowNode], 
        edges: List[WorkflowEdge]
    ) -> List[WorkflowNode]:
        """Sort nodes in execution order based on dependencies."""
        # Build adjacency list and in-degree count
        node_map = {n.id: n for n in nodes}
        in_degree = {n.id: 0 for n in nodes}
        adjacency = defaultdict(list)
        
        for edge in edges:
            adjacency[edge.source].append(edge.target)
            if edge.target in in_degree:
                in_degree[edge.target] += 1
        
        # Kahn's algorithm
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        
        while queue:
            # Sort by x position for consistent ordering
            queue.sort(key=lambda nid: node_map[nid].position.get("x", 0))
            node_id = queue.pop(0)
            result.append(node_map[node_id])
            
            for neighbor in adjacency[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Add any disconnected nodes at the end
        for node in nodes:
            if node not in result:
                result.append(node)
        
        return result
    
    def _get_node_input(
        self,
        node_id: str,
        edges: List[WorkflowEdge],
        outputs: Dict[str, pd.DataFrame]
    ) -> Optional[pd.DataFrame]:
        """Get input DataFrame for a node from connected sources."""
        incoming_edges = [e for e in edges if e.target == node_id]
        
        if not incoming_edges:
            return None
        
        # Collect all inputs
        input_dfs = []
        for edge in incoming_edges:
            source_id = edge.source
            if source_id in outputs and outputs[source_id] is not None:
                input_dfs.append(outputs[source_id])
        
        if not input_dfs:
            return None
        
        if len(input_dfs) == 1:
            return input_dfs[0]
        
        # Multiple inputs - concatenate
        try:
            combined = pd.concat(input_dfs, ignore_index=True)
            # Deduplicate by symbol if exists
            if "symbol" in combined.columns:
                combined = combined.drop_duplicates(subset=["symbol"], keep="first")
            return combined
        except Exception as e:
            self.logger.warning("input_merge_error", error=str(e))
            return input_dfs[0]  # Fallback to first
