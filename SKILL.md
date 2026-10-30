# CASCADE Frontend Design Skill

## Purpose
Redesign the CASCADE React frontend into a polished, research-grade product interface while preserving real-data integrity and existing backend/API behaviour.

Project identity:
- **CASCADE**
- Controlled Autoscaling Security & Cost Analysis Detection Environment
- Research theme: distinguishing EDoS from legitimate flash crowds in autoscaled applications

Visual character:
- modern
- technical
- research-grade
- precise
- calm
- professional
- data-dense without clutter
- suitable for professor/research demonstrations and portfolio presentation

Avoid:
- generic SaaS gradients everywhere
- excessive neon/cyberpunk styling
- gaming aesthetics
- huge decorative illustrations
- excessive rounded cards
- fake numbers or marketing claims
- visual noise

## 1. Research Integrity
The UI is an observation and analysis layer over a real research pipeline.

Never fabricate, hardcode, or cosmetically alter research results.

Metrics must come from:
- Kubernetes state
- Prometheus telemetry
- experiment artifacts
- model outputs
- baseline outputs
- feature-engineering results

If unavailable, show explicit states such as:
- Not available
- Not evaluated
- Held out
- Insufficient data
- No live cluster connected

Never substitute fake values.

## 2. Visual System
Use a restrained dark-first research interface.

Suggested foundation:
- Background: #0B0F14 / #10161F
- Surfaces: #151C26 / #1A2230
- Subtle slate borders
- Near-white primary text
- Muted secondary text

Semantic colours:
- green = success
- amber = warning/caveat
- red = attack/error/failure
- blue/purple = analytical differentiation only

If the existing project has theme tokens, extend them rather than creating a second system.

## 3. Typography
Prefer Inter, Geist, or Manrope if already available.

Hierarchy:
- clear page title
- small eyebrow/section label
- strong metric value
- compact metric label
- readable body text

Avoid oversized headings that waste space.

## 4. Application Shell
Use a persistent shell:

Sidebar:
- Overview
- Experiments
- Compare
- Detection
- Analysis
- Dataset
- Architecture
- System / Live Monitor

Top bar:
- page title
- optional breadcrumb
- live system status
- connection state

Sidebar should be compact, clear, and collapsible if practical.

## 5. Information Architecture

### Overview
Explain CASCADE, show system health, dataset/model status, and key findings.

### Experiments
Research-grade table with:
- Experiment ID
- Class
- Condition
- Request rate
- Peak replicas
- Cost
- Expensive ratio
- Detector
- Data status

Include search, filters, sorting, row hover, and click-through detail.

### Compare
Make this a flagship page:
**EDoS vs Flash Crowd Analysis**

Modes:
- Standard Comparison
- Matched Infrastructure
- Stealth EDoS

Show side-by-side:
- request rate
- peak request rate
- mean replicas
- peak replicas
- estimated cost
- cost/request
- cost-to-traffic
- expensive endpoint ratio
- search ratio
- endpoint diversity
- conversion rate

Then show feature differences and the real detector verdict.

### Detection
Show:
- detector result
- baseline comparison
- confusion matrix
- accuracy
- precision
- EDoS recall
- flash-crowd FPR/specificity
- F1
- threshold behaviour
- explanation

### Analysis
Show:
- SHAP
- ablation
- feature importance
- feature distributions
- separability visualizations only when real data exists

### Dataset
Show:
- primary dataset
- held-out conditions
- external datasets
- provenance
- experiment counts

### Architecture
Show the real pipeline:
Locust → FastAPI → Kubernetes/HPA → Prometheus → Feature Engineering → ML → Detection.

### System / Live Monitor
Keep live infrastructure visibility available, but do not let live execution dominate the research interface.

## 6. Overview Design
The first screen should answer within 5 seconds:
1. What is CASCADE?
2. Is the system connected?
3. What is the research status?
4. What has been demonstrated?
5. What remains limited?

Suggested header:
**CASCADE Research Console**

Subtitle:
> Distinguishing EDoS from legitimate flash crowds in autoscaled applications.

Status strip:
- Kubernetes
- Prometheus
- Application
- Model
- Dataset

Use real values.

## 7. Experiment Detail
Make the existing experiment-detail capability a polished analytical workspace.

Order:
1. Header + experiment identity
2. Classification/data-status banner
3. Key metrics
4. Request-rate timeline
5. Replica/CPU timeline
6. Cost timeline
7. Endpoint behaviour
8. Feature summary
9. SHAP explanation
10. Detection result
11. Provenance metadata

Use tabs if necessary:
- Overview
- Telemetry
- Behaviour
- Detection
- Provenance

## 8. Baseline vs Proposed
Create a dedicated analytical section.

Title:
**Baseline vs Proposed Detector**

Compare:
- Accuracy
- Precision
- EDoS recall
- Flash-crowd specificity
- F1
- False-positive rate

Preferred visuals:
1. Performance-profile line chart
2. Scenario-level detection comparison
3. Compact metrics table

Clearly label:
**Volume-only baseline**
vs
**Proposed LightGBM**

Never imply that a 100% result on the current test split means universal accuracy.

## 9. Ablation
Dedicated section:
**Feature Contribution & Ablation**

Compare:
- Full model
- Volume only
- Volume + resource
- Without cost
- Without behaviour
- Cost only
- Scaling only
- Behaviour only

Use:
- horizontal F1 comparison
- EDoS recall vs flash-crowd FPR

Interpretation should reflect actual data. The current project evidence indicates behavioural features provide the dominant measurable signal; do not claim cost/scaling improves performance unless the data supports it.

## 10. Charts
Rules:
- no 3D
- no chart junk
- restrained gridlines
- no rainbow palettes
- clear units
- readable legends
- semantic colours
- descriptive titles

Use:
- line charts for time series
- grouped bars for model comparisons
- horizontal bars for feature importance
- heatmaps for relationships
- scatter plots for separability only when actual data exists

## 11. Cards
Use cards for:
- key metrics
- system status
- research findings
- warnings
- summaries

Do not put every piece of data in a card.

Use subtle borders, modest radius, consistent padding.

## 12. Status / Trust UX
Use explicit labels:
- LIVE
- CONNECTED
- DISCONNECTED
- PRIMARY
- HELD OUT
- CALIBRATION
- NOT EVALUATED
- INSUFFICIENT DATA
- SUPPORTED
- NOT SUPPORTED
- INCONCLUSIVE

A research limitation is not an error.

## 13. Live Simulator Policy
The live simulator should not be the hero feature.

Keep backend functionality intact unless explicitly asked to remove it.

If accessible:
- place it under an advanced/experimental area
- clearly show one-run-at-a-time limitations
- show progress
- show conflict state
- show cancellation

The main research story should use recorded results and real artifacts.

## 14. Motion
Use restrained motion:
- subtle page transitions
- chart reveal
- hover states
- live-state pulse only when genuinely live
- loading skeletons

Avoid constant pulsing, bouncing cards, excessive blur, parallax, or decorative animation.

## 15. Loading / Empty / Error States
Every data component needs:
- loading skeleton
- meaningful empty state
- actionable error state
- explicit disconnected state

Example:
> Prometheus unavailable

is better than:
> Something went wrong.

Never render blank panels.

## 16. Accessibility
Require:
- keyboard navigation
- visible focus
- sufficient contrast
- semantic buttons
- useful aria labels
- no colour-only status
- readable chart labels
- responsive layout

## 17. Engineering Rules
Before changing anything:
1. Inspect the actual frontend.
2. Inspect routing.
3. Identify reusable components.
4. Inspect current dependencies.
5. Preserve API contracts.
6. Preserve real-data behaviour.

Do not rewrite backend logic unless strictly required for an existing UI capability.

Prefer reusable component groups:
components/layout
components/navigation
components/status
components/metrics
components/charts
components/tables
components/comparison
components/detection
components/research

Do not duplicate card/table/chart implementations.

## 18. Definition of Done
The redesign is complete when:
- the frontend has one coherent visual language
- navigation is consistent
- dashboard looks like a research console
- experiment browsing is polished
- experiment detail is analytical
- comparison is a flagship feature
- baseline vs proposed is clearly visualized
- ablation is clearly visualized
- SHAP is naturally integrated
- architecture is visually understandable
- live status is trustworthy
- loading/error/empty states are polished
- no research numbers are fabricated
- existing API/data contracts still work
- TypeScript build passes
- Vite production build passes
- relevant tests pass
- desktop and smaller-width layouts have been visually checked

## 19. Final Design Review
Ask:
- Does it look like one product?
- Is spacing consistent?
- Is typography clear?
- Are colours restrained?
- Are charts readable?
- Can a professor understand the project in 30 seconds?
- Can they reach the comparison page immediately?
- Can they inspect one experiment without getting lost?
- Can they distinguish live state from stored research results?
- Is every number traceable?
- Are primary and held-out data clearly distinguished?
- Are baseline and proposed methods clearly separated?
- Are components reusable?
- Are there no console errors?
