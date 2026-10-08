(() => {
  if (window.__BANDWIDTH_BRIDGE__) {
    return;
  }

  window.__BANDWIDTH_BRIDGE__ = true;

  let video = null;
  let iframe = null;

  let originalMuted = false;
  let originalDisplay = "";
  let originalVisibility = "";

  function findLectureVideo() {
    const videos = [...document.querySelectorAll("video")];
    if (!videos.length) return null;

    return (
      videos
        .filter((v) => {
          const rect = v.getBoundingClientRect();
          return rect.width > 200 && rect.height > 120;
        })
        .sort((a, b) => {
          const ar = a.getBoundingClientRect();
          const br = b.getBoundingClientRect();
          return br.width * br.height - ar.width * ar.height;
        })[0] || videos[0]
    );
  }

  function getLectureId(video) {
    if (!video) return null;
    if (video.dataset.bbLectureId) return video.dataset.bbLectureId;
    if (video.closest("[data-bb-lecture-id]")?.dataset.bbLectureId) {
      return video.closest("[data-bb-lecture-id]").dataset.bbLectureId;
    }
    if (window.location.hostname.includes("youtube.com")) {
      const v = new URLSearchParams(window.location.search).get("v");
      if (v) return `yt-${v.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
    }
    return null;
  }

  function resizePlayer() {
    if (!iframe || !video) return;

    const rect = video.getBoundingClientRect();
    iframe.style.left = `${rect.left}px`;
    iframe.style.top = `${rect.top}px`;
    iframe.style.width = `${rect.width}px`;
    iframe.style.height = `${rect.height}px`;
  }

  function createPlayer(lectureId, currentTime) {
    iframe = document.createElement("iframe");
    iframe.src = chrome.runtime.getURL(
      `player.html?lectureId=${encodeURIComponent(lectureId)}&start=${currentTime}`
    );
    iframe.setAttribute("allow", "autoplay");
    iframe.style.position = "fixed";
    iframe.style.zIndex = "2147483647";
    iframe.style.border = "0";
    iframe.style.borderRadius = "10px";
    iframe.style.boxShadow = "0 8px 30px rgba(0,0,0,.35)";
    document.documentElement.appendChild(iframe);
    resizePlayer();

    window.addEventListener("resize", resizePlayer);
    window.addEventListener("scroll", resizePlayer, true);
  }

  function hideOriginalVideo() {
    if (!video) return;

    originalMuted = video.muted;
    originalDisplay = video.style.display;
    originalVisibility = video.style.visibility;

    video.pause();
    video.muted = true;
    video.style.visibility = "hidden";
  }

  function restoreOriginalVideo() {
    if (!video) return;

    video.style.display = originalDisplay;
    video.style.visibility = originalVisibility;
    video.muted = originalMuted;

    if (iframe) {
      iframe.remove();
      iframe = null;
    }
  }

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data) return;

    if (data.type === "BB_USE_ORIGINAL_VIDEO") {
      restoreOriginalVideo();
    }
  });

  async function start() {
    video = findLectureVideo();
    if (!video) {
      alert("BandwidthBridge: no lecture video found.");
      return;
    }

    const lectureId = getLectureId(video);
    if (!lectureId) {
      if (window.location.hostname.includes("youtube.com")) {
        window.open(`http://127.0.0.1:8000/demo/generate.html?url=${encodeURIComponent(window.location.href)}`, "_blank");
        return;
      }
      alert("BandwidthBridge: add data-bb-lecture-id to the lecture video.");
      return;
    }

    const currentTime = Number(video.currentTime) || 0;

    const result = await chrome.runtime.sendMessage({
      type: "BB_START_LECTURE",
      lectureId,
      currentTime,
      apiBase: window.location.origin && window.location.origin.startsWith("http") && !window.location.hostname.includes("youtube.com") ? window.location.origin : undefined,
    });

    if (!result?.ok) {
      console.error(result);
      if (window.location.hostname.includes("youtube.com")) {
        if (confirm("BandwidthBridge: This YouTube video has not been packaged yet.\n\nWould you like to open the Generator now to create its low-bandwidth package?")) {
          window.open(`http://127.0.0.1:8000/demo/generate.html?url=${encodeURIComponent(window.location.href)}&lectureId=${encodeURIComponent(lectureId)}`, "_blank");
        }
        return;
      }
      alert(`BandwidthBridge failed: ${result?.error || "unknown error"}`);
      return;
    }

    createPlayer(lectureId, currentTime);
    hideOriginalVideo();
  }

  window.addEventListener("offline", () => {
    if (iframe) {
      iframe.contentWindow?.postMessage({ type: "BB_NETWORK_OFFLINE" }, "*");
    }
  });

  window.addEventListener("online", () => {
    if (iframe) {
      iframe.contentWindow?.postMessage({ type: "BB_NETWORK_ONLINE" }, "*");
    }
  });

  start();
})();
