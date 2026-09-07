<#
.SYNOPSIS
    CASCADE Phase 1 - print cluster status/evidence for review capture.
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

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "[cluster-status] ERROR: kubectl is not installed or not on PATH." -ForegroundColor Red
    exit 1
}

function Section($title) {
    Write-Host ""
    Write-Host "===== $title ====="
}

Section "kubectl config current-context"
kubectl config current-context

Section "kubectl cluster-info"
kubectl cluster-info

Section "kubectl get nodes -o wide"
kubectl get nodes -o wide

Section "kubectl get pods -A"
kubectl get pods -A

Section "kubectl get svc -A"
kubectl get svc -A

Write-Host ""
Write-Host "(Expected cluster: '$ClusterName' -- context should read 'k3d-$ClusterName')"
