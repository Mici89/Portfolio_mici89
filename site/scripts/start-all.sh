#!/usr/bin/env bash
set -euo pipefail

hub_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
monorepo_root="$(cd "$hub_root/.." && pwd)"
runtime_dir="$hub_root/.runtime"
log_dir="$runtime_dir/logs"
pid_dir="$runtime_dir/pids"

ai_db_root="${AI_DB_ROOT:-$monorepo_root/projects/ai-database-agent}"
qcc_root="${QCC_ROOT:-$monorepo_root/projects/enterprise-radar}"
knowledge_root="${KNOWLEDGE_ROOT:-$monorepo_root/projects/enterprise-knowledge-agent}"

mkdir -p "$log_dir" "$pid_dir"

require_path() {
  if [[ ! -e "$1" ]]; then
    echo "缺少项目路径：$1" >&2
    exit 1
  fi
}

port_is_open() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

start_process() {
  local name="$1"
  local port="$2"
  local workdir="$3"
  shift 3

  local pid_file="$pid_dir/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(<"$pid_file")" 2>/dev/null; then
    echo "[运行中] $name (PID $(<"$pid_file"), 端口 $port)"
    return
  fi
  if port_is_open "$port"; then
    echo "[端口冲突] $name 需要端口 $port，但该端口已被其他进程占用。" >&2
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
    exit 1
  fi

  (
    cd "$workdir"
    nohup "$@" >"$log_dir/$name.log" 2>&1 &
    echo $! >"$pid_file"
  )
  echo "[已启动] $name (端口 $port)"
}

require_path "$ai_db_root/backend"
require_path "$ai_db_root/frontend"
require_path "$qcc_root/app.py"
require_path "$knowledge_root/services/agent-api"
require_path "$knowledge_root/apps/web"

ensure_node_dependencies() {
  local project_dir="$1"
  if [[ ! -d "$project_dir/node_modules" ]]; then
    echo "安装 Node 依赖：$project_dir"
    (cd "$project_dir" && npm install)
  fi
}

ensure_uv_environment() {
  local project_dir="$1"
  local extra_args="${2:-}"
  if [[ ! -x "$project_dir/.venv/bin/uvicorn" ]]; then
    echo "安装 Python 依赖：$project_dir"
    (cd "$project_dir" && uv sync $extra_args)
  fi
}

ensure_qcc_environment() {
  if [[ ! -x "$qcc_root/.venv/bin/streamlit" ]]; then
    echo "安装 Python 依赖：$qcc_root"
    (cd "$qcc_root" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)
  fi
}

inherit_local_env() {
  local target="$1"
  local legacy_source="$2"
  if [[ ! -f "$target" && -f "$legacy_source" ]]; then
    echo "复用本机已有环境变量（不会进入 Git）：$target"
    cp "$legacy_source" "$target"
  fi
}

legacy_root="${LEGACY_PROJECT_ROOT:-$monorepo_root/..}"
inherit_local_env "$ai_db_root/backend/.env" "$legacy_root/AI_DB/backend/.env"
inherit_local_env "$qcc_root/.env" "$legacy_root/qcc/.env"
inherit_local_env "$knowledge_root/services/agent-api/.env" "$legacy_root/enterprise-knowledge-agent/services/agent-api/.env"

ai_db_required_env=()
if [[ ! -f "$ai_db_root/backend/.env" ]]; then
  echo "提示：未找到 AI Database Agent 的 .env，将使用本地测试凭据启动 API。"
  ai_db_required_env=(
    DB_PASSWORD=local_reader_ChangeMe_2026
    DB_WRITE_PASSWORD=local_writer_ChangeMe_2026
    AUTH_OPERATOR_PASSWORD=local_operator_ChangeMe_2026
    AUTH_TOKEN_SECRET=local_token_secret_for_development_only
  )
fi

ensure_node_dependencies "$hub_root"
ensure_node_dependencies "$ai_db_root/frontend"
ensure_node_dependencies "$knowledge_root/apps/web"
ensure_uv_environment "$ai_db_root/backend"
ensure_qcc_environment
ensure_uv_environment "$knowledge_root/services/agent-api" "--extra dev"

echo "启动数据库容器..."
docker compose -f "$ai_db_root/DB/mysql/docker-compose.yml" up -d
KNOWLEDGE_POSTGRES_PORT=5433 docker compose \
  -f "$knowledge_root/infra/compose.yaml" up -d

echo "等待 PostgreSQL 就绪..."
for _ in {1..30}; do
  if docker exec knowledge-agent-postgres pg_isready -U knowledge_agent -d knowledge_agent >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

knowledge_database_url="postgresql+psycopg://knowledge_agent:local_password@127.0.0.1:5433/knowledge_agent"
(
  cd "$knowledge_root/services/agent-api"
  DATABASE_URL="$knowledge_database_url" .venv/bin/alembic upgrade head
)

if (( ${#ai_db_required_env[@]} > 0 )); then
  start_process "ai-db-api" 8101 "$ai_db_root/backend" \
    env DB_PORT=3307 CORS_ORIGINS="http://localhost:3101,http://127.0.0.1:3101" "${ai_db_required_env[@]}" \
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8101
else
  start_process "ai-db-api" 8101 "$ai_db_root/backend" \
    env DB_PORT=3307 CORS_ORIGINS="http://localhost:3101,http://127.0.0.1:3101" \
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8101
fi

start_process "ai-db-web" 3101 "$ai_db_root/frontend" \
  env NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8101 npm run dev -- --host 127.0.0.1 --port 3101

start_process "qcc-web" 3102 "$qcc_root" \
  .venv/bin/streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 3102

start_process "knowledge-api" 8103 "$knowledge_root/services/agent-api" \
  env DATABASE_URL="$knowledge_database_url" CORS_ORIGINS='["http://localhost:3103","http://127.0.0.1:3103"]' \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8103

start_process "knowledge-web" 3103 "$knowledge_root/apps/web" \
  env NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8103 npm run dev -- --port 3103

if [[ -f "$hub_root/package.json" ]]; then
  start_process "portfolio-web" 3000 "$hub_root" npm run dev -- --port 3000
fi

wait_for_http() {
  local name="$1"
  local url="$2"
  for _ in {1..30}; do
    if curl --silent --fail --max-time 2 "$url" >/dev/null 2>&1; then
      echo "[健康] $name -> $url"
      return 0
    fi
    sleep 1
  done
  echo "[未就绪] $name -> ${url}（请查看 .runtime/logs/）" >&2
  return 1
}

echo
echo "等待应用健康检查..."
health_failed=0
wait_for_http "作品站" "http://127.0.0.1:3000" || health_failed=1
wait_for_http "AI Database Agent Web" "http://localhost:3101" || health_failed=1
wait_for_http "AI Database Agent API" "http://127.0.0.1:8101/health/live" || health_failed=1
wait_for_http "企信雷达" "http://127.0.0.1:3102/_stcore/health" || health_failed=1
wait_for_http "Knowledge Agent Web" "http://127.0.0.1:3103" || health_failed=1
wait_for_http "Knowledge Agent API" "http://127.0.0.1:8103/health" || health_failed=1

echo
echo "访问地址："
echo "  作品站：              http://127.0.0.1:3000"
echo "  AI Database Agent：   http://localhost:3101/demo"
echo "  企信雷达：            http://127.0.0.1:3102"
echo "  Knowledge Agent：     http://127.0.0.1:3103"
echo "  API 状态：             $hub_root/scripts/status.sh"

exit "$health_failed"
