import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.lecture_pipeline import generate_lecture_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a lecture video and generate a BandwidthBridge-compatible lecture package.")
    parser.add_argument("--url", required=True, help="YouTube lecture video URL")
    parser.add_argument("--lecture-id", default=None, help="Optional lecture identifier")
    parser.add_argument("--max-duration", type=float, default=None, help="Optional max duration in seconds for a short sample build")
    parser.add_argument("--output-root", default=str(Path(__file__).resolve().parent.parent / "packages"), help="Directory where the package is written")
    args = parser.parse_args()

    result = generate_lecture_package(
        video_url=args.url,
        lecture_id=args.lecture_id,
        output_root=args.output_root,
        max_duration=args.max_duration,
    )

    print(json.dumps({
        "lectureId": result["lectureId"],
        "title": result["title"],
        "duration": result["duration"],
        "packageDir": result["packageDir"],
    }, indent=2))


if __name__ == "__main__":
    main()
