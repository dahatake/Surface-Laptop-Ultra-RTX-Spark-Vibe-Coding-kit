"""Offline checks for English guide coverage, navigation, and media evidence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

import imageio_ffmpeg
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MEDIA = DOCS / "media"
EN = MEDIA / "en"


def headings(text: str) -> set[str]:
    anchors = set()
    duplicates: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE):
        heading = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", heading)
        anchor = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        n = duplicates.get(anchor, 0)
        duplicates[anchor] = n + 1
        anchors.add(f"{anchor}-{n}" if n else anchor)
    return anchors


class EnglishDocumentationTests(unittest.TestCase):
    def test_every_original_document_has_english_counterpart(self) -> None:
        sources = [ROOT / "README.md"] + sorted(DOCS.glob("*.md")) + sorted((DOCS / "use-cases").glob("*.md"))
        sources = [p for p in sources if not p.name.endswith(".en.md")]
        self.assertEqual(len(sources), 11)
        for source in sources:
            with self.subTest(document=source.relative_to(ROOT)):
                translated = source.with_name(source.stem + ".en.md")
                self.assertTrue(translated.is_file())
                original = source.read_text(encoding="utf-8")
                english = translated.read_text(encoding="utf-8")
                links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", english)
                self.assertTrue(any((translated.parent / link).resolve() == source.resolve()
                                    for link in links if not urlsplit(link).scheme),
                                f"No link back to {source.name}")
                self.assertGreaterEqual(
                    len(re.findall(r"^#{1,6} ", english, re.MULTILINE)),
                    len(re.findall(r"^#{1,6} ", original, re.MULTILINE)),
                )

    def test_english_links_and_heading_fragments_resolve(self) -> None:
        documents = [ROOT / "README.en.md"] + sorted(DOCS.rglob("*.en.md"))
        for doc in documents:
            text = doc.read_text(encoding="utf-8")
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
                with self.subTest(document=doc.relative_to(ROOT), link=target):
                    target = target.strip("<>")
                    url = urlsplit(target)
                    if url.scheme or url.netloc:
                        continue
                    path = (doc.parent / unquote(url.path)).resolve() if url.path else doc
                    self.assertTrue(path.exists(), f"Missing link target: {path}")
                    if url.fragment and path.suffix == ".md":
                        self.assertIn(unquote(url.fragment), headings(path.read_text(encoding="utf-8")))
                    if path.is_relative_to(MEDIA) and path.suffix in {".png", ".gif", ".mp4", ".svg"}:
                        self.assertTrue(path.is_relative_to(EN), "English doc refers to Japanese media")

    def test_measured_table_numbers_are_preserved(self) -> None:
        def table_rows(path: Path) -> list[list[str]]:
            return [[cell.strip() for cell in line.strip("|").split("|")]
                    for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("|")]

        for source in [DOCS / "measurements.md"] + sorted((DOCS / "use-cases").glob("*.md")):
            if source.name.endswith(".en.md"):
                continue
            with self.subTest(document=source.name):
                original = table_rows(source)
                translated = table_rows(source.with_name(source.stem + ".en.md"))
                self.assertEqual(len(original), len(translated))
                for row_index, (ja_row, en_row) in enumerate(zip(original, translated)):
                    self.assertEqual(len(ja_row), len(en_row))
                    for column, (ja, en) in enumerate(zip(ja_row, en_row)):
                        # Numeric data, not prose such as Japanese "1st" becoming "first".
                        if re.match(r"\d", ja.lstrip("*`")) and not re.search(r"[\u3040-\u9fff]", ja):
                            ja = re.sub(r"(?<=\d),(?=\d{3})", "", ja)
                            en = re.sub(r"(?<=\d),(?=\d{3})", "", en)
                            self.assertEqual(re.findall(r"\d+(?:\.\d+)?", ja),
                                             re.findall(r"\d+(?:\.\d+)?", en),
                                             f"{source.name} table row {row_index}, column {column}")


class EnglishMediaTests(unittest.TestCase):
    def test_all_original_media_have_counterparts(self) -> None:
        sources = [p for p in MEDIA.rglob("*") if p.is_file() and EN not in p.parents]
        self.assertEqual(len(sources), 22)
        for source in sources:
            self.assertTrue((EN / source.relative_to(MEDIA)).is_file(), str(source))

    def test_provenance_matches_unchanged_sources(self) -> None:
        report = json.loads((EN / "provenance.json").read_text(encoding="utf-8"))
        self.assertIs(report["new_measurements"], False)
        self.assertEqual(len(report["sources"]), 29)
        for name, digest in report["sources"].items():
            with self.subTest(source=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

    def test_console_images_and_timelines(self) -> None:
        for uc in ("uc1", "uc2", "uc3"):
            self.assertEqual((MEDIA / f"{uc}-gpu-timeline.svg").read_bytes(),
                             (EN / f"{uc}-gpu-timeline.svg").read_bytes())
            for tag in ("mid", "final"):
                with Image.open(EN / f"{uc}-shot-{tag}.png") as image:
                    image.load()
                    self.assertEqual(image.size, (1680, 1184))
                    self.assertGreater(len(image.crop((0, 1152, 1680, 1184)).getcolors(100000) or []), 2)

    def test_recordings_decode_and_retain_timing(self) -> None:
        report = json.loads((EN / "provenance.json").read_text(encoding="utf-8"))
        for uc in ("uc1", "uc2", "uc3"):
            with self.subTest(recording=uc):
                frames, seconds = imageio_ffmpeg.count_frames_and_secs(str(EN / f"{uc}-demo.mp4"))
                source_frames, source_seconds = imageio_ffmpeg.count_frames_and_secs(str(MEDIA / f"{uc}-demo.mp4"))
                self.assertEqual(frames, source_frames)
                self.assertAlmostEqual(seconds, source_seconds, places=2)
                self.assertEqual(frames, report["recordings"][uc]["frames"])
                self.assertTrue(all(report["recordings"][uc]["translation_row_matches"]))
                reader = imageio_ffmpeg.read_frames(str(EN / f"{uc}-demo.mp4"))
                try:
                    metadata = next(reader)
                    self.assertEqual(metadata["fps"], report["recordings"][uc]["fps"])
                    self.assertEqual(metadata["size"], (1680, 1184))
                finally:
                    reader.close()
                subprocess.run([
                    imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-xerror",
                    "-i", str(EN / f"{uc}-demo.mp4"), "-f", "null", "-",
                ], check=True, capture_output=True)
                with Image.open(EN / f"{uc}-demo.gif") as preview:
                    self.assertTrue(preview.is_animated)
                    duration_ms = 0
                    for frame in range(preview.n_frames):
                        preview.seek(frame)
                        preview.load()
                        duration_ms += preview.info["duration"]
                    self.assertLessEqual(abs(duration_ms / 1000 - seconds), 0.35)

    def test_english_ui_retains_each_original_defect(self) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 600})
            try:
                for original in sorted((ROOT / "bench" / "fixtures" / "ui").glob("*.html")):
                    variant = original.stem
                    with self.subTest(variant=variant):
                        html = EN / "uc3-variants" / original.name
                        page.goto(html.as_uri())
                        self.assertEqual(page.locator("html").get_attribute("lang"), "en")
                        self.assertNotRegex(page.locator("body").inner_text(), r"[\u3040-\u9fff]")
                        self.assertEqual(page.locator("button").inner_text(), "Run benchmark")
                        self.assertEqual(page.locator(".card").count(), 2 if variant == "fail_two_cards" else 3)
                        title = "GPU Monitor" if variant == "fail_wrong_title" else "RTX Spark Dashboard"
                        self.assertEqual(page.locator("h1").inner_text(), title)
                        color = page.locator("button").evaluate("(e) => getComputedStyle(e).backgroundColor")
                        self.assertEqual(color, "rgb(220, 38, 38)" if variant == "fail_red_button" else "rgb(37, 99, 235)")
                        background = page.locator("body").evaluate("(e) => getComputedStyle(e).backgroundColor")
                        self.assertEqual(background, "rgb(248, 250, 252)" if variant == "fail_light_theme" else "rgb(15, 23, 42)")
                        cards = page.locator(".card").all()
                        first, second = cards[0].bounding_box(), cards[1].bounding_box()
                        self.assertIsNotNone(first)
                        self.assertIsNotNone(second)
                        assert first is not None and second is not None
                        self.assertEqual(first["y"] == second["y"], variant != "fail_stacked")
                        values = page.locator(".card .v").all_text_contents()
                        self.assertEqual(values[:2], ["91%", "44 GB"] if variant == "pass_other_values" else ["72%", "38 GB"])
                        with Image.open(html.with_suffix(".png")) as screenshot:
                            screenshot.load()
                            self.assertEqual(screenshot.size, (1200, 600))
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
