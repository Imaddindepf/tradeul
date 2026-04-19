"""
RETE Manager
Gestiona el grafo RETE y la evaluacion de tickers
"""

import asyncio
from typing import List, Dict, Set, Optional, Any
from datetime import datetime

from .models import ScanRule, RuleOwnerType, ReteNetwork
from .compiler import compile_network, add_rule_to_network, remove_rule_from_network
from .evaluator import evaluate_ticker, get_matching_rules
from .system_rules import get_system_rules
from .user_rules import convert_user_filters

import sys
sys.path.append('/app')

try:
    from shared.utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class ReteManager:
    """
    Gestiona el ciclo de vida del grafo RETE.
    
    Responsabilidades:
    - Cargar reglas del sistema y usuarios
    - Compilar y mantener el network
    - Evaluar tickers
    - Hot-reload de reglas
    """
    
    def __init__(self, redis_client=None, db_client=None):
        self.redis = redis_client
        self.db = db_client
        
        self.network: Optional[ReteNetwork] = None
        self.last_compile: Optional[datetime] = None
        self.active_users: Set[str] = set()
        
        # Estadisticas
        self.total_evaluations = 0
        self.total_matches = 0
    
    async def initialize(self):
        """Inicializa el manager cargando reglas."""
        await self.reload_rules()
        
        # Suscribirse a cambios de reglas (evento inmediato)
        if self.redis:
            asyncio.create_task(self._listen_for_changes())
        
        # Recarga periódica como red de seguridad (si Pub/Sub falla)
        if self.db:
            asyncio.create_task(self._periodic_reload())
    
    async def reload_rules(self):
        """Recarga todas las reglas y recompila el network."""
        try:
            all_rules = []
            
            # 1. Cargar reglas del sistema
            system_rules = get_system_rules()
            all_rules.extend(system_rules)
            logger.info("loaded_system_rules", count=len(system_rules))
            
            # 2. Cargar TODAS las reglas de usuarios habilitadas
            if self.db:
                user_rules = await self._load_user_rules()
                all_rules.extend(user_rules)
            
            # 3. Compilar network
            self.network = compile_network(all_rules)
            self.last_compile = datetime.now()
            
            stats = self.network.get_stats()
            logger.info("network_compiled", **stats)
            
        except Exception as e:
            logger.error("error_reloading_rules", error=str(e))
    
    async def _load_user_rules(self) -> List[ScanRule]:
        """
        Carga TODAS las reglas de usuarios habilitadas desde BD.
        No requiere usuarios activos - procesa todas las reglas enabled.
        """
        rules = []
        
        if not self.db:
            return rules
        
        try:
            # Cargar TODAS las reglas habilitadas de todos los usuarios
            query = """
                SELECT id, user_id, name, enabled, filter_type, parameters, priority
                FROM user_scanner_filters
                WHERE enabled = true
            """
            rows = await self.db.fetch(query)
            
            for row in rows:
                filter_data = dict(row)
                user_id = filter_data.get('user_id', 'unknown')
                
                # Parsear parameters si es string (asyncpg puede devolver JSONB como string)
                params = filter_data.get('parameters')
                if isinstance(params, str):
                    import json
                    filter_data['parameters'] = json.loads(params)
                
                user_rules = convert_user_filters([filter_data], user_id)
                if user_rules:
                    logger.info("converted_user_filter",
                        filter_id=filter_data.get('id'),
                        name=filter_data.get('name'),
                        conditions=len(user_rules[0].conditions) if user_rules else 0
                    )
                rules.extend(user_rules)
            
            logger.info("loaded_user_rules", count=len(rules))
            
        except Exception as e:
            logger.error("error_loading_user_rules", error=str(e))
        
        return rules
    
    async def _periodic_reload(self):
        """
        Recarga periódica de reglas como red de seguridad.
        
        Si el Pub/Sub falla (ej: pool de conexiones saturado), esta tarea
        garantiza que nuevos scans de usuario se carguen en un máximo de 5 minutos.
        Solo recompila si el número de reglas en BD difiere del network actual.
        """
        RELOAD_INTERVAL_SECONDS = 300  # 5 minutos
        
        while True:
            try:
                await asyncio.sleep(RELOAD_INTERVAL_SECONDS)
                
                if not self.db:
                    continue
                
                # Consulta ligera: solo contar reglas habilitadas
                count_query = "SELECT COUNT(*) as cnt FROM user_scanner_filters WHERE enabled = true"
                rows = await self.db.fetch(count_query)
                db_count = rows[0]['cnt'] if rows else 0
                
                current_user_rules = self.network.user_rules if self.network else 0
                
                if db_count != current_user_rules:
                    logger.info(
                        "periodic_reload_triggered",
                        db_rules=db_count,
                        current_rules=current_user_rules,
                        reason="rule_count_mismatch"
                    )
                    await self.reload_rules()
                else:
                    logger.debug(
                        "periodic_reload_check_ok",
                        rules_count=db_count
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("periodic_reload_error", error=str(e))
                await asyncio.sleep(60)  # Esperar 1 min en caso de error
    
    async def _listen_for_changes(self):
        """Escucha cambios en reglas via Redis Pub/Sub."""
        if not self.redis:
            return
        
        try:
            # Obtener el cliente Redis subyacente (RedisClient wrapper vs direct client)
            redis_conn = getattr(self.redis, 'client', self.redis)
            
            if not hasattr(redis_conn, 'pubsub'):
                logger.info("pubsub_not_available_skipping_listener")
                return
            
            pubsub = redis_conn.pubsub()
            await pubsub.subscribe("scanner:rules:changed")
            logger.info("pubsub_listener_started", channel="scanner:rules:changed")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    logger.info("rules_changed_event_received")
                    await self.reload_rules()
                    
        except Exception as e:
            logger.warning("pubsub_listener_disabled", reason=str(e))
    
    def set_active_users(self, users: Set[str]):
        """Actualiza lista de usuarios activos."""
        self.active_users = users
    
    def add_active_user(self, user_id: str):
        """Agrega usuario a la lista de activos."""
        self.active_users.add(user_id)
    
    def remove_active_user(self, user_id: str):
        """Remueve usuario de la lista de activos."""
        self.active_users.discard(user_id)
    
    def evaluate(self, ticker: Any) -> Dict[str, bool]:
        """
        Evalua un ticker contra todas las reglas.
        
        Returns:
            Dict {rule_id: matched}
        """
        if not self.network:
            return {}
        
        self.total_evaluations += 1
        matches = evaluate_ticker(ticker, self.network)
        self.total_matches += sum(1 for m in matches.values() if m)
        
        return matches
    
    def evaluate_batch(
        self, 
        tickers: List[Any]
    ) -> Dict[str, List[Any]]:
        """
        Evalua batch de tickers.
        
        Returns:
            Dict {rule_id: [tickers_matched]}
        """
        if not self.network:
            return {}
        
        results: Dict[str, List[Any]] = {}
        
        for ticker in tickers:
            matches = self.evaluate(ticker)
            
            for rule_id, matched in matches.items():
                if matched:
                    if rule_id not in results:
                        results[rule_id] = []
                    results[rule_id].append(ticker)
        
        return results
    
    def get_system_results(
        self, 
        batch_results: Dict[str, List[Any]]
    ) -> Dict[str, List[Any]]:
        """Filtra solo resultados de categorias del sistema."""
        return {
            k: v for k, v in batch_results.items() 
            if k.startswith("category:")
        }
    
    def get_user_results(
        self, 
        batch_results: Dict[str, List[Any]],
        user_id: str
    ) -> Dict[str, List[Any]]:
        """Filtra resultados de un usuario especifico."""
        prefix = f"user:{user_id}:"
        return {
            k: v for k, v in batch_results.items() 
            if k.startswith(prefix)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas del manager."""
        network_stats = self.network.get_stats() if self.network else {}
        return {
            "network": network_stats,
            "active_users": len(self.active_users),
            "total_evaluations": self.total_evaluations,
            "total_matches": self.total_matches,
            "last_compile": self.last_compile.isoformat() if self.last_compile else None,
        }
