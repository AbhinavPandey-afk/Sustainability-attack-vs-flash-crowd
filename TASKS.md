CASCADE: Foundation & Local Kubernetes Testbed

Task Status

Phase: 1 of 8
Phase Name: Foundation and Local Kubernetes Environment
Objective: Establish a clean, reproducible local development environment and a working k3d/k3s Kubernetes cluster.

1. Context

Read the repository's CLAUDE.md completely before starting.

The project is:

Distinguishing Economic Denial of Sustainability (EDoS) Attacks from Legitimate Flash Crowds in Autoscaled Applications

The eventual system will contain:

Traffic Generators
      ↓
FastAPI Application
      ↓
Kubernetes HPA
      ↓
Prometheus
      ↓
Feature Engineering
      ↓
Cost + Scaling + Application Behaviour Features
      ↓
LightGBM
      ↓
EDoS / Flash Crowd

This task only covers the foundation and Kubernetes environment.

Do NOT implement the application, traffic generators, HPA, Prometheus, ML model, baselines, detector, or experiment pipeline yet.

2. Phase 1 Goal

By the end of this phase, the repository must have:

A clean project structure.

A documented local development environment.

A reproducible k3d/k3s cluster creation process.

A working Kubernetes cluster.

kubectl successfully connected to the cluster.

Basic Kubernetes verification commands documented.

A simple smoke-test workload proving that pods can be deployed and reached.

No unnecessary cloud dependencies.

The most important evidence must be:

kubectl get nodes
kubectl get pods -A
kubectl get svc

with the Kubernetes nodes showing Ready.

3. First Action — Inspect Before Changing Anything

Before creating or modifying files:

Inspect the entire repository.

Identify:

existing source files

existing README

existing Docker files

existing Kubernetes files

existing scripts

existing tests

existing package/configuration files

Determine whether a project structure already exists.

Preserve useful existing work.

Do NOT blindly replace existing files.

If existing files conflict with the architecture in CLAUDE.md, make the smallest clean change necessary and document it.

At the beginning of your implementation, briefly identify what already exists and how Phase 1 will integrate with it.

4. Target Phase 1 Structure

Create/adapt the repository toward:

project-root/
│
├── CLAUDE.md
├── TASK.md
├── README.md
├── .gitignore
├── .env.example
│
├── scripts/
│   ├── setup-cluster.sh
│   ├── delete-cluster.sh
│   ├── cluster-status.sh
│   └── smoke-test.sh
│
├── kubernetes/
│   └── smoke-test/
│       ├── namespace.yaml
│       ├── deployment.yaml
│       └── service.yaml
│
├── docs/
│   └── environment.md
│
└── tests/
    └── environment/

If the repository already has an appropriate structure, integrate into it instead of duplicating directories.

For Windows compatibility, if useful, also provide PowerShell equivalents:

scripts/
├── setup-cluster.ps1
├── delete-cluster.ps1
├── cluster-status.ps1
└── smoke-test.ps1

Do not add unnecessary duplicate scripts if the existing repository already has a clear cross-platform mechanism.

5. Prerequisites

Document the required local tools:

Docker

k3d

kubectl

The setup documentation must show how to verify:

docker --version
k3d version
kubectl version --client

Do not assume Docker is running without checking.

If a required tool is missing, the setup script should fail clearly and explain what is missing rather than producing a confusing error.

Do not install software automatically unless the repository already uses a safe package-manager-based installation workflow.

6. k3d Cluster Design

Create a lightweight local k3d cluster.

Default target:

1 server/control-plane
1–2 agent nodes

Use a configurable cluster name, preferably:

cascade

The exact number of agents should be chosen conservatively so the project can run on a normal student development machine.

The cluster must be suitable for the later phases:

FastAPI application
HPA
Prometheus
Locust
Feature extraction
LightGBM

Do not over-provision the cluster.

7. Cluster Setup Script

Create:

scripts/setup-cluster.sh

The script should:

Check prerequisites.

Check whether the cluster already exists.

Avoid creating duplicate clusters.

Create the k3d cluster if necessary.

Wait for nodes to become ready.

Verify Kubernetes connectivity.

Print useful verification commands.

Expected flow:

Check Docker
    ↓
Check k3d
    ↓
Check kubectl
    ↓
Check existing cascade cluster
    ↓
Create cluster if required
    ↓
Wait for Ready nodes
    ↓
kubectl get nodes

The script must exit non-zero on failure.

Do not hide errors.

8. Cluster Deletion Script

Create:

scripts/delete-cluster.sh

It should safely delete the project cluster.

It must:

Require the expected cluster name.

Avoid deleting unrelated clusters.

Clearly print what is being deleted.

Return successfully if the cluster does not exist.

Example:

./scripts/delete-cluster.sh

9. Cluster Status Script

Create:

scripts/cluster-status.sh

It should display at least:

kubectl get nodes -o wide
kubectl get pods -A
kubectl get svc -A

If useful, also display:

kubectl cluster-info

The output should make it easy to capture evidence for the Review 1 presentation.

10. Kubernetes Smoke Test

Create a minimal Kubernetes workload to prove that the cluster actually works.

Use a lightweight public image such as nginx or another simple HTTP server.

Create:

kubernetes/smoke-test/namespace.yaml
kubernetes/smoke-test/deployment.yaml
kubernetes/smoke-test/service.yaml

Requirements:

Use a dedicated namespace such as cascade-test.

Deployment should have a small replica count.

Service should expose the test application internally.

Do not expose it publicly by default.

Example conceptual structure:

k3s
 │
 └── cascade-test namespace
       │
       ├── smoke-test deployment
       │
       └── smoke-test service

11. Smoke-Test Script

Create:

scripts/smoke-test.sh

It should:

Create/apply the smoke-test namespace.

Deploy the smoke-test workload.

Wait for the deployment to become ready.

Verify the pods.

Verify the service.

Perform a local/internal HTTP request where practical.

Print a clear PASS/FAIL result.

The script must not require public internet exposure of the test service.

A preferred approach is to use:

kubectl port-forward

or an ephemeral Kubernetes client pod for the internal connectivity test.

Clean up temporary resources after the test.

12. Required Kubernetes Verification

Phase 1 must successfully produce output equivalent to:

kubectl get nodes

Expected:

NAME                  STATUS   ROLES
...                   Ready    ...
...                   Ready    ...

Also verify:

kubectl get pods -A

and:

kubectl get svc -A

The exact node names and counts will depend on the local environment.

Do not hard-code expected node names in tests.

13. Environment Documentation

Create:

docs/environment.md

Document:

Requirements

Docker

k3d

kubectl

Verify installation

Commands.

Create cluster

./scripts/setup-cluster.sh

Check cluster

./scripts/cluster-status.sh

Run smoke test

./scripts/smoke-test.sh

Delete cluster

./scripts/delete-cluster.sh

Troubleshooting

Include common issues:

Docker not running

port conflict

cluster already exists

kubectl context incorrect

node not becoming Ready

insufficient local resources

Do not include platform-specific troubleshooting unless it is relevant to the actual repository/environment.

14. README Update

Update README.md with a concise:

Current Status

Phase 1 — Foundation & Local Kubernetes Testbed
Status: In progress / Complete

Add:

Project purpose

Current architecture at a high level

Local prerequisites

Cluster setup

Verification commands

Phase 1 status

Do NOT write future implementation as if it already exists.

For example, do not claim:

"Prometheus monitors the application"

because Prometheus is not implemented in Phase 1.

It is acceptable to say:

"Prometheus will be introduced in a later phase."

15. .gitignore

Ensure .gitignore excludes local/generated artifacts such as:

.env
.venv/
venv/
__pycache__/
*.pyc
.DS_Store
.vscode/
.idea/
data/raw/
data/processed/
data/experiments/
results/

Do not ignore source code, configuration, Kubernetes manifests, or documentation.

16. Environment Test

Create basic automated checks where practical.

The tests should verify things such as:

required scripts exist

Kubernetes manifests are syntactically valid where tooling permits

cluster connectivity can be checked

smoke-test deployment becomes ready

Do not make the test suite require a live cluster for every ordinary unit test.

Clearly distinguish:

unit/static tests

from:

live environment tests

If a live-cluster test is created, label it clearly and make it easy to run separately.

17. No Application Yet

Do NOT implement these during Phase 1:

FastAPI business endpoints

expensive endpoint simulation

flash-crowd generator

EDoS generator

HPA

Prometheus application metrics

LightGBM

Random Forest

SHAP

rate limiter

volumetric detector

cost model

feature engineering

experiment matrix

Those belong to later phases.

The only workload allowed in this phase is the temporary smoke-test workload needed to prove Kubernetes works.

18. Review 1 Evidence

The phase must make it easy to capture evidence for the review rubric.

Generate/verify:

kubectl get nodes
kubectl get pods -A
kubectl get svc -A

Also capture:

kubectl get pods -n cascade-test
kubectl describe deployment smoke-test -n cascade-test

The final response after implementation must explicitly state which commands were successfully executed and summarize the observed result.

Do not fabricate command output.

19. Acceptance Criteria

Phase 1 is COMPLETE only if all of the following are true:

Repository

Repository was inspected before modification.

Existing useful structure was preserved.

Phase 1 files are organized cleanly.

.gitignore is appropriate.

Prerequisites

Docker availability is checked.

k3d availability is checked.

kubectl availability is checked.

Kubernetes

k3d cluster can be created.

Cluster uses k3s.

Kubernetes context is correct.

All expected nodes become Ready.

kubectl get nodes succeeds.

kubectl get pods -A succeeds.

kubectl get svc -A succeeds.

Smoke Test

Smoke-test namespace exists.

Smoke-test deployment becomes ready.

Smoke-test pod is running.

Smoke-test service exists.

Internal HTTP connectivity succeeds.

Smoke-test behaviour is reproducible.

Scripts

Setup script works.

Status script works.

Smoke-test script works.

Delete script works.

Scripts fail clearly when prerequisites are missing.

Documentation

docs/environment.md exists.

README contains Phase 1 setup instructions.

Commands are accurate for the implemented environment.

No future functionality is falsely described as implemented.

Quality

No unnecessary cloud service is introduced.

No paid dependency is required.

No destructive traffic-generation functionality exists.

No fabricated results or screenshots are added.

20. Final Validation Sequence

Before declaring Phase 1 complete, perform this sequence:

# 1. Check repository state
git status

# 2. Check prerequisites
docker --version
k3d version
kubectl version --client

# 3. Create cluster
./scripts/setup-cluster.sh

# 4. Verify cluster
kubectl get nodes
kubectl get pods -A
kubectl get svc -A

# 5. Run smoke test
./scripts/smoke-test.sh

# 6. Verify smoke-test resources
kubectl get pods -n cascade-test
kubectl get svc -n cascade-test

# 7. Run project status
./scripts/cluster-status.sh

# 8. Run tests
pytest

If the repository uses a different test command, use the project's established command and document it.

Finally:

./scripts/delete-cluster.sh

Then recreate the cluster once more to confirm setup reproducibility if local resources permit.

21. Final Deliverable

At the end of Phase 1, provide:

A concise summary of what was implemented.

List of files created/modified.

Exact commands used to verify the environment.

Actual verification results.

Any environment-specific issues encountered.

Confirmation of which acceptance criteria passed.

Any remaining issues that must be addressed before Phase 2.

Do NOT move to Phase 2 automatically.

Stop after Phase 1 is complete and verified.

22. Next Phase Preview

Phase 2 will implement the FastAPI application and application-level telemetry, including:

FastAPI
 ├── cheap endpoint
 ├── medium endpoint
 └── expensive endpoint
        │
        ▼
Prometheus application metrics

Phase 2 must build on the working environment established here.