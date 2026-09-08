const REFRESH_MS = 45000;
let currentRecommendation = null;
let chart, candleSeries, ema20Series, ema50Series;
let currentTF = "H1";
let currentJournalTab = "open";

// ---------------------------------------------------------------------------
// Utilitaires
// ---------------------------------------------------------------------------

function fmt(n, decimals = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "--";
  return Number(n).toLocaleString("fr-FR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function dirLabel(d) {
  return { long: "ACHAT", short: "VENTE", wait: "ATTENTE" }[d] || d;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Erreur ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Chargement statut + recommandation
// ---------------------------------------------------------------------------

async function loadStatus() {
  const status = await api("/api/status");
  const badge = document.getElementById("mode-badge");
  badge.textContent = status.mode === "live" ? "LIVE" : "DEMO";
  badge.className = "badge " + (status.mode === "live" ? "live" : "demo");
}

async function loadRecommendation() {
  try {
    const rec = await api("/api/recommendation");
    currentRecommendation = rec;
    renderRecommendation(rec);
  } catch (err) {
    document.getElementById("signal-headline").textContent = "Erreur lors du chargement : " + err.message;
  }
}

function renderRecommendation(rec) {
  document.getElementById("price-value").textContent = rec.price && rec.price.mid ? fmt(rec.price.mid, 2) : "--";

  const dirEl = document.getElementById("signal-direction");
  dirEl.textContent = dirLabel(rec.direction);
  dirEl.className = "signal-direction " + rec.direction;

  document.getElementById("confidence-fill").style.width = Math.max(4, rec.confidence) + "%";
  document.getElementById("confidence-label").textContent = `confiance ${fmt(rec.confidence, 0)}/100`;
  document.getElementById("signal-headline").textContent = rec.rationale;

  document.getElementById("lvl-entry").textContent = rec.entry !== null ? fmt(rec.entry, 2) : "--";
  document.getElementById("lvl-sl").textContent = rec.stop_loss !== null ? fmt(rec.stop_loss, 2) : "--";
  document.getElementById("lvl-tp").textContent = rec.take_profit !== null ? fmt(rec.take_profit, 2) : "--";
  const rr = rec.entry && rec.stop_loss && rec.take_profit
    ? Math.abs((rec.take_profit - rec.entry) / (rec.entry - rec.stop_loss)).toFixed(2)
    : null;
  document.getElementById("lvl-rr").textContent = rr ? `1:${rr}` : "--";

  const logBtn = document.getElementById("log-trade-btn");
  logBtn.disabled = rec.direction === "wait";

  const riskBanner = document.getElementById("risk-banner");
  if (rec.risk_warning) {
    riskBanner.classList.remove("hidden");
    riskBanner.textContent = "⚠️ " + (rec.macro ? rec.macro.rationale : "Evenement macro a risque imminent.");
  } else {
    riskBanner.classList.add("hidden");
  }

  renderStrategyCards(rec.strategies || []);
  renderMacro(rec);
}

function renderStrategyCards(strategies) {
  const grid = document.getElementById("strategy-grid");
  grid.innerHTML = "";
  strategies.forEach((s) => {
    const card = document.createElement("div");
    card.className = "strategy-card";
    card.innerHTML = `
      <h3>${s.name}</h3>
      <span class="strategy-badge ${s.direction}">${dirLabel(s.direction)}</span>
      <div class="strategy-conf">confiance ${fmt(s.confidence, 0)}/100${s.risk_reward ? ` &middot; R:R 1:${s.risk_reward}` : ""}</div>
      <p>${s.rationale}</p>
    `;
    grid.appendChild(card);
  });
}

function renderMacro(rec) {
  const usd = rec.usd_index;
  document.getElementById("usd-trend").textContent = usd
    ? { strengthening: "En hausse", weakening: "En baisse", flat: "Stable" }[usd.trend] + ` (${usd.change_pct > 0 ? "+" : ""}${fmt(usd.change_pct, 2)}%)`
    : "Indisponible";

  const y = rec.real_yield;
  document.getElementById("yield-trend").textContent = y && y.value !== null
    ? `${fmt(y.value, 2)}% (${{ rising: "en hausse", falling: "en baisse", flat: "stable" }[y.trend] || "n/d"})`
    : "Indisponible (cle FRED manquante)";

  const list = document.getElementById("risk-events-list");
  const events = rec.risk_events || [];
  if (events.length === 0) {
    list.innerHTML = `<li class="muted">Aucun evenement a risque dans les 48h</li>`;
  } else {
    list.innerHTML = events
      .map((e) => `<li class="${e.impact === "high" ? "impact-high" : ""}">${e.event} -- dans ${fmt(e.hours_until, 1)}h</li>`)
      .join("");
  }
}

// ---------------------------------------------------------------------------
// Graphique (lightweight-charts)
// ---------------------------------------------------------------------------

function initChart() {
  const container = document.getElementById("chart-container");
  chart = LightweightCharts.createChart(container, {
    layout: { background: { color: "#131722" }, textColor: "#8b91a7" },
    grid: { vertLines: { color: "#232838" }, horzLines: { color: "#232838" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "#232838" },
    width: container.clientWidth,
    height: 380,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#2ecc71", downColor: "#ef4444", borderVisible: false,
    wickUpColor: "#2ecc71", wickDownColor: "#ef4444",
  });
  ema20Series = chart.addLineSeries({ color: "#d4af37", lineWidth: 1 });
  ema50Series = chart.addLineSeries({ color: "#5b9bd5", lineWidth: 1 });

  window.addEventListener("resize", () => {
    chart.applyOptions({ width: container.clientWidth });
  });
}

function ema(values, period) {
  const k = 2 / (period + 1);
  const out = [];
  let prev = values[0];
  values.forEach((v, i) => {
    prev = i === 0 ? v : v * k + prev * (1 - k);
    out.push(prev);
  });
  return out;
}

async function loadChart(tf) {
  const candles = await api(`/api/candles?granularity=${tf}&count=250`);
  const candleData = candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close }));
  candleSeries.setData(candleData);

  const closes = candles.map((c) => c.close);
  const e20 = ema(closes, 20);
  const e50 = ema(closes, 50);
  ema20Series.setData(candles.map((c, i) => ({ time: c.time, value: e20[i] })));
  ema50Series.setData(candles.map((c, i) => ({ time: c.time, value: e50[i] })));
  chart.timeScale().fitContent();
}

// ---------------------------------------------------------------------------
// Journal
// ---------------------------------------------------------------------------

async function loadJournal() {
  const [trades, stats] = await Promise.all([
    api(`/api/journal/trades?status=${currentJournalTab}`),
    api("/api/journal/stats"),
  ]);
  renderStats(stats);
  renderTrades(trades);
}

function renderStats(stats) {
  const row = document.getElementById("stats-row");
  const boxes = [
    ["Trades cloturs", stats.total_closed_trades],
    ["Taux de reussite", stats.win_rate !== null ? stats.win_rate + "%" : "--"],
    ["P&L total", stats.total_pnl !== null ? fmt(stats.total_pnl, 2) + " $" : "--"],
    ["R moyen", stats.avg_r_multiple !== null ? stats.avg_r_multiple + "R" : "--"],
  ];
  row.innerHTML = boxes
    .map(([label, value]) => `<div class="stat-box"><span class="stat-label">${label}</span><span class="stat-value">${value}</span></div>`)
    .join("");
}

function renderTrades(trades) {
  const tbody = document.getElementById("trades-tbody");
  if (trades.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" class="muted">Aucun trade dans cette categorie.</td></tr>`;
    return;
  }
  tbody.innerHTML = trades
    .map((t) => {
      const strategies = JSON.parse(t.triggering_strategies || "[]").join(" + ") || "--";
      return `
      <tr>
        <td>${new Date(t.opened_at).toLocaleString("fr-FR")}</td>
        <td class="dir-${t.direction}">${dirLabel(t.direction)}</td>
        <td>${strategies}</td>
        <td>${fmt(t.confidence_at_signal, 0)}</td>
        <td>${fmt(t.actual_entry ?? t.recommended_entry, 2)}</td>
        <td>${fmt(t.actual_sl ?? t.recommended_sl, 2)}</td>
        <td>${fmt(t.actual_tp ?? t.recommended_tp, 2)}</td>
        <td>${t.actual_exit_price !== null ? fmt(t.actual_exit_price, 2) : "--"}</td>
        <td class="result-${t.result}">${t.result}</td>
        <td class="row-actions">
          ${t.result === "open" ? `<button class="btn" onclick="openExecutionModal(${t.id})">Executer</button>
          <button class="btn" onclick="openCloseModal(${t.id})">Cloturer</button>` : ""}
          <button class="btn btn-danger" onclick="deleteTrade(${t.id})">Suppr.</button>
        </td>
      </tr>`;
    })
    .join("");
}

async function deleteTrade(id) {
  if (!confirm("Supprimer ce trade du journal ?")) return;
  await api(`/api/journal/trades/${id}`, { method: "DELETE" });
  loadJournal();
}

// ---------------------------------------------------------------------------
// Modales
// ---------------------------------------------------------------------------

function showModal(html) {
  document.getElementById("modal").innerHTML = html;
  document.getElementById("modal-backdrop").classList.remove("hidden");
}
function closeModal() {
  document.getElementById("modal-backdrop").classList.add("hidden");
}

function openLogTradeModal() {
  if (!currentRecommendation || currentRecommendation.direction === "wait") return;
  const rec = currentRecommendation;
  const strategyNames = (rec.strategies || []).filter((s) => s.direction === rec.direction).map((s) => s.name);
  showModal(`
    <h3>Consigner ce trade</h3>
    <p class="muted">${dirLabel(rec.direction)} -- confiance ${fmt(rec.confidence, 0)}/100</p>
    <label>Notes (optionnel)</label>
    <textarea id="log-notes" rows="3" placeholder="Contexte, ressenti, taille prevue..."></textarea>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="submitLogTrade()">Consigner</button>
    </div>
  `);
  window._pendingLog = { rec, strategyNames };
}

async function submitLogTrade() {
  const { rec, strategyNames } = window._pendingLog;
  const notes = document.getElementById("log-notes").value;
  await api("/api/journal/trades", {
    method: "POST",
    body: JSON.stringify({
      direction: rec.direction,
      triggering_strategies: strategyNames,
      confidence_at_signal: rec.confidence,
      recommended_entry: rec.entry,
      recommended_sl: rec.stop_loss,
      recommended_tp: rec.take_profit,
      rationale_snapshot: rec.rationale,
      notes,
    }),
  });
  closeModal();
  currentJournalTab = "open";
  document.querySelectorAll("[data-journal]").forEach((b) => b.classList.toggle("active", b.dataset.journal === "open"));
  loadJournal();
}

function openExecutionModal(id) {
  showModal(`
    <h3>Enregistrer votre execution reelle</h3>
    <label>Prix d'entree reel</label>
    <input id="exec-entry" type="number" step="0.01">
    <label>Stop loss reel</label>
    <input id="exec-sl" type="number" step="0.01">
    <label>Take profit reel</label>
    <input id="exec-tp" type="number" step="0.01">
    <label>Taille (unites / onces)</label>
    <input id="exec-lot" type="number" step="0.01" value="1">
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="submitExecution(${id})">Enregistrer</button>
    </div>
  `);
}

async function submitExecution(id) {
  const body = {
    actual_entry: parseFloat(document.getElementById("exec-entry").value),
    actual_sl: parseFloat(document.getElementById("exec-sl").value) || null,
    actual_tp: parseFloat(document.getElementById("exec-tp").value) || null,
    lot_size: parseFloat(document.getElementById("exec-lot").value) || 1,
  };
  await api(`/api/journal/trades/${id}/execution`, { method: "PATCH", body: JSON.stringify(body) });
  closeModal();
  loadJournal();
}

function openCloseModal(id) {
  showModal(`
    <h3>Cloturer le trade</h3>
    <label>Prix de sortie reel</label>
    <input id="close-exit" type="number" step="0.01">
    <label>Notes (optionnel)</label>
    <textarea id="close-notes" rows="2"></textarea>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="submitClose(${id})">Cloturer</button>
    </div>
  `);
}

async function submitClose(id) {
  const body = {
    actual_exit_price: parseFloat(document.getElementById("close-exit").value),
    notes: document.getElementById("close-notes").value || null,
  };
  await api(`/api/journal/trades/${id}/close`, { method: "PATCH", body: JSON.stringify(body) });
  closeModal();
  loadJournal();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  initChart();
  await loadStatus();
  await loadRecommendation();
  await loadChart(currentTF);
  await loadJournal();

  document.getElementById("refresh-btn").addEventListener("click", loadRecommendation);
  document.getElementById("log-trade-btn").addEventListener("click", openLogTradeModal);
  document.getElementById("modal-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "modal-backdrop") closeModal();
  });

  document.querySelectorAll(".tf-btn[data-tf]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn[data-tf]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentTF = btn.dataset.tf;
      loadChart(currentTF);
    });
  });

  document.querySelectorAll(".tf-btn[data-journal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn[data-journal]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentJournalTab = btn.dataset.journal;
      loadJournal();
    });
  });

  setInterval(() => {
    loadRecommendation();
    loadChart(currentTF);
  }, REFRESH_MS);
});
