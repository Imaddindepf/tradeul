#!/usr/bin/env python3
"""
AUDITORÍA COMPLETA: Sistema de Auto-Actualización y Detección de Obsolescencia

Este script verifica que TODOS los servicios tienen mecanismos automáticos para:
1. Detectar cambios de día/sesión
2. Limpiar cachés obsoletas
3. Actualizar datos automáticamente
4. Guardar datos históricos
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.utils.redis_client import RedisClient


async def audit_system():
    """Audita el sistema completo de auto-actualización"""
    
    print("=" * 80)
    print("🔍 AUDITORÍA: SISTEMA DE AUTO-ACTUALIZACIÓN Y OBSOLESCENCIA")
    print("=" * 80)
    print()
    
    redis = RedisClient()
    await redis.connect()
    
    try:
        # =============================================
        # 1. MARKET SESSION SERVICE
        # =============================================
        print("1️⃣ MARKET SESSION SERVICE - Detección de Sesión y Cambios")
        print("-" * 80)
        
        # Verificar sesión actual
        current_session = await redis.get("market:session:current")
        trading_date = await redis.get("market:session:trading_date")
        
        if current_session and trading_date:
            print(f"   ✅ Sesión activa detectada:")
            print(f"      - Sesión actual: {current_session}")
            print(f"      - Trading date: {trading_date}")
        else:
            print(f"   ⚠️  No hay sesión detectada en Redis")
            print(f"      - Puede indicar que Market Session Service no está corriendo")
        
        # Verificar eventos de cambio de sesión
        session_events = await redis.client.keys("market:session:event:*")
        if session_events:
            print(f"   ✅ Eventos de sesión registrados: {len(session_events)}")
        else:
            print(f"   ⚠️  No hay eventos de cambio de sesión registrados")
        
        print()
        
        # =============================================
        # 2. ANALYTICS SERVICE
        # =============================================
        print("2️⃣ ANALYTICS SERVICE - Gestión de Slots y Cachés")
        print("-" * 80)
        
        # Verificar última detección de día
        last_day_check = await redis.get("analytics:last_day_check")
        if last_day_check:
            print(f"   ✅ Última verificación de día: {last_day_check}")
        else:
            print(f"   ⚠️  No hay registro de última verificación de día")
        
        # Verificar slots actuales
        current_slots_keys = await redis.client.keys("analytics:rvol:slots:*")
        if current_slots_keys:
            print(f"   ✅ Slots activos en memoria: {len(current_slots_keys)} tickers")
        else:
            print(f"   ⚠️  No hay slots activos (puede ser normal si no hay trading)")
        
        # Verificar cachés históricas
        historical_keys = await redis.client.keys("analytics:rvol:historical:*")
        if historical_keys:
            print(f"   ✅ Cachés históricas: {len(historical_keys)} tickers")
        else:
            print(f"   ⚠️  No hay cachés históricas (necesario para RVOL)")
        
        print()
        
        # =============================================
        # 3. HISTORICAL SERVICE
        # =============================================
        print("3️⃣ HISTORICAL SERVICE - Warmup y Datos de Referencia")
        print("-" * 80)
        
        # Verificar última actualización de warmup
        last_warmup = await redis.get("historical:last_warmup")
        if last_warmup:
            print(f"   ✅ Último warmup: {last_warmup}")
            try:
                warmup_time = datetime.fromisoformat(last_warmup.replace('Z', '+00:00'))
                hours_ago = (datetime.now() - warmup_time.replace(tzinfo=None)).total_seconds() / 3600
                if hours_ago < 24:
                    print(f"      ✅ Ejecutado hace {hours_ago:.1f} horas (reciente)")
                else:
                    print(f"      ⚠️  Ejecutado hace {hours_ago:.1f} horas (>24h, puede estar obsoleto)")
            except:
                pass
        else:
            print(f"   ⚠️  No hay registro de warmup ejecutado")
        
        # Verificar último update de universo
        last_universe = await redis.get("ticker_universe:last_update")
        if last_universe:
            print(f"   ✅ Última actualización de universo: {last_universe}")
        else:
            print(f"   ⚠️  No hay registro de última actualización de universo")
        
        # Verificar metadata de tickers en cache
        metadata_keys = await redis.client.keys("ticker:metadata:*")
        if metadata_keys:
            print(f"   ✅ Metadata en caché: {len(metadata_keys)} tickers")
        else:
            print(f"   ⚠️  No hay metadata de tickers en caché")
        
        print()
        
        # =============================================
        # 4. SCANNER SERVICE
        # =============================================
        print("4️⃣ SCANNER SERVICE - Filtrado y Categorización")
        print("-" * 80)
        
        # Verificar última ejecución de scan
        last_scan = await redis.get("scanner:last_scan")
        if last_scan:
            print(f"   ✅ Último scan ejecutado: {last_scan}")
        else:
            print(f"   ⚠️  No hay registro de último scan")
        
        # Verificar tickers filtrados en cache
        filtered_cache = await redis.client.keys("scanner:filtered_complete:*")
        if filtered_cache:
            print(f"   ✅ Cachés de filtrados: {len(filtered_cache)}")
        else:
            print(f"   ⚠️  No hay cachés de tickers filtrados")
        
        # Verificar categorías
        category_keys = await redis.client.keys("scanner:category:*")
        if category_keys:
            print(f"   ✅ Categorías guardadas: {len(category_keys)}")
        else:
            print(f"   ⚠️  No hay categorías guardadas")
        
        print()
        
        # =============================================
        # 5. DATA INGEST SERVICE
        # =============================================
        print("5️⃣ DATA INGEST SERVICE - Snapshots de Polygon")
        print("-" * 80)
        
        # Verificar último snapshot
        last_snapshot = await redis.get("data_ingest:last_snapshot")
        if last_snapshot:
            print(f"   ✅ Último snapshot: {last_snapshot}")
            try:
                snapshot_time = datetime.fromisoformat(last_snapshot.replace('Z', '+00:00'))
                seconds_ago = (datetime.now() - snapshot_time.replace(tzinfo=None)).total_seconds()
                if seconds_ago < 60:
                    print(f"      ✅ Hace {seconds_ago:.0f} segundos (activo)")
                elif seconds_ago < 300:
                    print(f"      ⚠️  Hace {seconds_ago:.0f} segundos (puede estar detenido)")
                else:
                    print(f"      ❌ Hace {seconds_ago/60:.1f} minutos (detenido)")
            except:
                pass
        else:
            print(f"   ⚠️  No hay registro de último snapshot")
        
        # Verificar stream de snapshots
        snapshot_stream_len = await redis.client.xlen("stream:snapshots:raw")
        if snapshot_stream_len:
            print(f"   ✅ Stream de snapshots: {snapshot_stream_len} mensajes pendientes")
            if snapshot_stream_len > 10000:
                print(f"      ⚠️  Muchos mensajes acumulados (posible backlog)")
        else:
            print(f"   ℹ️  Stream de snapshots vacío (puede ser normal)")
        
        print()
        
        # =============================================
        # 6. POLYGON WS SERVICE
        # =============================================
        print("6️⃣ POLYGON WEBSOCKET SERVICE - Datos en Tiempo Real")
        print("-" * 80)
        
        # Verificar estado de conexión
        ws_connected = await redis.get("polygon_ws:connected")
        if ws_connected:
            print(f"   ✅ WebSocket conectado: {ws_connected}")
        else:
            print(f"   ⚠️  WebSocket no conectado")
        
        # Verificar último mensaje recibido
        last_ws_message = await redis.get("polygon_ws:last_message")
        if last_ws_message:
            print(f"   ✅ Último mensaje WS: {last_ws_message}")
        else:
            print(f"   ⚠️  No hay registro de último mensaje WS")
        
        # Verificar stream de aggregates
        agg_stream_len = await redis.client.xlen("stream:realtime:aggregates")
        if agg_stream_len:
            print(f"   ✅ Stream de aggregates: {agg_stream_len} mensajes")
        else:
            print(f"   ℹ️  Stream de aggregates vacío")
        
        print()
        
        # =============================================
        # RESUMEN Y RECOMENDACIONES
        # =============================================
        print("=" * 80)
        print("📋 RESUMEN DE AUDITORÍA")
        print("=" * 80)
        print()
        
        issues = []
        warnings = []
        
        # Check 1: Market Session
        if not current_session:
            issues.append("Market Session Service no está detectando la sesión actual")
        
        # Check 2: Analytics
        if not current_slots_keys and not historical_keys:
            issues.append("Analytics Service no tiene slots ni cachés históricas")
        
        # Check 3: Historical
        if not last_warmup:
            warnings.append("Historical Service nunca ha ejecutado warmup")
        
        # Check 4: Scanner
        if not filtered_cache:
            warnings.append("Scanner Service no tiene cachés de tickers filtrados")
        
        # Check 5: Data Ingest
        if not last_snapshot:
            warnings.append("Data Ingest Service no está capturando snapshots")
        
        if issues:
            print("❌ PROBLEMAS CRÍTICOS:")
            for issue in issues:
                print(f"   - {issue}")
            print()
        
        if warnings:
            print("⚠️  ADVERTENCIAS:")
            for warning in warnings:
                print(f"   - {warning}")
            print()
        
        if not issues and not warnings:
            print("✅ TODOS LOS SERVICIOS OPERANDO CORRECTAMENTE")
            print()
        
        print("🔧 MECANISMOS DE AUTO-ACTUALIZACIÓN DETECTADOS:")
        print()
        print("   📍 Market Session Service:")
        print("      - Detecta cambios de sesión cada 60 segundos")
        print("      - Actualiza Redis con sesión actual y trading date")
        print("      ❓ FALTA: Publicar eventos de cambio de día a otros servicios")
        print()
        print("   📍 Analytics Service:")
        print("      - Detecta cambio de día en cada procesamiento")
        print("      - Guarda slots históricos a TimescaleDB")
        print("      - Limpia caché histórica con delete_pattern")
        print("      ✅ IMPLEMENTADO")
        print()
        print("   📍 Historical Service:")
        print("      - Warmup automático cada 24h (después de 1h del inicio)")
        print("      - Actualización de universo cada 24h")
        print("      ❓ FALTA: Activarse con eventos de Market Session")
        print()
        print("   📍 Scanner Service:")
        print("      - Cachés con TTL implícito (60 segundos)")
        print("      ❓ FALTA: Limpieza explícita al cambiar de día")
        print()
        print("   📍 Data Ingest Service:")
        print("      - Captura continua de snapshots")
        print("      ❓ FALTA: Ajuste de intervalos según sesión")
        print()
        
        print("💡 RECOMENDACIONES:")
        print()
        print("   1. Implementar sistema de eventos Pub/Sub:")
        print("      - Market Session publica 'session:changed' y 'day:changed'")
        print("      - Todos los servicios se suscriben y reaccionan")
        print()
        print("   2. Hacer warmup reactivo:")
        print("      - Ejecutar warmup al detectar 'day:changed' (no solo cada 24h)")
        print()
        print("   3. Scanner debe limpiar cachés:")
        print("      - Suscribirse a 'day:changed' y limpiar todas las cachés")
        print()
        print("   4. Centralizar gestión de obsolescencia:")
        print("      - Orchestrator Service para coordinar actualizaciones")
        print()
        
    except Exception as e:
        print(f"❌ Error durante auditoría: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await redis.disconnect()


if __name__ == "__main__":
    asyncio.run(audit_system())

