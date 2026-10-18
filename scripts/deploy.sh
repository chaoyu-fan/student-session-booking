#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/preflight.sh
docker compose up -d --build
docker compose ps
./scripts/doctor.sh
