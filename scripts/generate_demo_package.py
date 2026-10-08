import json
import math
import struct
import wave
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = ROOT / "packages" / "dbms-01"
AUDIO_DIR = PACKAGE_DIR / "audio"
SLIDE_DIR = PACKAGE_DIR / "slides"


def write_png(path: Path, width: int, height: int, r: int, g: int, b: int) -> None:
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        for _ in range(width):
            raw.extend((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def write_wav(path: Path, sample_rate: int, duration_seconds: int, frequency: float, amplitude: int) -> None:
    frame_count = sample_rate * duration_seconds
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = []
        for n in range(frame_count):
            t = n / sample_rate
            value = int(amplitude * math.sin(2 * math.pi * frequency * t))
            frames.append(struct.pack("<h", value))

        wav_file.writeframes(b"".join(frames))


PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SLIDE_DIR.mkdir(parents=True, exist_ok=True)

for i in range(6):
    color = ((i * 40) % 255, (i * 90) % 255, (i * 140) % 255)
    write_png(SLIDE_DIR / f"{i:04d}.png", 1280, 720, *color)

for i in range(6):
    write_wav(
        AUDIO_DIR / f"audio_{i:04d}.wav",
        sample_rate=8000,
        duration_seconds=30,
        frequency=220 + i * 20,
        amplitude=15000,
    )

manifest = {
    "lectureId": "dbms-01",
    "duration": 180,
    "segmentDuration": 30,
    "audioSegments": [
        {"index": i, "start": i * 30, "end": (i + 1) * 30, "url": f"audio/audio_{i:04d}.wav"}
        for i in range(6)
    ],
    "slides": [
        {"index": i, "t": i * 30, "url": f"slides/{i:04d}.png"}
        for i in range(6)
    ],
}
(PACKAGE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

try:
    from backend.database import upsert_lecture
    upsert_lecture(
        lecture_id="dbms-01",
        title="DBMS 01 - Query Optimization",
        source_url="https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
        package_dir=str(PACKAGE_DIR),
        duration=180.0,
    )
except Exception as e:
    pass

print(f"Generated lecture package in {PACKAGE_DIR}")
