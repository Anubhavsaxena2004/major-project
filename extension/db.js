const DB_NAME = "bandwidthbridge-cache";
const DB_VERSION = 1;

let dbPromise = null;

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function openDB() {
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;

      if (!db.objectStoreNames.contains("manifests")) {
        db.createObjectStore("manifests", {
          keyPath: "lectureId",
        });
      }

      if (!db.objectStoreNames.contains("audioSegments")) {
        const store = db.createObjectStore("audioSegments", {
          keyPath: "key",
        });

        store.createIndex("byLecture", "lectureId", {
          unique: false,
        });
      }

      if (!db.objectStoreNames.contains("slides")) {
        const store = db.createObjectStore("slides", {
          keyPath: "key",
        });

        store.createIndex("byLecture", "lectureId", {
          unique: false,
        });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  return dbPromise;
}

export async function saveManifest(manifest) {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const tx = db.transaction("manifests", "readwrite");
    tx.objectStore("manifests").put(manifest);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getManifest(lectureId) {
  const db = await openDB();
  const tx = db.transaction("manifests", "readonly");
  return requestToPromise(tx.objectStore("manifests").get(lectureId));
}

export async function saveAudioSegment(lectureId, index, start, end, blob) {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const tx = db.transaction("audioSegments", "readwrite");

    tx.objectStore("audioSegments").put({
      key: `${lectureId}:${index}`,
      lectureId,
      index,
      start,
      end,
      blob,
    });

    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAudioSegment(lectureId, index) {
  const db = await openDB();
  const tx = db.transaction("audioSegments", "readonly");
  return requestToPromise(tx.objectStore("audioSegments").get(`${lectureId}:${index}`));
}

export async function saveSlide(lectureId, index, time, blob) {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const tx = db.transaction("slides", "readwrite");

    tx.objectStore("slides").put({
      key: `${lectureId}:${index}`,
      lectureId,
      index,
      time,
      blob,
    });

    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getSlide(lectureId, index) {
  const db = await openDB();
  const tx = db.transaction("slides", "readonly");
  return requestToPromise(tx.objectStore("slides").get(`${lectureId}:${index}`));
}

export async function getLectureSegments(lectureId) {
  const db = await openDB();
  const tx = db.transaction("audioSegments", "readonly");
  return requestToPromise(tx.objectStore("audioSegments").index("byLecture").getAll(lectureId));
}

export async function getLectureSlides(lectureId) {
  const db = await openDB();
  const tx = db.transaction("slides", "readonly");
  return requestToPromise(tx.objectStore("slides").index("byLecture").getAll(lectureId));
}

export async function pruneLecture(lectureId, minimumTime) {
  const db = await openDB();
  const tx = db.transaction(["audioSegments", "slides"], "readwrite");

  const audioStore = tx.objectStore("audioSegments");
  const slideStore = tx.objectStore("slides");

  const audioItems = await requestToPromise(audioStore.index("byLecture").getAll(lectureId));
  for (const item of audioItems) {
    if (item.end < minimumTime) {
      audioStore.delete(item.key);
    }
  }

  const slides = await requestToPromise(slideStore.index("byLecture").getAll(lectureId));
  for (const slide of slides) {
    if (slide.time < minimumTime) {
      slideStore.delete(slide.key);
    }
  }

  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
