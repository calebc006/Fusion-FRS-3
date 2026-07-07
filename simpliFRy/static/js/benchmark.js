import { fetchSettings, showToast, updateBBoxes, clearBBoxes } from "./utils.js";

const videoInput = document.getElementById("video-input");
const runVideoButton = document.getElementById("run-video-button");
const exportButton = document.getElementById("export-button");
const settingsSummaryEl = document.getElementById("settings-summary");
const liveStatusEl = document.getElementById("live-status");
const resultsEl = document.getElementById("results");
const toast = document.getElementById("toast");
const videoContainer = document.getElementById("video-container");
const videoPlaybackEl = document.getElementById("video-playback");
const modelSettingsForm = document.getElementById("model-settings-form");
const historyButton = document.getElementById("history-button");

const HISTORY_STORAGE_KEY = "benchmarkHistory";
const MODEL_TOGGLE_NAMES = ["use_low_light_enhancement", "use_dehaze", "use_denoise", "use_lafs"];

let reader = null;
let currentVideoKey = null; // name+size of the video currently associated with runHistory
let runHistory = []; // one entry per completed run on the current video, across different model settings

const formatToggles = (settings) => {
    const active = Object.entries(settings)
        .filter(([k, v]) => k.startsWith("use_") && v)
        .map(([k]) => k.replace("use_", ""));
    return active.length ? active.join(", ") : "none";
};

/** Persists the current run history to localStorage so the /benchmark-history page can read it */
const persistHistory = () => {
    localStorage.setItem(
        HISTORY_STORAGE_KEY,
        JSON.stringify({ thumbnail: runHistory[0]?.thumbnail || null, runs: runHistory })
    );
};

historyButton.addEventListener("click", () => {
    window.location.href = "/benchmark-history";
});

// Populate the model toggle checkboxes with the current server-side settings on load
fetchSettings().then((settings) => {
    for (const name of MODEL_TOGGLE_NAMES) {
        const el = document.getElementById(name);
        if (el) el.checked = Boolean(settings[name]);
    }
});

modelSettingsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(modelSettingsForm);

    try {
        const response = await fetch("/api/submit_settings", { method: "POST", body: formData });
        if (!response.ok) {
            showToast(toast, "Failed to apply models", "error", 2000);
            return;
        }
        showToast(toast, "Models updated", "success", 1500);

        const settings = await fetchSettings();
        settingsSummaryEl.textContent = `Threshold: ${settings.threshold ?? 0.5} | Models used: ${formatToggles(settings)}`;
    } catch (err) {
        console.error(err);
        showToast(toast, "Failed to apply models", "error", 2000);
    }
});

/** Resets the run history whenever a genuinely different video file is selected */
const videoKeyFor = (file) => `${file.name}::${file.size}`;

videoInput.addEventListener("change", () => {
    const file = videoInput.files[0];
    if (!file) return;
    const key = videoKeyFor(file);
    if (key !== currentVideoKey) {
        currentVideoKey = key;
        runHistory = [];
        persistHistory();
        exportButton.disabled = true;
        resultsEl.textContent = "";
        liveStatusEl.textContent = "";
    }
});

runVideoButton.addEventListener("click", async () => {
    const file = videoInput.files[0];
    if (!file) {
        showToast(toast, "Choose a video file first", "error", 2000);
        return;
    }

    const key = videoKeyFor(file);
    if (key !== currentVideoKey) {
        currentVideoKey = key;
        runHistory = [];
    }

    const settings = await fetchSettings();
    const threshold = settings.threshold ?? 0.5;
    settingsSummaryEl.textContent = `Threshold: ${threshold} | Models used: ${formatToggles(settings)}`;

    runVideoButton.disabled = true;
    resultsEl.textContent = "";
    liveStatusEl.textContent = "Uploading video...";
    clearBBoxes(videoContainer);

    // Pooled across every recognized face in every frame (regardless of who), giving one
    // overall confidence score rather than splitting results out per person
    const scores = [];
    const namesSeen = new Set();
    let thumbnail = null; // first frame preview seen, used as the video's thumbnail in the export
    let buffer = "";

    try {
        const formData = new FormData();
        formData.append("video", file);
        const uploadResp = await fetch("/api/benchmark/upload", { method: "POST", body: formData });
        const uploadData = await uploadResp.json();
        if (!uploadResp.ok) {
            liveStatusEl.textContent = `Upload failed: ${uploadData.message || uploadResp.status}`;
            runVideoButton.disabled = false;
            return;
        }

        liveStatusEl.textContent = "Processing video...";

        const params = new URLSearchParams({ video_path: uploadData.video_path });
        const response = await fetch(`/api/benchmark/run?${params}`);
        if (!response.ok || !response.body) {
            liveStatusEl.textContent = "Failed to start video benchmark.";
            runVideoButton.disabled = false;
            return;
        }

        reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split("\n");
            buffer = parts[parts.length - 1];

            for (const part of parts.slice(0, -1)) {
                if (!part) continue;
                let payload;
                try {
                    payload = JSON.parse(part);
                } catch {
                    continue;
                }
                if (payload.error) {
                    liveStatusEl.textContent = `Error: ${payload.error}`;
                    continue;
                }

                const detections = payload.detections || [];

                // Image previews are throttled server-side - only move the boxes when a new
                // image actually arrives, so they don't visually detach from a stale/static image
                if (payload.frame_jpeg) {
                    videoPlaybackEl.src = `data:image/jpeg;base64,${payload.frame_jpeg}`;
                    updateBBoxes(videoContainer, detections, { showLabels: true, showUnknown: true });
                    if (!thumbnail) thumbnail = payload.frame_jpeg;
                }

                for (const d of detections) {
                    scores.push(d.score);
                    namesSeen.add(d.label);
                }

                const namesText = detections.map((d) => d.label).join(", ");
                liveStatusEl.textContent =
                    `Processing: frame ${payload.frame_idx} / ${payload.total_frames} ` +
                    `- ${scores.length} identified detections captured` +
                    (namesText ? `, currently seeing: ${namesText}` : "");
            }
        }
    } catch (err) {
        console.error(err);
        liveStatusEl.textContent = `Error: ${err.message}`;
    } finally {
        if (reader) {
            try { await reader.cancel(); } catch {}
            reader = null;
        }
    }

    reportResults(scores, namesSeen, threshold, thumbnail, settings);
    runVideoButton.disabled = false;
});

const reportResults = (scores, namesSeen, threshold, thumbnail, settings) => {
    if (scores.length === 0) {
        liveStatusEl.textContent = "";
        resultsEl.innerHTML = `<p class="no-results">No enrolled face was recognized in this video.</p>`;
        return;
    }

    const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const belowThreshold = scores.filter((s) => s < threshold).length;
    const pctIdentified = (100 * belowThreshold) / scores.length;

    liveStatusEl.textContent = "";
    resultsEl.innerHTML = `
        <h3>Averaged confidence across ${namesSeen.size} ${namesSeen.size === 1 ? "person" : "people"}</h3>
        <table class="results-table">
            <tr><td>Detections captured</td><td>${scores.length}</td></tr>
            <tr><td>Mean distance</td><td>${mean.toFixed(4)}</td></tr>
            <tr><td>Min distance (best)</td><td>${min.toFixed(4)}</td></tr>
            <tr><td>Max distance (worst)</td><td>${max.toFixed(4)}</td></tr>
            <tr><td>% detections identified (distance &lt; ${threshold})</td><td>${pctIdentified.toFixed(1)}%</td></tr>
        </table>
        <p class="benchmark-hint">People seen: ${[...namesSeen].join(", ")}</p>
        <p class="benchmark-hint">Run ${runHistory.length + 1} recorded for this video - change a model toggle and run again to compare, or export now.</p>
    `;

    runHistory.push({
        timestamp: new Date().toISOString(),
        thumbnail,
        toggles: formatToggles(settings) === "none" ? [] : formatToggles(settings).split(", "),
        people_seen: [...namesSeen],
        stats: {
            detections_captured: scores.length,
            mean,
            min,
            max,
            pct_identified: pctIdentified,
        },
    });
    persistHistory();
    exportButton.disabled = false;
};

exportButton.addEventListener("click", async () => {
    if (runHistory.length === 0) return;

    exportButton.disabled = true;
    try {
        const response = await fetch("/api/benchmark/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                thumbnail: runHistory[0].thumbnail,
                runs: runHistory,
            }),
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
