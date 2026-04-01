from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import suppress
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


VIEWPORT = "1280,900"
DEFAULT_OUTPUT = Path("docs/assets/codex-log-analysis-demo.gif")
STEPS = [
    ("sessions-top", 10),
    ("sessions-archived", 10),
    ("sessions-top", 8),
    ("issues-top", 10),
    ("issues-mid", 10),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a masked README demo GIF from the local Codex log analysis UI.",
    )
    parser.add_argument(
        "--date",
        default=(date.today() - timedelta(days=1)).isoformat(),
        help="target date passed to codex-log-analysis serve (default: yesterday)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="GIF output path (default: %(default)s)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="server host (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8876,
        help="server port (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="session limit passed to the web UI (default: %(default)s)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=8,
        help="target GIF framerate (default: %(default)s)",
    )
    return parser.parse_args()


def wait_for_server(base_url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url, timeout=2.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {base_url}") from last_error


def run_checked(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def capture_step(step_url: str, output_path: Path, *, cwd: Path) -> None:
    run_checked(
        [
            "npx",
            "--yes",
            "playwright",
            "screenshot",
            "--channel",
            "chrome",
            "--viewport-size",
            VIEWPORT,
            "--wait-for-selector",
            "body.report-ready",
            "--wait-for-timeout",
            "700",
            step_url,
            str(output_path),
        ],
        cwd=cwd,
    )


def build_gif(frames_dir: Path, output_path: Path, fps: int, *, cwd: Path) -> None:
    palette_path = frames_dir / "palette.png"
    run_checked(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame-%04d.png"),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-vf",
            "fps={fps},scale=1100:-1:flags=lanczos,palettegen".format(fps=fps),
            str(palette_path),
        ],
        cwd=cwd,
    )
    run_checked(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame-%04d.png"),
            "-i",
            str(palette_path),
            "-lavfi",
            "fps={fps},scale=1100:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5".format(
                fps=fps
            ),
            str(output_path),
        ],
        cwd=cwd,
    )


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_path: Path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_url = f"http://{args.host}:{args.port}"

    server = subprocess.Popen(
        [
            "uv",
            "run",
            "codex-log-analysis",
            "serve",
            "--date",
            args.date,
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--limit",
            str(args.limit),
        ],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        wait_for_server(base_url)
        with TemporaryDirectory(prefix="codex-log-analysis-demo-") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            frames_dir = tmp_dir / "frames"
            screenshots_dir = tmp_dir / "screens"
            frames_dir.mkdir()
            screenshots_dir.mkdir()

            frame_index = 1
            for step_name, repeat_count in STEPS:
                screenshot_path = screenshots_dir / f"{step_name}.png"
                step_url = f"{base_url}/?mask=1&step={step_name}"
                capture_step(step_url, screenshot_path, cwd=repo_root)
                for _ in range(repeat_count):
                    frame_path = frames_dir / f"frame-{frame_index:04d}.png"
                    shutil.copy2(screenshot_path, frame_path)
                    frame_index += 1

            build_gif(frames_dir, output_path, args.fps, cwd=repo_root)
    finally:
        server.terminate()
        with suppress(subprocess.TimeoutExpired):
            server.wait(timeout=5)
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)

    print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
