import { showToast } from "./utils.js";

const HISTORY_STORAGE_KEY = "benchmarkHistory";

const thumbnailEl = document.getElementById("thumbnail");
const noDataHintEl = document.getElementById("no-data-hint");
const tableBodyEl = document.getElementById("history-table-body");
const exportButton = document.getElementById("export-button");
const clearButton = document.getElementById("clear-button");
const toast = document.getElementById("toast");
const benchmarkButton = document.getElementById("benchmark-button");

benchmarkButton.addEventListener("click", () => {
    window.location.href = "/benchmark";
});

const loadHistory = () => {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return { thumbnail: null, runs: [] };
    try {
        return JSON.parse(raw);
    } catch {
        return { thumbnail: null, runs: [] };
    }
};

const render = () => {
    const { thumbnail, runs } = loadHistory();

    if (thumbnail) {
        thumbnailEl.src = `data:image/jpeg;base64,${thumbnail}`;
        thumbnailEl.classList.remove("hidden");
    } else {
        thumbnailEl.classList.add("hidden");
    }

    tableBodyEl.innerHTML = "";
    for (const run of runs) {
        const stats = run.stats || {};
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${new Date(run.timestamp).toLocaleString()}</td>
            <td>${run.toggles && run.toggles.length ? run.toggles.join(", ") : "none"}</td>
            <td>${run.people_seen && run.people_seen.length ? run.people_seen.join(", ") : "none"}</td>
            <td>${stats.detections_captured ?? ""}</td>
            <td>${stats.mean?.toFixed(4) ?? ""}</td>
            <td>${stats.min?.toFixed(4) ?? ""}</td>
            <td>${stats.max?.toFixed(4) ?? ""}</td>
            <td>${stats.pct_identified?.toFixed(1) ?? ""}%</td>
        `;
        tableBodyEl.appendChild(row);
    }

    const hasRuns = runs.length > 0;
    noDataHintEl.classList.toggle("hidden", hasRuns);
    exportButton.disabled = !hasRuns;
    clearButton.disabled = !hasRuns;
};

exportButton.addEventListener("click", async () => {
    const data = loadHistory();
    if (!data.runs.length) return;

    exportButton.disabled = true;
    try {
        const response = await fetch("/api/benchmark/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            showToast(toast, "Export failed", "error", 2000);
            return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "benchmark_report.xlsx";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error(err);
        showToast(toast, "Export failed", "error", 2000);
    } finally {
        exportButton.disabled = false;
    }
});

clearButton.addEventListener("click", () => {
    localStorage.removeItem(HISTORY_STORAGE_KEY);
    render();
});

render();
