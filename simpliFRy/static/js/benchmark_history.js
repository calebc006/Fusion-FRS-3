import { showToast } from "./utils.js";

const HISTORY_STORAGE_KEY = "benchmarkHistoryByVideo";

const noDataHintEl = document.getElementById("no-data-hint");
const videosContainerEl = document.getElementById("videos-container");
const exportButton = document.getElementById("export-button");
const clearButton = document.getElementById("clear-button");
const toast = document.getElementById("toast");
const benchmarkButton = document.getElementById("benchmark-button");

benchmarkButton.addEventListener("click", () => {
    window.location.href = "/benchmark";
});

const loadHistoryStore = () => {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY)) || {};
    } catch {
        return {};
    }
};

const MODEL_DISPLAY_NAMES = {
    low_light_enhancement: "Zero-DCE",
    dehaze: "Dehaze",
    denoise: "Nafnet",
    lafs: "LAFS",
};

const formatModelNames = (toggles) =>
    toggles && toggles.length
        ? toggles.map((t) => MODEL_DISPLAY_NAMES[t] || t).join(", ")
        : "None";

const buildVideoSection = (hash, entry) => {
    const section = document.createElement("div");
    section.className = "video-section";

    const rows = (entry.runs || [])
        .map((run) => {
            const stats = run.stats || {};
            return `
                <tr>
                    <td>${new Date(run.timestamp).toLocaleString()}</td>
                    <td>${formatModelNames(run.toggles)}</td>
                    <td>${run.people_seen && run.people_seen.length ? run.people_seen.join(", ") : "none"}</td>
                    <td>${stats.detections_captured ?? ""}</td>
                    <td>${stats.mean?.toFixed(4) ?? ""}</td>
                    <td>${stats.min?.toFixed(4) ?? ""}</td>
                    <td>${stats.max?.toFixed(4) ?? ""}</td>
                    <td>${stats.pct_identified?.toFixed(1) ?? ""}%</td>
                </tr>
            `;
        })
        .join("");

    section.innerHTML = `
        <div class="video-section-header">
            ${entry.thumbnail ? `<img class="thumbnail" src="data:image/jpeg;base64,${entry.thumbnail}" alt="${entry.video_name || "video"}" />` : ""}
            <h2>${entry.video_name || "Untitled video"}</h2>
        </div>
        <div class="sheet-scroll">
            <table class="sheet-table">
                <thead>
                    <tr>
                        <th>Run Time</th>
                        <th>Models Used</th>
                        <th>People Seen</th>
                        <th>Detections Captured</th>
                        <th>Mean Distance</th>
                        <th>Min Distance</th>
                        <th>Max Distance</th>
                        <th>% Identified</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
    return section;
};

const render = () => {
    const store = loadHistoryStore();
    const entries = Object.entries(store).filter(([, v]) => v.runs && v.runs.length > 0);

    videosContainerEl.innerHTML = "";
    for (const [hash, entry] of entries) {
        videosContainerEl.appendChild(buildVideoSection(hash, entry));
    }

    const hasData = entries.length > 0;
    noDataHintEl.classList.toggle("hidden", hasData);
    exportButton.disabled = !hasData;
    clearButton.disabled = !hasData;
};

exportButton.addEventListener("click", async () => {
    const store = loadHistoryStore();
    const videos = Object.values(store)
        .filter((v) => v.runs && v.runs.length > 0)
        .map((v) => ({
            ...v,
            runs: v.runs.map((run) => ({
                ...run,
                toggles: run.toggles && run.toggles.length ? run.toggles.map((t) => MODEL_DISPLAY_NAMES[t] || t) : [],
            })),
        }));
    if (!videos.length) return;

    exportButton.disabled = true;
    try {
        const response = await fetch("/api/benchmark/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ videos }),
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
