#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd -P)
PORT=8766

if [[ ! -x .venv/bin/python || ! -f frontend/dist/index.html ]]; then
  echo 'Instale as dependências e compile o frontend conforme README.md.' >&2
  exit 1
fi

# Processo desta aplicação: uvicorn de backend.app:app iniciado nesta pasta.
is_ours() {
  local pid=$1
  [[ -r /proc/$pid/cmdline ]] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'uvicorn backend.app:app' || return 1
  [[ $(readlink "/proc/$pid/cwd" 2>/dev/null) == "$ROOT" ]]
}

listeners() {
  ss -ltnHp "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u || true
}

instances() {
  local pid
  for pid in $(pgrep -f 'uvicorn backend.app:app' || true); do
    [[ $pid != $$ ]] && is_ours "$pid" && echo "$pid"
  done
}

# Uma porta ocupada por outro programa não é encerrada.
for pid in $(listeners); do
  if ! is_ours "$pid"; then
    echo "A porta $PORT está em uso por outro processo (PID $pid: $(ps -o comm= -p "$pid")). Encerre-o manualmente." >&2
    exit 1
  fi
done

old=$(printf '%s\n%s\n' "$(listeners)" "$(instances)" | sort -u | grep -v '^$' || true)
if [[ -n $old ]]; then
  echo "Encerrando instância anterior (PID: $(echo $old))…"
  kill -TERM $old 2>/dev/null || true
  for _ in $(seq 1 100); do
    alive=false
    for pid in $old; do kill -0 "$pid" 2>/dev/null && alive=true; done
    $alive || break
    sleep 0.1
  done
  for pid in $old; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "PID $pid não encerrou; forçando."
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  sleep 0.3
fi

if [[ -n $(listeners) ]]; then
  echo "Não foi possível liberar a porta $PORT." >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "$PORT" --no-access-log
