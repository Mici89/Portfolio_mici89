#!/usr/bin/env bash
set -euo pipefail

hub_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pid_dir="$hub_root/.runtime/pids"

if [[ ! -d "$pid_dir" ]]; then
  echo "没有由作品站启动器管理的应用进程。"
  exit 0
fi

for pid_file in "$pid_dir"/*.pid; do
  [[ -e "$pid_file" ]] || continue
  name="$(basename "$pid_file" .pid)"
  pid="$(<"$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "[已停止] $name (PID $pid)"
  fi
  rm -f "$pid_file"
done

echo "数据库容器仍保留运行。如需停止，请单独执行对应项目的 docker compose down。"
