"""
Workflow Execution Handler
==========================
Handles visual workflow execution requests.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
import structlog
import numpy as np
import pandas as pd

from agent import MarketAgent, execute_tool

logger = structlog.get_logger()


def _serialize_result(result: Any) -> Any:
    """Serialize result for JSON, handling numpy types."""
    # Handle numpy scalar types
    if isinstance(result, (np.integer,)):
        return int(result)
    if isinstance(result, (np.floating,)):
        return float(result)
    if isinstance(result, np.ndarray):
        return result.tolist()
    if isinstance(result, np.bool_):
        return bool(result)
    
    # Handle pandas
    if isinstance(result, pd.DataFrame):
        # Convert to JSON-safe records
        records = []
        for _, row in result.head(100).iterrows():
            record = {}
            for col in result.columns:
                val = row[col]
                if pd.isna(val):
                    record[col] = None
                elif isinstance(val, (np.integer,)):
                    record[col] = int(val)
                elif isinstance(val, (np.floating,)):
                    record[col] = float(val)
                else:
                    record[col] = val
            records.append(record)
        return {
            'type': 'dataframe',
            'columns': list(result.columns),
            'data': records,
            'count': len(result)
        }
    
    if isinstance(result, pd.Series):
        return _serialize_result(result.to_dict())
    
    # Handle dict recursively
    if isinstance(result, dict):
        return {str(k): _serialize_result(v) for k, v in result.items()}
    
    # Handle list recursively
    if isinstance(result, list):
        return [_serialize_result(item) for item in result[:100]]
    
    # Handle NaN/None
    if result is None or (isinstance(result, float) and np.isnan(result)):
        return None
    
    return result


# Map workflow node types to tool calls
# NEW CONCEPTUAL NODES (v2)
NODE_TYPE_TO_TOOL: Dict[str, str] = {
    # Data Sources
    'market_pulse': 'get_market_snapshot',  # New name for scanner
    
    # Detection & Analysis
    'volume_surge': 'get_market_snapshot',  # Uses scanner with volume filter
    'momentum_wave': 'get_top_movers',  # Uses top movers logic
    'sector_flow': 'classify_synthetic_sectors',  # New name for sectors
    
    # Enrichment
    'news_validator': 'research_ticker',  # Uses Grok for news analysis
    
    # Output
    'results': None,  # Display node - passthrough
    
    # Legacy aliases (for backward compatibility)
    'scanner': 'get_market_snapshot',
    'top_movers': 'get_top_movers',
    'sectors': 'classify_synthetic_sectors',
    'synthetic': 'classify_synthetic_sectors',
    'synthetic_sectors': 'classify_synthetic_sectors',
    'research': 'research_ticker',
    'display': None,  # Passthrough
}


class WorkflowExecutor:
    """
    Executes visual workflows by:
    1. Topologically sorting nodes
    2. Executing each node's tool
    3. Passing data between connected nodes
    """
    
    def __init__(self, agent: MarketAgent, context: Dict[str, Any] = None):
        self.agent = agent
        # Build full context with llm_client (the agent itself acts as llm client)
        base_context = context or {"session": "UNKNOWN", "time_et": ""}
        self.context = {
            **base_context,
            "llm_client": agent  # Agent acts as llm_client for tools
        }
        self.node_results: Dict[str, Any] = {}
    
    async def execute(
        self,
        workflow: Dict[str, Any],
        on_node_start: Optional[callable] = None,
        on_node_complete: Optional[callable] = None,
        on_node_error: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow and return results.
        """
        nodes = workflow['nodes']
        edges = workflow['edges']
        
        # Build execution order (topological sort)
        order = self._topological_sort(nodes, edges)
        
        logger.info("workflow_execution_started", 
                    workflow_id=workflow.get('id'),
                    node_count=len(nodes),
                    execution_order=order)
        
        results = {}
        
        for node_id in order:
            node = next((n for n in nodes if n['id'] == node_id), None)
            if not node:
                continue
            
            node_type = self._get_node_type(node)
            
            # Notify start
            if on_node_start:
                await on_node_start(node_id, node_type)
            
            start_time = time.time()
            
            try:
                # Get input data from connected nodes
                input_data = self._get_node_inputs(node_id, edges, results)
                
                # Execute the node
                result = await self._execute_node(node, input_data)
                
                execution_time = int((time.time() - start_time) * 1000)
                
                results[node_id] = {
                    'nodeId': node_id,
                    'status': 'success',
                    'data': _serialize_result(result),
                    'executionTime': execution_time
                }
                
                # Notify completion
                if on_node_complete:
                    await on_node_complete(node_id, result, execution_time)
                
                logger.info("workflow_node_completed",
                           node_id=node_id,
                           node_type=node_type,
                           execution_time=execution_time)
                
            except Exception as e:
                error_msg = str(e)
                results[node_id] = {
                    'nodeId': node_id,
                    'status': 'error',
                    'error': error_msg
                }
                
                # Notify error
                if on_node_error:
                    await on_node_error(node_id, error_msg)
                
                logger.error("workflow_node_failed",
                            node_id=node_id,
                            node_type=node_type,
                            error=error_msg)
        
        return {
            'workflowId': workflow.get('id'),
            'status': 'completed',
            'nodeResults': results
        }
    
    def _topological_sort(
        self, 
        nodes: List[Dict], 
        edges: List[Dict]
    ) -> List[str]:
        """Topologically sort nodes for execution order."""
        # Build adjacency list
        adj: Dict[str, List[str]] = {n['id']: [] for n in nodes}
        in_degree: Dict[str, int] = {n['id']: 0 for n in nodes}
        
        for edge in edges:
            source = edge['source']
            target = edge['target']
            if source in adj:
                adj[source].append(target)
            if target in in_degree:
                in_degree[target] += 1
        
        # Kahn's algorithm
        queue = [n['id'] for n in nodes if in_degree.get(n['id'], 0) == 0]
        order = []
        
        while queue:
            node_id = queue.pop(0)
            order.append(node_id)
            
            for neighbor in adj.get(node_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        return order
    
    def _get_node_type(self, node: Dict) -> str:
        """Extract node type from node data."""
        # First check explicit type field
        if node.get('type') and node['type'] not in ('custom', 'customNode', 'default'):
            return node['type']
        # Fallback: extract from node ID (e.g., 'scanner-123' -> 'scanner')
        node_id = node['id']
        return node_id.split('-')[0] if '-' in node_id else 'unknown'
    
    def _get_node_inputs(
        self, 
        node_id: str, 
        edges: List[Dict], 
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get input data from connected source nodes."""
        inputs = {}
        source_count = 0
        
        for edge in edges:
            if edge['target'] == node_id:
                source_id = edge['source']
                if source_id in results and results[source_id].get('status') == 'success':
                    source_data = results[source_id].get('data', {})
                    # Use unique key for each source to avoid overwriting
                    handle = edge.get('sourceHandle')
                    if not handle:
                        # Generate unique key: input_0, input_1, etc.
                        handle = f'input_{source_count}'
                        source_count += 1
                    inputs[handle] = source_data
        
        # If only one input, also add it as 'data' for backward compatibility
        if len(inputs) == 1:
            inputs['data'] = list(inputs.values())[0]
        
        return inputs
    
    async def _execute_node(
        self, 
        node: Dict, 
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single workflow node."""
        node_type = self._get_node_type(node)
        config = node.get('data', {}).get('config', {})
        
        # Map to tool
        tool_name = NODE_TYPE_TO_TOOL.get(node_type)
        
        if tool_name:
            # Build tool arguments from config and inputs
            args = self._build_tool_args(tool_name, config, input_data)
            
            # Execute tool with context
            result = await execute_tool(tool_name, args, self.context)
            return result
        
        # Handle output nodes (display, alert, export)
        if node_type == 'display' or node_type == 'results':
            # If multiple inputs, combine them
            if len(input_data) > 1:
                combined_sources = []
                for key, source_data in input_data.items():
                    if key.startswith('input_') or key == 'data':
                        # Extract the actual dataframe/data
                        actual_data = source_data
                        if isinstance(source_data, dict):
                            if 'data' in source_data:
                                actual_data = source_data['data']
                        combined_sources.append({
                            'source': key,
                            'data': actual_data
                        })
                return {
                    'type': 'display',
                    'title': config.get('title', 'Results'),
                    'displayType': 'combined',
                    'sources': combined_sources,
                    'data': combined_sources[0]['data'] if combined_sources else {}  # Primary data for backwards compat
                }
            else:
                # Single input - extract the data directly
                single_data = input_data.get('data') or (list(input_data.values())[0] if input_data else {})
                if isinstance(single_data, dict) and 'data' in single_data:
                    single_data = single_data['data']
                return {
                    'type': 'display',
                    'title': config.get('title', 'Results'),
                    'displayType': config.get('type', 'table'),
                    'data': single_data
                }
        
        if node_type == 'alert':
            return {
                'type': 'alert',
                'channel': config.get('channel', 'notification'),
                'triggered': len(input_data) > 0,
                'data': input_data
            }
        
        if node_type == 'export':
            return {
                'type': 'export',
                'format': config.get('format', 'csv'),
                'filename': config.get('filename', 'export'),
                'data': input_data
            }
        
        # Handle filter nodes
        if node_type == 'screener':
            return await self._execute_screener(config, input_data)
        
        return {'raw': input_data}
    
    def _build_tool_args(
        self, 
        tool_name: str, 
        config: Dict, 
        input_data: Dict
    ) -> Dict[str, Any]:
        """Build tool arguments from node config and inputs."""
        args = {}
        
        if tool_name == 'get_market_snapshot':
            # All scanner config params
            args['filter_type'] = config.get('filter_type', 'all')
            args['limit'] = config.get('limit', 200)  # Increased default
            if config.get('min_volume'):
                args['min_volume'] = config['min_volume']
            if config.get('min_price'):
                args['min_price'] = config['min_price']
            if config.get('sector'):
                args['sector'] = config['sector']
            
        elif tool_name == 'get_historical_data':
            args['date'] = config.get('date', 'yesterday')
            if config.get('start_hour'):
                args['start_hour'] = config['start_hour']
            if config.get('end_hour'):
                args['end_hour'] = config['end_hour']
            if config.get('symbols'):
                args['symbols'] = config['symbols']
            
        elif tool_name == 'get_top_movers':
            args['date'] = config.get('date', 'yesterday')
            args['direction'] = config.get('direction', 'up')
            args['limit'] = config.get('limit', 50)  # Increased default
            args['min_volume'] = config.get('min_volume', 100000)
            
        elif tool_name == 'classify_synthetic_sectors':
            args['date'] = config.get('date', 'today')
            args['max_sectors'] = config.get('max_sectors', 20)
            # Pass input data from connected node (Scanner, Top Movers, etc.)
            # Data comes serialized from _serialize_result as { type: 'dataframe', columns: [...], data: [...] }
            if input_data:
                logger.info("synthetic_build_args", 
                           input_data_keys=list(input_data.keys()) if isinstance(input_data, dict) else None)
                # Look for serialized dataframe in common locations
                for key in ['data', 'tickers', 'filtered', 'output']:
                    if key in input_data:
                        found = input_data[key]
                        # Found: { success: True, data: { type: 'dataframe', ... }, count: X }
                        if isinstance(found, dict):
                            # Check if it has nested serialized dataframe
                            if found.get('data', {}).get('type') == 'dataframe':
                                args['input_data'] = found['data']  # Pass the serialized DF directly
                                logger.info("synthetic_passing_nested_serialized_df", 
                                           rows=found['data'].get('count', 0))
                            # Or it IS the serialized dataframe
                            elif found.get('type') == 'dataframe':
                                args['input_data'] = found
                                logger.info("synthetic_passing_serialized_df", 
                                           rows=found.get('count', 0))
                            else:
                                args['input_data'] = found
                        break
            
        elif tool_name == 'research_ticker':
            # Get tickers from input if available
            tickers = input_data.get('tickers', input_data.get('filtered', []))
            if config.get('ticker'):
                args['symbol'] = config['ticker']
            elif isinstance(tickers, list) and len(tickers) > 0:
                args['symbol'] = tickers[0] if isinstance(tickers[0], str) else tickers[0].get('symbol', '')
            else:
                args['symbol'] = ''
            args['query'] = config.get('query', '')
            
        elif tool_name == 'execute_analysis':
            args['prompt'] = config.get('prompt', '')
            args['data'] = input_data
        
        return args
    
    async def _execute_screener(
        self, 
        config: Dict, 
        input_data: Dict
    ) -> Dict[str, Any]:
        """Execute screener filter on input tickers."""
        tickers_data = input_data.get('tickers', input_data.get('data', []))
        
        if not tickers_data:
            return {'filtered': [], 'count': 0}
        
        # Get filter criteria
        min_price = config.get('min_price', 0)
        max_price = config.get('max_price', float('inf'))
        min_volume = config.get('min_volume', 0)
        min_change = config.get('min_change', -float('inf'))
        max_change = config.get('max_change', float('inf'))
        
        filtered = []
        
        for ticker in tickers_data:
            if isinstance(ticker, dict):
                price = ticker.get('price', ticker.get('last', 0)) or 0
                volume = ticker.get('volume', 0) or 0
                change = ticker.get('change_percent', ticker.get('change', 0)) or 0
                
                if (min_price <= price <= max_price and
                    volume >= min_volume and
                    min_change <= change <= max_change):
                    filtered.append(ticker)
        
        return {
            'filtered': filtered,
            'count': len(filtered),
            'original_count': len(tickers_data)
        }


async def handle_workflow_execution(
    workflow: Dict[str, Any],
    agent: MarketAgent,
    send_update: callable
) -> Dict[str, Any]:
    """
    Handle workflow execution request from WebSocket.
    """
    executor = WorkflowExecutor(agent)
    
    async def on_start(node_id: str, node_type: str):
        await send_update({
            'type': 'node_started',
            'nodeId': node_id,
            'nodeType': node_type
        })
    
    async def on_complete(node_id: str, result: Any, exec_time: int):
        await send_update({
            'type': 'node_completed',
            'nodeId': node_id,
            'result': _serialize_result(result),
            'executionTime': exec_time
        })
    
    async def on_error(node_id: str, error: str):
        await send_update({
            'type': 'node_error',
            'nodeId': node_id,
            'error': error
        })
    
    result = await executor.execute(
        workflow,
        on_node_start=on_start,
        on_node_complete=on_complete,
        on_node_error=on_error
    )
    
    await send_update({
        'type': 'workflow_completed',
        'result': result
    })
    
    return result
