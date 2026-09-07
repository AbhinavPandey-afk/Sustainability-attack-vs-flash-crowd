#!/usr/bin/env bash
# CASCADE Phase 1 — create (or reuse) the local k3d/k3s cluster.
#
# Flow:
#   Check Docker -> Check k3d -> Check kubectl -> Check existing cluster
#   -> Create cluster if required -> Wait for Ready nodes -> kubectl get nodes
#
# Idempotent: re-running this script reuses an existing "cascade" cluster
# instead of creating a duplicate.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
[ -f "$REPO_ROOT/.env" ] && source "$REPO_ROOT/.env"

CLUSTER_NAME="${CASCADE_CLUSTER_NAME:-cascade}"
SERVER_COUNT="${CASCADE_SERVER_COUNT:-1}"
AGENT_COUNT="${CASCADE_AGENT_COUNT:-2}"
READY_TIMEOUT="${CASCADE_NODE_READY_TIMEOUT:-120s}"

info()  { printf '[setup-cluster] %s\n' "$1"; }
error() { printf '[setup-cluster] ERROR: %s\n' "$1" >&2; }

fail() {
  error "$1"
  exit 1
}

info "Checking prerequisites..."

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker is not installed or not on PATH. Install Docker before continuing."
fi
if ! docker info >/dev/null 2>&1; then
  fail "Docker is installed but not usable (daemon not running or not accessible). Start Docker and retry."
fi
info "Docker OK: $(docker --version)"

if ! command -v k3d >/dev/null 2>&1; then
  fail "k3d is not installed or not on PATH. Install k3d before continuing (https://k3d.io)."
fi
info "k3d OK: $(k3d version | head -n1)"

if ! command -v kubectl >/dev/null 2>&1; then
  fail "kubectl is not installed or not on PATH. Install kubectl before continuing."
fi
info "kubectl OK: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

info "Checking for existing cluster '$CLUSTER_NAME'..."
if k3d cluster list -o json 2>/dev/null | grep -q "\"name\":\"${CLUSTER_NAME}\""; then
  info "Cluster '$CLUSTER_NAME' already exists. Reusing it (no duplicate will be created)."
else
  info "Creating k3d cluster '$CLUSTER_NAME' (servers=$SERVER_COUNT, agents=$AGENT_COUNT)..."
  if ! k3d cluster create "$CLUSTER_NAME" \
      --servers "$SERVER_COUNT" \
      --agents "$AGENT_COUNT" \
      --wait; then
    fail "k3d cluster create failed. See output above for details."
  fi
fi

info "Setting kubectl context to k3d-$CLUSTER_NAME..."
kubectl config use-context "k3d-${CLUSTER_NAME}" >/dev/null

info "Waiting for all nodes to reach Ready (timeout ${READY_TIMEOUT})..."
if ! kubectl wait --for=condition=Ready nodes --all --timeout="$READY_TIMEOUT"; then
  fail "Nodes did not become Ready within ${READY_TIMEOUT}. Run 'kubectl get nodes' and 'kubectl describe node <name>' to investigate."
fi

info "Cluster is ready. Current nodes:"
kubectl get nodes -o wide

info "Done. Next steps:"
echo "    kubectl get pods -A"
echo "    kubectl get svc -A"
echo "    ./scripts/smoke-test.sh"
