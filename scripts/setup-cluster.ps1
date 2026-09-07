<#
.SYNOPSIS
    CASCADE Phase 1 - create (or reuse) the local k3d/k3s cluster.

.DESCRIPTION
    Flow: Check Docker -> Check k3d -> Check kubectl -> Check existing cluster
    -> Create cluster if required -> Wait for Ready nodes -> kubectl get nodes

    Idempotent: re-running this script reuses an existing "cascade" cluster
    instead of creating a duplicate.
#>
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot '.env'

$ClusterName = $env:CASCADE_CLUSTER_NAME
$ServerCount = $env:CASCADE_SERVER_COUNT
$AgentCount = $env:CASCADE_AGENT_COUNT
$ReadyTimeout = $env:CASCADE_NODE_READY_TIMEOUT

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
        }
    }
    if (-not $ClusterName) { $ClusterName = $env:CASCADE_CLUSTER_NAME }
    if (-not $ServerCount) { $ServerCount = $env:CASCADE_SERVER_COUNT }
    if (-not $AgentCount) { $AgentCount = $env:CASCADE_AGENT_COUNT }
}

if (-not $ClusterName) { $ClusterName = 'cascade' }
if (-not $ServerCount) { $ServerCount = '1' }
if (-not $AgentCount) { $AgentCount = '2' }
if (-not $ReadyTimeout) { $ReadyTimeout = '120s' }

function Write-Info($msg)  { Write-Host "[setup-cluster] $msg" }
function Write-Err($msg)   { Write-Host "[setup-cluster] ERROR: $msg" -ForegroundColor Red }

function Fail($msg) {
    Write-Err $msg
    exit 1
}

Write-Info "Checking prerequisites..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed or not on PATH. Install Docker Desktop before continuing."
}
try {
    docker info *> $null
} catch {
    Fail "Docker is installed but not usable (daemon not running or not accessible). Start Docker and retry."
}
Write-Info "Docker OK: $(docker --version)"

if (-not (Get-Command k3d -ErrorAction SilentlyContinue)) {
    Fail "k3d is not installed or not on PATH. Install k3d before continuing (https://k3d.io)."
}
Write-Info "k3d OK: $((k3d version) | Select-Object -First 1)"

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Fail "kubectl is not installed or not on PATH. Install kubectl before continuing."
}
Write-Info "kubectl OK: $(kubectl version --client)"

Write-Info "Checking for existing cluster '$ClusterName'..."
$existing = k3d cluster list -o json | ConvertFrom-Json
$found = $existing | Where-Object { $_.name -eq $ClusterName }

if ($found) {
    Write-Info "Cluster '$ClusterName' already exists. Reusing it (no duplicate will be created)."
} else {
    Write-Info "Creating k3d cluster '$ClusterName' (servers=$ServerCount, agents=$AgentCount)..."
    k3d cluster create $ClusterName --servers $ServerCount --agents $AgentCount --wait
    if ($LASTEXITCODE -ne 0) {
        Fail "k3d cluster create failed. See output above for details."
    }
}

Write-Info "Setting kubectl context to k3d-$ClusterName..."
kubectl config use-context "k3d-$ClusterName" | Out-Null

Write-Info "Waiting for all nodes to reach Ready (timeout $ReadyTimeout)..."
kubectl wait --for=condition=Ready nodes --all --timeout=$ReadyTimeout
if ($LASTEXITCODE -ne 0) {
    Fail "Nodes did not become Ready within $ReadyTimeout. Run 'kubectl get nodes' and 'kubectl describe node <name>' to investigate."
}

Write-Info "Cluster is ready. Current nodes:"
kubectl get nodes -o wide

Write-Info "Done. Next steps:"
Write-Host "    kubectl get pods -A"
Write-Host "    kubectl get svc -A"
Write-Host "    .\scripts\smoke-test.ps1"
