import {
  saveManifest,
  getManifest,
  saveAudioSegment,
  getAudioSegment,
  saveSlide,
  getSlide,
  pruneLecture,
} from "./db.js";

let apiBase = "http://127.0.0.1:8010";
const BUFFER_AHEAD_SECONDS = 300;
const KEEP_BEHIND_SECONDS = 120;

async function getApiBase() {
  if (apiBase) {
    try {
      const res = await fetch(`${apiBase}/`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return apiBase;
    } catch {}
  }

  const candidates = [
    "http://127.0.0.1:8010",
    "http://localhost:8010",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
  ];

  for (const candidate of candidates) {
    try {
      const res = await fetch(`${candidate}/`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) {
        apiBase = candidate;
        return apiBase;
      }
    } catch {}
  }

  return apiBase || "http://127.0.0.1:8010";
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;

  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (error) {
    console.error("BandwidthBridge injection failed:", error);
  }
});

async function fetchManifestFromServer(lectureId) {
  const base = await getApiBase();
  const url = `${base}/api/lectures/${encodeURIComponent(lectureId)}/manifest`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Manifest HTTP ${response.status}`);
  }

  return await response.json();
}

async function packageURL(lectureId, relativePath) {
  const base = await getApiBase();
  return new URL(relativePath, `${base}/packages/${encodeURIComponent(lectureId)}/`).href;
}

async function fetchBlob(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Asset HTTP ${response.status}`);
  }

  return await response.blob();
}

async function ensureManifest(lectureId) {
  let manifest = await getManifest(lectureId);

  if (!manifest) {
    manifest = await fetchManifestFromServer(lectureId);
    manifest.lectureId = lectureId;
    await saveManifest(manifest);
  }

  return manifest;
}

async function blobToDataUrl(blob) {
  if (!blob) return null;
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const len = bytes.byteLength;
  for (let i = 0; i < len; i += 8192) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + 8192, len)));
  }
  return `data:${blob.type || "application/octet-stream"};base64,${btoa(binary)}`;
}

async function prefetchLecture(lectureId, currentTime) {
  const manifest = await ensureManifest(lectureId);
  const endTime = Math.min(manifest.duration, currentTime + BUFFER_AHEAD_SECONDS);

  let downloadedSegments = 0;
  let downloadedSlides = 0;

  const audioSegments = manifest.audioSegments || [];
  for (const segment of audioSegments) {
    const overlaps = segment.end > currentTime && segment.start < endTime;
    if (!overlaps) continue;

    const existing = await getAudioSegment(lectureId, segment.index);
    if (existing) continue;

    const url = await packageURL(lectureId, segment.url);
    const blob = await fetchBlob(url);

    await saveAudioSegment(lectureId, segment.index, segment.start, segment.end, blob);
    downloadedSegments++;
  }

  const slides = manifest.slides || [];
  let currentSlide = null;

  for (const slide of slides) {
    if (slide.t <= currentTime) {
      currentSlide = slide;
    }
  }

  const slidesToCache = [];
  if (currentSlide) slidesToCache.push(currentSlide);

  for (const slide of slides) {
    if (slide.t > currentTime && slide.t <= endTime) {
      slidesToCache.push(slide);
    }
  }

  for (const slide of slidesToCache) {
    const existing = await getSlide(lectureId, slide.index);
    if (existing) continue;

    const url = await packageURL(lectureId, slide.url);
    const blob = await fetchBlob(url);

    await saveSlide(lectureId, slide.index, slide.t, blob);
    downloadedSlides++;
  }

  await pruneLecture(lectureId, Math.max(0, currentTime - KEEP_BEHIND_SECONDS));

  return {
    ok: true,
    cacheUntil: endTime,
    downloadedSegments,
    downloadedSlides,
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    switch (message.type) {
      case "BB_START_LECTURE": {
        if (message.apiBase && typeof message.apiBase === "string" && message.apiBase.startsWith("http")) {
          apiBase = message.apiBase.replace(/\/+$/, "");
        }
        const manifest = await ensureManifest(message.lectureId);
        const result = await prefetchLecture(message.lectureId, message.currentTime || 0);
        return { ok: true, manifest, ...result };
      }

      case "BB_PREFETCH": {
        return await prefetchLecture(message.lectureId, message.currentTime || 0);
      }

      case "BB_GET_MANIFEST": {
        const manifest = await ensureManifest(message.lectureId);
        return { ok: true, manifest };
      }

      case "BB_GET_AUDIO_SEGMENT": {
        const item = await getAudioSegment(message.lectureId, message.index);
        if (!item) {
          return { ok: false, error: "Audio segment not cached" };
        }

        const dataUrl = await blobToDataUrl(item.blob);
        return {
          ok: true,
          dataUrl,
          start: item.start,
          end: item.end,
        };
      }

      case "BB_GET_SLIDE": {
        const item = await getSlide(message.lectureId, message.index);
        if (!item) {
          return { ok: false, error: "Slide not cached" };
        }

        const dataUrl = await blobToDataUrl(item.blob);
        return {
          ok: true,
          dataUrl,
          time: item.time,
        };
      }

      default:
        return { ok: false, error: "Unknown message" };
    }
  })()
    .then(sendResponse)
    .catch((error) => {
      console.error(error);
      sendResponse({ ok: false, error: error.message });
    });

  return true;
});
