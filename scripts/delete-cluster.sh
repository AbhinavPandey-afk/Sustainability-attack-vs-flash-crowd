#!/usr/bin/env bash
# CASCADE Phase 1 — safely delete ONLY the project's dedicated k3d cluster.
#
# This script never touches other k3d clusters, Docker containers, or the
# local Docker environment in general.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
[ -f "$REPO_ROOT/.env" ] && source "$REPO_ROOT/.env"

CLUSTER_NAME="${CASCADE_CLUSTER_NAME:-cascade}"

info()  { printf '[delete-cluster] %s\n' "$1"; }
error() { printf '[delete-cluster] ERROR: %s\n' "$1" >&2; }

if ! command -v k3d >/dev/null 2>&1; then
  error "k3d is not installed or not on PATH."
  exit 1
fi

info "Target cluster: '$CLUSTER_NAME' (only this cluster will be affected)"

if ! k3d cluster list -o json 2>/dev/null | grep -q "\"name\":\"${CLUSTER_NAME}\""; then
  info "Cluster '$CLUSTER_NAME' does not exist. Nothing to delete."
  exit 0
fi

info "Deleting cluster '$CLUSTER_NAME'..."
k3d cluster delete "$CLUSTER_NAME"
info "Cluster '$CLUSTER_NAME' deleted."
