import {
  getManifest,
  saveManifest,
  getAudioSegment,
  saveAudioSegment,
  getSlide,
  saveSlide,
} from "./db.js";

const params = new URLSearchParams(window.location.search);
const lectureId = params.get("lectureId");
const startTime = Number(params.get("start") || 0);

const audio = document.getElementById("audio");
const slide = document.getElementById("slide");
const status = document.getElementById("status");
const bufferInfo = document.getElementById("bufferInfo");
const offlineBadge = document.getElementById("offlineBadge");
const playBtn = document.getElementById("playBtn");
const pauseBtn = document.getElementById("pauseBtn");
const speed = document.getElementById("speed");
const originalBtn = document.getElementById("originalBtn");

let manifest = null;
let activeSegment = null;
let segmentObjectURL = null;
let slideObjectURL = null;
let currentSlideIndex = null;
let currentLectureTime = startTime;
let cacheUntil = 0;
let playing = false;

function formatTime(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function setStatus(text) {
  status.textContent = text;
}

function setBufferText() {
  bufferInfo.textContent = `Cached ahead until ${formatTime(cacheUntil)}`;
}

function isValidBlob(b) {
  return b instanceof Blob && b.size > 0;
}

async function fetchAssetBlob(relativePath) {
  const candidates = [
    `http://127.0.0.1:8010/packages/${encodeURIComponent(lectureId)}/${relativePath}`,
    `http://localhost:8010/packages/${encodeURIComponent(lectureId)}/${relativePath}`,
    `http://127.0.0.1:8000/packages/${encodeURIComponent(lectureId)}/${relativePath}`,
    `http://localhost:8000/packages/${encodeURIComponent(lectureId)}/${relativePath}`,
  ];

  for (const url of candidates) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        return await res.blob();
      }
    } catch {}
  }
  return null;
}

async function fetchManifestDirect(lectureId) {
  const candidates = [
    `http://127.0.0.1:8010/api/lectures/${encodeURIComponent(lectureId)}/manifest`,
    `http://localhost:8010/api/lectures/${encodeURIComponent(lectureId)}/manifest`,
    `http://127.0.0.1:8000/api/lectures/${encodeURIComponent(lectureId)}/manifest`,
    `http://localhost:8000/api/lectures/${encodeURIComponent(lectureId)}/manifest`,
  ];

  for (const url of candidates) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        return await res.json();
      }
    } catch {}
  }
  return null;
}

async function loadManifest() {
  manifest = await getManifest(lectureId);

  if (!manifest) {
    try {
      const response = await chrome.runtime.sendMessage({
        type: "BB_GET_MANIFEST",
        lectureId,
      });

      if (response?.ok && response.manifest) {
        manifest = response.manifest;
      }
    } catch {}
  }

  if (!manifest) {
    manifest = await fetchManifestDirect(lectureId);
    if (manifest) {
      manifest.lectureId = lectureId;
      await saveManifest(manifest).catch(() => {});
    }
  }

  if (!manifest) {
    throw new Error(`Cannot load manifest for lecture '${lectureId}'. Verify server is running.`);
  }

  manifest.audioSegments = [...(manifest.audioSegments || [])].sort((a, b) => a.start - b.start);
  manifest.slides = [...(manifest.slides || [])].sort((a, b) => a.t - b.t);
}

function findSegment(time) {
  return manifest.audioSegments.find((segment) => time >= segment.start && time < segment.end);
}

function findSlide(time) {
  let current = null;

  for (const item of manifest.slides) {
    if (item.t <= time) {
      current = item;
    } else {
      break;
    }
  }

  return current;
}

async function loadSlide(time) {
  const target = findSlide(time);
  if (!target) return;

  if (currentSlideIndex === target.index) return;

  // 1. Retrieve cached slide directly from IndexedDB
  let item = await getSlide(lectureId, target.index);

  // 2. If not in cache or invalid, trigger background prefetch
  if (!item || !isValidBlob(item.blob)) {
    try {
      await chrome.runtime.sendMessage({
        type: "BB_PREFETCH",
        lectureId,
        currentTime: time,
      });
      item = await getSlide(lectureId, target.index);
    } catch (err) {
      console.warn("Slide prefetch failed:", err);
    }
  }

  // 3. Fallback: fetch directly from active server if online
  if (!item || !isValidBlob(item.blob)) {
    const directBlob = await fetchAssetBlob(target.url);
    if (directBlob && isValidBlob(directBlob)) {
      item = { blob: directBlob };
      await saveSlide(lectureId, target.index, target.t, directBlob).catch(() => {});
    }
  }

  if (!item || !isValidBlob(item.blob)) {
    setStatus("Slide is not in local cache.");
    return;
  }

  if (slideObjectURL) {
    URL.revokeObjectURL(slideObjectURL);
  }

  slideObjectURL = URL.createObjectURL(item.blob);
  slide.src = slideObjectURL;
  currentSlideIndex = target.index;
}

async function loadSegment(time, autoPlay = false) {
  const segment = findSegment(time);

  if (!segment) {
    setStatus("End of lecture.");
    playing = false;
    return;
  }

  if (activeSegment && activeSegment.index === segment.index) {
    const offset = Math.max(0, time - segment.start);
    audio.currentTime = Math.min(offset, audio.duration || offset);
    if (autoPlay) await audio.play();
    return;
  }

  // 1. Retrieve cached audio segment directly from IndexedDB
  let item = await getAudioSegment(lectureId, segment.index);

  // 2. If not in cache or invalid, trigger background prefetch
  if (!item || !isValidBlob(item.blob)) {
    try {
      await chrome.runtime.sendMessage({
        type: "BB_PREFETCH",
        lectureId,
        currentTime: time,
      });
      item = await getAudioSegment(lectureId, segment.index);
    } catch (err) {
      console.warn("Audio prefetch failed:", err);
    }
  }

  // 3. Fallback: fetch directly from active server if online
  if (!item || !isValidBlob(item.blob)) {
    const directBlob = await fetchAssetBlob(segment.url);
    if (directBlob && isValidBlob(directBlob)) {
      item = { blob: directBlob };
      await saveAudioSegment(lectureId, segment.index, segment.start, segment.end, directBlob).catch(() => {});
    }
  }

  if (!item || !isValidBlob(item.blob)) {
    setStatus(`Offline cache exhausted at ${formatTime(segment.start)}`);
    playing = false;
    return;
  }

  if (segmentObjectURL) {
    URL.revokeObjectURL(segmentObjectURL);
  }

  segmentObjectURL = URL.createObjectURL(item.blob);
  activeSegment = segment;
  audio.src = segmentObjectURL;

  await new Promise((resolve) => {
    if (audio.readyState >= 1) {
      resolve();
      return;
    }

    audio.addEventListener("loadedmetadata", resolve, { once: true });
  });

  const offset = Math.max(0, time - segment.start);
  audio.currentTime = Math.min(offset, Math.max(0, audio.duration - 0.01));
  currentLectureTime = time;

  await loadSlide(time);

  if (autoPlay) {
    try {
      await audio.play();
    } catch {
      setStatus("Click Play to continue.");
    }
  }
}

async function prefetch() {
  if (!navigator.onLine) return;

  try {
    const response = await chrome.runtime.sendMessage({
      type: "BB_PREFETCH",
      lectureId,
      currentTime: currentLectureTime,
    });

    if (response?.ok) {
      cacheUntil = response.cacheUntil || 0;
      setBufferText();
      setStatus(`Online • cache ahead ${formatTime(cacheUntil)}`);
    }
  } catch (error) {
    console.error("Prefetch failed:", error);
  }
}

function calculateLectureTime() {
  if (!activeSegment) return currentLectureTime;
  return activeSegment.start + audio.currentTime;
}

async function updatePlayback() {
  if (!activeSegment) return;

  currentLectureTime = calculateLectureTime();
  await loadSlide(currentLectureTime);

  if (navigator.onLine && currentLectureTime > cacheUntil - 60) {
    await prefetch();
  }

  if (!navigator.onLine) {
    offlineBadge.style.display = "block";
    setStatus("Internet unavailable • using local cache");
  } else {
    offlineBadge.style.display = "none";
  }
}

audio.addEventListener("timeupdate", updatePlayback);

audio.addEventListener("ended", async () => {
  if (!activeSegment) return;

  const next = manifest.audioSegments.find((segment) => segment.index === activeSegment.index + 1);
  if (!next) {
    setStatus("Lecture completed.");
    playing = false;
    return;
  }

  await loadSegment(next.start, true);
});

playBtn.addEventListener("click", async () => {
  if (!activeSegment) {
    await loadSegment(currentLectureTime, true);
    return;
  }

  try {
    await audio.play();
    playing = true;
  } catch {
    setStatus("Browser blocked autoplay. Click Play again.");
  }
});

pauseBtn.addEventListener("click", () => {
  audio.pause();
  playing = false;
});

speed.addEventListener("change", () => {
  audio.playbackRate = Number(speed.value);
});

originalBtn.addEventListener("click", () => {
  window.parent.postMessage({ type: "BB_USE_ORIGINAL_VIDEO" }, "*");
});

window.addEventListener("message", (event) => {
  const data = event.data;
  if (!data) return;

  if (data.type === "BB_NETWORK_OFFLINE") {
    offlineBadge.style.display = "block";
    setStatus("Network lost • continuing from local cache");
  }

  if (data.type === "BB_NETWORK_ONLINE") {
    offlineBadge.style.display = "none";
    prefetch();
  }
});

async function start() {
  if (!lectureId) {
    setStatus("Missing lecture ID.");
    return;
  }

  try {
    setStatus("Loading BandwidthBridge...");
    await loadManifest();
    await prefetch();
    await loadSegment(startTime, false);
    setBufferText();
    setStatus(`Ready • ${formatTime(startTime)}`);

    try {
      await audio.play();
      playing = true;
    } catch {
      setStatus("Ready • click Play");
    }
  } catch (error) {
    console.error(error);
    setStatus(`Error: ${error.message}`);
  }
}

setInterval(() => {
  if (navigator.onLine && playing) {
    prefetch();
  }
}, 5000);

start();
