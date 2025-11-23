"""
Cliente para SEC Stream API (WebSocket)
Recibe filings en tiempo real y los guarda en BD
"""
import asyncio
import websockets
import orjson
from datetime import datetime
from typing import Optional, List
from models import SECFiling
from utils.database import db_client
from config import settings


class SECStreamClient:
    """Cliente WebSocket para SEC Stream API"""
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        self.stats = {
            "connected": False,
            "last_filing_received": None,
            "total_filings_received": 0,
            "uptime_seconds": 0.0,
            "reconnect_count": 0,
            "start_time": None,
        }
    
    async def connect(self):
        """Conectar al WebSocket de SEC"""
        try:
            print(f"🔌 Connecting to SEC Stream API...")
            self.ws = await websockets.connect(
                settings.sec_stream_ws_url,
                ping_interval=settings.STREAM_PING_TIMEOUT,
                ping_timeout=10,
                close_timeout=10
            )
            self.stats["connected"] = True
            self.stats["start_time"] = datetime.now()
            print(f"✅ Connected to SEC Stream API")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to SEC Stream API: {e}")
            self.stats["connected"] = False
            return False
    
    async def disconnect(self):
        """Desconectar del WebSocket"""
        self.is_running = False
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.stats["connected"] = False
        print("✅ Disconnected from SEC Stream API")
    
    def parse_filing(self, filing_data: dict) -> Optional[SECFiling]:
        """
        Parsear datos raw del Stream API a modelo SECFiling
        
        Args:
            filing_data: Dict con datos raw del filing
            
        Returns:
            Objeto SECFiling o None si hay error
        """
        try:
            # El Stream API envía filedAt como string, necesitamos parsearlo
            if 'filedAt' in filing_data and isinstance(filing_data['filedAt'], str):
                filing_data['filedAt'] = datetime.fromisoformat(
                    filing_data['filedAt'].replace('Z', '+00:00')
                )
            
            # Crear objeto SECFiling
            filing = SECFiling(**filing_data)
            return filing
        except Exception as e:
            print(f"❌ Error parsing filing: {e}")
            print(f"   Data: {filing_data.get('accessionNo', 'unknown')}")
            return None
    
    async def process_message(self, message: str):
        """
        Procesar mensaje del WebSocket
        
        Args:
            message: String con mensaje JSON del Stream API
        """
        try:
            # Parse JSON (puede ser array de filings)
            data = orjson.loads(message)
            
            # El mensaje es un array de filings
            if not isinstance(data, list):
                print(f"⚠️ Unexpected message format (not a list)")
                return
            
            # Procesar cada filing
            for filing_data in data:
                filing = self.parse_filing(filing_data)
                if filing:
                    # Guardar en BD
                    success = await db_client.insert_filing(filing)
                    if success:
                        self.stats["total_filings_received"] += 1
                        self.stats["last_filing_received"] = datetime.now()
                        print(
                            f"💾 Filing saved: {filing.formType} | "
                            f"{filing.ticker or filing.cik} | "
                            f"{filing.accessionNo[:20]}..."
                        )
                    else:
                        print(f"❌ Failed to save filing: {filing.accessionNo}")
        
        except Exception as e:
            print(f"❌ Error processing message: {e}")
    
    async def run(self):
        """
        Ejecutar el loop principal del Stream Client
        Mantiene conexión y re-conecta automáticamente
        """
        self.is_running = True
        
        while self.is_running:
            try:
                # Conectar si no estamos conectados
                if not self.ws or self.ws.closed:
                    connected = await self.connect()
                    if not connected:
                        print(f"⏳ Retrying in {settings.STREAM_RECONNECT_DELAY}s...")
                        await asyncio.sleep(settings.STREAM_RECONNECT_DELAY)
                        self.stats["reconnect_count"] += 1
                        continue
                
                # Recibir mensajes
                async for message in self.ws:
                    await self.process_message(message)
                    
                    # Actualizar uptime
                    if self.stats["start_time"]:
                        elapsed = datetime.now() - self.stats["start_time"]
                        self.stats["uptime_seconds"] = elapsed.total_seconds()
            
            except websockets.exceptions.ConnectionClosed:
                print("⚠️ WebSocket connection closed, reconnecting...")
                self.stats["connected"] = False
                self.stats["reconnect_count"] += 1
                await asyncio.sleep(settings.STREAM_RECONNECT_DELAY)
            
            except Exception as e:
                print(f"❌ Stream error: {e}")
                self.stats["connected"] = False
                await asyncio.sleep(settings.STREAM_RECONNECT_DELAY)
        
        print("✅ Stream client stopped")
    
    def get_status(self) -> dict:
        """Obtener estado del stream"""
        return {
            "connected": self.stats["connected"],
            "last_filing_received": (
                self.stats["last_filing_received"].isoformat()
                if self.stats["last_filing_received"]
                else None
            ),
            "total_filings_received": self.stats["total_filings_received"],
            "uptime_seconds": self.stats["uptime_seconds"],
            "reconnect_count": self.stats["reconnect_count"],
        }


# Singleton
stream_client = SECStreamClient()

