#!/usr/bin/env bash
set -euo pipefail

# Home Assistant helper for local dev:
# - stop: stop running HA instances
# - health: run local health checks
# - stop-and-health: stop instances, then run health checks

PORT="${HA_PORT:-8123}"
CORE_DIR="${HA_CORE_DIR:-/workspaces/core}"
CONFIG_DIR="${HA_CONFIG_DIR:-$CORE_DIR/config}"
LOG_FILE="$CONFIG_DIR/home-assistant.log"

log() {
  printf "[%s] %s\n" "$(date +"%H:%M:%S")" "$*"
}

find_ha_pids() {
  # Match plain HA start and debugpy launcher starts.
  pgrep -f "(python|python3).*(-m[[:space:]]+homeassistant|debugpy/.*/launcher.*-m[[:space:]]+homeassistant)" || true
}

find_go2rtc_pids() {
  # go2rtc can be left behind and block HA startup (port bind conflicts).
  pgrep -f "(^|/)go2rtc([[:space:]]|$)" || true
}

stop_instances() {
  mapfile -t pids < <(find_ha_pids)
  mapfile -t go2rtc_pids < <(find_go2rtc_pids)

  if [[ "${#pids[@]}" -eq 0 && "${#go2rtc_pids[@]}" -eq 0 ]]; then
    log "Keine laufenden Home-Assistant- oder go2rtc-Instanzen gefunden."
    return 0
  fi

  if [[ "${#pids[@]}" -gt 0 ]]; then
    log "Stoppe laufende Home-Assistant-Instanzen: ${pids[*]}"
    kill -TERM "${pids[@]}" || true
  fi

  if [[ "${#go2rtc_pids[@]}" -gt 0 ]]; then
    log "Stoppe laufende go2rtc-Prozesse: ${go2rtc_pids[*]}"
    kill -TERM "${go2rtc_pids[@]}" || true
  fi

  for _ in {1..20}; do
    mapfile -t pids < <(find_ha_pids)
    mapfile -t go2rtc_pids < <(find_go2rtc_pids)
    if [[ "${#pids[@]}" -eq 0 && "${#go2rtc_pids[@]}" -eq 0 ]]; then
      log "Alle Instanzen sauber beendet."
      return 0
    fi
    sleep 0.5
  done

  if [[ "${#pids[@]}" -gt 0 ]]; then
    log "Einige Home-Assistant-Instanzen laufen noch, erzwinge Stop: ${pids[*]}"
    kill -KILL "${pids[@]}" || true
  fi
  if [[ "${#go2rtc_pids[@]}" -gt 0 ]]; then
    log "Einige go2rtc-Prozesse laufen noch, erzwinge Stop: ${go2rtc_pids[*]}"
    kill -KILL "${go2rtc_pids[@]}" || true
  fi
  sleep 0.2

  mapfile -t pids < <(find_ha_pids)
  mapfile -t go2rtc_pids < <(find_go2rtc_pids)
  if [[ "${#pids[@]}" -eq 0 && "${#go2rtc_pids[@]}" -eq 0 ]]; then
    log "Alle Instanzen beendet (SIGKILL)."
    return 0
  fi

  log "WARNUNG: Diese Home-Assistant-PIDs laufen weiterhin: ${pids[*]:-none}"
  log "WARNUNG: Diese go2rtc-PIDs laufen weiterhin: ${go2rtc_pids[*]:-none}"
  return 1
}

healthcheck() {
  local rc=0

  log "Healthcheck startet (core=$CORE_DIR, config=$CONFIG_DIR, port=$PORT)"

  mapfile -t pids < <(find_ha_pids)
  if [[ "${#pids[@]}" -gt 0 ]]; then
    log "OK: HA-Prozess(e) gefunden: ${pids[*]}"
  else
    log "WARN: Kein HA-Prozess gefunden."
    rc=1
  fi

  if ss -ltn 2>/dev/null | grep -qE ":[0-9]*${PORT}[[:space:]]"; then
    log "OK: Port ${PORT} lauscht."
  else
    log "WARN: Port ${PORT} lauscht nicht."
    rc=1
  fi

  local http_code
  http_code="$(curl -sS -m 5 -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/manifest.json" || true)"
  if [[ "$http_code" != "000" ]]; then
    log "OK: HTTP antwortet auf 127.0.0.1:${PORT} (status=${http_code})."
  else
    log "WARN: Kein HTTP-Response von 127.0.0.1:${PORT}."
    rc=1
  fi

  if [[ -f "$LOG_FILE" ]]; then
    log "Log-Datei gefunden: $LOG_FILE"
    if command -v rg >/dev/null 2>&1; then
      local err_count
      err_count="$(rg -n "ERROR|CRITICAL|Traceback|Exception" "$LOG_FILE" | tail -n 20 | wc -l | tr -d ' ')"
      if [[ "$err_count" != "0" ]]; then
        log "Hinweis: letzte Fehlerzeilen im Log (max 20):"
        rg -n "ERROR|CRITICAL|Traceback|Exception" "$LOG_FILE" | tail -n 20 || true
      else
        log "OK: Keine aktuellen Fehler/Tracebacks in den letzten Treffern gefunden."
      fi
    else
      log "Hinweis: 'rg' nicht verfügbar, überspringe detaillierte Fehlersuche im Log."
    fi

    log "Letzte 10 Log-Zeilen:"
    tail -n 10 "$LOG_FILE" || true
  else
    log "WARN: Log-Datei nicht gefunden unter $LOG_FILE"
    rc=1
  fi

  return "$rc"
}

usage() {
  cat <<'EOF'
Usage:
  ha_doctor.sh stop             # laufende HA-Instanzen beenden
  ha_doctor.sh health           # Healthcheck ausführen
  ha_doctor.sh stop-and-health  # stop + healthcheck

Optional env vars:
  HA_CORE_DIR   (default: /workspaces/core)
  HA_CONFIG_DIR (default: $HA_CORE_DIR/config)
  HA_PORT       (default: 8123)
EOF
}

main() {
  local cmd="${1:-stop-and-health}"

  case "$cmd" in
    stop)
      stop_instances
      ;;
    health)
      healthcheck
      ;;
    stop-and-health)
      stop_instances
      healthcheck
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Unbekannter Befehl: $cmd" >&2
      usage
      return 2
      ;;
  esac
}

main "$@"
