# Super Script de Diagnóstico del Sistema de Mantenimiento

## 🎯 ¿Qué hace?

Este script verifica **TODO** el sistema de mantenimiento automático:

✅ **Servicios Docker** (TimescaleDB, Redis, Data Maintenance)
✅ **API del servicio** (health, status)  
✅ **Base de datos TimescaleDB** (OHLC, Volume Slots, Metadata)
✅ **Redis** (cache, estado de mantenimiento)
✅ **Días faltantes** (detecta automáticamente)
✅ **Archivos de logs** (verifica accesibilidad)

## 🚀 Uso

### Diagnóstico básico:
```bash
cd /opt/tradeul
python3 scripts/check_maintenance_status.py
```

### Output en JSON:
```bash
python3 scripts/check_maintenance_status.py --json > diagnostico.json
```

### Auto-reparar días faltantes:
```bash
python3 scripts/check_maintenance_status.py --fix
```

## 📊 Ejemplo de Output

```
================================================================================
                 SUPER DIAGNÓSTICO DEL SISTEMA DE MANTENIMIENTO                 
================================================================================

▶ Verificando Servicios Docker
--------------------------------------------------------------------------------
✓ Timescale Up 47 hours (healthy)
✓ Redis Up 47 hours (healthy)
✓ Data_maintenance Up 20 minutes

▶ Verificando API de Mantenimiento
--------------------------------------------------------------------------------
✓ API de Mantenimiento Disponible
  Last Maintenance: 2025-11-21
  Scheduler Running: True
  All Tasks Success: True
  Duration: 283.2s

▶ Verificando Datos en TimescaleDB
--------------------------------------------------------------------------------
✓ OHLC Data (market_data_daily) 6 días encontrados
    2025-11-24 (Monday): 11,686 tickers
    2025-11-21 (Friday): 11,591 tickers
    2025-11-20 (Thursday): 11,673 tickers
    ...
    
✓ Volume Slots 6 días encontrados
    2025-11-24 (Monday): 11,313 tickers
    2025-11-21 (Friday): 11,295 tickers
    ...

✓ Ticker Metadata 12,381 tickers totales
    Con Market Cap: 5,917 (47.8%)
    Última actualización: 2025-11-25 09:19:36

▶ Verificando Datos en Redis
--------------------------------------------------------------------------------
✓ Redis Keys 42,290 claves totales
✓ Maintenance Status Keys 6 encontradas
    2025-11-21: ✓ Completado exitosamente
    2025-11-20: ✓ Completado exitosamente
✓ Metadata Cache 12,370 tickers en cache
✓ RVOL Cache 5,458 tickers con datos

▶ Detectando Días Faltantes
--------------------------------------------------------------------------------
⚠ Día faltante detectado 2025-11-14 (Friday)
⚠ Día faltante detectado 2025-11-13 (Thursday)
✗ Días faltantes 4 detectados

▶ Verificando Archivos de Logs
--------------------------------------------------------------------------------
✓ Directorio de logs Encontrado
    maintenance.log: 4.3M
    maintenance_errors.log: 11K
✓ Logs accesibles Últimas 10 líneas leídas correctamente

================================================================================
                                 RESUMEN FINAL                                  
================================================================================

✗ PROBLEMAS ENCONTRADOS:
  • 4 días de trading faltantes

💡 Tip: Usa --fix para auto-reparar días faltantes
```

## 🔧 Códigos de Salida

- **0**: Todo está perfecto ✅
- **1**: Hay problemas detectados ⚠️

## 💡 Tips

### Integración con CI/CD
```bash
# En un script de monitoreo
if ! python3 scripts/check_maintenance_status.py --json > /tmp/status.json; then
    # Enviar alerta
    echo "Sistema de mantenimiento tiene problemas!"
    cat /tmp/status.json
fi
```

### Cronjob para monitoreo diario
```bash
# Agregar a crontab
0 18 * * * cd /opt/tradeul && python3 scripts/check_maintenance_status.py >> /var/log/maintenance_check.log 2>&1
```

### Auto-reparación nocturna
```bash
# Ejecutar a las 2 AM todos los días
0 2 * * * cd /opt/tradeul && python3 scripts/check_maintenance_status.py --fix >> /var/log/maintenance_autofix.log 2>&1
```

## 🎨 Colores en el Output

- 🟢 **Verde**: Todo correcto
- 🔴 **Rojo**: Errores críticos
- 🟡 **Amarillo**: Advertencias
- 🔵 **Azul**: Información

## 🔍 Qué verifica cada sección

### 1. Servicios Docker
- Verifica que los contenedores estén corriendo
- Verifica el estado de salud (healthy)
- Muestra el uptime

### 2. API de Mantenimiento
- Hace health check al endpoint `/health`
- Obtiene estado del último mantenimiento desde `/status`
- Verifica que el scheduler esté activo

### 3. Datos en TimescaleDB
- **OHLC**: Últimos 10 días de market_data_daily
- **Volume Slots**: Últimos 10 días de volume_slots
- **Metadata**: Count total y % con market cap

### 4. Datos en Redis
- Total de claves
- Claves de estado de mantenimiento (maintenance:status:*)
- Cache de metadata (metadata:ticker:*)
- Cache de RVOL (rvol:hist:avg:*)

### 5. Días Faltantes
- Compara últimos 10 días de trading
- Detecta días de semana sin datos
- Excluye automáticamente fines de semana

### 6. Archivos de Logs
- Verifica existencia de /var/log/tradeul/
- Muestra tamaño de archivos
- Verifica que sean accesibles

## 🐛 Troubleshooting

### Error: "docker: command not found"
```bash
# Instalar Docker si no está disponible
curl -fsSL https://get.docker.com | sh
```

### Error: "ModuleNotFoundError"
```bash
# El script usa solo librerías estándar de Python
# Asegúrate de usar Python 3.7+
python3 --version
```

### Error: "Permission denied"
```bash
# Hacer el script ejecutable
chmod +x scripts/check_maintenance_status.py

# O ejecutar con python3
python3 scripts/check_maintenance_status.py
```

## 📝 Changelog

### v1.0.0 (2025-11-25)
- ✨ Implementación inicial
- ✅ Verificación de servicios Docker
- ✅ Verificación de API
- ✅ Verificación de datos en TimescaleDB y Redis
- ✅ Detección de días faltantes
- ✅ Verificación de logs
- ✅ Modo --fix para auto-reparación
- ✅ Output en JSON con --json

