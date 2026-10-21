# shellcheck shell=bash
# A progress bar for a silent wait in a shell script, drawn on a terminal only. The bash
# twin of scripts/wait_progress.py: it fills toward the wait's usual duration, never
# reaches the end before the wait does, and says it is still working when the wait runs
# long. Off a terminal (a log, a pipe, a capture) it draws nothing.
#
#   started="$(date +%s)"
#   while waiting; do pellier_progress_draw "Waiting for Pellier" 15 "$started"; sleep 1; done
#   pellier_progress_clear
#
# bash 3.2 syntax only.

PELLIER_PROGRESS_WIDTH=20

pellier_progress_clock() {
  printf '%d:%02d' $(( $1 / 60 )) $(( $1 % 60 ))
}

# The line for a wait: label, typical seconds, elapsed seconds.
pellier_progress_line() {
  local label="$1" typical="$2" elapsed="$3" filled=0 bar="" i=0 full="#" empty="-" state
  case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *UTF-8* | *utf8* | *UTF8* | *utf-8*) full="█"; empty="░" ;;
  esac
  if [ "$typical" -gt 0 ]; then
    filled=$(( elapsed * (PELLIER_PROGRESS_WIDTH - 1) / typical ))
  fi
  [ "$filled" -gt $(( PELLIER_PROGRESS_WIDTH - 1 )) ] && filled=$(( PELLIER_PROGRESS_WIDTH - 1 ))
  while [ "$i" -lt "$PELLIER_PROGRESS_WIDTH" ]; do
    if [ "$i" -lt "$filled" ]; then bar="$bar$full"; else bar="$bar$empty"; fi
    i=$(( i + 1 ))
  done
  if [ "$elapsed" -le "$typical" ]; then
    state="$(pellier_progress_clock "$elapsed"), usually about $(pellier_progress_clock "$typical")"
  else
    state="$(pellier_progress_clock "$elapsed"), still working"
  fi
  printf '  %s  %s  %s' "$label" "$bar" "$state"
}

pellier_progress_on_terminal() {
  [ -t 1 ] && [ "${TERM:-}" != "dumb" ]
}

# Redraw the bar in place: label, typical seconds, the wait's start in epoch seconds.
pellier_progress_draw() {
  pellier_progress_on_terminal || return 0
  printf '\r\033[K%s' "$(pellier_progress_line "$1" "$2" $(( $(date +%s) - $3 )))"
}

pellier_progress_clear() {
  pellier_progress_on_terminal || return 0
  printf '\r\033[K'
}

# Wait for a background process under a bar: pid, label, typical seconds. Returns its status.
pellier_progress_wait_for() {
  local pid="$1" label="$2" typical="$3" started
  started="$(date +%s)"
  while kill -0 "$pid" 2>/dev/null; do
    pellier_progress_draw "$label" "$typical" "$started"
    sleep 0.5
  done
  pellier_progress_clear
  wait "$pid"
}
