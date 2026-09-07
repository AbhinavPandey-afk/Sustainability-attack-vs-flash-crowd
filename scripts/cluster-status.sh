#!/usr/bin/env bash
# CASCADE Phase 1 — print cluster status/evidence for review capture.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
[ -f "$REPO_ROOT/.env" ] && source "$REPO_ROOT/.env"

CLUSTER_NAME="${CASCADE_CLUSTER_NAME:-cascade}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "[cluster-status] ERROR: kubectl is not installed or not on PATH." >&2
  exit 1
fi

section() { printf '\n===== %s =====\n' "$1"; }

section "kubectl config current-context"
kubectl config current-context || true

section "kubectl cluster-info"
kubectl cluster-info || true

section "kubectl get nodes -o wide"
kubectl get nodes -o wide

section "kubectl get pods -A"
kubectl get pods -A

section "kubectl get svc -A"
kubectl get svc -A

echo
echo "(Expected cluster: '$CLUSTER_NAME' — context should read 'k3d-${CLUSTER_NAME}')"
