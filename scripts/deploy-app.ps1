<#
.SYNOPSIS
    CASCADE Phase 3 - build the app image, load it into the k3d cluster
    (no external registry is used), and deploy app + HPA + Prometheus.
#>
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot '.env'

$ClusterName = $env:CASCADE_CLUSTER_NAME
$RolloutTimeout = $env:CASCADE_ROLLOUT_TIMEOUT
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
        }
    }
    if (-not $ClusterName) { $ClusterName = $env:CASCADE_CLUSTER_NAME }
}
if (-not $ClusterName) { $ClusterName = 'cascade' }
if (-not $RolloutTimeout) { $RolloutTimeout = '240s' }

$Namespace = 'cascade'
$Image = 'cascade-app:latest'

function Write-Info($msg) { Write-Host "[deploy-app] $msg" }
function Fail($msg) { Write-Host "[deploy-app] ERROR: $msg" -ForegroundColor Red; exit 1 }

foreach ($cmd in @('docker', 'k3d', 'kubectl')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Fail "$cmd is not installed or not on PATH."
    }
}

$existing = k3d cluster list -o json | ConvertFrom-Json
if (-not ($existing | Where-Object { $_.name -eq $ClusterName })) {
    Fail "Cluster '$ClusterName' does not exist. Run .\scripts\setup-cluster.ps1 first."
}

Write-Info "Building image $Image..."
docker build -t $Image (Join-Path $RepoRoot 'app')
if ($LASTEXITCODE -ne 0) { Fail "docker build failed." }

Write-Info "Importing $Image into cluster '$ClusterName'..."
k3d image import $Image -c $ClusterName
if ($LASTEXITCODE -ne 0) { Fail "k3d image import failed." }

Write-Info "Applying namespace..."
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\namespace.yaml')

Write-Info "Applying application Deployment/Service/HPA..."
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\app-deployment.yaml')
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\app-service.yaml')
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\hpa.yaml')

Write-Info "Applying Prometheus (RBAC, config, deployment, service)..."
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\prometheus\rbac.yaml')
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\prometheus\config.yaml')
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\prometheus\deployment.yaml')
kubectl apply -f (Join-Path $RepoRoot 'kubernetes\prometheus\service.yaml')

Write-Info "Waiting for cascade-app rollout (timeout $RolloutTimeout)..."
kubectl -n $Namespace rollout status deployment/cascade-app --timeout=$RolloutTimeout
if ($LASTEXITCODE -ne 0) { Fail "cascade-app deployment did not become ready." }

Write-Info "Waiting for prometheus rollout (timeout $RolloutTimeout)..."
kubectl -n $Namespace rollout status deployment/prometheus --timeout=$RolloutTimeout
if ($LASTEXITCODE -ne 0) { Fail "prometheus deployment did not become ready." }

Write-Info "Done. Verify with:"
Write-Host "    kubectl -n $Namespace get pods,svc,hpa"
Write-Host "    kubectl -n $Namespace port-forward svc/prometheus 9090:9090"
