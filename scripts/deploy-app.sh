#!/usr/bin/env bash
# CASCADE Phase 3 — build the app image, load it into the k3d cluster
# (no external registry is used), and deploy app + HPA + Prometheus.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
[ -f "$REPO_ROOT/.env" ] && source "$REPO_ROOT/.env"

CLUSTER_NAME="${CASCADE_CLUSTER_NAME:-cascade}"
NAMESPACE="cascade"
IMAGE="cascade-app:latest"
ROLLOUT_TIMEOUT="${CASCADE_ROLLOUT_TIMEOUT:-240s}"

info()  { printf '[deploy-app] %s\n' "$1"; }
error() { printf '[deploy-app] ERROR: %s\n' "$1" >&2; }
fail()  { error "$1"; exit 1; }

command -v docker >/dev/null 2>&1 || fail "Docker is not installed or not on PATH."
command -v k3d >/dev/null 2>&1 || fail "k3d is not installed or not on PATH."
command -v kubectl >/dev/null 2>&1 || fail "kubectl is not installed or not on PATH."

if ! k3d cluster list -o json 2>/dev/null | grep -q "\"name\":\"${CLUSTER_NAME}\""; then
  fail "Cluster '$CLUSTER_NAME' does not exist. Run ./scripts/setup-cluster.sh first."
fi

info "Building image $IMAGE..."
docker build -t "$IMAGE" "$REPO_ROOT/app" || fail "docker build failed."

info "Importing $IMAGE into cluster '$CLUSTER_NAME'..."
k3d image import "$IMAGE" -c "$CLUSTER_NAME" || fail "k3d image import failed."

info "Applying namespace..."
kubectl apply -f "$REPO_ROOT/kubernetes/namespace.yaml"

info "Applying application Deployment/Service/HPA..."
kubectl apply -f "$REPO_ROOT/kubernetes/app-deployment.yaml"
kubectl apply -f "$REPO_ROOT/kubernetes/app-service.yaml"
kubectl apply -f "$REPO_ROOT/kubernetes/hpa.yaml"

info "Applying Prometheus (RBAC, config, deployment, service)..."
kubectl apply -f "$REPO_ROOT/kubernetes/prometheus/rbac.yaml"
kubectl apply -f "$REPO_ROOT/kubernetes/prometheus/config.yaml"
kubectl apply -f "$REPO_ROOT/kubernetes/prometheus/deployment.yaml"
kubectl apply -f "$REPO_ROOT/kubernetes/prometheus/service.yaml"

info "Waiting for cascade-app rollout (timeout ${ROLLOUT_TIMEOUT})..."
kubectl -n "$NAMESPACE" rollout status deployment/cascade-app --timeout="$ROLLOUT_TIMEOUT" \
  || fail "cascade-app deployment did not become ready."

info "Waiting for prometheus rollout (timeout ${ROLLOUT_TIMEOUT})..."
kubectl -n "$NAMESPACE" rollout status deployment/prometheus --timeout="$ROLLOUT_TIMEOUT" \
  || fail "prometheus deployment did not become ready."

info "Done. Verify with:"
echo "    kubectl -n $NAMESPACE get pods,svc,hpa"
echo "    kubectl -n $NAMESPACE port-forward svc/prometheus 9090:9090"
