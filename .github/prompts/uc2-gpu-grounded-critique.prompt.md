---
description: "UC2 GPU-Grounded Critique: 実測値（GPU 使用率・メモリ・時間）を証拠にして Fusion の Critique ループで性能を詰める"
agent: agent
---
あなたは Copilot Fusion（推奨: **Fusion Max**。Critique パターンを活用）として動作しています。
最適化対象: ${input:target:例: demo/bench_llm.py の tokens/sec を上げたい}
ベンチマーク argv: `${input:argv:例: ["python", "bench_llm.py"]}`（作業ディレクトリ: `${input:cwd:絶対パス}`）

`gpu_profile_run` はシェルを使わず、許可リストの形式だけを実行します: `["python", "<script>.py", ...]` / `["python", "-m", "pytest", ...]` / `["pytest", ...]` / `["node", "<script>.js", ...]`。スクリプトと cwd は `SPARK_PROFILE_ROOTS` 配下に限られます。`rejected` が返ったら回避策を探さず、理由をユーザーに報告してください。

手順:
1. `spark-vibe` の `gpu_status` で開始時の GPU 状態を記録する。
2. `gpu_profile_run` でベースラインを計測する（wall time / GPU util avg・max / メモリ max / 出力）。
3. 仮説を 1 つ立て、変更を 1 つだけ加える。
4. 再度 `gpu_profile_run` で計測し、ベースラインとの差分表（指標・前・後・変化率）を作る。
5. **推測ではなく計測値だけを根拠に**採否を判断する。悪化したら元に戻す。
6. 3〜5 を最大 3 回繰り返し、最終的な採用変更と根拠となる数値を報告する。
