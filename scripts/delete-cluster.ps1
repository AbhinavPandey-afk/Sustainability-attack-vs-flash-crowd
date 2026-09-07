<#
.SYNOPSIS
    CASCADE Phase 1 - safely delete ONLY the project's dedicated k3d cluster.

.DESCRIPTION
    This script never touches other k3d clusters, Docker containers, or the
    local Docker environment in general.
#>
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot '.env'

$ClusterName = $env:CASCADE_CLUSTER_NAME
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
        }
    }
    if (-not $ClusterName) { $ClusterName = $env:CASCADE_CLUSTER_NAME }
}
if (-not $ClusterName) { $ClusterName = 'cascade' }

function Write-Info($msg) { Write-Host "[delete-cluster] $msg" }
function Write-Err($msg)  { Write-Host "[delete-cluster] ERROR: $msg" -ForegroundColor Red }

if (-not (Get-Command k3d -ErrorAction SilentlyContinue)) {
    Write-Err "k3d is not installed or not on PATH."
    exit 1
}

Write-Info "Target cluster: '$ClusterName' (only this cluster will be affected)"

$existing = k3d cluster list -o json | ConvertFrom-Json
$found = $existing | Where-Object { $_.name -eq $ClusterName }

if (-not $found) {
    Write-Info "Cluster '$ClusterName' does not exist. Nothing to delete."
    exit 0
}

Write-Info "Deleting cluster '$ClusterName'..."
k3d cluster delete $ClusterName
Write-Info "Cluster '$ClusterName' deleted."
