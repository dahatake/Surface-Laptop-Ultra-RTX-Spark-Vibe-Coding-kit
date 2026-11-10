"""Record the live demos: one conhost window per use case, captured by title with ffmpeg gdigrab.

Outputs (docs/media/): <uc>-demo.mp4 (real time), <uc>-demo.gif (preview), <uc>-shot-*.png (key frames).
Only the demo window is captured, never the rest of the desktop.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time

import imageio_ffmpeg

from common import BENCH, RESULTS, ROOT

FF = imageio_ffmpeg.get_ffmpeg_exe()
MEDIA = ROOT / "docs" / "media"
user32 = ctypes.windll.user32


def wait_window(title: str, timeout: float = 30) -> int:
    end = time.time() + timeout
    while time.time() < end:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            return hwnd
        time.sleep(0.2)
    raise TimeoutError(f"window '{title}' did not appear")


def record(uc: str) -> None:
    title = f"spark-vibe {uc} live demo"
    done = RESULTS / f"demo_{uc}.done"
    done.unlink(missing_ok=True)
    mp4 = MEDIA / f"{uc}-demo.mp4"
    demo = subprocess.Popen(["conhost.exe", sys.executable, str(BENCH / "demo.py"), uc, "--title", title,
                             "--hold", "3"], cwd=BENCH)
    hwnd = wait_window(title)
    user32.ShowWindow(hwnd, 9)
    user32.SetWindowPos(hwnd, 0, 40, 40, 0, 0, 0x0001 | 0x0004)  # SWP_NOSIZE | SWP_NOZORDER
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    ff = subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab", "-framerate", "10",
                           "-draw_mouse", "0", "-i", f"title={title}",
                           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
                          stdin=subprocess.PIPE)
    while not done.exists():
        if demo.poll() is not None:
            break
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)
    time.sleep(2.0)
    ff.communicate(b"q", timeout=60)
    demo.wait(timeout=120)
    if demo.returncode:
        raise RuntimeError(f"{uc} demo exited with {demo.returncode}; see bench/results/demo_{uc}.stderr.log")

    _, secs = imageio_ffmpeg.count_frames_and_secs(str(mp4))
    for tag, t in (("mid", secs * 0.55), ("final", max(secs - 0.5, 0))):
        subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4),
                        "-frames:v", "1", str(MEDIA / f"{uc}-shot-{tag}.png")], check=True)
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4), "-vf",
                    "fps=4,scale=880:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none",
                    str(MEDIA / f"{uc}-demo.gif")], check=True)
    print(f"{uc}: {secs:.1f}s -> {mp4.name}, {uc}-demo.gif, {uc}-shot-mid.png, {uc}-shot-final.png")


if __name__ == "__main__":
    MEDIA.mkdir(parents=True, exist_ok=True)
    for uc in sys.argv[1:] or ["uc1", "uc2", "uc3"]:
        record(uc)
