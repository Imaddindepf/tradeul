#!/usr/bin/env python3
"""
Super Script de Diagnóstico del Sistema de Mantenimiento
=========================================================

Verifica:
- Estado de servicios (Docker containers)
- Base de datos TimescaleDB (OHLC, volume slots, metadata)
- Redis (cache, estado de mantenimiento)
- Logs del servicio
- Días faltantes
- Salud general del sistema

Uso:
    python3 check_maintenance_status.py
    python3 check_maintenance_status.py --json  # Output en JSON
    python3 check_maintenance_status.py --fix   # Auto-fix días faltantes
"""

import asyncio
import sys
import os
import json
import subprocess
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import argparse
from collections import defaultdict

# Global flag para modo silencioso (JSON mode)
SILENT_MODE = False

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_header(text: str):
    """Print header bonito"""
    if SILENT_MODE:
        return
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}\n")

def print_section(text: str):
    """Print sección"""
    if SILENT_MODE:
        return
    print(f"\n{Colors.BOLD}{Colors.BLUE}▶ {text}{Colors.END}")
    print(f"{Colors.BLUE}{'-'*80}{Colors.END}")

def print_success(text: str, details: str = ""):
    """Print éxito"""
    if SILENT_MODE:
        return
    print(f"{Colors.GREEN}✓{Colors.END} {text}", end="")
    if details:
        print(f" {Colors.WHITE}{details}{Colors.END}")
    else:
        print()

def print_error(text: str, details: str = ""):
    """Print error"""
    if SILENT_MODE:
        return
    print(f"{Colors.RED}✗{Colors.END} {text}", end="")
    if details:
        print(f" {Colors.RED}{details}{Colors.END}")
    else:
        print()

def print_warning(text: str, details: str = ""):
    """Print warning"""
    if SILENT_MODE:
        return
    print(f"{Colors.YELLOW}⚠{Colors.END} {text}", end="")
    if details:
        print(f" {Colors.YELLOW}{details}{Colors.END}")
    else:
        print()

def print_info(text: str, value: str = ""):
    """Print info"""
    if SILENT_MODE:
        return
    print(f"  {Colors.WHITE}{text}:{Colors.END}", end="")
    if value:
        print(f" {Colors.CYAN}{value}{Colors.END}")
    else:
        print()

def run_command(cmd: List[str], capture_output=True) -> Tuple[int, str, str]:
    """Ejecutar comando y retornar código, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def run_docker_cmd(container: str, cmd: List[str]) -> Tuple[int, str, str]:
    """Ejecutar comando dentro de un contenedor Docker"""
    full_cmd = ["docker", "exec", "-i", container] + cmd
    return run_command(full_cmd)

def check_docker_services() -> Dict:
    """Verificar estado de servicios Docker"""
    print_section("Verificando Servicios Docker")
    
    services = {
        'timescale': 'tradeul_timescale',
        'redis': 'tradeul_redis',
        'data_maintenance': 'tradeul_data_maintenance'
    }
    
    results = {}
    
    for service_name, container_name in services.items():
        code, stdout, stderr = run_command(['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Status}}'])
        
        if code == 0 and stdout.strip():
            status = stdout.strip()
            is_healthy = 'healthy' in status.lower() or 'up' in status.lower()
            results[service_name] = {
                'running': True,
                'healthy': is_healthy,
                'status': status
            }
            
            if is_healthy:
                print_success(f"{service_name.capitalize()}", status)
            else:
                print_warning(f"{service_name.capitalize()}", status)
        else:
            results[service_name] = {
                'running': False,
                'healthy': False,
                'status': 'Not running'
            }
            print_error(f"{service_name.capitalize()}", "Not running")
    
    return results

def check_maintenance_api() -> Dict:
    """Verificar API del servicio de mantenimiento"""
    print_section("Verificando API de Mantenimiento")
    
    results = {}
    
    try:
        # Health check usando curl
        code, stdout, stderr = run_command(['curl', '-s', 'http://localhost:8008/health'])
        
        if code == 0 and stdout.strip():
            try:
                data = json.loads(stdout.strip())
                results['api'] = {
                    'available': True,
                    'data': data
                }
                
                print_success("API de Mantenimiento", "Disponible")
                print_info("  Last Maintenance", data.get('last_maintenance', 'N/A'))
                print_info("  Scheduler Running", str(data.get('scheduler_running', False)))
                
                # Status endpoint
                code2, stdout2, _ = run_command(['curl', '-s', 'http://localhost:8008/status'])
                if code2 == 0 and stdout2.strip():
                    try:
                        status_data = json.loads(stdout2.strip())
                        results['last_run'] = status_data
                        
                        if status_data.get('status') == 'ok':
                            details = status_data.get('details', {})
                            print_info("  All Tasks Success", str(details.get('all_success', False)))
                            print_info("  Duration", f"{details.get('duration_seconds', 0):.1f}s")
                    except json.JSONDecodeError:
                        pass
            except json.JSONDecodeError as e:
                results['api'] = {'available': False, 'error': 'Invalid JSON response'}
                print_error("API de Mantenimiento", "Respuesta inválida")
        else:
            results['api'] = {'available': False}
            print_error("API de Mantenimiento", "No disponible")
    
    except Exception as e:
        results['api'] = {'available': False, 'error': str(e)}
        print_error("API de Mantenimiento", str(e))
    
    return results

def check_timescale_data() -> Dict:
    """Verificar datos en TimescaleDB"""
    print_section("Verificando Datos en TimescaleDB")
    
    results = {}
    
    # OHLC Data (market_data_daily)
    code, stdout, stderr = run_docker_cmd(
        'tradeul_timescale',
        ['psql', '-U', 'tradeul_user', '-d', 'tradeul', '-t', '-c',
         "SELECT trading_date, COUNT(*) FROM market_data_daily WHERE trading_date >= CURRENT_DATE - INTERVAL '10 days' GROUP BY trading_date ORDER BY trading_date DESC;"]
    )
    
    if code == 0 and stdout.strip():
        ohlc_data = []
        for line in stdout.strip().split('\n'):
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) == 2 and parts[0]:
                    ohlc_data.append({'date': parts[0], 'count': int(parts[1])})
        
        results['ohlc'] = ohlc_data
        
        print_success(f"OHLC Data (market_data_daily)", f"{len(ohlc_data)} días encontrados")
        for item in ohlc_data[:5]:
            date_obj = datetime.strptime(item['date'], '%Y-%m-%d').date()
            day_name = date_obj.strftime('%A')
            print_info(f"    {item['date']} ({day_name})", f"{item['count']:,} tickers")
    else:
        results['ohlc'] = []
        print_error("OHLC Data", stderr or "No data found")
    
    # Volume Slots
    code, stdout, stderr = run_docker_cmd(
        'tradeul_timescale',
        ['psql', '-U', 'tradeul_user', '-d', 'tradeul', '-t', '-c',
         "SELECT date, COUNT(DISTINCT symbol) FROM volume_slots WHERE date >= CURRENT_DATE - INTERVAL '10 days' GROUP BY date ORDER BY date DESC;"]
    )
    
    if code == 0 and stdout.strip():
        volume_data = []
        for line in stdout.strip().split('\n'):
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) == 2 and parts[0]:
                    volume_data.append({'date': parts[0], 'count': int(parts[1])})
        
        results['volume_slots'] = volume_data
        
        print_success(f"Volume Slots", f"{len(volume_data)} días encontrados")
        for item in volume_data[:5]:
            date_obj = datetime.strptime(item['date'], '%Y-%m-%d').date()
            day_name = date_obj.strftime('%A')
            print_info(f"    {item['date']} ({day_name})", f"{item['count']:,} tickers")
    else:
        results['volume_slots'] = []
        print_error("Volume Slots", stderr or "No data found")
    
    # Ticker Metadata
    code, stdout, stderr = run_docker_cmd(
        'tradeul_timescale',
        ['psql', '-U', 'tradeul_user', '-d', 'tradeul', '-t', '-c',
         "SELECT COUNT(*) as total, COUNT(CASE WHEN market_cap IS NOT NULL THEN 1 END) as with_market_cap, MAX(updated_at) as last_update FROM tickers_unified;"]
    )
    
    if code == 0 and stdout.strip():
        parts = [p.strip() for p in stdout.strip().split('|')]
        if len(parts) >= 3:
            results['metadata'] = {
                'total': int(parts[0]),
                'with_market_cap': int(parts[1]),
                'last_update': parts[2]
            }
            
            print_success("Ticker Metadata", f"{parts[0]} tickers totales")
            print_info("    Con Market Cap", f"{parts[1]} ({int(parts[1])/int(parts[0])*100:.1f}%)")
            print_info("    Última actualización", parts[2])
    else:
        results['metadata'] = {}
        print_error("Ticker Metadata", stderr or "No data found")
    
    return results

def check_redis_data() -> Dict:
    """Verificar datos en Redis"""
    print_section("Verificando Datos en Redis")
    
    results = {}
    
    # Get Redis password
    redis_password = os.getenv('REDIS_PASSWORD', 'tradeul_redis_secure_2024')
    
    # DBSIZE
    code, stdout, stderr = run_docker_cmd(
        'tradeul_redis',
        ['redis-cli', '-a', redis_password, '--no-auth-warning', 'DBSIZE']
    )
    
    if code == 0 and stdout.strip():
        key_count = int(stdout.strip())
        results['total_keys'] = key_count
        print_success("Redis Keys", f"{key_count:,} claves totales")
    else:
        results['total_keys'] = 0
        print_error("Redis Keys", "No se pudo obtener")
    
    # Check maintenance status keys
    code, stdout, stderr = run_docker_cmd(
        'tradeul_redis',
        ['redis-cli', '-a', redis_password, '--no-auth-warning', 'KEYS', 'maintenance:status:*']
    )
    
    if code == 0 and stdout.strip():
        status_keys = [k.strip() for k in stdout.strip().split('\n') if k.strip()]
        results['maintenance_keys'] = status_keys
        
        print_success("Maintenance Status Keys", f"{len(status_keys)} encontradas")
        
        # Get details of each key
        for key in status_keys[-5:]:  # Last 5
            code, data, _ = run_docker_cmd(
                'tradeul_redis',
                ['redis-cli', '-a', redis_password, '--no-auth-warning', 'GET', key]
            )
            
            if code == 0 and data.strip():
                try:
                    status_data = json.loads(data.strip())
                    date_str = status_data.get('date', 'N/A')
                    all_success = status_data.get('all_success', False)
                    
                    if all_success:
                        print_info(f"    {date_str}", "✓ Completado exitosamente")
                    else:
                        print_warning(f"    {date_str}", "✗ Completado con errores")
                except:
                    pass
    else:
        results['maintenance_keys'] = []
        print_warning("Maintenance Status Keys", "No se encontraron")
    
    # Check metadata keys
    code, stdout, stderr = run_docker_cmd(
        'tradeul_redis',
        ['redis-cli', '-a', redis_password, '--no-auth-warning', 'KEYS', 'metadata:ticker:*']
    )
    
    if code == 0 and stdout.strip():
        metadata_keys = len([k for k in stdout.strip().split('\n') if k.strip()])
        results['metadata_keys'] = metadata_keys
        print_success("Metadata Cache", f"{metadata_keys:,} tickers en cache")
    
    # Check RVOL keys
    code, stdout, stderr = run_docker_cmd(
        'tradeul_redis',
        ['redis-cli', '-a', redis_password, '--no-auth-warning', 'KEYS', 'rvol:hist:avg:*']
    )
    
    if code == 0 and stdout.strip():
        rvol_keys = len([k for k in stdout.strip().split('\n') if k.strip()])
        results['rvol_keys'] = rvol_keys
        print_success("RVOL Cache", f"{rvol_keys:,} tickers con datos")
    
    return results

def check_missing_days(ohlc_data: List[Dict]) -> List[date]:
    """Detectar días de trading faltantes"""
    print_section("Detectando Días Faltantes")
    
    if not ohlc_data:
        print_error("No se puede verificar", "No hay datos OHLC")
        return []
    
    # Get dates from data
    existing_dates = set()
    for item in ohlc_data:
        try:
            existing_dates.add(datetime.strptime(item['date'], '%Y-%m-%d').date())
        except:
            pass
    
    # Check last 10 trading days
    today = datetime.now().date()
    missing_dates = []
    
    check_date = today - timedelta(days=1)
    days_checked = 0
    
    while days_checked < 10:
        # Skip weekends
        if check_date.weekday() < 5:  # Monday = 0, Friday = 4
            if check_date not in existing_dates:
                missing_dates.append(check_date)
                print_warning(f"Día faltante detectado", check_date.strftime('%Y-%m-%d (%A)'))
            days_checked += 1
        
        check_date -= timedelta(days=1)
    
    if not missing_dates:
        print_success("No hay días faltantes", "Últimos 10 días de trading completos")
    else:
        print_error(f"Días faltantes", f"{len(missing_dates)} detectados")
    
    return missing_dates

def check_log_files() -> Dict:
    """Verificar archivos de logs"""
    print_section("Verificando Archivos de Logs")
    
    results = {}
    
    code, stdout, stderr = run_docker_cmd(
        'tradeul_data_maintenance',
        ['ls', '-lh', '/var/log/tradeul/']
    )
    
    if code == 0 and stdout.strip():
        print_success("Directorio de logs", "Encontrado")
        
        for line in stdout.strip().split('\n'):
            if 'maintenance' in line:
                parts = line.split()
                if len(parts) >= 9:
                    size = parts[4]
                    filename = parts[8]
                    print_info(f"    {filename}", size)
        
        # Check last 10 lines of maintenance.log
        code, stdout, stderr = run_docker_cmd(
            'tradeul_data_maintenance',
            ['tail', '-10', '/var/log/tradeul/maintenance.log']
        )
        
        if code == 0:
            results['log_accessible'] = True
            print_success("Logs accesibles", "Últimas 10 líneas leídas correctamente")
    else:
        results['log_accessible'] = False
        print_error("Directorio de logs", "No encontrado o inaccesible")
    
    return results

def generate_summary(all_results: Dict) -> str:
    """Generar resumen final"""
    print_header("RESUMEN FINAL")
    
    issues = []
    warnings = []
    
    # Check services
    services = all_results.get('docker_services', {})
    for service, status in services.items():
        if not status.get('running'):
            issues.append(f"Servicio {service} no está corriendo")
        elif not status.get('healthy'):
            warnings.append(f"Servicio {service} no está healthy")
    
    # Check data
    ohlc_data = all_results.get('timescale_data', {}).get('ohlc', [])
    if len(ohlc_data) < 5:
        issues.append(f"Pocos días de OHLC data ({len(ohlc_data)} días)")
    
    volume_data = all_results.get('timescale_data', {}).get('volume_slots', [])
    if len(volume_data) < 5:
        issues.append(f"Pocos días de volume slots ({len(volume_data)} días)")
    
    # Check missing days
    missing_days = all_results.get('missing_days', [])
    if missing_days:
        issues.append(f"{len(missing_days)} días de trading faltantes")
    
    # Print summary
    if not issues and not warnings:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ TODO ESTÁ PERFECTO!{Colors.END}")
        print(f"{Colors.GREEN}El sistema de mantenimiento está funcionando correctamente.{Colors.END}")
        return "healthy"
    else:
        if issues:
            print(f"{Colors.RED}{Colors.BOLD}✗ PROBLEMAS ENCONTRADOS:{Colors.END}")
            for issue in issues:
                print(f"{Colors.RED}  • {issue}{Colors.END}")
        
        if warnings:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ ADVERTENCIAS:{Colors.END}")
            for warning in warnings:
                print(f"{Colors.YELLOW}  • {warning}{Colors.END}")
        
        return "degraded" if not issues else "unhealthy"

def trigger_maintenance_fix(missing_dates: List[date]):
    """Trigger manual maintenance for missing dates"""
    print_section("Ejecutando Auto-Fix")
    
    import time
    
    for missing_date in sorted(missing_dates):
        date_str = missing_date.isoformat()
        print(f"\n{Colors.CYAN}Ejecutando mantenimiento para {date_str}...{Colors.END}")
        
        try:
            # Use curl to POST
            code, stdout, stderr = run_command([
                'curl', '-s', '-X', 'POST',
                'http://localhost:8008/trigger',
                '-H', 'Content-Type: application/json',
                '-d', json.dumps({'target_date': date_str})
            ])
            
            if code == 0 and stdout.strip():
                try:
                    data = json.loads(stdout.strip())
                    print_success(f"Triggered para {date_str}", data.get('message', ''))
                    
                    # Wait a bit before next
                    if missing_date != missing_dates[-1]:
                        print(f"{Colors.WHITE}Esperando 60 segundos antes del siguiente...{Colors.END}")
                        time.sleep(60)
                except json.JSONDecodeError:
                    print_error(f"Failed para {date_str}", "Respuesta inválida")
            else:
                print_error(f"Failed para {date_str}", stderr or "Request failed")
        except Exception as e:
            print_error(f"Error para {date_str}", str(e))

def main():
    """Main function"""
    global SILENT_MODE
    
    parser = argparse.ArgumentParser(description='Super Script de Diagnóstico del Sistema de Mantenimiento')
    parser.add_argument('--json', action='store_true', help='Output en formato JSON')
    parser.add_argument('--fix', action='store_true', help='Auto-fix días faltantes')
    args = parser.parse_args()
    
    SILENT_MODE = args.json
    
    if not args.json:
        print_header("SUPER DIAGNÓSTICO DEL SISTEMA DE MANTENIMIENTO")
        print(f"{Colors.WHITE}Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}\n")
    
    all_results = {}
    
    # 1. Check Docker services
    all_results['docker_services'] = check_docker_services()
    
    # 2. Check Maintenance API
    all_results['maintenance_api'] = check_maintenance_api()
    
    # 3. Check TimescaleDB data
    all_results['timescale_data'] = check_timescale_data()
    
    # 4. Check Redis data
    all_results['redis_data'] = check_redis_data()
    
    # 5. Check missing days
    ohlc_data = all_results['timescale_data'].get('ohlc', [])
    missing_days = check_missing_days(ohlc_data)
    all_results['missing_days'] = [d.isoformat() for d in missing_days]
    
    # 6. Check log files
    all_results['log_files'] = check_log_files()
    
    # Generate summary
    if not args.json:
        health_status = generate_summary(all_results)
        all_results['overall_health'] = health_status
        
        # Auto-fix if requested
        if args.fix and missing_days:
            trigger_maintenance_fix(missing_days)
        elif missing_days and not args.fix:
            print(f"\n{Colors.YELLOW}💡 Tip: Usa --fix para auto-reparar días faltantes{Colors.END}")
    
    # JSON output
    if args.json:
        print(json.dumps(all_results, indent=2, default=str))
    
    return 0 if all_results.get('overall_health') == 'healthy' else 1

if __name__ == '__main__':
    sys.exit(main())

