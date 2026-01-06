"""
Service Clients for AI Agent

Clientes HTTP para comunicarse con los servicios internos de TradeUL.
En lugar de reinventar la rueda, usamos los servicios existentes:

- api_gateway: Para snapshots y datos de chart de Polygon
- ticker_metadata: Para metadata de compañías
- scanner: Para datos filtrados en tiempo real

Esto mantiene la arquitectura limpia y evita duplicación de lógica.
"""

import httpx
import pandas as pd
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta, time as dt_time, date as dt_date
import pytz
import structlog

logger = structlog.get_logger(__name__)

# Timezone de mercado US Eastern
ET = pytz.timezone('America/New_York')


class ServiceClients:
    """
    Cliente unificado para servicios internos de TradeUL.
    
    Ventajas:
    - Reutiliza cache existente en cada servicio
    - Centraliza llamadas a Polygon a través de api_gateway
    - Mantiene consistencia de datos
    """
    
    def __init__(
        self,
        api_gateway_url: str = "http://api_gateway:8000",
        ticker_metadata_url: str = "http://ticker_metadata:8010",
        scanner_url: str = "http://scanner:8005"
    ):
        self.api_gateway_url = api_gateway_url
        self.ticker_metadata_url = ticker_metadata_url
        self.scanner_url = scanner_url
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _parse_date_expression(self, date: Union[datetime, str]) -> dt_date:
        """
        Parsea expresiones de fecha flexibles.
        
        Soporta:
            - 'yesterday', 'ayer'
            - 'today', 'hoy'
            - 'hace N días', 'N days ago'
            - 'YYYY-MM-DD' (ISO)
            - datetime objects
        
        Returns:
            date object
        """
        import re
        
        if isinstance(date, datetime):
            return date.date()
        
        if hasattr(date, 'date') and callable(date.date):
            return date.date()
        
        date_str = str(date).lower().strip()
        today = datetime.now(ET).date()
        
        # Palabras clave directas
        if date_str in ['yesterday', 'ayer']:
            return today - timedelta(days=1)
        elif date_str in ['today', 'hoy']:
            return today
        
        # Patrones "hace N días" / "N days ago"
        patterns = [
            r'hace\s+(\d+)\s*d[ií]as?',      # "hace 2 días", "hace 3 dias"
            r'(\d+)\s*d[ií]as?\s+atr[aá]s',  # "2 días atrás"
            r'(\d+)\s*days?\s+ago',           # "2 days ago"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                days_back = int(match.group(1))
                return today - timedelta(days=days_back)
        
        # Intentar parsear como fecha ISO
        try:
            return pd.to_datetime(date_str).date()
        except Exception:
            logger.warning("unparseable_date", date=date_str, fallback="yesterday")
            return today - timedelta(days=1)
    
    def _format_date_label(self, date: Union[datetime, str]) -> str:
        """
        Genera label legible para un periodo.
        
        Returns:
            'Hoy', 'Ayer', 'Hace 2 días', '2024-01-05', etc.
        """
        import re
        
        if isinstance(date, datetime):
            target = date.date()
        elif hasattr(date, 'date') and callable(date.date):
            target = date.date()
        else:
            target = self._parse_date_expression(date)
        
        today = datetime.now(ET).date()
        diff = (today - target).days
        
        if diff == 0:
            return 'Hoy'
        elif diff == 1:
            return 'Ayer'
        elif diff <= 7:
            return f'Hace {diff} días'
        else:
            return target.isoformat()
    
    # =========================================================================
    # API GATEWAY - Snapshots y Charts (Polygon)
    # =========================================================================
    
    async def get_ticker_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene snapshot de un ticker via api_gateway.
        
        api_gateway ya:
        - Tiene cache de 5 minutos
        - Maneja rate limiting de Polygon
        - Formatea la respuesta
        """
        try:
            client = await self._get_client()
            url = f"{self.api_gateway_url}/api/v1/ticker/{symbol}/snapshot"
            
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                logger.info("ticker_snapshot_fetched", symbol=symbol, source="api_gateway")
                return data
            elif response.status_code == 404:
                logger.warning("ticker_not_found", symbol=symbol)
                return None
            else:
                logger.warning("api_gateway_error", symbol=symbol, status=response.status_code)
                return None
                
        except Exception as e:
            logger.error("ticker_snapshot_error", symbol=symbol, error=str(e))
            return None
    
    async def get_chart_data(
        self,
        symbol: str,
        interval: str = "1hour",
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Obtiene datos de chart via api_gateway.
        
        api_gateway ya:
        - Usa Polygon para intraday
        - Usa FMP para daily
        - Tiene cache inteligente
        """
        try:
            client = await self._get_client()
            url = f"{self.api_gateway_url}/api/v1/chart/{symbol}"
            params = {"interval": interval, "limit": limit}
            
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                bars = data.get("data", [])
                logger.info("chart_data_fetched", symbol=symbol, bars=len(bars))
                return bars
            else:
                logger.warning("chart_data_error", symbol=symbol, status=response.status_code)
                return []
                
        except Exception as e:
            logger.error("chart_data_error", symbol=symbol, error=str(e))
            return []
    
    # =========================================================================
    # TICKER METADATA - Información de Compañías
    # =========================================================================
    
    async def get_ticker_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene metadata de un ticker via ticker_metadata service.
        
        ticker_metadata ya:
        - Cache Redis (1h TTL)
        - Persistencia TimescaleDB
        - Enriquecimiento desde Polygon
        """
        try:
            client = await self._get_client()
            url = f"{self.ticker_metadata_url}/api/v1/metadata/{symbol}"
            
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                logger.info("metadata_fetched", symbol=symbol)
                return data
            else:
                logger.warning("metadata_not_found", symbol=symbol)
                return None
                
        except Exception as e:
            logger.error("metadata_error", symbol=symbol, error=str(e))
            return None
    
    async def search_tickers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Busca tickers por nombre o símbolo.
        
        Usa la búsqueda optimizada de ticker_metadata (PostgreSQL + índices GIN).
        """
        try:
            client = await self._get_client()
            url = f"{self.ticker_metadata_url}/api/v1/metadata/search"
            params = {"q": query, "limit": limit}
            
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                logger.info("ticker_search", query=query, results=len(results))
                return results
            else:
                return []
                
        except Exception as e:
            logger.error("ticker_search_error", query=query, error=str(e))
            return []
    
    # =========================================================================
    # SCANNER - Datos Filtrados en Tiempo Real
    # =========================================================================
    
    async def check_ticker_in_scanner(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Verifica si un ticker está en el scanner y obtiene sus datos.
        """
        try:
            client = await self._get_client()
            url = f"{self.scanner_url}/api/scanner/filtered"
            
            response = await client.get(url)
            
            if response.status_code == 200:
                tickers = response.json()
                for ticker in tickers:
                    if ticker.get("symbol", "").upper() == symbol.upper():
                        return ticker
                return None
            else:
                return None
                
        except Exception as e:
            logger.error("scanner_check_error", symbol=symbol, error=str(e))
            return None
    
    # =========================================================================
    # MÉTODOS INTELIGENTES - Combinan múltiples fuentes
    # =========================================================================
    
    async def get_ticker_full_info(self, symbol: str) -> Dict[str, Any]:
        """
        Obtiene información completa de un ticker combinando fuentes.
        
        Estrategia:
        1. Buscar en scanner (datos tiempo real si está activo)
        2. SIEMPRE obtener snapshot de Polygon para OHLC completo
        3. Enriquecer con metadata de ticker_metadata
        
        Returns:
            Dict con toda la información disponible y su fuente
        """
        symbol = symbol.upper()
        result = {
            "symbol": symbol,
            "found": False,
            "sources": [],
            "data": {}
        }
        
        # 1. Intentar scanner primero (datos tiempo real más frescos)
        scanner_data = await self.check_ticker_in_scanner(symbol)
        if scanner_data:
            result["found"] = True
            result["sources"].append("scanner")
            result["data"]["realtime"] = scanner_data
            result["data"]["price"] = scanner_data.get("price")
            result["data"]["change_percent"] = scanner_data.get("change_percent")
            result["data"]["volume"] = scanner_data.get("volume_today")
            # El scanner también puede tener OHLC
            result["data"]["open"] = scanner_data.get("open")
            result["data"]["high"] = scanner_data.get("high") or scanner_data.get("intraday_high")
            result["data"]["low"] = scanner_data.get("low") or scanner_data.get("intraday_low")
            result["data"]["prev_close"] = scanner_data.get("prev_close")
            result["data"]["vwap"] = scanner_data.get("vwap")
        
        # 2. Si no tenemos OHLC del scanner, obtener de Polygon
        needs_ohlc = not result["data"].get("open") or not result["data"].get("high")
        
        if needs_ohlc or not result["found"]:
            snapshot = await self.get_ticker_snapshot(symbol)
            if snapshot and snapshot.get("ticker"):
                if not result["found"]:
                    result["found"] = True
                result["sources"].append("polygon_snapshot")
                ticker_data = snapshot.get("ticker", {})
                result["data"]["snapshot"] = ticker_data
                
                # Extraer datos del snapshot (solo si no los tenemos del scanner)
                if "day" in ticker_data:
                    day = ticker_data["day"]
                    if not result["data"].get("price"):
                        result["data"]["price"] = day.get("c")  # close
                    if not result["data"].get("open"):
                        result["data"]["open"] = day.get("o")
                    if not result["data"].get("high"):
                        result["data"]["high"] = day.get("h")
                    if not result["data"].get("low"):
                        result["data"]["low"] = day.get("l")
                    if not result["data"].get("volume"):
                        result["data"]["volume"] = day.get("v")
                    if not result["data"].get("vwap"):
                        result["data"]["vwap"] = day.get("vw")
                
                if "prevDay" in ticker_data:
                    prev = ticker_data["prevDay"]
                    if not result["data"].get("prev_close"):
                        result["data"]["prev_close"] = prev.get("c")
                    # Calcular change_percent si no lo tenemos
                    if not result["data"].get("change_percent"):
                        prev_close = prev.get("c", 0)
                        current = result["data"].get("price", 0)
                        if prev_close and current:
                            result["data"]["change_percent"] = round(
                                ((current - prev_close) / prev_close) * 100, 2
                            )
        
        # 3. Enriquecer con metadata (sector, industry, market_cap)
        metadata = await self.get_ticker_metadata(symbol)
        if metadata:
            result["sources"].append("metadata")
            result["data"]["metadata"] = metadata
            result["data"]["company_name"] = metadata.get("company_name")
            result["data"]["sector"] = metadata.get("sector")
            result["data"]["industry"] = metadata.get("industry")
            result["data"]["market_cap"] = metadata.get("market_cap")
        
        return result
    
    # =========================================================================
    # FUNCIONES AVANZADAS DE TIEMPO - Para consultas temporales específicas
    # =========================================================================
    
    async def get_bars_range(
        self,
        symbol: str,
        from_datetime: Union[datetime, str],
        to_datetime: Union[datetime, str],
        interval: str = "5min"
    ) -> pd.DataFrame:
        """
        Obtiene barras en un rango de tiempo específico usando Polygon directamente.
        
        Args:
            symbol: Ticker symbol
            from_datetime: Inicio del rango (datetime o string 'YYYY-MM-DD HH:MM')
            to_datetime: Fin del rango (datetime o string 'YYYY-MM-DD HH:MM')
            interval: 1min, 5min, 15min, 30min, 1hour, 4hour, 1day
        
        Returns:
            DataFrame con barras filtradas al rango exacto
        """
        import os
        
        # Parsear fechas si son strings
        if isinstance(from_datetime, str):
            from_datetime = pd.to_datetime(from_datetime)
        if isinstance(to_datetime, str):
            to_datetime = pd.to_datetime(to_datetime)
        
        # Si from/to no tienen timezone, asumir ET y convertir a naive para Polygon
        if from_datetime.tzinfo is not None:
            from_datetime = from_datetime.astimezone(ET).replace(tzinfo=None)
        if to_datetime.tzinfo is not None:
            to_datetime = to_datetime.astimezone(ET).replace(tzinfo=None)
        
        # Mapear interval a formato Polygon
        interval_map = {
            "1min": (1, "minute"), "5min": (5, "minute"), "15min": (15, "minute"),
            "30min": (30, "minute"), "1hour": (1, "hour"), "4hour": (4, "hour"), "1day": (1, "day")
        }
        multiplier, span = interval_map.get(interval, (5, "minute"))
        
        # Llamar a Polygon directamente
        api_key = os.getenv("POLYGON_API_KEY")
        if not api_key:
            logger.error("POLYGON_API_KEY not set")
            return pd.DataFrame()
        
        from_str = from_datetime.strftime('%Y-%m-%d')
        to_str = to_datetime.strftime('%Y-%m-%d')
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{span}/{from_str}/{to_str}"
        params = {"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": 50000}
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning("polygon_bars_range_error", symbol=symbol, status=response.status_code)
                return pd.DataFrame()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                return pd.DataFrame()
            
            # Convertir a DataFrame
            df = pd.DataFrame(results)
            df = df.rename(columns={'t': 'time', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
            df['time'] = df['time'] // 1000  # ms to seconds
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
            df['datetime_et'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert(ET)
            
            # Filtrar al rango horario exacto
            from_dt_et = ET.localize(from_datetime)
            to_dt_et = ET.localize(to_datetime)
            
            mask = (df['datetime_et'] >= from_dt_et) & (df['datetime_et'] <= to_dt_et)
            result = df[mask].copy()
            
            logger.info(
                "bars_range_fetched",
                symbol=symbol,
                from_dt=str(from_dt_et),
                to_dt=str(to_dt_et),
                total_bars=len(results),
                filtered_bars=len(result)
            )
            
            return result
            
        except Exception as e:
            logger.error("bars_range_error", symbol=symbol, error=str(e))
            return pd.DataFrame()
    
    async def get_bars_for_date(
        self,
        symbol: str,
        date: Union[datetime, str],
        start_time: str = "09:30",
        end_time: str = "16:00",
        interval: str = "5min"
    ) -> pd.DataFrame:
        """
        Obtiene barras de una fecha específica en una franja horaria.
        
        Args:
            symbol: Ticker symbol
            date: Fecha (datetime o 'YYYY-MM-DD')
            start_time: Hora inicio en formato 'HH:MM' (default: apertura 09:30)
            end_time: Hora fin en formato 'HH:MM' (default: cierre 16:00)
            interval: Timeframe
        
        Returns:
            DataFrame con barras de esa fecha y franja horaria
        
        Ejemplo:
            # Última hora de ayer (15:00-16:00)
            df = await get_bars_for_date('AAPL', 'yesterday', start_time='15:00', end_time='16:00')
            
            # Pre-market de hoy (04:00-09:30)
            df = await get_bars_for_date('AAPL', 'today', start_time='04:00', end_time='09:30')
        """
        # Procesar fecha especial
        target_date = self._parse_date_expression(date)
        
        # Parsear horas
        start_h, start_m = map(int, start_time.split(':'))
        end_h, end_m = map(int, end_time.split(':'))
        
        # Crear datetimes con timezone ET
        from_dt = ET.localize(datetime.combine(target_date, dt_time(start_h, start_m)))
        to_dt = ET.localize(datetime.combine(target_date, dt_time(end_h, end_m)))
        
        return await self.get_bars_range(symbol, from_dt, to_dt, interval)
    
    async def get_last_n_minutes_of_date(
        self,
        symbol: str,
        date: Union[datetime, str],
        minutes: int = 15,
        interval: str = "1min"
    ) -> pd.DataFrame:
        """
        Obtiene los últimos N minutos de trading de una fecha específica.
        
        Args:
            symbol: Ticker
            date: Fecha ('yesterday', 'today', '2024-01-05')
            minutes: Minutos antes del cierre (default: 15)
            interval: Timeframe para las barras
        
        Returns:
            DataFrame con las últimas N minutos del día
        
        Ejemplo:
            # Últimos 15 minutos de ayer
            df = await get_last_n_minutes_of_date('AAPL', 'yesterday', minutes=15)
        """
        # 16:00 - N minutos
        end_time = "16:00"
        close_minutes = 16 * 60  # 960 minutos desde medianoche
        start_minutes = close_minutes - minutes
        start_h = start_minutes // 60
        start_m = start_minutes % 60
        start_time = f"{start_h:02d}:{start_m:02d}"
        
        return await self.get_bars_for_date(symbol, date, start_time, end_time, interval)
    
    async def get_top_movers_at_time(
        self,
        date: Union[datetime, str],
        start_time: str,
        end_time: str,
        direction: str = "up",
        limit: int = 20
    ) -> pd.DataFrame:
        """
        Obtiene los top movers (subiendo o bajando) en una franja horaria específica del pasado.
        
        Estrategia:
        1. Obtener símbolos del scanner actual (los más activos probables)
        2. Para cada uno, obtener barras de esa franja horaria
        3. Calcular cambio % en esa franja
        4. Ordenar y retornar top
        
        Args:
            date: Fecha objetivo
            start_time: Hora inicio 'HH:MM'
            end_time: Hora fin 'HH:MM'
            direction: 'up' o 'down'
            limit: Número de resultados
        
        Returns:
            DataFrame con symbol, price_start, price_end, change_pct
        
        Ejemplo:
            # Top acciones subiendo de 15:00-16:00 de ayer
            df = await get_top_movers_at_time('yesterday', '15:00', '16:00', direction='up')
        """
        # Obtener candidatos del scanner actual
        scanner_data = await self.check_ticker_in_scanner("")  # Hack para obtener todos
        
        # Alternativa: obtener del scanner endpoint completo
        try:
            client = await self._get_client()
            url = f"{self.scanner_url}/api/scanner/filtered"
            response = await client.get(url)
            if response.status_code == 200:
                tickers = response.json()
            else:
                tickers = []
        except Exception:
            tickers = []
        
        # Limitar candidatos iniciales (los más activos por volumen)
        symbols = [t.get('symbol') for t in tickers[:50] if t.get('symbol')]
        
        # Usar métodos de parseo flexibles
        periodo_label = self._format_date_label(date)
        target_date = self._parse_date_expression(date).isoformat()
        
        results = []
        for symbol in symbols:
            try:
                df = await self.get_bars_for_date(symbol, date, start_time, end_time, interval="5min")
                if len(df) >= 2:
                    price_start = df.iloc[0]['open']
                    price_end = df.iloc[-1]['close']
                    change_pct = round(((price_end - price_start) / price_start) * 100, 2)
                    results.append({
                        'periodo': periodo_label,
                        'symbol': symbol,
                        'price_start': round(price_start, 2),
                        'price_end': round(price_end, 2),
                        'change_pct': change_pct,
                        'volume': int(df['volume'].sum()),
                        'date': target_date,
                        'time_range': f"{start_time}-{end_time}"
                    })
            except Exception as e:
                logger.warning("error_processing_symbol", symbol=symbol, error=str(e))
                continue
        
        # Ordenar
        result_df = pd.DataFrame(results)
        if result_df.empty:
            return result_df
        
        ascending = direction.lower() != "up"
        result_df = result_df.sort_values('change_pct', ascending=ascending).head(limit)
        result_df = result_df.reset_index(drop=True)
        
        logger.info(
            "top_movers_at_time",
            date=str(date),
            time_range=f"{start_time}-{end_time}",
            direction=direction,
            results=len(result_df)
        )
        
        return result_df


    async def get_extended_hours_movers(
        self,
        date: Union[datetime, str],
        session: str = "postmarket",  # "premarket" o "postmarket"
        direction: str = "up",
        limit: int = 20
    ) -> pd.DataFrame:
        """
        Obtiene los top movers en pre-market o post-market de una fecha específica.
        
        Args:
            date: Fecha ('yesterday', 'today', '2024-01-05')
            session: 'premarket' (04:00-09:30) o 'postmarket' (16:00-20:00)
            direction: 'up' o 'down'
            limit: Número de resultados
        
        Returns:
            DataFrame con symbol, price_start, price_end, change_pct, volume
        
        Ejemplo:
            # Top movers en post-market de ayer
            df = await get_extended_hours_movers('yesterday', session='postmarket', direction='up')
        """
        # Definir horas según la sesión
        if session.lower() == "premarket":
            start_time = "04:00"
            end_time = "09:30"
        else:  # postmarket
            start_time = "16:00"
            end_time = "20:00"
        
        # Usar parseo flexible de fechas
        target_date = self._parse_date_expression(date)
        periodo_label = self._format_date_label(date)
        
        # Obtener candidatos del scanner (los más activos)
        try:
            client = await self._get_client()
            url = f"{self.scanner_url}/api/scanner/filtered"
            response = await client.get(url)
            if response.status_code == 200:
                tickers = response.json()
            else:
                tickers = []
        except Exception:
            tickers = []
        
        # Tomar los más activos por volumen
        symbols = [t.get('symbol') for t in sorted(
            tickers, 
            key=lambda x: x.get('volume_today', 0), 
            reverse=True
        )[:60] if t.get('symbol')]
        
        session_label = "Pre-Market" if session.lower() == "premarket" else "Post-Market"
        
        results = []
        
        for symbol in symbols:
            try:
                # Usar get_bars_for_date que llama a Polygon con fechas correctas
                df = await self.get_bars_for_date(symbol, date, start_time, end_time, interval="5min")
                
                if len(df) >= 2:
                    price_start = df.iloc[0]['open']
                    price_end = df.iloc[-1]['close']
                    volume = df['volume'].sum()
                    change_pct = round(((price_end - price_start) / price_start) * 100, 2) if price_start > 0 else 0
                    
                    results.append({
                        'periodo': periodo_label,
                        'session': session_label,
                        'symbol': symbol,
                        'price_start': round(price_start, 2),
                        'price_end': round(price_end, 2),
                        'change_pct': change_pct,
                        'volume': int(volume),
                        'date': str(target_date),
                        'time_range': f"{start_time}-{end_time}"
                    })
            except Exception as e:
                logger.warning("extended_hours_error", symbol=symbol, error=str(e))
                continue
        
        if not results:
            return pd.DataFrame()
        
        # Ordenar por cambio
        result_df = pd.DataFrame(results)
        ascending = direction.lower() != "up"
        
        if direction.lower() == "up":
            result_df = result_df[result_df['change_pct'] > 0]
        else:
            result_df = result_df[result_df['change_pct'] < 0]
        
        result_df = result_df.sort_values('change_pct', ascending=ascending).head(limit)
        result_df = result_df.reset_index(drop=True)
        
        logger.info(
            "extended_hours_movers",
            date=str(target_date),
            session=session,
            direction=direction,
            results=len(result_df)
        )
        
        return result_df


# Instancia global (se inicializa en main.py)
service_clients: Optional[ServiceClients] = None


def get_service_clients() -> ServiceClients:
    global service_clients
    if service_clients is None:
        service_clients = ServiceClients()
    return service_clients

