#!/usr/bin/env bash
set -euo pipefail

check_http() {
  local name="$1"
  local url="$2"
  if curl --silent --fail --max-time 3 "$url" >/dev/null; then
    printf '[正常]   %-28s %s\n' "$name" "$url"
  else
    printf '[未就绪] %-28s %s\n' "$name" "$url"
  fi
}

check_tcp() {
  local name="$1"
  local port="$2"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    printf '[监听]   %-28s 127.0.0.1:%s\n' "$name" "$port"
  else
    printf '[未监听] %-28s 127.0.0.1:%s\n' "$name" "$port"
  fi
}

check_http "作品站" "http://127.0.0.1:3000"
check_http "AI Database Agent Web" "http://localhost:3101"
check_http "AI Database Agent API" "http://127.0.0.1:8101/health/live"
check_http "企信雷达" "http://127.0.0.1:3102/_stcore/health"
check_http "Knowledge Agent Web" "http://127.0.0.1:3103"
check_http "Knowledge Agent API" "http://127.0.0.1:8103/health"

echo
check_tcp "MySQL" 3307
check_tcp "Oracle" 1522
check_tcp "PostgreSQL / pgvector" 5433
