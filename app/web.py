import threading

from flask import Flask, jsonify, render_template_string

from app.history import load_history
from app.state import AppState, run_scan_and_record

INDEX_TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>Kongflix Metadata</title>
  <style>
    body { font-family: sans-serif; max-width: 720px; margin: 2rem auto; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }
    button { padding: 0.5rem 1rem; font-size: 1rem; }
  </style>
</head>
<body>
  <h1>Kongflix Metadata</h1>
  <p id="status">Loading status...</p>
  <button id="scan-btn" onclick="triggerScan()">Scan Now</button>
  <h2>Recent scans</h2>
  <table id="history-table">
    <thead><tr><th>Scanned</th><th>Flagged</th><th>Refreshed</th><th>Skipped</th><th>Failed</th></tr></thead>
    <tbody></tbody>
  </table>

  <script>
    async function refreshStatus() {
      const res = await fetch("/api/status");
      const data = await res.json();
      const statusEl = document.getElementById("status");
      if (data.scanning) {
        statusEl.textContent = "Scan in progress...";
      } else if (data.last_result) {
        statusEl.textContent = "Last run: " + (data.last_run_at || "unknown");
      } else {
        statusEl.textContent = "No scans yet.";
      }
    }

    async function refreshHistory() {
      const res = await fetch("/api/history");
      const data = await res.json();
      const tbody = document.querySelector("#history-table tbody");
      tbody.innerHTML = "";
      for (const entry of data.slice().reverse()) {
        const row = document.createElement("tr");
        if (entry.error) {
          row.innerHTML = "<td colspan='5'>Error: " + entry.error + "</td>";
        } else {
          row.innerHTML = "<td>" + entry.scanned + "</td><td>" + entry.flagged + "</td><td>" +
            entry.refreshed + "</td><td>" + entry.skipped + "</td><td>" + entry.failures.length + "</td>";
        }
        tbody.appendChild(row);
      }
    }

    async function triggerScan() {
      await fetch("/api/scan", { method: "POST" });
      refreshStatus();
    }

    refreshStatus();
    refreshHistory();
    setInterval(refreshStatus, 5000);
    setInterval(refreshHistory, 5000);
  </script>
</body>
</html>
"""


def create_app(client, state: AppState, max_refreshes_per_run: int, history_path: str) -> Flask:
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
        })

    @app.route("/api/history")
    def history():
        return jsonify(load_history(history_path))

    @app.route("/api/scan", methods=["POST"])
    def scan():
        if not state.try_start_scan():
            return jsonify({"error": "scan already in progress"}), 409
        thread = threading.Thread(
            target=run_scan_and_record,
            args=(state, client, max_refreshes_per_run, history_path),
            daemon=True,
        )
        thread.start()
        return jsonify({"started": True}), 202

    return app
