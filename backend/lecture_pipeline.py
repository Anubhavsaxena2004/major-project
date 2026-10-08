from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yt_dlp


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "packages"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"^-+|-+$", "", value)
    return value or "lecture"


def resolve_ffmpeg() -> str:
    resolved = shutil.which("ffmpeg")
    if not resolved:
        # Dynamic search in Windows WinGet packages directory
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.exists():
                for found in winget_pkgs.glob("**/ffmpeg.exe"):
                    if found.is_file():
                        resolved = str(found)
                        break

    if not resolved:
        candidates = [
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\Git\usr\bin\ffmpeg.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                resolved = str(candidate)
                break

    if not resolved:
        raise RuntimeError("FFmpeg was not found. Install it or add it to PATH.")

    ffmpeg_dir = str(Path(resolved).parent)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    return resolved


def resolve_ffprobe() -> str:
    ffmpeg_path = Path(resolve_ffmpeg())
    probe = ffmpeg_path.with_name("ffprobe.exe")
    if probe.exists():
        return str(probe)
    tool = shutil.which("ffprobe")
    if tool:
        return tool
    raise RuntimeError("ffprobe was not found near the FFmpeg installation.")


def get_video_duration(video_path: str | Path) -> float:
    probe = resolve_ffprobe()
    proc = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nokey=1:noprint_wrappers=1", str(video_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Could not read duration for {video_path!s}") from exc


def download_video(video_url: str, temp_dir: Path, max_duration: float | None = None) -> Path:
    ffmpeg_bin = Path(resolve_ffmpeg())
    ffmpeg_dir = str(ffmpeg_bin.parent)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    temp_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "noplaylist": True,
        "outtmpl": str(temp_dir / "source.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_dir,
        "retries": 10,
        "extractor_retries": 10,
        "socket_timeout": 30,
        "http_timeout": 30,
        "skip_download": False,
    }

    if max_duration and max_duration > 0:
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(0, max_duration)])
        ydl_opts["force_keyframes_at_cuts"] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)

    if isinstance(info, dict):
        if not info.get("title"):
            raise RuntimeError(f"No video metadata returned for {video_url}")
    elif info is None:
        raise RuntimeError(f"No video metadata returned for {video_url}")

    candidates = sorted(temp_dir.glob("source.*"))
    if not candidates:
        raise RuntimeError(f"No video file was downloaded for {video_url}")

    video_file = candidates[0]
    if video_file.suffix.lower() not in {".mp4", ".webm", ".mkv", ".mov", ".avi"}:
        video_file = max(candidates, key=lambda p: p.stat().st_size)

    return video_file


def trim_video_to_duration(video_path: str | Path, output_path: str | Path, duration_limit: float | None) -> Path:
    source = Path(video_path)
    if duration_limit is None:
        return source

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg()

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-ss",
            "0",
            "-to",
            str(duration_limit),
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def has_audio_stream(video_path: str | Path) -> bool:
    try:
        probe = resolve_ffprobe()
        proc = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "default=nokey=1:noprint_wrappers=1", str(video_path)],
            capture_output=True,
            text=True,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return True


def extract_audio(video_path: str | Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "audio_full.webm"
    ffmpeg = resolve_ffmpeg()

    if has_audio_stream(video_path):
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(video_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "16k",
                    str(audio_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return audio_path
        except subprocess.CalledProcessError:
            pass

    # Fallback to generating silent audio for videos without an audio track
    duration = max(1.0, get_video_duration(video_path))
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            str(duration),
            "-c:a",
            "libopus",
            "-b:a",
            "16k",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return audio_path


def segment_audio(audio_path: str | Path, output_dir: Path, segment_seconds: int = 30) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            "-c",
            "copy",
            str(output_dir / "audio_%04d.webm"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    segments: list[dict[str, Any]] = []
    for index, item in enumerate(sorted(output_dir.glob("audio_*.webm"))):
        start = index * segment_seconds
        end = start + segment_seconds
        segments.append({
            "index": index,
            "start": start,
            "end": end,
            "url": f"audio/{item.name}",
        })
    return segments


def save_slide(frame: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), frame)
    if not ok:
        raise RuntimeError(f"Could not save slide {output_path}")


def detect_slides(video_path: str | Path, output_dir: Path, threshold: float = 0.92, min_gap_seconds: float = 2.0) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video {video_path!s}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 1.0
    previous_hist = None
    last_saved_time = -10_000
    slides: list[dict[str, Any]] = []
    frame_index = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        timestamp = frame_index / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        if previous_hist is not None:
            similarity = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_CORREL))
            if similarity < threshold and (timestamp - last_saved_time) >= min_gap_seconds:
                file_name = f"{len(slides):04d}.png"
                save_slide(frame, output_dir / file_name)
                slides.append({"index": len(slides), "t": float(timestamp), "url": f"slides/{file_name}"})
                last_saved_time = timestamp
        elif len(slides) == 0:
            file_name = f"{len(slides):04d}.png"
            save_slide(frame, output_dir / file_name)
            slides.append({"index": len(slides), "t": float(timestamp), "url": f"slides/{file_name}"})
            last_saved_time = timestamp

        previous_hist = hist
        frame_index += 1

    cap.release()
    return slides


def build_manifest(lecture_id: str, package_dir: Path, duration: float, audio_segments: list[dict[str, Any]], slides: list[dict[str, Any]], segment_duration: int = 30) -> dict[str, Any]:
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "lectureId": lecture_id,
        "duration": int(duration),
        "segmentDuration": segment_duration,
        "audioSegments": audio_segments,
        "slides": slides,
    }

    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def generate_lecture_package(video_url: str, lecture_id: str | None = None, output_root: str | Path = DEFAULT_OUTPUT_ROOT, max_duration: float | None = None) -> dict[str, Any]:
    if not video_url or not video_url.strip():
        raise ValueError("A valid YouTube lecture URL is required.")

    title = youtube_title(video_url) or "lecture"
    lecture_key = slugify(lecture_id or title)
    package_dir = Path(output_root) / lecture_key
    package_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bb-lecture-") as temp_root:
        temp_dir = Path(temp_root)
        source_video = download_video(video_url, temp_dir, max_duration=max_duration)
        trimmed_video = trim_video_to_duration(source_video, temp_dir / "trimmed.mp4", max_duration)

        audio_path = extract_audio(trimmed_video, package_dir)
        audio_segments = segment_audio(audio_path, package_dir / "audio")
        slides = detect_slides(trimmed_video, package_dir / "slides")
        duration = get_video_duration(trimmed_video)
        manifest = build_manifest(lecture_key, package_dir, duration, audio_segments, slides)

    return {
        "lectureId": lecture_key,
        "title": title,
        "sourceUrl": video_url,
        "packageDir": str(package_dir),
        "duration": int(duration),
        "manifest": manifest,
    }


def generate_lecture_package_from_file(video_path: str | Path, lecture_id: str | None = None, output_root: str | Path = DEFAULT_OUTPUT_ROOT, max_duration: float | None = None) -> dict[str, Any]:
    source_path = Path(video_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Local video file not found: {source_path}")

    title = source_path.stem.replace("_", " ").strip() or "lecture"
    lecture_key = slugify(lecture_id or title)
    package_dir = Path(output_root) / lecture_key
    package_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bb-local-") as temp_root:
        temp_dir = Path(temp_root)
        working_video = temp_dir / source_path.name

        if source_path.suffix.lower() != ".mp4":
            ffmpeg = resolve_ffmpeg()
            subprocess.run(
                [ffmpeg, "-y", "-i", str(source_path), "-c:v", "libx264", "-c:a", "aac", str(working_video)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            shutil.copy2(source_path, working_video)

        trimmed_video = trim_video_to_duration(working_video, temp_dir / "trimmed.mp4", max_duration)
        audio_path = extract_audio(trimmed_video, package_dir)
        audio_segments = segment_audio(audio_path, package_dir / "audio")
        slides = detect_slides(trimmed_video, package_dir / "slides")
        duration = get_video_duration(trimmed_video)
        manifest = build_manifest(lecture_key, package_dir, duration, audio_segments, slides)

    return {
        "lectureId": lecture_key,
        "title": title,
        "sourceUrl": str(source_path),
        "packageDir": str(package_dir),
        "duration": int(duration),
        "manifest": manifest,
    }


def youtube_title(video_url: str) -> str:
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(video_url, download=False)
    return (info or {}).get("title") or "lecture"
