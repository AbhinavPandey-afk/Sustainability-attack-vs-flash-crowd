/*
 * Storefront demo behaviour. Every user action here calls the same
 * real /api/* endpoints as the traffic generators (traffic/generators/)
 * and the dashboard's live simulators — nothing is faked client-side.
 * The only client-side data is FIXTURE_PRODUCTS, purely cosmetic
 * (names/prices for the "cheap" product grid), never sent to the server
 * or used to compute any research metric.
 */
(function () {
  "use strict";

  const FIXTURE_PRODUCTS = [
    { id: "p1", name: "Trail Runner Shoes", price: 89.99, emoji: "👟" },
    { id: "p2", name: "3-Season Tent", price: 249.0, emoji: "⛺" },
    { id: "p3", name: "Insulated Jacket", price: 159.5, emoji: "🧥" },
    { id: "p4", name: "Titanium Cookset", price: 64.0, emoji: "🍽️" },
    { id: "p5", name: "60L Backpack", price: 189.99, emoji: "🎒" },
    { id: "p6", name: "Trekking Poles", price: 44.0, emoji: "🧑‍🦽" },
    { id: "p7", name: "Water Filter", price: 34.5, emoji: "💧" },
    { id: "p8", name: "Down Sleeping Bag", price: 219.0, emoji: "🛌" },
  ];

  function fmtMoney(n) {
    return "$" + Number(n).toFixed(2);
  }

  // ------------------------------------------------------------ products --

  function renderProducts(products) {
    const grid = document.getElementById("product-grid");
    grid.innerHTML = "";
    for (const p of products) {
      const card = document.createElement("div");
      card.className = "product-card";
      card.innerHTML =
        '<div class="product-emoji">' + p.emoji + "</div>" +
        '<div class="product-name">' + p.name + "</div>" +
        '<div class="product-price">' + fmtMoney(p.price) + "</div>" +
        '<button type="button">Buy now</button>';
      card.querySelector("button").addEventListener("click", () => buy(card, p));
      grid.appendChild(card);
    }
  }

  async function buy(card, product) {
    const btn = card.querySelector("button");
    btn.disabled = true;
    btn.textContent = "Adding…";
    try {
      const res = await fetch("/api/checkout", { method: "POST" });
      if (!res.ok) throw new Error(res.status);
      btn.textContent = "Purchased ✓";
    } catch (e) {
      btn.textContent = "Failed — retry";
      btn.disabled = false;
    }
  }

  async function loadHome() {
    try {
      await fetch("/api/home");
    } catch (e) {
      // Home ping failing shouldn't block rendering the storefront shell.
    }
    renderProducts(FIXTURE_PRODUCTS);
  }

  // ------------------------------------------------------------- search --

  function deterministicPrice(id) {
    // Cosmetic only: turns a search-result id into a stable-looking price.
    return 19.99 + ((id * 37) % 180);
  }

  function renderSearchResults(results) {
    const grid = document.getElementById("search-grid");
    grid.innerHTML = "";
    for (const r of results) {
      const card = document.createElement("div");
      card.className = "product-card";
      card.innerHTML =
        '<div class="product-emoji">🛍️</div>' +
        '<div class="product-name">' + r.title + "</div>" +
        '<div class="product-price">' + fmtMoney(deterministicPrice(r.id)) + "</div>" +
        '<button type="button">Buy now</button>';
      card.querySelector("button").addEventListener("click", () => buy(card, r));
      grid.appendChild(card);
    }
  }

  async function doSearch(query) {
    const status = document.getElementById("search-status");
    status.className = "status-line";
    status.textContent = "Searching…";
    try {
      const res = await fetch("/api/search?q=" + encodeURIComponent(query));
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      renderSearchResults(data.results);
      status.className = "status-line ok";
      status.textContent =
        data.results.length + " results" + (data.cached ? " (cache hit)" : " (cache miss)");
    } catch (e) {
      status.className = "status-line err";
      status.textContent = "Search failed: " + e.message;
    }
  }

  // ------------------------------------------------------------- report --

  async function generateReport() {
    const btn = document.getElementById("generate-report-btn");
    const status = document.getElementById("report-status");
    const complexity = Number(document.getElementById("complexity-range").value);
    btn.disabled = true;
    status.className = "status-line";
    status.textContent = "Generating…";
    const started = performance.now();
    try {
      const res = await fetch("/api/generate-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ complexity }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      const clientMs = Math.round(performance.now() - started);
      status.className = "status-line ok";
      status.textContent =
        "Done in " + data.duration_seconds.toFixed(3) + "s server-side (" + clientMs +
        "ms round trip), " + data.iterations.toLocaleString() + " iterations.";
    } catch (e) {
      status.className = "status-line err";
      status.textContent = "Report generation failed: " + e.message;
    } finally {
      btn.disabled = false;
    }
  }

  // --------------------------------------------------------- impact strip --

  const DASHBOARD_API = window.CASCADE_IMPACT_API;
  let dashboardReachable = false;
  let lastReplicas = null;

  function fmtRate(v) {
    return v === null || v === undefined ? "–" : v.toFixed(2);
  }

  function updateImpactStrip(data) {
    const badge = document.getElementById("impact-status");
    if (!data) {
      badge.textContent = "dashboard backend unreachable";
      badge.className = "impact-badge down";
      renderPods(null);
      renderMeters(null);
      renderBanner(null);
      updateSimAvailability();
      return;
    }

    document.getElementById("impact-replicas").textContent =
      data.replicas === null || data.replicas === undefined ? "n/a" : data.replicas;
    document.getElementById("impact-cpu").textContent =
      data.cpu_utilization_pct === null || data.cpu_utilization_pct === undefined
        ? "n/a"
        : data.cpu_utilization_pct + "%";
    document.getElementById("impact-rps-total").textContent = fmtRate(data.request_rate_total);
    const byClass = data.request_rate_by_class || {};
    document.getElementById("impact-rps-cheap").textContent = fmtRate(byClass.cheap);
    document.getElementById("impact-rps-medium").textContent = fmtRate(byClass.medium);
    document.getElementById("impact-rps-expensive").textContent = fmtRate(byClass.expensive);
    document.getElementById("impact-cost-rate").textContent = fmtRate(data.cost_rate_per_minute);
    document.getElementById("impact-cost-total").textContent = fmtRate(data.estimated_cost_session);

    if (data.kubernetes_available && data.prometheus_available) {
      badge.textContent = "live";
      badge.className = "impact-badge ok";
    } else {
      badge.textContent = "partially connected";
      badge.className = "impact-badge";
    }

    if (lastReplicas !== null && data.replicas !== null && data.replicas > lastReplicas) {
      const strip = document.getElementById("impact-strip");
      strip.classList.remove("scaling-pulse");
      // eslint-disable-next-line no-unused-expressions
      void strip.offsetWidth; // restart the CSS animation
      strip.classList.add("scaling-pulse");
    }
    lastReplicas = data.replicas;

    renderPods(data);
    renderMeters(data);
    renderBanner(data);
    appendFeed(data);
  }

  async function pollImpact() {
    try {
      const res = await fetch(DASHBOARD_API + "/api/storefront/impact");
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      dashboardReachable = true;
      updateImpactStrip(data);
    } catch (e) {
      dashboardReachable = false;
      updateImpactStrip(null);
    }
  }

  // ------------------------------------------------------- attack theatre --
  // Everything below reads/reacts to real signals returned by
  // /api/storefront/impact (live_impact.py) — replica counts, Prometheus
  // rates, and real per-poll counter deltas. The one exception is the
  // banner's classification (renderBanner): that is a simple, illustrative
  // threshold on expensive_endpoint_ratio/total rate for this page only,
  // NOT the trained CASCADE LightGBM model's verdict — the model's actual
  // evaluated predictions live in the dashboard (webapp/frontend), trained
  // on proper rolling-window features, not this single live number.

  function renderPods(data) {
    const row = document.getElementById("pods-row");
    const caption = document.getElementById("pods-caption");
    if (!data || !data.kubernetes_available) {
      row.innerHTML = '<div class="pod pod-unknown">?</div>';
      caption.textContent =
        data && data.kubernetes_available === false
          ? "No Kubernetes cluster connected — deploy via kubernetes/ (k3d) to see live autoscaling here."
          : "";
      return;
    }
    const replicas = data.replicas || 0;
    const max = data.max_replicas || Math.max(replicas, 1);
    row.innerHTML = "";
    for (let i = 0; i < max; i++) {
      const pod = document.createElement("div");
      pod.className = "pod " + (i < replicas ? "pod-active" : "pod-empty");
      pod.textContent = "▮";
      row.appendChild(pod);
    }
    caption.textContent =
      replicas + " / " + max + " replicas" + (data.min_replicas != null ? " (min " + data.min_replicas + ")" : "");
  }

  const METER_MAX_RPS = 30; // cosmetic visual scale cap, not a threshold

  function renderMeters(data) {
    const byClass = (data && data.request_rate_by_class) || {};
    for (const cls of ["cheap", "medium", "expensive"]) {
      const rate = byClass[cls];
      const fill = document.getElementById("meter-" + cls);
      const valueEl = document.getElementById("meter-" + cls + "-value");
      if (rate === null || rate === undefined) {
        fill.style.width = "0%";
        valueEl.textContent = "n/a";
        continue;
      }
      const pct = Math.max(rate > 0 ? 3 : 0, Math.min(100, (rate / METER_MAX_RPS) * 100));
      fill.style.width = pct + "%";
      valueEl.textContent = rate.toFixed(2);
    }
  }

  function renderBanner(data) {
    const el = document.getElementById("theatre-banner");
    if (!data || !data.prometheus_available) {
      el.textContent = "Traffic data unavailable";
      el.className = "theatre-banner unknown";
      return;
    }
    const total = data.request_rate_total || 0;
    const ratio = data.expensive_endpoint_ratio;
    if (total < 1) {
      el.textContent = "Quiet — baseline traffic";
      el.className = "theatre-banner quiet";
    } else if (ratio !== null && ratio !== undefined && ratio > 0.6) {
      el.textContent = "Concentrated on the expensive endpoint (cost-heavy pattern)";
      el.className = "theatre-banner hot";
    } else if (total > 15) {
      el.textContent = "Broad surge across endpoints (flash-crowd-like pattern)";
      el.className = "theatre-banner surge";
    } else {
      el.textContent = "Elevated traffic";
      el.className = "theatre-banner warm";
    }
  }

  const FEED_MAX_LINES = 40;

  function appendFeed(data) {
    const feed = document.getElementById("traffic-feed");
    const deltas = data && data.request_delta_by_class;
    if (!deltas) return; // no baseline yet (first poll after backend restart), or Prometheus down
    const parts = [];
    for (const cls of ["expensive", "medium", "cheap"]) {
      const d = deltas[cls];
      if (d && d > 0) parts.push("+" + Math.round(d) + " " + cls);
    }
    if (parts.length === 0) return;
    const line = document.createElement("div");
    const time = new Date().toLocaleTimeString();
    const expensiveShare = deltas.expensive || 0;
    const otherShare = (deltas.cheap || 0) + (deltas.medium || 0);
    const flagged = expensiveShare > 0 && expensiveShare >= otherShare;
    line.className = "feed-line" + (flagged ? " feed-line-hot" : "");
    line.textContent = "[" + time + "] " + parts.join(" · ");
    feed.prepend(line);
    while (feed.children.length > FEED_MAX_LINES) {
      feed.removeChild(feed.lastChild);
    }
  }

  // --------------------------------------------------------- simulate ui --
  // Starts/stops a REAL live traffic scenario against this app via the
  // dashboard backend's existing Attack/Flash Crowd Simulator
  // (webapp/backend/scenario_builder.py + runner.py) — the same code path
  // the dashboard's own simulator pages use. Nothing here is simulated in
  // the browser.

  let lastSimKind = null;

  function setSimButtonsRunning(running) {
    document.getElementById("sim-flash-crowd-btn").disabled = running || !dashboardReachable;
    document.getElementById("sim-attack-btn").disabled = running || !dashboardReachable;
    document.getElementById("sim-stop-btn").disabled = !running;
  }

  function updateSimAvailability() {
    if (!dashboardReachable) {
      document.getElementById("sim-flash-crowd-btn").disabled = true;
      document.getElementById("sim-attack-btn").disabled = true;
      document.getElementById("sim-stop-btn").disabled = true;
      const status = document.getElementById("sim-status");
      status.className = "status-line err";
      status.textContent = "Dashboard backend (port 8500) unreachable — simulate controls disabled.";
    }
  }

  async function startSimulation(kind) {
    if (!dashboardReachable) return;
    const durationInput = document.getElementById("sim-duration");
    const duration = Math.max(10, Math.min(300, Number(durationInput.value) || 60));
    durationInput.value = duration;
    const status = document.getElementById("sim-status");
    setSimButtonsRunning(true);
    status.className = "status-line";
    status.textContent = "Starting " + kind + "…";
    try {
      const res = await fetch(DASHBOARD_API + "/api/simulator/" + kind + "/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_seconds: duration }),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(res.status + " " + body);
      }
      const data = await res.json();
      lastSimKind = kind;
      status.className = "status-line ok";
      status.textContent = "Running " + data.experiment_id;
    } catch (e) {
      status.className = "status-line err";
      status.textContent = "Failed to start: " + e.message;
      setSimButtonsRunning(false);
    }
  }

  async function stopSimulation() {
    const kind = lastSimKind || "attack";
    try {
      await fetch(DASHBOARD_API + "/api/simulator/" + kind + "/stop", { method: "POST" });
    } catch (e) {
      // Status poll will reconcile the button state regardless.
    }
  }

  async function pollSimStatus() {
    if (!dashboardReachable) return;
    try {
      const res = await fetch(DASHBOARD_API + "/api/demo/status");
      if (!res.ok) return;
      const data = await res.json();
      const status = document.getElementById("sim-status");
      const running = data.state === "RUNNING" || data.state === "STARTING" || data.state === "SUMMARIZING";
      setSimButtonsRunning(running);
      if (running) {
        status.className = "status-line ok";
        const elapsed = data.elapsed_seconds != null ? Math.round(data.elapsed_seconds) : "?";
        const dur = data.duration_seconds != null ? data.duration_seconds : "?";
        status.textContent = data.state + " — " + (data.experiment_id || "") + " (" + elapsed + "s / " + dur + "s)";
      } else if (data.state === "COMPLETED") {
        status.className = "status-line ok";
        status.textContent = "Completed: " + (data.experiment_id || "");
      } else if (data.state === "FAILED") {
        status.className = "status-line err";
        status.textContent = "Failed: " + (data.error || "");
      } else if (data.state === "CANCELLED") {
        status.className = "status-line";
        status.textContent = "Cancelled.";
      }
    } catch (e) {
      // Leave the last-known status displayed rather than flashing errors.
    }
  }

  // ------------------------------------------------------------- wiring --

  document.getElementById("search-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = document.getElementById("search-input").value.trim();
    if (q) doSearch(q);
  });

  document.getElementById("complexity-range").addEventListener("input", (ev) => {
    document.getElementById("complexity-value").textContent = ev.target.value;
  });

  document.getElementById("generate-report-btn").addEventListener("click", generateReport);
  document.getElementById("sim-flash-crowd-btn").addEventListener("click", () => startSimulation("flash-crowd"));
  document.getElementById("sim-attack-btn").addEventListener("click", () => startSimulation("attack"));
  document.getElementById("sim-stop-btn").addEventListener("click", stopSimulation);

  loadHome();
  pollImpact();
  pollSimStatus();
  setInterval(pollImpact, 2000);
  setInterval(pollSimStatus, 2000);
})();
