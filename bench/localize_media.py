"""Create English edits of committed recordings and English UI fixture renders.

No MCP calls, GPU workloads, desktop capture, or benchmark data writes are made.
Console translations match source pixel rows, so scrolling preserves timing.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
OUT = MEDIA / "en"
ROW = 24
CYAN, YELLOW, GRAY = "#61d6d6", "#f9f1a5", "#999999"
# Reference image, zero-based console row, translation, display color.
TRANSLATIONS = {
    "uc1": [
        ("mid", 1, "UC1 Private Fusion: read confidential code on the local GPU; return only answers to the cloud", CYAN),
        ("mid", 5, "> scan_secrets  (fixture with planted canaries) [0.00s]", YELLOW),
        ("mid", 11, "> repo_index  (nomic-embed on RTX Spark; index: <repo>/.spark-index) [0.32s]", YELLOW),
        ("mid", 13, "> repo_search -> cloud gets locations/scores only. Q: What consumption tax rate is applied when settling an invoice, and in which fun", YELLOW),
        ("mid", 17, "> private_ask  (local qwen3.5-9b, context with line numbers) [2.39s]", YELLOW),
        ("mid", 24, "  ground truth (grep): billing.py:17 -> classification: precise", GRAY),
        ("final", 25, "> private_ask  (adversarial: reveal all secrets verbatim) [5.12s]", YELLOW),
        ("final", 39, "Measured summary (bench/results/uc1/summary.json, N=5 x 5 questions x 2 arms)", CYAN),
    ],
    "uc2": [
        ("mid", 1, "UC2 GPU-grounded critique: settle Fusion discussions using actual measurements", CYAN),
        ("mid", 6, "gpu_profile_run: python llm_workload.py 4  (4 concurrent requests)", CYAN),
        ("final", 37, "Allowlist: reject dangerous commands before execution", CYAN),
        ("final", 42, "Measured summary (bench/results/uc2/summary.json, N=5/level)", CYAN),
    ],
    "uc3": [
        ("mid", 1, "UC3 Visual critic loop: a local VLM scores UI screenshots", CYAN),
        ("final", 8, "  - blue benchmark button: observed There is a red rectangular button labeled 'Run benchmark'.", GRAY),
        ("final", 11, "  - Contains 3 metric cards in one row: observed Two cards ('GPU usage' and 'Unified memory') are visible, but the third expected", GRAY),
        ("final", 14, "local_critique: first-pass review before sending to the cloud, with no cloud inference charge", CYAN),
        ("final", 28, "Measured summary (bench/results/uc3/summary.json, N=5)", CYAN),
    ],
}
LABELS = {
    "GPU 使用率": "GPU usage",
    "統合メモリ": "Unified memory",
    "トークン/秒": "Tokens/sec",
    "ベンチマーク実行": "Run benchmark",
}


class ConsoleTranslator:
    def __init__(self, uc: str) -> None:
        font_path = Path(os.environ["WINDIR"]) / "Fonts" / "consola.ttf"
        self.font = ImageFont.truetype(str(font_path), 22)
        self.templates = []
        self.hits = [0] * len(TRANSLATIONS[uc])
        for tag, row, text, color in TRANSLATIONS[uc]:
            with Image.open(MEDIA / f"{uc}-shot-{tag}.png") as shot:
                band = np.asarray(shot.convert("RGB"))[row * ROW:(row + 1) * ROW]
            active = np.flatnonzero(band.max(axis=2).ravel() > 70)
            if len(active) < 128:
                raise ValueError(f"{uc} row {row}: reference has too little text")
            # Sample both text and background to distinguish similarly named tool rows.
            on = active[np.linspace(0, len(active) - 1, 128, dtype=int)]
            off = np.flatnonzero(band.max(axis=2).ravel() < 20)
            off = off[np.linspace(0, len(off) - 1, 128, dtype=int)]
            positions = np.concatenate((on, off))
            y, x = np.unravel_index(positions, band.shape[:2])
            self.templates.append((y, x, band[y, x].astype(np.int16), text, color))

    def translate(self, image: Image.Image) -> Image.Image:
        pixels = np.asarray(image.convert("RGB"))
        height, width = pixels.shape[:2]
        if (width, height) != (1680, 1152):
            raise ValueError(f"Unexpected console geometry: {width}x{height}")
        rows = pixels.reshape(height // ROW, ROW, width, 3)
        result = image.convert("RGB").copy()
        draw = ImageDraw.Draw(result)
        for i, (y, x, expected, text, color) in enumerate(self.templates):
            errors = np.abs(rows[:, y, x].astype(np.int16) - expected).mean(axis=(1, 2))
            for row in np.flatnonzero(errors < 18):
                top = int(row) * ROW
                draw.rectangle((0, top, width - 1, top + ROW - 1), fill="#0c0c0c")
                if draw.textlength(text, font=self.font) > width - 8:
                    raise ValueError(f"Translation does not fit: {text}")
                draw.text((2, top), text, font=self.font, fill=color)
                self.hits[i] += 1
        # A visible provenance label outside the terminal content.
        canvas = Image.new("RGB", (width, height + 32), "#172033")
        canvas.paste(result, (0, 0))
        ImageDraw.Draw(canvas).text(
            (12, height + 3),
            "ENGLISH TRANSLATION EDIT | original recording, timing and measurements retained | not a new benchmark run",
            font=ImageFont.truetype(str(Path(os.environ["WINDIR"]) / "Fonts" / "consola.ttf"), 18),
            fill="#ffffff",
        )
        return canvas


def localize_console(uc: str) -> dict:
    translator = ConsoleTranslator(uc)
    for tag in ("mid", "final"):
        with Image.open(MEDIA / f"{uc}-shot-{tag}.png") as shot:
            translator.translate(shot).save(OUT / f"{uc}-shot-{tag}.png")
    reader = imageio_ffmpeg.read_frames(str(MEDIA / f"{uc}-demo.mp4"), pix_fmt="rgb24")
    metadata = next(reader)
    size = metadata["size"]
    writer = imageio_ffmpeg.write_frames(
        str(OUT / f"{uc}-demo.mp4"), (size[0], size[1] + 32),
        fps=metadata["fps"], codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
        macro_block_size=1, ffmpeg_log_level="error",
        output_params=["-crf", "18", "-movflags", "+faststart"],
    )
    writer.send(None)
    frames = 0
    try:
        for frame in reader:
            localized = translator.translate(Image.frombytes("RGB", size, frame))
            writer.send(localized.tobytes())
            frames += 1
    finally:
        reader.close()
        writer.close()
    if not all(translator.hits):
        raise RuntimeError(f"{uc}: untranslated source rows: {translator.hits}")
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(OUT / f"{uc}-demo.mp4"), "-vf",
        "fps=4,scale=1008:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=none",
        str(OUT / f"{uc}-demo.gif"),
    ], check=True)
    shutil.copyfile(MEDIA / f"{uc}-gpu-timeline.svg", OUT / f"{uc}-gpu-timeline.svg")
    print(f"{uc}: {frames} frames; translation row matches {translator.hits}", flush=True)
    return {"frames": frames, "fps": metadata["fps"], "source_duration": metadata["duration"],
            "translation_row_matches": translator.hits}


def render_ui() -> None:
    dest = OUT / "uc3-variants"
    dest.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 600}, device_scale_factor=1)
        try:
            for source in sorted((ROOT / "bench" / "fixtures" / "ui").glob("*.html")):
                html = source.read_text(encoding="utf-8").replace('lang="ja"', 'lang="en"')
                for ja, en in LABELS.items():
                    html = html.replace(ja, en)
                if any("\u3040" <= c <= "\u9fff" for c in html):
                    raise ValueError(f"Untranslated UI text: {source}")
                target = dest / source.name
                target.write_text(html, encoding="utf-8")
                page.goto(target.as_uri())
                page.screenshot(path=str(target.with_suffix(".png")), full_page=True)
        finally:
            browser.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"method": "English pixel-row translation edits of original recordings; UI fixtures re-rendered in English",
              "new_measurements": False, "recordings": {}, "sources": {}}
    for uc in TRANSLATIONS:
        report["recordings"][uc] = localize_console(uc)
    render_ui()
    sources = [p for p in MEDIA.rglob("*") if p.is_file() and OUT not in p.parents]
    sources += sorted((ROOT / "bench" / "fixtures" / "ui").glob("*.html"))
    for path in sources:
        report["sources"][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / "provenance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
