#!/usr/bin/env bash
#
# Tradeul health watchdog
# ========================
# Vigila la salud del host y de los contenedores. Disenado para correr
# cada minuto via systemd timer (tradeul-watchdog.timer).
#
# Que hace:
#   1. Detecta cualquier contenedor tradeul_* que NO este corriendo y lo
#      relanza (red de seguridad ademas del restart policy de Docker).
#   2. Detecta OOM-kills recientes del kernel y los registra.
#   3. Registra uso de memoria y swap del host.
#   4. Si MEM o SWAP superan umbrales, lo marca como WARN.
#   5. Si WATCHDOG_WEBHOOK esta definido, envia una alerta (Slack/Discord/etc).
#
# Todo se escribe en /opt/tradeul/logs/watchdog.log
set -uo pipefail

LOG_DIR="/opt/tradeul/logs"
LOG_FILE="${LOG_DIR}/watchdog.log"
STATE_DIR="/opt/tradeul/logs/.watchdog_state"
MEM_WARN_PCT=88        # alerta si la RAM usada supera este %
SWAP_WARN_PCT=80       # alerta si el swap usado supera este %
WEBHOOK="${WATCHDOG_WEBHOOK:-}"

mkdir -p "$LOG_DIR" "$STATE_DIR"

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "$(ts) $*" >>"$LOG_FILE"; }

alert() {
  # $1 = nivel (WARN/CRIT), $2 = mensaje. Deduplica por clave para no spamear.
  local level="$1"; local msg="$2"; local key="${3:-$msg}"
  log "${level}: ${msg}"
  if [ -n "$WEBHOOK" ]; then
    local statef="${STATE_DIR}/$(echo "$key" | tr -c 'a-zA-Z0-9' '_')"
    # Dedup: no reenviar la misma alerta en menos de 30 min.
    if [ -f "$statef" ] && [ $(( $(date +%s) - $(stat -c %Y "$statef") )) -lt 1800 ]; then
      return
    fi
    touch "$statef"
    curl -fsS -m 10 -H 'Content-Type: application/json' \
      -d "{\"text\":\"[tradeul-watchdog] ${level}: ${msg}\"}" \
      "$WEBHOOK" >/dev/null 2>&1 || log "WARN: webhook send failed"
  fi
}

# ── 1. Contenedores caidos ────────────────────────────────────────────
mapfile -t down < <(docker ps -a --filter 'name=tradeul_' --format '{{.Names}}\t{{.State}}' \
                    | awk -F'\t' '$2!="running"{print $1}')
for c in "${down[@]:-}"; do
  [ -z "$c" ] && continue
  alert "CRIT" "container ${c} is DOWN — attempting restart" "down_${c}"
  if docker start "$c" >/dev/null 2>&1; then
    log "INFO: restarted ${c}"
  else
    alert "CRIT" "FAILED to restart ${c}" "restartfail_${c}"
  fi
done

# ── 2. OOM-kills recientes (ultimos 90s) ──────────────────────────────
if command -v dmesg >/dev/null 2>&1; then
  oom=$(dmesg -T 2>/dev/null | grep -i 'Killed process' | tail -5)
  if [ -n "$oom" ]; then
    last_oom_hash=$(echo "$oom" | md5sum | awk '{print $1}')
    seen_file="${STATE_DIR}/last_oom_hash"
    if [ ! -f "$seen_file" ] || [ "$(cat "$seen_file")" != "$last_oom_hash" ]; then
      echo "$last_oom_hash" >"$seen_file"
      alert "WARN" "kernel OOM-kill detected: $(echo "$oom" | tail -1)" "oom"
    fi
  fi
fi

# ── 3 & 4. Memoria / swap del host ────────────────────────────────────
read -r mem_total mem_used <<<"$(free -m | awk '/^Mem:/{print $2, $3}')"
read -r swap_total swap_used <<<"$(free -m | awk '/^Swap:/{print $2, $3}')"
mem_pct=$(( mem_used * 100 / mem_total ))
swap_pct=0; [ "$swap_total" -gt 0 ] && swap_pct=$(( swap_used * 100 / swap_total ))
log "INFO: mem=${mem_used}/${mem_total}MB (${mem_pct}%) swap=${swap_used}/${swap_total}MB (${swap_pct}%)"

[ "$mem_pct" -ge "$MEM_WARN_PCT" ]   && alert "WARN" "host memory at ${mem_pct}%"  "mem_high"
[ "$swap_pct" -ge "$SWAP_WARN_PCT" ] && alert "WARN" "host swap at ${swap_pct}%"   "swap_high"

# ── 5. Backups a R2 ───────────────────────────────────────────────────
# El backup escribe /var/log/tradeul-backup-status (OK/FAILED + fecha).
# Alerta si fallo o si lleva >26h sin completarse (estuvo 28 dias roto en
# silencio en may-jun 2026).
BACKUP_STATUS="/var/log/tradeul-backup-status"
if [ -f "$BACKUP_STATUS" ]; then
  if grep -q '^FAILED' "$BACKUP_STATUS"; then
    alert "CRIT" "backup a R2 FALLIDO: $(cat "$BACKUP_STATUS")" "backup_failed"
  elif [ $(( $(date +%s) - $(stat -c %Y "$BACKUP_STATUS") )) -gt 93600 ]; then
    alert "CRIT" "backup a R2 no se ejecuta desde hace >26h" "backup_stale"
  fi
else
  alert "WARN" "sin fichero de estado de backup (${BACKUP_STATUS})" "backup_nostatus"
fi

exit 0
