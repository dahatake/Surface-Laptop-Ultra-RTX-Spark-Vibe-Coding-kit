---
description: "UC3 Local Visual Critic Loop: UI を Vibe Coding し、スクリーンショットをローカル VLM が無料・無制限で審査する自走ループ"
agent: agent
---
あなたは Copilot Fusion（推奨: **Fusion Standard**。反復回数が多いため Cascade で軽量モデル中心）として動作しています。
作りたい UI: ${input:design:例: ダークテーマで 3 枚の指標カードと青いボタンがあるダッシュボード}
HTML の出力先: `${input:htmlPath:例: C:/Work/Temp/spark-fusion-vibe/demo/ui/index.html}`

ループ（最大 5 回）:
1. HTML/CSS を実装・修正する。
2. Playwright MCP（`browser_navigate` → `browser_take_screenshot`）または
   `msedge --headless=new --screenshot=<png> --window-size=1200,600 <file-uri>` でスクリーンショットを保存する。
3. `spark-vibe` の `visual_review`（RTX Spark 上のローカル VLM）に画像と受け入れ基準を渡す。
4. `issues` を受け入れ基準に照らして妥当なものだけ採用し、次の修正に反映する（ローカル VLM の指摘は「シグナル」として扱い、盲信しない）。
5. `verdict: pass` かつ score 8 以上、または 5 回到達で終了。
最後に各反復の score 推移表と、採用/却下した指摘を報告する。
