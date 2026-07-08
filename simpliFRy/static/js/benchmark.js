import { fetchSettings, showToast, updateBBoxes, clearBBoxes } from "./utils.js";

const videoInput = document.getElementById("video-input");
const runVideoButton = document.getElementById("run-video-button");
const settingsSummaryEl = document.getElementById("settings-summary");
const liveStatusEl = document.getElementById("live-status");
const resultsEl = document.getElementById("results");
const toast = document.getElementById("toast");
const videoContainer = document.getElementById("video-container");
const videoPlaybackEl = document.getElementById("video-playback");
const modelSettingsForm = document.getElementById("model-settings-form");
const historyButton = document.getElementById("history-button");

const HISTORY_STORAGE_KEY = "benchmarkHistoryByVideo";
const MODEL_TOGGLE_NAMES = ["use_low_light_enhancement", "use_dehaze", "use_denoise", "use_lafs"];

let reader = null;
let currentVideoHash = null; // content hash of the video currently selected
let historyStore = loadHistoryStore(); // { [videoHash]: { video_name, thumbnail, runs: [] } }

function loadHistoryStore() {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

const persistHistoryStore = () => {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(historyStore));
};

/** Content hash (SHA-256) of a file's bytes - identifies "the same video" regardless of filename */
const hashFile = async (file) => {
    // crypto.subtle only works in secure contexts (HTTPS or localhost) - this app is often
    // accessed over plain HTTP via a LAN IP for the camera setup, where it's unavailable
    if (window.crypto?.subtle) {
        try {
            const buffer = await file.arrayBuffer();
            const digest = await crypto.subtle.digest("SHA-256", buffer);
            return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
        } catch (err) {
            console.warn("crypto.subtle hashing failed, falling back to file metadata:", err);
        }
    }
    // Fallback: name+size+lastModified isn't content-based, but still recognizes "the same
    // file" across sessions as long as it isn't re-saved/re-encoded under the same name
    return `fallback::${file.name}::${file.size}::${file.lastModified}`;
};

const formatToggles = (settings) => {
    const active = Object.entries(settings)
        .filter(([k, v]) => k.startsWith("use_") && v)
        .map(([k]) => k.replace("use_", ""));
    return active.length ? active.join(", ") : "none";
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

    // /api/submit_settings treats a missing checkbox field the same as "unchecked" - since this
    // form only contains the 4 model toggles, submitting it as-is would silently disable
    // use_differentiator/use_persistor (and perf_logging) if they were previously on. Explicitly
    // carry forward their current values so this form only ever changes the model toggles.
    const currentSettings = await fetchSettings();
    for (const name of ["use_differentiator", "use_persistor", "perf_logging"]) {
        if (currentSettings[name]) formData.set(name, "on");
    }

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

/** Renders the most recent recorded run for a recognized video, so past results show immediately */
const showExistingHistory = (hash) => {
    const entry = historyStore[hash];
    if (!entry || entry.runs.length === 0) {
        resultsEl.textContent = "";
        return;
    }

    const latest = entry.runs[entry.runs.length - 1];
    const stats = latest.stats || {};
    resultsEl.innerHTML = `
        <p class="benchmark-hint">
            This video has been benchmarked before - ${entry.runs.length} run(s) recorded.
            Showing the most recent run below; run again to add another comparison.
        </p>
        <h3>Last run: ${latest.people_seen?.join(", ") || "no one identified"}</h3>
        <table class="results-table">
            <tr><td>Models used</td><td>${latest.toggles?.length ? latest.toggles.join(", ") : "none"}</td></tr>
            <tr><td>Detections captured</td><td>${stats.detections_captured ?? ""}</td></tr>
            <tr><td>Mean distance</td><td>${stats.mean?.toFixed(4) ?? ""}</td></tr>
            <tr><td>Min distance (best)</td><td>${stats.min?.toFixed(4) ?? ""}</td></tr>
            <tr><td>Max distance (worst)</td><td>${stats.max?.toFixed(4) ?? ""}</td></tr>
            <tr><td>% detections identified</td><td>${stats.pct_identified?.toFixed(1) ?? ""}%</td></tr>
        </table>
    `;
    if (entry.thumbnail) {
        videoPlaybackEl.src = `data:image/jpeg;base64,${entry.thumbnail}`;
    }
};

videoInput.addEventListener("change", async () => {
    const file = videoInput.files[0];
    if (!file) return;

    liveStatusEl.textContent = "Checking video...";
    currentVideoHash = await hashFile(file);
    liveStatusEl.textContent = "";

    if (historyStore[currentVideoHash]) {
        showExistingHistory(currentVideoHash);
    } else {
        resultsEl.textContent = "";
    }
});

runVideoButton.addEventListener("click", async () => {
    const file = videoInput.files[0];
    if (!file) {
        showToast(toast, "Choose a video file first", "error", 2000);
        return;
    }

    if (!currentVideoHash) {
        currentVideoHash = await hashFile(file);
    }
    if (!historyStore[currentVideoHash]) {
        historyStore[currentVideoHash] = { video_name: file.name, thumbnail: null, runs: [] };
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

    reportResults(scores, namesSeen, threshold, thumbnail, settings, file.name);
    runVideoButton.disabled = false;
});

const reportResults = (scores, namesSeen, threshold, thumbnail, settings, videoName) => {
    const entry = historyStore[currentVideoHash];

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
        <p class="benchmark-hint">Run ${entry.runs.length + 1} recorded for this video - change a model toggle and run again to compare, or export now.</p>
    `;

    entry.video_name = entry.video_name || videoName;
    entry.thumbnail = entry.thumbnail || thumbnail;
    entry.runs.push({
        timestamp: new Date().toISOString(),
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
    persistHistoryStore();
};
