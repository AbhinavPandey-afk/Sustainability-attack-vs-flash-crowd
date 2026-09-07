# Environment — Phase 1: Foundation & Local Kubernetes Testbed

This document describes the local development environment for the CASCADE
project as implemented in **Phase 1 only**. It covers the Docker/k3d/k3s
cluster and a minimal Kubernetes smoke test. It does **not** cover the
FastAPI application, HPA, Prometheus, traffic generation, or ML pipeline —
those are introduced in later phases (see `TASKS.md`).

## 1. Requirements

| Tool | Purpose | Verify with |
|---|---|---|
| [Docker](https://www.docker.com/) | Container runtime that backs k3d nodes | `docker --version` and `docker info` |
| [k3d](https://k3d.io/) | Runs k3s (lightweight Kubernetes) in Docker | `k3d version` |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Kubernetes CLI | `kubectl version --client` |

`docker --version` only confirms the CLI is installed. `docker info` must
also succeed — that confirms the Docker daemon is actually running and
reachable, which is required before k3d can create cluster containers.

## 2. Verify installation

Bash (Linux/macOS/WSL/Git Bash):

```bash
docker --version
docker info >/dev/null && echo "Docker daemon OK"
k3d version
kubectl version --client
```

PowerShell (Windows):

```powershell
docker --version
docker info | Out-Null; if ($?) { "Docker daemon OK" }
k3d version
kubectl version --client
```

If any command is not found or fails, install/start the corresponding tool
before continuing. The setup scripts described below perform these same
checks automatically and exit with a non-zero status and a clear message if
a prerequisite is missing.

## 3. Cluster design

- Cluster name: `cascade` (configurable via `CASCADE_CLUSTER_NAME`, see
  `.env.example`)
- Topology: 1 k3s server (control-plane) node + 2 k3s agent (worker) nodes
  by default (configurable via `CASCADE_SERVER_COUNT` / `CASCADE_AGENT_COUNT`)
- This topology is intentionally conservative so the cluster runs on a
  normal student laptop/desktop, while still being enough nodes to later
  observe HPA-driven scheduling across nodes.

## 4. Create the cluster

```bash
./scripts/setup-cluster.sh
```

```powershell
.\scripts\setup-cluster.ps1
```

The script is **idempotent**: if a cluster named `cascade` already exists it
is reused rather than recreated. It will:

1. Check Docker, k3d, and kubectl are installed and usable.
2. Check whether a `cascade` cluster already exists.
3. Create the cluster only if it does not already exist.
4. Set the `kubectl` context to `k3d-cascade`.
5. Wait for all nodes to report `Ready`.
6. Print `kubectl get nodes -o wide`.

## 5. Verify the cluster

```bash
kubectl get nodes
kubectl get pods -A
kubectl get svc -A
kubectl cluster-info
```

Expected node output shape (actual names/counts depend on your machine):

```text
NAME                     STATUS   ROLES                  AGE   VERSION
k3d-cascade-server-0     Ready    control-plane,master   1m    v1.x.x
k3d-cascade-agent-0      Ready    <none>                 1m    v1.x.x
k3d-cascade-agent-1      Ready    <none>                 1m    v1.x.x
```

`kubectl get pods -A` at this point should only show core k3s/system
components (`kube-system`, `metrics-server` if enabled by k3d, `local-path-provisioner`,
etc.) — there is no CASCADE application deployed yet.

Or use the bundled status script, which prints all of the above in one go
and is convenient for capturing Review 1 evidence:

```bash
./scripts/cluster-status.sh
```

```powershell
.\scripts\cluster-status.ps1
```

## 6. Run the smoke test

```bash
./scripts/smoke-test.sh
```

```powershell
.\scripts\smoke-test.ps1
```

This applies `kubernetes/smoke-test/{namespace,deployment,service}.yaml`
(an `nginx` pod in the `cascade-test` namespace), waits for the rollout to
become ready, and verifies internal HTTP connectivity by running a
temporary `busybox` client pod inside the cluster that issues a `wget`
against the ClusterIP service. The service is **not** exposed outside the
cluster. The script prints `RESULT: PASS` or `RESULT: FAIL`.

The smoke-test `Deployment`/`Service` are left running afterward so they
can be inspected manually:

```bash
kubectl get pods -n cascade-test
kubectl get svc -n cascade-test
kubectl describe deployment smoke-test -n cascade-test
```

Only the temporary HTTP-check client pod is cleaned up automatically
(`kubectl run ... --rm`).

## 7. Delete the cluster

```bash
./scripts/delete-cluster.sh
```

```powershell
.\scripts\delete-cluster.ps1
```

This deletes **only** the `cascade` k3d cluster (by exact name). It does not
touch other k3d clusters, unrelated Docker containers, or your Docker
environment generally. It exits successfully (no-op) if the cluster does
not exist.

## 8. Troubleshooting

**Docker not running**
`docker info` fails. Start Docker Desktop (or the Docker daemon) and retry.

**Port conflict when creating the cluster**
k3d exposes the Kubernetes API and (optionally) an ingress port on the
host. If a port is already in use, k3d will report a bind error on cluster
creation. Stop the conflicting process, or delete a stale k3d cluster with
`k3d cluster delete cascade` before retrying.

**Cluster already exists**
`./scripts/setup-cluster.sh` detects this and reuses the existing cluster
rather than failing or duplicating it. If you want a fresh cluster, run
`./scripts/delete-cluster.sh` first.

**kubectl context incorrect**
`kubectl config current-context` should read `k3d-cascade` after running
the setup script. If it points elsewhere (e.g. a different cluster),
run `kubectl config use-context k3d-cascade`.

**Node not becoming Ready**
Wait a little longer — k3s images may still be pulling on first run. Check
`kubectl describe node <name>` and `kubectl get pods -A` for pods stuck in
`Pending`/`ImagePullBackOff`, and confirm Docker has enough CPU/memory
allocated (see below).

**Insufficient local resources**
k3d containers share the host's Docker resource limits. If nodes stay
`NotReady` or pods stay `Pending`, increase Docker's allocated CPU/memory
(Docker Desktop → Settings → Resources), or reduce
`CASCADE_AGENT_COUNT` to `1` in `.env`.

**Smoke test fails with "Deployment did not become ready" right after cluster creation**
`./scripts/delete-cluster.sh` removes the cluster's cached-image volume
along with the cluster, so every fresh `setup-cluster` → `smoke-test` cycle
re-pulls `nginx:1.27-alpine` (and `busybox:1.36` for the connectivity
check) from scratch. On a slow connection this can take well over a
minute. `smoke-test.sh` / `.ps1` default to a 240s rollout timeout
(`CASCADE_ROLLOUT_TIMEOUT` in `.env`) to accommodate this; if it still
times out, check `kubectl get pods -n cascade-test` and
`kubectl describe pod -n cascade-test -l app=smoke-test` — a `Pulling`
event with no `Pulled` event yet means it's still downloading, not stuck.
Simply re-run the script once the image finishes pulling.

**CoreDNS/other system pods briefly show `FailedCreatePodSandBox: ... flannel 'subnet.env' ... no such file or directory`**
Observed once during rapid cluster recreation: the first pod scheduled
right after cluster creation can race k3s's flannel CNI before it writes
`/run/flannel/subnet.env`. kubelet retries automatically and it resolves
itself within the same pod (check `kubectl describe pod` — a later
`Pulling`/`Started` event after the warning means it recovered). If it
does not recover after a minute or two, delete and recreate the cluster.

## 9. What is intentionally NOT part of Phase 1

The following are planned for later phases and are **not** implemented yet:
Prometheus, the FastAPI application, HPA, Locust traffic generation,
cost modelling, feature engineering, and the LightGBM detector. Do not
interpret the presence of the `cascade-test` smoke-test workload as any of
the above — it is a disposable nginx pod used only to prove that the
Kubernetes control plane, scheduler, networking, and service discovery work
end to end.
