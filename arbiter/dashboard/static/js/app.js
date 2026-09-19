/**
 * ARBITER Real-Time Telemetry & MAB Dashboard Client
 */

class ArbiterDashboard {
  constructor() {
    this.ws = null;
    this.feedRows = [];
    this.arms = [];
    this.healthStatuses = [];
    this.stats = {
      spend24h: 0,
      totalRequests: 0,
      avgLatency: 0,
      avgQuality: 0
    };

    this.initElements();
    this.initTabs();
    this.initWebSocket();
    this.initEventListeners();
    this.loadHistoricalAnalytics();
  }

  initElements() {
    this.feedTbody = document.getElementById("feed-tbody");
    this.wsIndicator = document.getElementById("ws-indicator");
    this.wsStatusText = document.getElementById("ws-status-text");
    this.feedCount = document.getElementById("feed-count");
    this.sbSpend = document.getElementById("sb-spend");
    this.sbRequests = document.getElementById("sb-requests");
    this.valLatency = document.getElementById("val-latency");
    this.valQuality = document.getElementById("val-quality");
    this.valForecast = document.getElementById("val-forecast");
    this.armsContainer = document.getElementById("arms-container");
    this.healthContainer = document.getElementById("health-cards-container");
    this.chkAutoScroll = document.getElementById("chk-autoscroll");
  }

  initTabs() {
    document.querySelectorAll(".nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

        btn.classList.add("active");
        const tabId = btn.getAttribute("data-tab");
        const pane = document.getElementById(tabId);
        if (pane) pane.classList.add("active");

        if (tabId === "tab-analytics") {
          this.loadHistoricalAnalytics();
        } else if (tabId === "tab-bandit") {
          this.loadBanditArms();
        } else if (tabId === "tab-health") {
          this.loadHealth();
        }
      });
    });
  }

  initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8000";
    const wsUrl = `${protocol}//${host}/ws/dashboard`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.wsIndicator.className = "indicator connected";
        this.wsStatusText.textContent = "Connected";
      };

      this.ws.onclose = () => {
        this.wsIndicator.className = "indicator disconnected";
        this.wsStatusText.textContent = "Reconnecting...";
        setTimeout(() => this.initWebSocket(), 3000);
      };

      this.ws.onerror = () => {
        this.wsIndicator.className = "indicator disconnected";
        this.wsStatusText.textContent = "Disconnected";
      };

      this.ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data);
          this.handleEvent(event);
        } catch (e) {
          console.error("WS Parse error:", e);
        }
      };
    } catch (err) {
      console.warn("WebSocket could not connect, falling back to polling.", err);
    }
  }

  handleEvent(event) {
    if (event.event === "ping") return;

    if (event.event === "initial_snapshot") {
      if (event.data.feed) {
        event.data.feed.forEach(item => this.prependFeedRow(item));
      }
      if (event.data.health) {
        this.renderHealth(event.data.health);
      }
    } else if (event.event === "request_completed") {
      this.prependFeedRow(event.data);
      this.stats.totalRequests++;
      this.stats.spend24h += (event.data.actual_cost || 0);
      this.updateTopbarStats();
    } else if (event.event === "feedback_recorded") {
      this.updateFeedbackRow(event.data);
    }
  }

  prependFeedRow(item) {
    const tr = document.createElement("tr");
    const timeStr = item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    const reqIdShort = (item.id || item.request_id || "req-000").substring(0, 10);
    const costStr = `$${(item.actual_cost || 0).toFixed(5)}`;
    const latStr = `${item.latency_ms || 0} ms`;
    const qScore = item.quality_score !== undefined ? (item.quality_score).toFixed(2) : "—";
    const category = item.task_category || item.category || "conversation";
    const model = item.model || "—";
    const strategy = item.strategy || "auto";

    // Category tag style
    let tagClass = "tag-conv";
    if (category.includes("code")) tagClass = "tag-code";
    else if (category.includes("reason")) tagClass = "tag-reason";
    else if (category.includes("trans")) tagClass = "tag-trans";
    else if (category.includes("sum")) tagClass = "tag-sum";

    tr.innerHTML = `
      <td style="color: var(--text-muted); font-family: var(--font-mono);">${timeStr}</td>
      <td style="font-family: var(--font-mono);">${reqIdShort}</td>
      <td><span class="tag ${tagClass}">${category}</span></td>
      <td style="font-size: 11px; color: var(--accent-cyan); font-weight: 500;">${strategy}</td>
      <td><strong>${model}</strong></td>
      <td style="font-family: var(--font-mono);">${latStr}</td>
      <td style="font-family: var(--font-mono); color: var(--accent-amber);">${costStr}</td>
      <td><span style="font-weight: 600; color: ${item.quality_score >= 0.8 ? 'var(--accent-green)' : 'var(--accent-amber)'}">${qScore}</span></td>
      <td>
        <button class="fb-btn ${item.user_feedback === 1 ? 'rated-pos' : ''}" onclick="window.arbiterDashboard.submitFeedback('${item.id || item.request_id}', 1, this)">👍</button>
        <button class="fb-btn ${item.user_feedback === -1 ? 'rated-neg' : ''}" onclick="window.arbiterDashboard.submitFeedback('${item.id || item.request_id}', -1, this)">👎</button>
      </td>
    `;

    if (this.feedTbody.firstChild) {
      this.feedTbody.insertBefore(tr, this.feedTbody.firstChild);
    } else {
      this.feedTbody.appendChild(tr);
    }

    // Keep max 100 rows
    if (this.feedTbody.children.length > 100) {
      this.feedTbody.removeChild(this.feedTbody.lastChild);
    }

    this.feedCount.textContent = this.feedTbody.children.length;
  }

  async submitFeedback(requestId, rating, btn) {
    try {
      const resp = await fetch("/v1/arbiter/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, rating: rating })
      });
      if (resp.ok) {
        btn.classList.add(rating === 1 ? "rated-pos" : "rated-neg");
        btn.parentElement.querySelectorAll(".fb-btn").forEach(b => {
          if (b !== btn) b.className = "fb-btn";
        });
      }
    } catch (e) {
      console.error("Failed to submit feedback:", e);
    }
  }

  updateFeedbackRow(data) {
    // Optionally refresh bandit tab
    if (document.getElementById("tab-bandit").classList.contains("active")) {
      this.loadBanditArms();
    }
  }

  updateTopbarStats() {
    this.sbSpend.textContent = `$${this.stats.spend24h.toFixed(4)}`;
    this.sbRequests.textContent = this.stats.totalRequests;
  }

  async loadHistoricalAnalytics() {
    try {
      const resp = await fetch("/v1/arbiter/analytics/summary");
      if (!resp.ok) return;
      const data = await resp.json();

      // Forecast cards
      if (data.forecast) {
        this.valForecast.textContent = `$${data.forecast.projected_monthly_cost.toFixed(2)}`;
        document.getElementById("val-forecast-sub").textContent = `${data.forecast.requests_last_24h * 30} projected reqs`;
      }

      // Win rates
      this.renderWinRates(data.win_rates || []);

      // Category spend
      this.renderCategorySpend(data.cost_by_category || []);

      // Latency percentiles
      this.renderLatencyTable(data.latencies || {});

      // Quality heatmap
      this.renderHeatmap(data.quality_heatmap || []);
    } catch (e) {
      console.error("Failed to load analytics:", e);
    }
  }

  renderWinRates(winRates) {
    const container = document.getElementById("chart-winrates");
    container.innerHTML = "";
    if (!winRates.length) {
      container.innerHTML = "<p style='color: var(--text-muted); font-size: 13px;'>No requests recorded yet.</p>";
      return;
    }

    winRates.slice(0, 6).forEach(wr => {
      const pct = (wr.win_rate * 100).toFixed(1);
      const row = document.createElement("div");
      row.className = "bar-row";
      row.innerHTML = `
        <span class="bar-label" title="${wr.model}">${wr.model}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${pct}%; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-blue));"></div>
        </div>
        <span class="bar-val">${pct}%</span>
      `;
      container.appendChild(row);
    });
  }

  renderCategorySpend(categories) {
    const container = document.getElementById("chart-categories");
    container.innerHTML = "";
    if (!categories.length) {
      container.innerHTML = "<p style='color: var(--text-muted); font-size: 13px;'>No category spending recorded yet.</p>";
      return;
    }

    const maxCost = Math.max(...categories.map(c => c.total_cost || 0.001), 0.001);
    categories.forEach(cat => {
      const widthPct = Math.min(100, Math.max(5, (cat.total_cost / maxCost) * 100));
      const row = document.createElement("div");
      row.className = "bar-row";
      row.innerHTML = `
        <span class="bar-label">${cat.task_category}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${widthPct}%; background: linear-gradient(90deg, var(--accent-purple), var(--accent-rose));"></div>
        </div>
        <span class="bar-val">$${(cat.total_cost || 0).toFixed(4)}</span>
      `;
      container.appendChild(row);
    });
  }

  renderLatencyTable(latencies) {
    const tbody = document.getElementById("latency-tbody");
    tbody.innerHTML = "";
    for (const [model, stats] of Object.entries(latencies)) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${model}</strong></td>
        <td>${stats.count}</td>
        <td style="color: var(--accent-green); font-weight: 600;">${stats.p50.toFixed(0)} ms</td>
        <td>${stats.p95.toFixed(0)} ms</td>
        <td style="color: var(--accent-rose);">${stats.p99.toFixed(0)} ms</td>
        <td>${stats.min.toFixed(0)} ms</td>
        <td>${stats.max.toFixed(0)} ms</td>
      `;
      tbody.appendChild(tr);
    }
  }

  renderHeatmap(heatmapData) {
    const container = document.getElementById("heatmap-container");
    if (!heatmapData.length) {
      container.innerHTML = "<p style='color: var(--text-muted); font-size: 13px;'>Heatmap data accumulating...</p>";
      return;
    }

    let html = "<table class='data-table'><thead><tr><th>Category</th><th>Model</th><th>Avg Quality</th><th>Count</th></tr></thead><tbody>";
    heatmapData.forEach(h => {
      const color = h.avg_quality >= 0.8 ? 'var(--accent-green)' : 'var(--accent-amber)';
      html += `
        <tr>
          <td><span class="tag tag-code">${h.task_category}</span></td>
          <td><strong>${h.model}</strong></td>
          <td style="color: ${color}; font-weight: 600;">${(h.avg_quality).toFixed(3)}</td>
          <td>${h.sample_count}</td>
        </tr>
      `;
    });
    html += "</tbody></table>";
    container.innerHTML = html;
  }

  async loadBanditArms() {
    try {
      const resp = await fetch("/v1/arbiter/analytics/bandit");
      if (!resp.ok) return;
      const arms = await resp.json();
      this.renderBanditArms(arms);
    } catch (e) {
      console.error("Failed to load bandit arms:", e);
    }
  }

  renderBanditArms(arms) {
    this.armsContainer.innerHTML = "";
    if (!arms.length) {
      this.armsContainer.innerHTML = "<p style='color: var(--text-muted); font-size: 13px;'>No active bandit arms initialized.</p>";
      return;
    }

    arms.forEach((arm, idx) => {
      const card = document.createElement("div");
      card.className = "arm-card";
      const canvasId = `arm-canvas-${idx}`;

      card.innerHTML = `
        <div class="arm-title">
          <span>${arm.model}</span>
          <span style="color: var(--accent-cyan); font-family: var(--font-mono);">${(arm.expected_win_rate * 100).toFixed(1)}%</span>
        </div>
        <div class="arm-category">${arm.task_category}</div>
        <div class="arm-canvas-wrap">
          <canvas id="${canvasId}" width="260" height="80"></canvas>
        </div>
        <div class="arm-stats">
          <span>α = ${arm.alpha}</span>
          <span>β = ${arm.beta}</span>
          <span>N = ${arm.trials}</span>
        </div>
      `;
      this.armsContainer.appendChild(card);

      // Draw Beta PDF curve
      setTimeout(() => this.drawBetaPDF(canvasId, arm.pdf_curve), 50);
    });
  }

  drawBetaPDF(canvasId, curve) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !curve || !curve.length) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const maxY = Math.max(...curve.map(p => p.y), 1.0);
    const pad = 6;
    const w = canvas.width - pad * 2;
    const h = canvas.height - pad * 2;

    ctx.beginPath();
    ctx.strokeStyle = "#00f2fe";
    ctx.lineWidth = 2;

    curve.forEach((p, i) => {
      const cx = pad + p.x * w;
      const cy = canvas.height - pad - (p.y / maxY) * h;
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });

    ctx.stroke();

    // Fill gradient
    ctx.lineTo(canvas.width - pad, canvas.height - pad);
    ctx.lineTo(pad, canvas.height - pad);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
    grad.addColorStop(0, "rgba(0, 242, 254, 0.25)");
    grad.addColorStop(1, "rgba(0, 242, 254, 0.0)");
    ctx.fillStyle = grad;
    ctx.fill();
  }

  async loadHealth() {
    try {
      const resp = await fetch("/v1/arbiter/health");
      if (!resp.ok) return;
      const statuses = await resp.json();
      this.renderHealth(statuses);
    } catch (e) {
      console.error("Failed to load health:", e);
    }
  }

  renderHealth(statuses) {
    this.healthContainer.innerHTML = "";
    statuses.forEach(st => {
      const card = document.createElement("div");
      card.className = "card health-card";
      const circuitLower = (st.circuit_state || "CLOSED").toLowerCase();
      const rpmPct = Math.round((st.rpm_used_ratio || 0) * 100);
      const tpmPct = Math.round((st.tpm_used_ratio || 0) * 100);

      card.innerHTML = `
        <div class="card-header">
          <h3>${st.provider.toUpperCase()}</h3>
          <span class="circuit-tag ${circuitLower}">${st.circuit_state}</span>
        </div>
        <div class="utilization-meter">
          <div class="meter-label">
            <span>RPM Limit Utilization</span>
            <span>${rpmPct}%</span>
          </div>
          <div class="meter-track">
            <div class="meter-fill" style="width: ${rpmPct}%;"></div>
          </div>
        </div>
        <div class="utilization-meter">
          <div class="meter-label">
            <span>TPM Limit Utilization</span>
            <span>${tpmPct}%</span>
          </div>
          <div class="meter-track">
            <div class="meter-fill" style="width: ${tpmPct}%; background: var(--accent-purple);"></div>
          </div>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
          Latency: <strong style="color: #fff;">${st.latency_ms || '—'} ms</strong> | Status: ${st.is_healthy ? '🟢 Healthy' : '🔴 Degraded'}
        </div>
      `;
      this.healthContainer.appendChild(card);
    });
  }

  initEventListeners() {
    // Simulator controls
    const slider = document.getElementById("sim-explore-slider");
    const valLabel = document.getElementById("sim-explore-val");
    if (slider && valLabel) {
      slider.addEventListener("input", (e) => {
        valLabel.textContent = `${e.target.value}%`;
      });
    }

    const decaySlider = document.getElementById("sim-decay-slider");
    const decayVal = document.getElementById("sim-decay-val");
    if (decaySlider && decayVal) {
      decaySlider.addEventListener("input", (e) => {
        decayVal.textContent = `${e.target.value}h`;
      });
    }

    // Test query execution
    const btnSubmit = document.getElementById("btn-submit-test");
    const resultBox = document.getElementById("test-result-output");
    if (btnSubmit && resultBox) {
      btnSubmit.addEventListener("click", async () => {
        const strat = document.getElementById("test-strategy-select").value;
        const budget = parseFloat(document.getElementById("test-budget-input").value) || null;
        const prompt = document.getElementById("test-prompt-input").value;

        btnSubmit.disabled = true;
        btnSubmit.textContent = "Routing request...";
        resultBox.style.display = "block";
        resultBox.textContent = "Sending request to /v1/chat/completions...";

        try {
          const resp = await fetch("/v1/chat/completions", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Arbiter-Strategy": strat,
              ...(budget ? { "X-Arbiter-Budget": budget.toString() } : {})
            },
            body: JSON.stringify({
              messages: [{ role: "user", content: prompt }]
            })
          });

          const data = await resp.json();
          resultBox.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
          resultBox.textContent = `Error: ${err.message}`;
        } finally {
          btnSubmit.disabled = false;
          btnSubmit.textContent = "Execute via /v1/chat/completions";
        }
      });
    }

    const btnTestModal = document.getElementById("btn-test-request");
    if (btnTestModal) {
      btnTestModal.addEventListener("click", () => {
        const healthBtn = document.querySelector(".nav-item[data-tab='tab-health']");
        if (healthBtn) healthBtn.click();
        const testConsole = document.querySelector(".test-modal-card");
        if (testConsole) testConsole.scrollIntoView({ behavior: "smooth" });
      });
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.arbiterDashboard = new ArbiterDashboard();
});
