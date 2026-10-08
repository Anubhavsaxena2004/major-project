from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_manifest(lecture_id: str, output_dir: Path, duration: int = 180, segment_duration: int = 30) -> dict[str, Any]:
    """Create a minimal lecture manifest matching the extension contract."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = output_dir / "audio"
    slides_dir = output_dir / "slides"
    audio_dir.mkdir(exist_ok=True)
    slides_dir.mkdir(exist_ok=True)

    audio_segments = []
    for i in range(0, duration, segment_duration):
        start = i
        end = min(i + segment_duration, duration)
        audio_segments.append(
            {
                "index": len(audio_segments),
                "start": start,
                "end": end,
                "url": f"audio/audio_{len(audio_segments):04d}.wav",
            }
        )

    slides = []
    for i in range(0, duration, 12):
        slides.append({
            "index": len(slides),
            "t": float(i),
            "url": f"slides/{len(slides):04d}.png",
        })

    manifest = {
        "lectureId": lecture_id,
        "duration": duration,
        "segmentDuration": segment_duration,
        "audioSegments": audio_segments,
        "slides": slides,
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
