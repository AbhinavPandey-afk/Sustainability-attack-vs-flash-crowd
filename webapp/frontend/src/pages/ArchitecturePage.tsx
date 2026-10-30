export function ArchitecturePage() {
  return (
    <div>
      <div className="page-title">
        <h2>Architecture</h2>
      </div>
      <p className="page-subtitle">
        The real pipeline this dashboard observes and controls — every stage below is implemented and has
        produced real artifacts on disk.
      </p>

      <div className="arch-diagram">
        <div className="arch-branch">
          <div className="arch-node">
            <h4>Flash-Crowd Generator</h4>
            <p>Locust — diverse endpoints, session continuity, realistic think-time</p>
          </div>
          <div className="arch-node">
            <h4>EDoS Generator</h4>
            <p>Locust — concentrated on the expensive endpoint, minimal think-time</p>
          </div>
        </div>
        <div className="arch-arrow">↓</div>
        <div className="arch-node">
          <h4>FastAPI Application (cascade-app)</h4>
          <p>Cheap / medium / expensive endpoint classes, Prometheus metrics, session &amp; conversion simulation</p>
        </div>
        <div className="arch-arrow">↓</div>
        <div className="arch-branch">
          <div className="arch-node">
            <h4>Kubernetes HPA</h4>
            <p>CPU-utilization-based autoscaling, 1–8 replicas (configurable)</p>
          </div>
          <div className="arch-node">
            <h4>Prometheus</h4>
            <p>Scrapes application + replica metrics</p>
          </div>
        </div>
        <div className="arch-arrow">↓</div>
        <div className="arch-node">
          <h4>Feature Engineering</h4>
          <p>Traffic + Cost + Scaling + Application-Behaviour features over rolling windows, no future leakage</p>
        </div>
        <div className="arch-arrow">↓</div>
        <div className="arch-branch">
          <div className="arch-node">
            <h4>Rate Limiter Baseline</h4>
            <p>Percentile threshold calibrated on legitimate traffic</p>
          </div>
          <div className="arch-node">
            <h4>Volumetric z-score Baseline</h4>
            <p>Rolling z-score anomaly detector</p>
          </div>
          <div className="arch-node">
            <h4>CASCADE (LightGBM)</h4>
            <p>Cost + scaling + behaviour features, ablation-studied, SHAP-explained</p>
          </div>
        </div>
        <div className="arch-arrow">↓</div>
        <div className="arch-node">
          <h4>This Dashboard</h4>
          <p>Reads real artifacts on disk / live cluster checks — triggers real experiment runs, never fabricates a result</p>
        </div>
      </div>
    </div>
  )
}
