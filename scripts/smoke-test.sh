#!/usr/bin/env bash
# CASCADE Phase 1 — deploy and verify the Kubernetes smoke-test workload.
#
# Proves: Docker -> k3d -> k3s -> Kubernetes -> Pod -> Service -> HTTP
#
# The smoke-test Deployment/Service are left running afterwards for manual
# inspection; only the temporary HTTP-check client pod is cleaned up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_DIR="$REPO_ROOT/kubernetes/smoke-test"

# shellcheck disable=SC1091
[ -f "$REPO_ROOT/.env" ] && source "$REPO_ROOT/.env"

NAMESPACE="${CASCADE_TEST_NAMESPACE:-cascade-test}"
ROLLOUT_TIMEOUT="${CASCADE_ROLLOUT_TIMEOUT:-240s}"

info()  { printf '[smoke-test] %s\n' "$1"; }
error() { printf '[smoke-test] ERROR: %s\n' "$1" >&2; }

fail_result() {
  error "$1"
  echo
  echo "RESULT: FAIL"
  exit 1
}

if ! command -v kubectl >/dev/null 2>&1; then
  fail_result "kubectl is not installed or not on PATH."
fi

info "Applying namespace..."
kubectl apply -f "$MANIFEST_DIR/namespace.yaml" || fail_result "Failed to apply namespace.yaml"

info "Applying deployment..."
kubectl apply -f "$MANIFEST_DIR/deployment.yaml" || fail_result "Failed to apply deployment.yaml"

info "Applying service..."
kubectl apply -f "$MANIFEST_DIR/service.yaml" || fail_result "Failed to apply service.yaml"

info "Waiting for deployment rollout (timeout ${ROLLOUT_TIMEOUT})..."
kubectl -n "$NAMESPACE" rollout status deployment/smoke-test --timeout="$ROLLOUT_TIMEOUT" \
  || fail_result "Deployment did not become ready within ${ROLLOUT_TIMEOUT}."

info "Verifying pod status..."
kubectl -n "$NAMESPACE" get pods -l app=smoke-test

RUNNING_COUNT=$(kubectl -n "$NAMESPACE" get pods -l app=smoke-test \
  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$RUNNING_COUNT" -lt 1 ]; then
  fail_result "No smoke-test pod is in Running phase."
fi

info "Verifying service..."
kubectl -n "$NAMESPACE" get svc smoke-test || fail_result "smoke-test service not found."

info "Testing internal HTTP connectivity via a temporary client pod..."
CLIENT_POD="smoke-test-client-$$"

cleanup_client_pod() {
  kubectl -n "$NAMESPACE" delete pod "$CLIENT_POD" --ignore-not-found=true >/dev/null 2>&1 || true
}

# Run the client pod detached (no --rm/-i attach) to avoid a known kubectl
# race where attaching to a very short-lived container intermittently fails
# even though the pod itself runs and exits successfully.
kubectl -n "$NAMESPACE" run "$CLIENT_POD" --restart=Never \
  --image=busybox:1.36 --command -- \
  wget -qO- --timeout=5 "http://smoke-test.${NAMESPACE}.svc.cluster.local" \
  || { cleanup_client_pod; fail_result "Failed to create the HTTP-check client pod."; }

if ! kubectl -n "$NAMESPACE" wait --for=jsonpath='{.status.phase}'=Succeeded \
    "pod/$CLIENT_POD" --timeout=30s >/dev/null 2>&1; then
  info "Client pod diagnostics:"
  kubectl -n "$NAMESPACE" describe pod "$CLIENT_POD" || true
  cleanup_client_pod
  fail_result "HTTP-check client pod did not complete successfully within 30s."
fi

RESPONSE="$(kubectl -n "$NAMESPACE" logs "$CLIENT_POD")"
cleanup_client_pod

if ! printf '%s' "$RESPONSE" | grep -qi "nginx\|welcome"; then
  fail_result "HTTP response did not contain expected nginx welcome content."
fi

info "HTTP request succeeded."

echo
echo "RESULT: PASS"
echo "Namespace '$NAMESPACE', Deployment/Service 'smoke-test' are left running for inspection."
echo "Inspect with: kubectl get pods -n $NAMESPACE ; kubectl get svc -n $NAMESPACE"
