# English media

[English user guide](../../README.en.md) | [Japanese originals](../)

These are separate English counterparts of **all 22 original media files** in the user guide: three MP4 recordings, three animated GIF previews, six console screenshots, three GPU timelines, and seven UI-variant screenshots.

## What was translated

- **Console PNGs and MP4s**: Japanese narration, labels, and Japanese UI labels quoted in model responses are replaced with English text in the original captured frames. Matching uses pixel-row templates from the committed screenshots and follows those rows when the console scrolls. A visible footer identifies every translated console image and video as a translation edit, **not a new benchmark run**.
- **Timing and evidence**: MP4 frame counts, frame rate, sequence, and duration are retained. Measured values, tool responses outside the translated rows, and benchmark logs are unchanged. Timings printed in translated labels come from the original recording, not the current machine. These recordings have no audio narration.
- **GIFs**: Animated previews are generated from the English MP4s at 4 fps, just as the Japanese previews were derived from their recordings.
- **UI variants**: The seven HTML fixtures are translated and rendered afresh using Playwright at 1200 × 600. Only the language and visible labels change. Values, CSS, and each deliberately introduced defect are preserved. The English HTML sources are included alongside their PNGs. **The reported VLM scores were measured on the Japanese originals**, not on these translated renders; no new model assessment is claimed.
- **GPU timelines**: Already fully English; copied byte-for-byte, with no change to the plotted measurements.

| Use case | Video | Preview | Screenshots | Timeline |
|---|---|---|---|---|
| UC1 | [MP4](./uc1-demo.mp4) | [GIF](./uc1-demo.gif) | [Mid](./uc1-shot-mid.png) / [Final](./uc1-shot-final.png) | [SVG](./uc1-gpu-timeline.svg) |
| UC2 | [MP4](./uc2-demo.mp4) | [GIF](./uc2-demo.gif) | [Mid](./uc2-shot-mid.png) / [Final](./uc2-shot-final.png) | [SVG](./uc2-gpu-timeline.svg) |
| UC3 | [MP4](./uc3-demo.mp4) | [GIF](./uc3-demo.gif) | [Mid](./uc3-shot-mid.png) / [Final](./uc3-shot-final.png) | [SVG](./uc3-gpu-timeline.svg) |

### UI variants

| Variant | English screenshot | Render source |
|---|---|---|
| Original passing UI | [PNG](./uc3-variants/pass_original.png) | [HTML](./uc3-variants/pass_original.html) |
| Different passing values | [PNG](./uc3-variants/pass_other_values.png) | [HTML](./uc3-variants/pass_other_values.html) |
| Stacked cards | [PNG](./uc3-variants/fail_stacked.png) | [HTML](./uc3-variants/fail_stacked.html) |
| Missing third card | [PNG](./uc3-variants/fail_two_cards.png) | [HTML](./uc3-variants/fail_two_cards.html) |
| Red button | [PNG](./uc3-variants/fail_red_button.png) | [HTML](./uc3-variants/fail_red_button.html) |
| Wrong title | [PNG](./uc3-variants/fail_wrong_title.png) | [HTML](./uc3-variants/fail_wrong_title.html) |
| Light theme | [PNG](./uc3-variants/fail_light_theme.png) | [HTML](./uc3-variants/fail_light_theme.html) |

## Reproduce and verify

From the repository root on Windows, using the existing project environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r bench\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe bench\localize_media.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_localization.py -v
```

The generator also requires the root project's dependencies and Windows' Consolas font. It does not open desktop windows, capture the desktop, call MCP tools, run GPU workloads, or overwrite Japanese assets or benchmark results. It fails on unexpected console geometry, missing translation matches, overlong labels, or untranslated fixture text.

[`provenance.json`](./provenance.json) records source SHA-256 hashes, frame counts, frame rates, durations, and translation-row match counts. If original recordings or screenshots change, review and update the row templates in [`bench/localize_media.py`](../../../bench/localize_media.py) before regenerating. Re-run the English document checks when updating Japanese documentation; [`bench/report.py`](../../../bench/report.py) updates only the Japanese measured reports.
