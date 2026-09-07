# CLAUDE.md — CASCADE
## Cost-Aware Scaling and Application-behaviour Detection Engine

> **Project:** Distinguishing Economic Denial of Sustainability (EDoS) Attacks from Legitimate Flash Crowds in Autoscaled Applications  
> **Primary goal:** Build a reproducible local Kubernetes research testbed and a cost/scaling/application-behaviour-aware detector that distinguishes simulated EDoS traffic from legitimate flash-crowd traffic.

---

## 1. Project Mission

Build an end-to-end, reproducible research prototype that answers:

> **Can economic and autoscaling behaviour distinguish a low-volume EDoS attack from a legitimate flash crowd when traffic volume alone cannot?**

The project must demonstrate the complete experimental chain:

```text
Traffic Generator
      │
      ├── Legitimate Flash Crowd
      │
      └── Simulated EDoS
               │
               ▼
       Autoscaled FastAPI App
               │
               ▼
          Kubernetes HPA
               │
               ▼
           Prometheus
               │
               ▼
       Feature Engineering
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
   Cost     Scaling   Behaviour
 Features  Features   Features
     │         │         │
     └─────────┼─────────┘
               ▼
            LightGBM
               │
       ┌───────┴────────┐
       ▼                ▼
     EDoS          Flash Crowd
```

The project is a **research experiment**, not a production security product.

All attack traffic must remain **synthetic and confined to the local testbed**. Do not implement functionality for attacking third-party systems, evading real-world defenses, or generating uncontrolled external traffic.

---

# 2. Core Research Question

### Primary Research Question

> How can an autoscaled web application distinguish a low-volume Economic Denial of Sustainability attack from a legitimate flash crowd when both produce comparable scaling and resource-cost behaviour?

### Research Hypothesis

**H1:**

> Under comparable request-volume conditions, a detector using cost and scaling behaviour can achieve at least 90% EDoS attack recall while reducing the false-positive rate on legitimate flash crowds by at least 30% compared with a conventional volumetric anomaly detector.

### Null Hypothesis

**H0:**

> Cost and scaling behaviour do not provide a statistically significant improvement over a volume-only baseline for distinguishing EDoS attacks from legitimate flash crowds.

### Secondary Hypothesis

**H2:**

> EDoS traffic produces a higher cost-per-request and cost-to-traffic ratio than legitimate flash-crowd traffic at comparable request volumes.

The thresholds above are **research targets**, not results. Never report them as achieved until experiments actually establish them.

---

# 3. Non-Negotiable Design Principles

1. **Local-first:** The complete core experiment must work without AWS, Azure, GCP, EKS, or paid cloud services.
2. **Reproducibility:** Every experiment must be configurable from files/CLI arguments and have a saved configuration.
3. **No fabricated results:** Never invent accuracy, latency, cost, replica counts, or baseline performance.
4. **Actual measurements only:** Results shown in reports/README must come from generated experiment artifacts.
5. **Controlled attack traffic:** EDoS traffic is synthetic and only targets the local application.
6. **Flash crowd is an explicit legitimate class:** Do not treat it as merely "normal traffic."
7. **Comparable traffic:** Experiments must be able to match or closely control request volume/rate between EDoS and flash-crowd scenarios.
8. **Cost is modeled, not claimed as an actual cloud bill:** Use a configurable replica-minute/resource cost model.
9. **Traffic volume is not the main proposed feature:** It may be included for comparison, but the proposed detector must rely substantially on cost, scaling, and application-behaviour features.
10. **Baselines must actually run:** Rate limiting and volumetric anomaly detection must produce measurable outputs.
11. **Time-series integrity:** Features must be generated from timestamped observations without leaking future information into the past.
12. **Train/test separation:** No experiment window, session, user, or generated sample may accidentally appear in both training and test data.
13. **Explainability:** Use SHAP or equivalent feature attribution for the final LightGBM detector.
14. **No unnecessary complexity:** Prefer a working, reproducible research prototype over a large production-like platform.

---

# 4. Technology Stack

## Required

| Layer | Technology |
|---|---|
| OS | Linux / WSL2 / macOS / Windows with Docker |
| Containers | Docker |
| Kubernetes | k3d + k3s |
| Application | Python + FastAPI |
| Autoscaling | Kubernetes HPA |
| Metrics | Prometheus |
| Traffic generation | Locust |
| Data processing | Python + Pandas + NumPy |
| ML | LightGBM |
| ML comparison | Random Forest |
| Explainability | SHAP |
| Evaluation | scikit-learn |
| Configuration | YAML/JSON |
| Testing | pytest |

## Optional

- Grafana for dashboards
- k6 as a second traffic generator
- MLflow only if experiment tracking becomes difficult without it
- SQLite for lightweight local metadata
- Docker Compose only for non-Kubernetes development helpers

Do not introduce Redis, PostgreSQL, Kafka, cloud-managed services, or other infrastructure unless there is a demonstrated research need.

---

# 5. Target Repository Structure

Build toward the following structure:

```text
codebase/
│
├── CLAUDE.md
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
│
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py
│       ├── config.py
│       ├── models.py
│       ├── metrics.py
│       ├── cost.py
│       ├── sessions.py
│       └── endpoints/
│           ├── cheap.py
│           ├── medium.py
│           └── expensive.py
│
├── kubernetes/
│   ├── namespace.yaml
│   ├── app-deployment.yaml
│   ├── app-service.yaml
│   ├── hpa.yaml
│   ├── metrics-server/
│   └── prometheus/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── config.yaml
│
├── traffic/
│   ├── locustfile.py
│   ├── scenarios/
│   │   ├── normal.yaml
│   │   ├── flash_crowd.yaml
│   │   └── edos.yaml
│   └── generators/
│       ├── flash_crowd.py
│       └── edos.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── features/
│   └── experiments/
│
├── feature_engineering/
│   ├── collect_metrics.py
│   ├── build_features.py
│   ├── cost_features.py
│   ├── scaling_features.py
│   └── behaviour_features.py
│
├── models/
│   ├── train_lightgbm.py
│   ├── train_random_forest.py
│   ├── predict.py
│   ├── evaluate.py
│   └── explain.py
│
├── baselines/
│   ├── rate_limiter.py
│   └── volumetric_detector.py
│
├── experiments/
│   ├── configs/
│   ├── run_experiment.py
│   ├── run_matrix.py
│   └── summarize_results.py
│
├── tests/
│   ├── test_app.py
│   ├── test_cost.py
│   ├── test_features.py
│   ├── test_baselines.py
│   └── test_model_pipeline.py
│
├── results/
│   ├── figures/
│   ├── tables/
│   ├── metrics/
│   └── reports/
│
└── docs/
    ├── architecture.md
    ├── experiment_protocol.md
    ├── feature_dictionary.md
    └── literature_gap.md
```

The exact structure may be simplified if the repository already contains an established architecture. Do not duplicate functionality merely to match this tree.

---

# 6. Application Requirements

Create a small FastAPI application with endpoints whose computational cost is intentionally different.

## Endpoint classes

### Cheap endpoint

Example:

```text
GET /api/home
```

Characteristics:
- Minimal CPU
- Minimal response payload
- No expensive computation

### Medium endpoint

Example:

```text
GET /api/search?q=<query>
```

Characteristics:
- Simulated search computation
- Configurable CPU workload
- Can optionally simulate cache hits/misses

### Expensive endpoint

Example:

```text
POST /api/generate-report
```

Characteristics:
- Deliberately CPU-intensive local computation
- Configurable workload
- No external service calls
- Must have a bounded maximum execution time

The expensive operation should be deterministic/reproducible enough for experiments.

Do not make the endpoint perform real-world destructive or resource-exhaustion operations.

---

# 7. Application-Level Metrics

Expose Prometheus metrics from the FastAPI application.

At minimum collect:

```text
http_requests_total
http_request_duration_seconds
app_endpoint_requests_total
app_endpoint_duration_seconds
app_active_sessions
app_cache_hits_total
app_cache_misses_total
app_conversion_total
```

Use labels carefully.

Avoid unbounded Prometheus labels such as:
- arbitrary user IDs
- raw URLs
- session IDs
- arbitrary query strings

Prefer bounded labels such as:
- endpoint class
- HTTP method
- status class
- scenario

---

# 8. Kubernetes Requirements

Use k3d to create a local k3s cluster.

Minimum desired cluster:

```text
1 server/control-plane
1–2 agent nodes
```

The exact number should depend on the developer machine's available resources.

Required verification:

```bash
kubectl get nodes
kubectl get pods -A
kubectl get svc
kubectl get hpa
```

The application must run as a Kubernetes Deployment.

Example desired HPA behaviour:

```text
1 replica
   ↓
2 replicas
   ↓
3 replicas
   ↓
4+ replicas
```

The exact maximum replica count must be configurable.

Do not claim HPA scaling has occurred until actual Kubernetes output confirms it.

---

# 9. Autoscaling Design

Use CPU utilization initially because it is easy to reproduce locally.

Example:

```text
minReplicas: 1
maxReplicas: 8
targetCPUUtilization: 60%
```

These are defaults, not mandatory values.

Make HPA parameters configurable.

Record:

- timestamp
- current replicas
- desired replicas
- CPU utilization
- memory utilization if available
- scale-up events
- scale-down events
- time spent at each replica count

The detector must use the **observed** scaling behaviour, not merely the configured HPA target.

---

# 10. Cost Model

Do NOT depend on actual AWS/Azure/GCP billing.

Implement a platform-independent experimental cost model.

## Base model

For each replica:

```text
replica_cost = replica_rate_per_minute × active_minutes
```

Total cost:

```text
total_cost = Σ(replica_rate × replica_minutes)
```

Primary derived metrics:

```text
cost_per_request
cost_per_second
replica_minutes_per_request
cpu_seconds_per_request
cost_to_traffic_ratio
```

Make the replica-minute rate configurable, for example:

```yaml
cost_model:
  replica_cost_per_minute: 1.0
  cpu_cost_weight: 0.0
  memory_cost_weight: 0.0
```

Do not describe `1.0` as a real-world currency amount unless explicitly calibrated.

Use **cost units** by default.

The README must clearly state:

> "The cost model is an experimental proxy for infrastructure expenditure and is intentionally independent of a specific cloud provider."

---

# 11. Traffic Classes

Implement exactly two primary classes.

## Class 0 — Legitimate Flash Crowd

Represent a realistic demand surge.

Desired characteristics:

- Many simulated users
- Rapid but plausible arrival growth
- Diverse endpoints
- Session continuity
- Repeated browsing/navigation patterns
- Normal conversion behaviour
- Traffic volume can be high
- Resource demand should be legitimate

Example behavioural sequence:

```text
home
  ↓
search
  ↓
product
  ↓
checkout
```

Not every session needs to convert.

---

## Class 1 — EDoS

Generate controlled synthetic traffic that:

- Remains below or near volumetric thresholds
- Concentrates on expensive endpoints
- Can use fewer simulated clients
- Produces high resource consumption per request
- Produces elevated replica-minutes
- Has abnormal session/request structure
- Has low or configurable conversion behaviour

Example:

```text
generate-report
generate-report
generate-report
...
```

The exact attack profile must be configurable.

---

# 12. Traffic Comparability Requirement

The research depends on a fair comparison.

Experiments must include conditions where EDoS and flash-crowd traffic have:

- Similar total request counts, OR
- Similar request-rate ranges, OR
- Similar peak request rates

depending on the experiment.

Record:

```text
total_requests
requests_per_second
peak_rps
duration
unique_clients
endpoint_distribution
```

Do not compare a 10-minute 10 RPS EDoS run against a 30-second 500 RPS flash crowd and claim that cost differences prove the hypothesis.

---

# 13. Traffic Experiment Scenarios

At minimum implement:

### E0 — Normal baseline

Normal application traffic.

### E1 — Flash crowd only

Legitimate surge.

### E2 — EDoS only

Synthetic economic attack.

### E3 — Flash crowd + EDoS

Both simultaneously.

### E4 — Interleaved

Alternate windows:

```text
Flash Crowd
      ↓
EDoS
      ↓
Flash Crowd
      ↓
EDoS
```

### E5 — Volume-matched

Keep request volume approximately equivalent between EDoS and flash crowd.

### E6 — Scaling-matched

Tune traffic until both scenarios cause comparable replica counts.

### E7 — Threshold-evasion

Generate EDoS below the rate-limiting/volumetric baseline threshold.

---

# 14. Feature Engineering

The feature pipeline is the central research component.

Features should be calculated over configurable rolling windows, e.g. 10s, 30s, 60s.

Do not hard-code a single window if experiments need comparison.

---

## 14.1 Traffic Features

Include:

```text
request_rate
request_count
peak_request_rate
request_rate_std
request_burstiness
response_rate
error_rate
```

These are baseline/context features, not the primary novelty.

---

## 14.2 Cost Features — IMPORTANT

Include:

```text
cost_per_request
cost_per_second
replica_minutes_per_request
cpu_seconds_per_request
estimated_cost
cost_to_traffic_ratio
```

These are core proposed features.

---

## 14.3 Scaling Features — IMPORTANT

Include:

```text
current_replica_count
mean_replica_count
max_replica_count
replica_growth_rate
replica_change_count
scale_up_events
scale_down_events
time_at_elevated_replicas
cpu_growth_rate
replica_to_request_ratio
```

Use timestamps to calculate rates correctly.

---

## 14.4 Application Behaviour Features — IMPORTANT

Include:

```text
endpoint_diversity
unique_endpoint_ratio
expensive_endpoint_ratio
cheap_endpoint_ratio
search_ratio
report_generation_ratio
requests_per_session
session_duration
unique_client_ratio
cache_hit_rate
cache_miss_rate
conversion_rate
```

---

## 14.5 Combined Relationship Features

These may become particularly important:

```text
cost_per_request / request_rate
replica_count / request_rate
cpu_utilization / request_rate
expensive_endpoint_ratio × cost_per_request
replica_growth_rate / request_rate
```

The purpose is to capture:

> **How much infrastructure impact is produced by a given amount of traffic?**

---

# 15. Feature Dictionary

Create `docs/feature_dictionary.md`.

For every feature document:

```text
Name
Definition
Unit
Collection source
Calculation window
Formula
Expected relevance
Potential leakage
```

Example:

```text
cost_per_request

Definition:
Estimated infrastructure cost generated during the observation window
divided by the number of completed requests.

Formula:
window_cost / request_count

Unit:
cost units/request

Expected relevance:
Potentially higher for EDoS because the attack intentionally causes
disproportionate resource consumption.
```

---

# 16. Proposed ML Model

## Primary model: LightGBM

Use a binary classifier:

```text
0 = Flash Crowd
1 = EDoS
```

Do not call LightGBM itself the research novelty.

The novelty is the **feature and experimental framework**:

```text
Cost
+
Scaling
+
Application Behaviour
+
Traffic
        ↓
    LightGBM
        ↓
 EDoS / Flash Crowd
```

Use probability output:

```text
P(EDoS)
```

Make the classification threshold configurable.

Do not automatically assume `0.5` is optimal. Tune it using the training/validation data only.

---

# 17. ML Training Requirements

Use:

```python
LightGBM
scikit-learn
pandas
numpy
```

Training pipeline:

```text
Raw telemetry
    ↓
Windowing
    ↓
Feature engineering
    ↓
Data validation
    ↓
Train / validation / test split
    ↓
LightGBM
    ↓
Threshold selection
    ↓
Test evaluation
```

Important:

### Avoid temporal leakage

Do not randomly split adjacent time windows from the same continuous experiment into train and test.

Prefer:

```text
Experiment runs 1–N
        ↓
Training

Different experiment runs
        ↓
Validation

Completely held-out runs
        ↓
Testing
```

If session IDs or client IDs are available, keep related sessions within the same split.

---

# 18. ML Comparison Model

Implement Random Forest as a secondary model.

Purpose:

> Determine whether the observed performance is specific to LightGBM or whether the feature representation itself is useful.

Compare:

```text
Random Forest
vs
LightGBM
```

Keep the model configuration documented.

---

# 19. Feature Ablation Experiments

This is strongly recommended.

Train/evaluate at least:

### Model A — Volume only

```text
request_rate
request_count
peak_rps
```

### Model B — Volume + resource

```text
Volume
+
CPU
+
Memory
```

### Model C — Proposed

```text
Volume
+
Cost
+
Scaling
+
Application behaviour
```

### Model D — Proposed without cost

```text
Volume
+
Scaling
+
Application behaviour
```

### Model E — Proposed without application behaviour

```text
Volume
+
Cost
+
Scaling
```

This lets the research demonstrate **which feature family contributes to the distinction**.

---

# 20. Baseline 1 — Rate Limiting

Implement a conventional request-rate threshold.

The threshold should be calibrated from legitimate traffic.

Preferred rule:

```text
threshold = percentile of legitimate baseline traffic
```

For example, the experiment may use a 95th percentile threshold.

The exact percentile must be configurable.

Measure:

```text
attack_detected
false_positive_on_flash_crowd
detection_latency
cost_before_detection
```

Critical experiment:

```text
EDoS request rate < threshold
```

Expected outcome:

> Rate limiting may fail to detect the low-volume EDoS attack.

This must be **measured**, not assumed.

---

# 21. Baseline 2 — Volumetric Anomaly Detector

Implement a simple rolling z-score detector.

Formula:

```text
z = (x - rolling_mean) / rolling_std
```

Default alert:

```text
abs(z) > 3
```

Make the threshold configurable.

Measure:

```text
TPR
FPR
precision
recall
F1
detection_latency
cost_before_detection
```

Evaluate specifically on:

```text
EDoS
Flash Crowd
EDoS + Flash Crowd
Interleaved
```

---

# 22. Detector Decision Logic

The initial detector should operate on time windows.

Example:

```text
Prometheus telemetry
       ↓
60-second feature window
       ↓
Feature vector
       ↓
LightGBM
       ↓
P(EDoS)
       ↓
threshold
       ↓
EDoS / Flash Crowd
```

To reduce noisy alerts, support configurable temporal smoothing such as:

```text
Alert if EDoS probability > threshold
for K of the last N windows
```

Do not add smoothing until the raw classifier has been evaluated first. Report both where useful.

---

# 23. Evaluation Metrics

At minimum report:

### Classification

```text
TP
TN
FP
FN
Accuracy
Precision
Recall / TPR
Specificity / TNR
F1
ROC-AUC
PR-AUC
```

### Security-specific

```text
Flash-crowd false-positive rate
EDoS detection rate
Detection latency
```

### Economic

```text
Cost before detection
Total cost
Cost/request
Cost/second
Replica-minutes
Replica-minutes/request
```

### Operational

```text
Peak replicas
Average replicas
CPU utilization
Memory utilization
```

---

# 24. Most Important Evaluation

The central comparison should look like:

```text
                    EDoS Detection
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
 Rate Limiter       Volumetric          CASCADE
                    Detector            LightGBM
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
                Compare Results
```

Then compare:

```text
Detection latency
Cost before detection
EDoS recall
Flash-crowd FPR
F1
```

The proposed method should not be declared better unless the measurements support it.

---

# 25. Statistical Evaluation

Where enough independent experiment runs exist, report:

- Mean
- Median
- Standard deviation
- 95% confidence interval

For paired comparisons, use an appropriate statistical test based on the data distribution.

For example:

- paired t-test for suitable approximately normal paired measurements
- Wilcoxon signed-rank test for non-normal paired measurements

Do not choose a statistical test solely to obtain significance.

Report:

```text
effect size
p-value
confidence interval
```

where appropriate.

---

# 26. Separability Analysis

Because the project specifically asks whether the classes are distinguishable, include:

### 2D visualization

Use PCA or another dimensionality-reduction method for visualization only.

Recommended plots:

```text
Cost/request vs request rate
Cost/request vs replica growth rate
Endpoint diversity vs expensive endpoint ratio
PCA feature space
```

Use the plots to visually inspect:

```text
EDoS cluster
vs
Flash Crowd cluster
```

Do not claim that visual separation alone proves detection quality.

---

# 27. SHAP Explainability

For the final LightGBM model, generate:

### Global feature importance

Top features.

### SHAP summary

Show which features increase/decrease EDoS probability.

Example expected output format:

```text
Feature                    Importance
-------------------------------------
cost_per_request           ...
expensive_endpoint_ratio   ...
replica_growth_rate        ...
requests_per_session       ...
endpoint_diversity         ...
```

Do not hard-code these rankings. They must come from the trained model.

Use SHAP to answer:

> Which features actually distinguish EDoS from legitimate flash crowds?

---

# 28. Experiment Configuration

Use YAML files.

Example:

```yaml
experiment:
  name: volume_matched_01
  duration_seconds: 600
  warmup_seconds: 60
  seed: 42

traffic:
  flash_crowd_rps: 50
  edos_rps: 50
  clients: 100

hpa:
  min_replicas: 1
  max_replicas: 8
  target_cpu: 60

cost_model:
  replica_cost_per_minute: 1.0

detector:
  window_seconds: 60
  threshold: 0.5
```

Every generated result must retain the configuration used to produce it.

---

# 29. Reproducibility

Every experiment must have:

```text
experiment_id
timestamp
git_commit
config_file
random_seed
traffic parameters
HPA parameters
cost-model parameters
model version
feature version
results
```

Store a machine-readable metadata file.

Example:

```text
data/experiments/<experiment_id>/metadata.json
```

---

# 30. Experiment Naming

Use predictable names:

```text
FC_001
EDOS_001
MIX_001
INTERLEAVED_001
VOLUME_MATCHED_001
SCALING_MATCHED_001
BASELINE_RATE_001
BASELINE_VOLUME_001
```

---

# 31. Minimum Viable Research Version

Before adding advanced features, make this work:

```text
1. k3d cluster
2. FastAPI application
3. HPA
4. Prometheus
5. Locust
6. Flash-crowd generator
7. EDoS generator
8. Replica-minute cost model
9. Feature extraction
10. Rate-limit baseline
11. Volumetric baseline
12. LightGBM
13. Evaluation
14. Saved plots/results
```

Only after this pipeline works should you add:

```text
Grafana
SHAP
advanced session modelling
multiple HPA configurations
additional models
statistical testing
```

---

# 32. Development Order

Claude should implement in this order.

## Phase 1 — Repository and environment

- Inspect existing repository before changing anything.
- Preserve useful existing files.
- Add/update `.gitignore`.
- Add README sections where appropriate.
- Create local k3d setup scripts.
- Verify `kubectl get nodes`.

### Acceptance criterion

A clean machine with Docker installed can create the local cluster using documented commands.

---

## Phase 2 — Application

Implement:

- FastAPI
- cheap endpoint
- medium endpoint
- expensive endpoint
- Prometheus metrics
- session/conversion simulation

### Acceptance criterion

The app runs in Docker and responds correctly to all endpoints.

---

## Phase 3 — Kubernetes

Implement:

- Deployment
- Service
- HPA
- metrics-server
- Prometheus

### Acceptance criterion

```bash
kubectl get nodes
kubectl get pods
kubectl get hpa
```

all show healthy/running resources.

---

## Phase 4 — Traffic

Implement Locust scenarios:

- normal
- flash crowd
- EDoS

### Acceptance criterion

Both traffic classes can be generated independently and produce saved telemetry.

---

## Phase 5 — Cost model

Implement replica-minute accounting.

### Acceptance criterion

Given known replica intervals, cost calculations can be tested deterministically.

---

## Phase 6 — Feature engineering

Implement all four feature groups:

```text
Traffic
Cost
Scaling
Application Behaviour
```

### Acceptance criterion

A single experiment produces a clean feature CSV/Parquet file with labels.

---

## Phase 7 — Baselines

Implement:

- rate limiter
- volumetric z-score detector

### Acceptance criterion

Both baselines produce measurable detection outputs and metrics.

---

## Phase 8 — LightGBM

Implement:

- train
- validate
- test
- probability prediction
- threshold tuning
- metrics

### Acceptance criterion

A complete train/test run produces a saved model and evaluation JSON.

---

## Phase 9 — Explainability

Implement SHAP.

### Acceptance criterion

The final model produces feature importance/SHAP artifacts.

---

## Phase 10 — Experiment matrix

Run controlled experiments.

### Acceptance criterion

Results can be regenerated from configurations and produce comparable tables/plots.

---

# 33. Testing Requirements

Write tests for:

### Application

```text
endpoint status
response schema
metrics exposure
```

### Cost model

```text
known replica duration → known cost
zero requests handled safely
zero replicas handled safely
```

### Features

```text
correct request rate
correct cost/request
correct replica growth
correct endpoint ratios
correct session metrics
```

### Baselines

```text
below threshold → no alert
above threshold → alert
z-score behaviour
```

### ML pipeline

```text
feature schema
missing values
label encoding
train/test separation
prediction shape
metric calculation
```

Do not let tests depend on live external cloud services.

---

# 34. Data Validation

Before model training, validate:

- No NaN in required features
- No infinite values
- Labels are only `0` or `1`
- Timestamp ordering is valid
- No duplicated observation windows
- No future leakage
- No train/test experiment overlap
- Feature distributions are plausible

Generate a validation report.

---

# 35. Logging

Use structured logs.

Every experiment should record:

```text
timestamp
experiment_id
scenario
event
replica_count
request_rate
estimated_cost
```

Avoid logging sensitive or unnecessary information.

No real user data is needed.

---

# 36. Safety Constraints

This is a controlled cybersecurity research project.

The implementation must:

- Generate traffic only against the local test application.
- Bind test services to localhost where practical.
- Avoid public exposure by default.
- Use explicit safety warnings in traffic-generator documentation.
- Keep attack intensity bounded and configurable.
- Never include instructions for attacking third-party infrastructure.
- Never implement credential theft, exploitation, persistence, botnet behaviour, or evasion against real services.

The purpose is to study detection and economic impact in a controlled environment.

---

# 37. README Requirements

README must eventually contain:

## Project overview

Explain EDoS and the flash-crowd distinction.

## Research gap

State:

> Existing research generally investigates EDoS detection or flash-crowd discrimination separately. This project combines both and evaluates cost/scaling/application behaviour as distinguishing signals.

## Architecture

Include the full system diagram.

## Setup

Document:

```bash
docker --version
k3d --version
kubectl version
```

Then cluster creation.

## Run application

Commands.

## Run traffic

Commands.

## Run experiments

Commands.

## Train model

Commands.

## Evaluate

Commands.

## Results

Only measured results.

## Reproducibility

Explain experiment IDs, seeds and configuration.

---

# 38. Required Research Artifacts

The project should produce:

```text
results/
├── figures/
│   ├── traffic_comparison.png
│   ├── replica_scaling.png
│   ├── cost_comparison.png
│   ├── confusion_matrix.png
│   ├── roc_curve.png
│   ├── pr_curve.png
│   ├── feature_importance.png
│   └── shap_summary.png
│
├── tables/
│   ├── baseline_results.csv
│   ├── model_comparison.csv
│   ├── ablation_results.csv
│   └── feature_statistics.csv
│
└── metrics/
    ├── baseline_metrics.json
    ├── lightgbm_metrics.json
    └── experiment_summary.json
```

---

# 39. Review 1 Evidence Checklist

The first review requires direct evidence.

Before the presentation, make sure the repository can produce:

### Environment evidence

```bash
kubectl get nodes
kubectl get pods
kubectl get hpa
```

### Autoscaling evidence

Show:

```text
1 → 2 → 3 → 4 replicas
```

during controlled traffic.

### Baseline evidence

Run the baseline and record actual numbers:

```text
Attack request rate
Baseline threshold
TPR
FPR
Detection latency
Cost before detection
```

Do not put placeholder numbers into the presentation.

---

# 40. Review 1 Presentation Alignment

The research presentation should directly map to:

### Literature Survey — 3 marks

Show 12–15 papers from 2021 onward in a gap table with:

```text
Paper
Method
Dataset/Testbed
Metric
Limitation
```

### Problem Statement & Hypothesis — 2 marks

Show:

```text
Problem statement
H1
H0
```

### Testbed Evidence — 3 marks

Show actual:

```text
kubectl get nodes
kubectl get pods
kubectl get hpa
```

and autoscaling evidence.

### Baseline Reproduced — 2 marks

Show actual baseline measurements.

---

# 41. Definition of Done

The project is considered complete only when:

- [ ] Local k3d/k3s cluster works
- [ ] FastAPI application works
- [ ] Different endpoint costs are measurable
- [ ] HPA scales the application
- [ ] Prometheus collects telemetry
- [ ] Flash-crowd generator works
- [ ] EDoS generator works
- [ ] Traffic volumes can be matched
- [ ] Replica-minute cost model works
- [ ] Feature extraction works
- [ ] Rate-limit baseline runs
- [ ] Volumetric anomaly baseline runs
- [ ] LightGBM trains
- [ ] Random Forest comparison runs
- [ ] Test split avoids leakage
- [ ] Metrics are calculated
- [ ] Flash-crowd FPR is explicitly reported
- [ ] Detection latency is measured
- [ ] Cost before detection is measured
- [ ] Ablation study runs
- [ ] SHAP analysis runs
- [ ] Experiment configurations are saved
- [ ] Results are reproducible
- [ ] README contains complete setup/run instructions
- [ ] Review evidence can be generated from actual commands

---

# 42. Important Implementation Guidance for Claude

When working on this repository:

1. **Inspect first.** Do not overwrite an existing architecture without understanding it.
2. **Implement incrementally.** Keep each phase runnable.
3. **Run tests after meaningful changes.**
4. **Use real command output to verify Kubernetes behaviour.**
5. **Do not fabricate experimental results.**
6. **Do not silently change the research hypothesis.**
7. **Keep the cost model explicit and configurable.**
8. **Keep EDoS and flash-crowd labels unambiguous.**
9. **Record experiment configurations.**
10. **Prefer simple, interpretable features before adding sophisticated ones.**
11. **Do not use a neural network merely because the project involves AI. LightGBM is the primary proposed model.**
12. **Do not call the model novel solely because it uses LightGBM.**
13. **The research contribution is the cost + scaling + application-behaviour feature framework and explicit flash-crowd negative class.**
14. **Use SHAP to investigate whether the model is learning meaningful economic/scaling signals.**
15. **Any performance claim must point to a generated result artifact.**
16. **If a design decision affects the research validity, document it in `docs/experiment_protocol.md`.**
17. **Keep all traffic-generation defaults safe and local.**
18. **Do not add cloud dependencies unless specifically requested.**

---

# 43. Final Intended Architecture

The completed project should implement:

```text
                         LOCAL MACHINE
                              │
                            Docker
                              │
                             k3d
                              │
                             k3s
                              │
              ┌───────────────┼────────────────┐
              │               │                │
              ▼               ▼                ▼
          FastAPI             HPA          Prometheus
              │               │                │
              │               │                │
       ┌──────┼──────┐        │                │
       │      │      │        │                │
     Home   Search  Report    │                │
       │      │      │        │                │
       └──────┼──────┘        │                │
              │               │                │
              └───────────────┼────────────────┘
                              │
                 ┌────────────┴────────────┐
                 │                         │
                 ▼                         ▼
          Flash Crowd                  EDoS
          Generator                  Generator
                 │                         │
                 └────────────┬────────────┘
                              ▼
                     Experiment Telemetry
                              │
                              ▼
                     Feature Engineering
                              │
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
       Traffic              Cost                Scaling
      Features            Features             Features
          │                   │                    │
          └───────────────────┼────────────────────┘
                              │
                              ▼
                       Behaviour Features
                              │
                              ▼
                       Feature Dataset
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
               Baselines            LightGBM
                    │                   │
          ┌─────────┴─────────┐         │
          │                   │         │
      Rate Limit        Volumetric     │
                         Detector      │
          │                   │         │
          └─────────┬─────────┘         │
                    │                   │
                    └────────┬──────────┘
                             ▼
                       Evaluation Engine
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
      Detection           Economic          False Positive
       Latency             Impact               Rate
          │                  │                   │
          └──────────────────┼───────────────────┘
                             ▼
                       Research Results
                             │
                             ▼
                    Tables + Figures + SHAP
```

---

# 44. Final Research Positioning

The final project should communicate the following clearly:

> **We are not trying to build another generic DDoS classifier.**

The research focus is:

```text
EDoS
  +
Legitimate Flash Crowd
  +
Autoscaling
  +
Economic Cost
  +
Application Behaviour
```

The central distinction is:

```text
Traffic volume alone
        ≠
Economic impact
```

The proposed detector therefore learns:

```text
How much infrastructure impact
is produced by how much traffic
and what kind of application behaviour?
```

The final research comparison is:

```text
              SAME / COMPARABLE TRAFFIC
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
      Flash Crowd                   EDoS
            │                         │
            ▼                         ▼
       Legitimate                Malicious
       demand                    cost-inducing
            │                         │
            └────────────┬────────────┘
                         ▼
               Cost + Scaling +
              Application Behaviour
                         │
                         ▼
                      CASCADE
                         │
                  ┌──────┴──────┐
                  ▼             ▼
                EDoS       Flash Crowd
```

The project should remain focused on proving or disproving the hypothesis through controlled experiments rather than assuming the proposed method will outperform the baselines.
