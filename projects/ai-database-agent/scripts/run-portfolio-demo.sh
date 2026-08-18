#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/frontend"

if [[ ! -d node_modules ]]; then
  npm install
fi

echo "Portfolio demo: http://localhost:3000/demo"
npm run dev
