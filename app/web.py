import threading

from flask import Flask, jsonify, render_template_string

from app.history import load_history, load_missing_items
from app.runner import clear_missing_items, retry_item, run_scan_and_record
from app.state import AppState

INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kongflix Metadata</title>
<style>
  :root {
    --bg: #14141f;
    --bg-elev: #1c1c2b;
    --bg-elev-2: #232335;
    --border: #2e2e44;
    --text: #eceaf7;
    --text-dim: #9c99b8;
    --accent: #8b7fd6;
    --accent-strong: #6f5fd0;
    --accent-soft: rgba(139, 127, 214, 0.15);
    --good: #4fd6a0;
    --bad: #e8697d;
    --radius: 12px;
    --shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 2.5rem 1.5rem 4rem;
    background: radial-gradient(circle at 10% 0%, #1b1b30 0%, var(--bg) 55%);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    min-height: 100vh;
  }
  .wrap { max-width: 1200px; margin: 0 auto; }

  header { display: flex; align-items: center; gap: 0.9rem; margin-bottom: 2rem; }
  header .logo { width: 44px; height: 44px; flex-shrink: 0; }
  header h1 { font-size: 1.5rem; margin: 0; letter-spacing: -0.01em; }
  header p { margin: 0.15rem 0 0; color: var(--text-dim); font-size: 0.88rem; }

  .card {
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }

  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1.5rem;
  }
  .status-left { display: flex; align-items: center; gap: 0.7rem; }
  .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--text-dim);
    box-shadow: 0 0 0 0 rgba(0,0,0,0);
  }
  .dot.idle { background: var(--text-dim); }
  .dot.ok { background: var(--good); }
  .dot.scanning {
    background: var(--accent);
    animation: pulse 1.4s ease-in-out infinite;
  }
  .dot.error { background: var(--bad); }
  @keyframes pulse {
    0%   { box-shadow: 0 0 0 0 var(--accent-soft); }
    70%  { box-shadow: 0 0 0 9px rgba(139, 127, 214, 0); }
    100% { box-shadow: 0 0 0 0 rgba(139, 127, 214, 0); }
  }
  .status-text .title { font-weight: 600; font-size: 0.98rem; }
  .status-text .subtitle { color: var(--text-dim); font-size: 0.82rem; margin-top: 0.1rem; }

  button.scan-btn {
    display: inline-flex; align-items: center; gap: 0.5rem;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
    color: white; border: none; border-radius: 9px;
    padding: 0.65rem 1.15rem; font-size: 0.92rem; font-weight: 600;
    cursor: pointer; transition: transform 0.12s ease, box-shadow 0.12s ease, opacity 0.12s ease;
    box-shadow: 0 4px 14px rgba(111, 95, 208, 0.35);
  }
  button.scan-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(111, 95, 208, 0.45); }
  button.scan-btn:active:not(:disabled) { transform: translateY(0); }
  button.scan-btn:disabled { opacity: 0.55; cursor: not-allowed; box-shadow: none; }

  .spinner {
    width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.35);
    border-top-color: white;
    animation: spin 0.7s linear infinite;
    display: none;
  }
  .spinner.show { display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .stats {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.9rem;
    margin-bottom: 1.5rem;
  }
  .stat {
    padding: 1rem 0.9rem;
    text-align: left;
  }
  .stat .value { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }
  .stat .label { color: var(--text-dim); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.15rem; }
  .stat.flagged .value { color: var(--accent); }
  .stat.failed .value { color: var(--bad); }
  .stat.refreshed .value { color: var(--good); }

  .section-title {
    font-size: 0.95rem; font-weight: 600; color: var(--text-dim);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin: 0 0 0.8rem 0.1rem;
  }

  .history-card { padding: 0.3rem; overflow: hidden; }
  .table-scroll { overflow-x: auto; }
  table { width: 100%; min-width: 640px; border-collapse: collapse; }
  thead th {
    text-align: left; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--text-dim); font-weight: 600;
    padding: 0.7rem 1rem; border-bottom: 1px solid var(--border);
  }
  tbody td { padding: 0.7rem 1rem; font-size: 0.88rem; border-bottom: 1px solid var(--border); }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover { background: var(--bg-elev-2); }
  td.error-cell { color: var(--bad); font-weight: 500; }
  .badge {
    display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
    font-size: 0.75rem; font-weight: 600;
  }
  .badge.zero { background: rgba(156, 153, 184, 0.15); color: var(--text-dim); }
  .badge.nonzero-bad { background: rgba(232, 105, 125, 0.15); color: var(--bad); }
  .badge.nonzero-good { background: rgba(79, 214, 160, 0.15); color: var(--good); }

  .empty-state {
    padding: 2.5rem 1rem; text-align: center; color: var(--text-dim); font-size: 0.9rem;
  }
  .filter-input {
    width: 100%;
    padding: 0.6rem 0.9rem;
    margin-bottom: 0.9rem;
    background: var(--bg-elev-2);
    border: 1px solid var(--border);
    border-radius: 9px;
    color: var(--text);
    font-size: 0.88rem;
  }
  .filter-input::placeholder { color: var(--text-dim); }
  .filter-input:focus { outline: none; border-color: var(--accent); }
  .type-tag {
    font-size: 0.72rem; color: var(--text-dim); background: rgba(156, 153, 184, 0.12);
    padding: 0.1rem 0.45rem; border-radius: 6px;
  }
  .series-name {
    font-size: 0.76rem; color: var(--text-dim); margin-top: 0.15rem;
  }
  .pagination {
    display: flex; align-items: center; justify-content: center; gap: 1rem;
    padding: 0.8rem 1rem; border-top: 1px solid var(--border);
  }
  .page-btn {
    background: var(--bg-elev-2); border: 1px solid var(--border); color: var(--text);
    padding: 0.4rem 0.9rem; border-radius: 8px; font-size: 0.82rem; cursor: pointer;
    transition: background 0.12s ease;
  }
  .page-btn:hover:not(:disabled) { background: var(--accent-soft); }
  .page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .page-info { color: var(--text-dim); font-size: 0.82rem; }
  .retry-btn {
    background: var(--bg-elev-2); border: 1px solid var(--border); color: var(--accent);
    padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.72rem; cursor: pointer;
    margin-left: 0.5rem;
  }
  .retry-btn:hover { background: var(--accent-soft); }
  .retry-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .missing-actions {
    display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.9rem;
  }
  .missing-actions .filter-input { margin-bottom: 0; flex: 1; }
  .clear-btn {
    background: var(--bg-elev-2); border: 1px solid var(--border); color: var(--bad);
    padding: 0.6rem 0.9rem; border-radius: 9px; font-size: 0.85rem; cursor: pointer;
    white-space: nowrap;
  }
  .clear-btn:hover { background: rgba(232, 105, 125, 0.12); }
  .watch-hint {
    color: var(--text-dim); font-size: 0.82rem; margin: -0.4rem 0 0.9rem 0.1rem;
  }
  .missing-tag {
    display: inline-block; font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 6px;
    background: rgba(139, 127, 214, 0.15); color: var(--accent); margin-right: 0.3rem;
  }
  .badge.status-refreshed { background: rgba(79, 214, 160, 0.15); color: var(--good); }
  .badge.status-failed { background: rgba(232, 105, 125, 0.15); color: var(--bad); }
  .badge.status-pending { background: rgba(156, 153, 184, 0.15); color: var(--text-dim); }

  .toast {
    position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%) translateY(8px);
    background: var(--bg-elev-2); border: 1px solid var(--border); color: var(--text);
    padding: 0.7rem 1.1rem; border-radius: 9px; font-size: 0.85rem;
    box-shadow: var(--shadow); opacity: 0; pointer-events: none;
    transition: opacity 0.2s ease, transform 0.2s ease;
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

  @media (max-width: 620px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .status-bar { flex-direction: column; align-items: stretch; }
  }
</style>
</head>
<body>
<div class="wrap">

  <header>
    <svg class="logo" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bell" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#8b7fd6"/>
          <stop offset="100%" stop-color="#5f4fbf"/>
        </linearGradient>
      </defs>
      <path d="M32 56 C32 32 48 20 64 20 C80 20 96 32 96 56 C96 62 90 64 64 64 C38 64 32 62 32 56 Z" fill="url(#bell)"/>
      <path d="M42 62 C40 78 46 84 44 100" stroke="#8b7fd6" stroke-width="5" stroke-linecap="round" fill="none"/>
      <path d="M64 65 C64 84 64 90 64 106" stroke="#a89ae0" stroke-width="5" stroke-linecap="round" fill="none"/>
      <path d="M86 62 C88 78 82 84 84 100" stroke="#8b7fd6" stroke-width="5" stroke-linecap="round" fill="none"/>
    </svg>
    <div>
      <h1>Kongflix Metadata</h1>
      <p>Jellyfin poster &amp; overview scanner</p>
    </div>
  </header>

  <div class="card status-bar">
    <div class="status-left">
      <span id="status-dot" class="dot idle"></span>
      <div class="status-text">
        <div id="status-title" class="title">Loading&hellip;</div>
        <div id="status-subtitle" class="subtitle">&nbsp;</div>
      </div>
    </div>
    <button id="scan-btn" class="scan-btn" onclick="triggerScan()">
      <span id="scan-spinner" class="spinner"></span>
      <span id="scan-btn-label">Scan Now</span>
    </button>
  </div>

  <div id="stats" class="stats"></div>

  <div class="section-title">Recent scans</div>
  <div class="card history-card">
    <div class="table-scroll">
      <table id="history-table">
        <thead>
          <tr><th>When</th><th>Scanned</th><th>Flagged</th><th>Refreshed</th><th>Skipped</th><th>Failed</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
    <div id="history-empty" class="empty-state" style="display:none;">No scans yet — click "Scan Now" to run the first one.</div>
  </div>

  <div class="section-title" style="margin-top: 1.5rem;">Missing metadata</div>
  <div id="watch-hint" class="watch-hint" style="display:none;">Watch mode only reacts to newly added items — click "Scan Now" to refresh this list.</div>
  <div class="missing-actions">
    <input id="missing-filter" class="filter-input" type="text" placeholder="Filter by title...">
    <button id="clear-list-btn" class="clear-btn" onclick="clearMissingList()">Clear List</button>
  </div>
  <div class="card history-card">
    <div class="table-scroll">
      <table id="missing-table">
        <thead>
          <tr><th>Title</th><th>Type</th><th>Season</th><th>Missing</th><th>Status</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
    <div id="missing-empty" class="empty-state" style="display:none;">Nothing missing metadata right now.</div>
    <div id="missing-pagination" class="pagination" style="display:none;">
      <button id="missing-prev" class="page-btn" onclick="changeMissingPage(-1)">&larr; Prev</button>
      <span id="missing-page-info" class="page-info"></span>
      <button id="missing-next" class="page-btn" onclick="changeMissingPage(1)">Next &rarr;</button>
    </div>
  </div>

</div>

<div id="toast" class="toast"></div>

<script>
  function fmtTime(iso) {
    if (!iso) return "never";
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    } catch (e) {
      return iso;
    }
  }

  function badge(value, kind) {
    const span = document.createElement("span");
    const cls = value === 0 ? "zero" : (kind === "bad" ? "nonzero-bad" : "nonzero-good");
    span.className = "badge " + cls;
    span.textContent = value;
    return span;
  }

  function renderStats(result) {
    const el = document.getElementById("stats");
    el.innerHTML = "";
    const fields = result && !result.error ? [
      ["scanned", "Scanned", ""],
      ["flagged", "Flagged", "flagged"],
      ["refreshed", "Refreshed", "refreshed"],
      ["skipped", "Skipped", ""],
      ["failedCount", "Failed", "failed"],
    ] : [
      ["scanned", "Scanned", ""], ["flagged", "Flagged", "flagged"],
      ["refreshed", "Refreshed", "refreshed"], ["skipped", "Skipped", ""],
      ["failedCount", "Failed", "failed"],
    ];
    for (const [key, label, cls] of fields) {
      const value = result && !result.error
        ? (key === "failedCount" ? (result.failures ? result.failures.length : 0) : (result[key] ?? 0))
        : 0;
      const card = document.createElement("div");
      card.className = "card stat" + (cls ? " " + cls : "");
      const valueEl = document.createElement("div");
      valueEl.className = "value";
      valueEl.textContent = value;
      const labelEl = document.createElement("div");
      labelEl.className = "label";
      labelEl.textContent = label;
      card.appendChild(valueEl);
      card.appendChild(labelEl);
      el.appendChild(card);
    }
  }

  let scanning = false;
  let lastRenderedRunAt = null;

  async function refreshStatus() {
    const res = await fetch("/api/status");
    const data = await res.json();
    scanning = !!data.scanning;
    document.getElementById("watch-hint").style.display = data.run_mode === "watch" ? "block" : "none";

    if (data.last_run_at !== lastRenderedRunAt) {
      refreshMissingItems();
      lastRenderedRunAt = data.last_run_at;
    }

    const dot = document.getElementById("status-dot");
    const title = document.getElementById("status-title");
    const subtitle = document.getElementById("status-subtitle");
    const btn = document.getElementById("scan-btn");
    const spinner = document.getElementById("scan-spinner");
    const label = document.getElementById("scan-btn-label");

    if (data.scanning) {
      dot.className = "dot scanning";
      title.textContent = "Scan in progress";
      subtitle.textContent = "This can take a while on large libraries";
      btn.disabled = true;
      spinner.classList.add("show");
      label.textContent = "Scanning…";
    } else {
      spinner.classList.remove("show");
      btn.disabled = false;
      label.textContent = "Scan Now";
      if (data.last_result && data.last_result.error) {
        dot.className = "dot error";
        title.textContent = "Last scan failed";
        subtitle.textContent = data.last_result.error;
      } else if (data.last_result) {
        dot.className = "dot ok";
        title.textContent = "Idle";
        subtitle.textContent = "Last run: " + fmtTime(data.last_run_at);
      } else {
        dot.className = "dot idle";
        title.textContent = "Idle";
        subtitle.textContent = "No scans yet";
      }
    }

    renderStats(data.last_result);
  }

  async function refreshHistory() {
    const res = await fetch("/api/history");
    const data = await res.json();
    const tbody = document.querySelector("#history-table tbody");
    const empty = document.getElementById("history-empty");
    const table = document.getElementById("history-table");
    tbody.innerHTML = "";

    if (!data.length) {
      table.style.display = "none";
      empty.style.display = "block";
      return;
    }
    table.style.display = "table";
    empty.style.display = "none";

    for (const entry of data.slice().reverse()) {
      const row = document.createElement("tr");
      const when = document.createElement("td");
      when.textContent = fmtTime(entry.timestamp);
      when.style.whiteSpace = "nowrap";
      row.appendChild(when);

      if (entry.error) {
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.className = "error-cell";
        cell.textContent = "Error: " + entry.error;
        row.appendChild(cell);
      } else {
        const scanned = document.createElement("td");
        scanned.textContent = entry.scanned;
        row.appendChild(scanned);

        const flagged = document.createElement("td");
        flagged.textContent = entry.flagged;
        row.appendChild(flagged);

        const refreshed = document.createElement("td");
        refreshed.textContent = entry.refreshed;
        row.appendChild(refreshed);

        const skipped = document.createElement("td");
        skipped.textContent = entry.skipped;
        row.appendChild(skipped);

        const failedCell = document.createElement("td");
        failedCell.appendChild(badge(entry.failures.length, "bad"));
        row.appendChild(failedCell);
      }
      tbody.appendChild(row);
    }
  }

  let allMissingItems = [];
  const MISSING_PAGE_SIZE = 50;
  let currentMissingPage = 1;

  function changeMissingPage(delta) {
    currentMissingPage += delta;
    renderMissingItems();
  }

  function renderMissingItems() {
    const filterValue = document.getElementById("missing-filter").value.trim().toLowerCase();
    const tbody = document.querySelector("#missing-table tbody");
    const empty = document.getElementById("missing-empty");
    const table = document.getElementById("missing-table");
    const pagination = document.getElementById("missing-pagination");
    tbody.innerHTML = "";

    const filtered = filterValue
      ? allMissingItems.filter((item) => (item.name || "").toLowerCase().includes(filterValue))
      : allMissingItems;

    if (!filtered.length) {
      table.style.display = "none";
      empty.style.display = "block";
      pagination.style.display = "none";
      return;
    }
    table.style.display = "table";
    empty.style.display = "none";

    const totalPages = Math.max(1, Math.ceil(filtered.length / MISSING_PAGE_SIZE));
    if (currentMissingPage > totalPages) currentMissingPage = totalPages;
    if (currentMissingPage < 1) currentMissingPage = 1;

    const startIndex = (currentMissingPage - 1) * MISSING_PAGE_SIZE;
    const pageItems = filtered.slice(startIndex, startIndex + MISSING_PAGE_SIZE);

    pagination.style.display = totalPages > 1 ? "flex" : "none";
    document.getElementById("missing-page-info").textContent =
      "Page " + currentMissingPage + " of " + totalPages + " (" + filtered.length + " items)";
    document.getElementById("missing-prev").disabled = currentMissingPage <= 1;
    document.getElementById("missing-next").disabled = currentMissingPage >= totalPages;

    for (const item of pageItems) {
      const row = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.textContent = item.name || "";
      if (item.series) {
        const seriesLine = document.createElement("div");
        seriesLine.className = "series-name";
        seriesLine.textContent = item.series;
        nameCell.appendChild(seriesLine);
      }
      row.appendChild(nameCell);

      const typeCell = document.createElement("td");
      const typeTag = document.createElement("span");
      typeTag.className = "type-tag";
      typeTag.textContent = item.type;
      typeCell.appendChild(typeTag);
      row.appendChild(typeCell);

      const seasonCell = document.createElement("td");
      seasonCell.textContent = (item.season !== null && item.season !== undefined) ? "Season " + item.season : "—";
      row.appendChild(seasonCell);

      const missingCell = document.createElement("td");
      for (const reason of item.missing) {
        const tag = document.createElement("span");
        tag.className = "missing-tag";
        tag.textContent = reason;
        missingCell.appendChild(tag);
      }
      row.appendChild(missingCell);

      const statusCell = document.createElement("td");
      const statusBadge = document.createElement("span");
      statusBadge.className = "badge status-" + item.status;
      statusBadge.textContent = item.status;
      statusCell.appendChild(statusBadge);

      if (item.status === "failed" || item.status === "pending") {
        const retryBtn = document.createElement("button");
        retryBtn.className = "retry-btn";
        retryBtn.textContent = "Retry";
        retryBtn.onclick = () => retryItem(item.id, retryBtn);
        statusCell.appendChild(retryBtn);
      }

      row.appendChild(statusCell);

      tbody.appendChild(row);
    }
  }

  async function retryItem(itemId, buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = "Retrying…";

    const res = await fetch("/api/retry-item/" + encodeURIComponent(itemId), { method: "POST" });

    if (res.status === 404) {
      showToast("Item not found — try refreshing the page");
      return;
    }
    if (!res.ok) {
      showToast("Retry failed to start");
      buttonEl.disabled = false;
      buttonEl.textContent = "Retry";
      return;
    }

    const updated = await res.json();
    const index = allMissingItems.findIndex((entry) => entry.id === updated.id);
    if (index !== -1) {
      allMissingItems[index] = updated;
    }
    showToast(updated.status === "refreshed" ? "Refreshed successfully" : "Retry failed again");
    renderMissingItems();
  }

  async function clearMissingList() {
    if (!confirm("Clear the missing-metadata list? This does not affect Jellyfin — it just resets what's shown here until the next scan.")) {
      return;
    }

    const res = await fetch("/api/clear-missing-items", { method: "POST" });
    if (!res.ok) {
      showToast("Could not clear the list");
      return;
    }

    allMissingItems = [];
    currentMissingPage = 1;
    renderMissingItems();
    showToast("List cleared");
  }

  async function refreshMissingItems() {
    const res = await fetch("/api/missing-items");
    allMissingItems = await res.json();
    renderMissingItems();
  }

  function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2600);
  }

  async function triggerScan() {
    const res = await fetch("/api/scan", { method: "POST" });
    if (res.status === 409) {
      showToast("A scan is already in progress");
    } else if (res.ok) {
      showToast("Scan started");
    } else {
      showToast("Could not start scan");
    }
    refreshStatus();
  }

  document.getElementById("missing-filter").addEventListener("input", () => {
    currentMissingPage = 1;
    renderMissingItems();
  });

  refreshStatus();
  refreshHistory();
  refreshMissingItems();
  setInterval(refreshStatus, 3000);
  setInterval(refreshHistory, 5000);
</script>
</body>
</html>
"""


def create_app(client, state: AppState, max_refreshes_per_run: int, history_path: str, missing_items_path: str, run_mode: str) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(INDEX_TEMPLATE)

    @app.route("/api/status")
    def status():
        return jsonify({
            "scanning": state.scanning,
            "last_result": state.last_result,
            "last_run_at": state.last_run_at,
            "run_mode": run_mode,
        })

    @app.route("/api/history")
    def history():
        return jsonify(load_history(history_path))

    @app.route("/api/missing-items")
    def missing_items():
        return jsonify(load_missing_items(missing_items_path))

    @app.route("/api/scan", methods=["POST"])
    def scan():
        if not state.try_start_scan():
            return jsonify({"error": "scan already in progress"}), 409
        thread = threading.Thread(
            target=run_scan_and_record,
            args=(state, client, max_refreshes_per_run, history_path, missing_items_path),
            daemon=True,
        )
        thread.start()
        return jsonify({"started": True}), 202

    @app.route("/api/retry-item/<item_id>", methods=["POST"])
    def retry(item_id):
        result = retry_item(client, missing_items_path, item_id)
        if result is None:
            return jsonify({"error": "item not found"}), 404
        return jsonify(result)

    @app.route("/api/clear-missing-items", methods=["POST"])
    def clear_missing_items_route():
        clear_missing_items(missing_items_path)
        return jsonify({"cleared": True})

    return app
