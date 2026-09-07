<#
.SYNOPSIS
    CASCADE Phase 1 - deploy and verify the Kubernetes smoke-test workload.

.DESCRIPTION
    Proves: Docker -> k3d -> k3s -> Kubernetes -> Pod -> Service -> HTTP

    The smoke-test Deployment/Service are left running afterwards for manual
    inspection; only the temporary HTTP-check client pod is cleaned up.
#>
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ManifestDir = Join-Path $RepoRoot 'kubernetes\smoke-test'
$EnvFile = Join-Path $RepoRoot '.env'

$Namespace = $env:CASCADE_TEST_NAMESPACE
$RolloutTimeout = $env:CASCADE_ROLLOUT_TIMEOUT
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
        }
    }
    if (-not $Namespace) { $Namespace = $env:CASCADE_TEST_NAMESPACE }
}
if (-not $Namespace) { $Namespace = 'cascade-test' }
if (-not $RolloutTimeout) { $RolloutTimeout = '240s' }

function Write-Info($msg) { Write-Host "[smoke-test] $msg" }
function Write-Err($msg)  { Write-Host "[smoke-test] ERROR: $msg" -ForegroundColor Red }

function Fail-Result($msg) {
    Write-Err $msg
    Write-Host ""
    Write-Host "RESULT: FAIL" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Fail-Result "kubectl is not installed or not on PATH."
}

Write-Info "Applying namespace..."
kubectl apply -f (Join-Path $ManifestDir 'namespace.yaml')
if ($LASTEXITCODE -ne 0) { Fail-Result "Failed to apply namespace.yaml" }

Write-Info "Applying deployment..."
kubectl apply -f (Join-Path $ManifestDir 'deployment.yaml')
if ($LASTEXITCODE -ne 0) { Fail-Result "Failed to apply deployment.yaml" }

Write-Info "Applying service..."
kubectl apply -f (Join-Path $ManifestDir 'service.yaml')
if ($LASTEXITCODE -ne 0) { Fail-Result "Failed to apply service.yaml" }

Write-Info "Waiting for deployment rollout (timeout $RolloutTimeout)..."
kubectl -n $Namespace rollout status deployment/smoke-test --timeout=$RolloutTimeout
if ($LASTEXITCODE -ne 0) { Fail-Result "Deployment did not become ready within $RolloutTimeout." }

Write-Info "Verifying pod status..."
kubectl -n $Namespace get pods -l app=smoke-test

$running = kubectl -n $Namespace get pods -l app=smoke-test --field-selector=status.phase=Running --no-headers 2>$null
if (-not $running) {
    Fail-Result "No smoke-test pod is in Running phase."
}

Write-Info "Verifying service..."
kubectl -n $Namespace get svc smoke-test
if ($LASTEXITCODE -ne 0) { Fail-Result "smoke-test service not found." }

Write-Info "Testing internal HTTP connectivity via a temporary client pod..."
$clientPod = "smoke-test-client-$PID"

function Remove-ClientPod {
    kubectl -n $Namespace delete pod $clientPod --ignore-not-found=true | Out-Null
}

# Run the client pod detached (no --rm/-i attach) to avoid a known kubectl
# race where attaching to a very short-lived container intermittently fails
# even though the pod itself runs and exits successfully.
kubectl -n $Namespace run $clientPod --restart=Never `
    --image=busybox:1.36 --command -- `
    wget -qO- --timeout=5 "http://smoke-test.$Namespace.svc.cluster.local" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Remove-ClientPod
    Fail-Result "Failed to create the HTTP-check client pod."
}

kubectl -n $Namespace wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$clientPod" --timeout=30s | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Info "Client pod diagnostics:"
    kubectl -n $Namespace describe pod $clientPod
    Remove-ClientPod
    Fail-Result "HTTP-check client pod did not complete successfully within 30s."
}

$response = (kubectl -n $Namespace logs $clientPod | Out-String)
Remove-ClientPod

if ($response -notmatch '(?i)nginx|welcome') {
    Fail-Result "HTTP response did not contain expected nginx welcome content."
}

Write-Info "HTTP request succeeded."
Write-Host ""
Write-Host "RESULT: PASS" -ForegroundColor Green
Write-Host "Namespace '$Namespace', Deployment/Service 'smoke-test' are left running for inspection."
Write-Host "Inspect with: kubectl get pods -n $Namespace ; kubectl get svc -n $Namespace"
