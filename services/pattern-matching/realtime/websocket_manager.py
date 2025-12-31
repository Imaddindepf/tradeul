"""
Pattern Real-Time - WebSocket Manager
=====================================

Manages WebSocket connections for real-time updates.
Supports:
- Multiple concurrent connections
- Job-specific subscriptions
- Broadcast to all subscribers of a job
- Heartbeat/ping-pong
"""

import asyncio
from datetime import datetime
from typing import Dict, Set, Optional, Any
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
import structlog

from .models import (
    WSMessage,
    WSMessageType,
    WSProgressMessage,
    WSResultMessage,
    WSVerificationMessage,
    WSJobCompleteMessage,
    PredictionResult,
    VerificationResult,
)

logger = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and subscriptions
    
    Features:
    - Track active connections
    - Job-specific subscriptions (one connection can subscribe to multiple jobs)
    - Broadcast messages to all subscribers of a job
    - Connection cleanup on disconnect
    """
    
    def __init__(self):
        # Active WebSocket connections
        self._connections: Set[WebSocket] = set()
        
        # Job subscriptions: job_id -> set of websockets
        self._subscriptions: Dict[str, Set[WebSocket]] = defaultdict(set)
        
        # Reverse mapping: websocket -> set of job_ids
        self._ws_to_jobs: Dict[WebSocket, Set[str]] = defaultdict(set)
        
        # Stats
        self._total_connections = 0
        self._total_messages_sent = 0
        
        logger.info("WebSocketManager initialized")
    
    # ========================================================================
    # Connection Management
    # ========================================================================
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self._connections.add(websocket)
        self._total_connections += 1
        
        logger.info(
            "WebSocket connected",
            active_connections=len(self._connections),
            total_connections=self._total_connections
        )
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Handle WebSocket disconnect"""
        # Remove from connections
        self._connections.discard(websocket)
        
        # Remove from all subscriptions
        for job_id in self._ws_to_jobs.get(websocket, set()).copy():
            self._subscriptions[job_id].discard(websocket)
            if not self._subscriptions[job_id]:
                del self._subscriptions[job_id]
        
        # Clean up reverse mapping
        if websocket in self._ws_to_jobs:
            del self._ws_to_jobs[websocket]
        
        logger.info(
            "WebSocket disconnected",
            active_connections=len(self._connections)
        )
    
    # ========================================================================
    # Subscription Management
    # ========================================================================
    
    def subscribe(self, websocket: WebSocket, job_id: str) -> None:
        """Subscribe a connection to a job's updates"""
        self._subscriptions[job_id].add(websocket)
        self._ws_to_jobs[websocket].add(job_id)
        
        logger.info(
            "ws_subscribed_to_job",
            job_id=job_id,
            subscribers=len(self._subscriptions[job_id])
        )
    
    def unsubscribe(self, websocket: WebSocket, job_id: str) -> None:
        """Unsubscribe a connection from a job"""
        self._subscriptions[job_id].discard(websocket)
        self._ws_to_jobs[websocket].discard(job_id)
        
        # Cleanup empty sets
        if not self._subscriptions[job_id]:
            del self._subscriptions[job_id]
        
        logger.debug("WebSocket unsubscribed from job", job_id=job_id)
    
    def get_subscribers(self, job_id: str) -> Set[WebSocket]:
        """Get all subscribers for a job"""
        return self._subscriptions.get(job_id, set()).copy()
    
    # ========================================================================
    # Message Sending
    # ========================================================================
    
    async def send_personal(
        self,
        websocket: WebSocket,
        message: Dict[str, Any]
    ) -> bool:
        """Send message to a specific connection"""
        try:
            await websocket.send_json(message)
            self._total_messages_sent += 1
            return True
        except Exception as e:
            logger.warning("Failed to send message", error=str(e))
            return False
    
    async def broadcast_to_job(
        self,
        job_id: str,
        message: Dict[str, Any]
    ) -> int:
        """Broadcast message to all subscribers of a job"""
        subscribers = self.get_subscribers(job_id)
        
        if not subscribers:
            return 0
        
        sent_count = 0
        failed = []
        
        for websocket in subscribers:
            try:
                await websocket.send_json(message)
                sent_count += 1
                self._total_messages_sent += 1
            except Exception as e:
                logger.warning("Failed to send to subscriber", error=str(e))
                failed.append(websocket)
        
        # Clean up failed connections
        for ws in failed:
            self.disconnect(ws)
        
        return sent_count
    
    async def broadcast_all(self, message: Dict[str, Any]) -> int:
        """Broadcast message to ALL connected clients"""
        if not self._connections:
            return 0
        
        sent_count = 0
        failed = []
        
        for websocket in self._connections.copy():
            try:
                await websocket.send_json(message)
                sent_count += 1
                self._total_messages_sent += 1
            except Exception:
                failed.append(websocket)
        
        for ws in failed:
            self.disconnect(ws)
        
        return sent_count
    
    # ========================================================================
    # Typed Message Broadcasting
    # ========================================================================
    
    async def send_progress(
        self,
        job_id: str,
        completed: int,
        total: int,
        failed: int = 0
    ) -> int:
        """Send progress update to job subscribers"""
        message = {
            "type": WSMessageType.PROGRESS.value,
            "job_id": job_id,
            "data": {
                "completed": completed,
                "total": total,
                "failed": failed
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.broadcast_to_job(job_id, message)
    
    async def send_result(
        self,
        job_id: str,
        result: PredictionResult
    ) -> int:
        """Send individual result to job subscribers"""
        message = {
            "type": WSMessageType.RESULT.value,
            "job_id": job_id,
            "data": result.model_dump(mode="json"),
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.broadcast_to_job(job_id, message)
    
    async def send_verification(
        self,
        verification: VerificationResult
    ) -> int:
        """Send verification result to ALL connections"""
        message = {
            "type": WSMessageType.VERIFICATION.value,
            "data": verification.model_dump(mode="json"),
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.broadcast_all(message)
    
    async def send_job_complete(
        self,
        job_id: str,
        total_results: int,
        total_failures: int,
        duration_seconds: float
    ) -> int:
        """Send job completion message"""
        message = {
            "type": WSMessageType.JOB_COMPLETE.value,
            "job_id": job_id,
            "data": {
                "total_results": total_results,
                "total_failures": total_failures,
                "duration_seconds": round(duration_seconds, 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.broadcast_to_job(job_id, message)
    
    async def send_error(
        self,
        websocket: WebSocket,
        error: str,
        job_id: Optional[str] = None
    ) -> bool:
        """Send error message to specific connection"""
        message = {
            "type": WSMessageType.ERROR.value,
            "job_id": job_id,
            "data": {"error": error},
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.send_personal(websocket, message)
    
    async def send_pong(self, websocket: WebSocket) -> bool:
        """Send pong response"""
        message = {
            "type": WSMessageType.PONG.value,
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.send_personal(websocket, message)
    
    # ========================================================================
    # Message Handler
    # ========================================================================
    
    async def handle_message(
        self,
        websocket: WebSocket,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle incoming WebSocket message
        
        Supported message types:
        - subscribe: Subscribe to job updates
        - unsubscribe: Unsubscribe from job
        - ping: Heartbeat (responds with pong)
        """
        msg_type = data.get("type")
        
        if msg_type == "subscribe":
            job_id = data.get("job_id")
            if job_id:
                self.subscribe(websocket, job_id)
                await self.send_personal(websocket, {
                    "type": "subscribed",
                    "job_id": job_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                await self.send_error(websocket, "Missing job_id")
        
        elif msg_type == "unsubscribe":
            job_id = data.get("job_id")
            if job_id:
                self.unsubscribe(websocket, job_id)
                await self.send_personal(websocket, {
                    "type": "unsubscribed",
                    "job_id": job_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        elif msg_type == "ping":
            await self.send_pong(websocket)
        
        else:
            await self.send_error(
                websocket, 
                f"Unknown message type: {msg_type}"
            )
    
    # ========================================================================
    # Stats
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics"""
        return {
            "active_connections": len(self._connections),
            "total_connections": self._total_connections,
            "total_messages_sent": self._total_messages_sent,
            "active_subscriptions": len(self._subscriptions),
            "jobs_with_subscribers": list(self._subscriptions.keys())
        }


# ============================================================================
# Global Instance
# ============================================================================

ws_manager = WebSocketManager()

