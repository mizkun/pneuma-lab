# 審査員の方へ — 5分でこの作品に到達する地図

**作品名**: Pneuma Lab — 心を計算し、行動は選ばないハーネス
**参加形態**: 個人
**一言で**: LLMキャラクターの性格・感情・関係を毎ターン決定論計算して「内面」として注入し、素のLLM・固定キャラ設定と**同一条件で比較**して、人間らしい社会的挙動（個性・率直さ・裏切り・自己犠牲）がどこから生まれるかを検証した。

## まず見るもの（時間がない方向け）

| 時間 | 見るもの | 場所 |
|---|---|---|
| 3分 | デモ動画（またはブラウザで `docs/demo-reel.html` を開いて▶） | YouTube限定公開リンク（提出フォーム記載） |
| +3分 | 実験レポート（初見向け・検証と撤回の経緯込み） | `docs/report.html` をブラウザで開く |
| +2分 | デスゲームのリプレイ（実ログをそのまま再生） | `output/theater_deathgame2.html` |
| +2分 | 仕組みの解説（難易度スライダー: たとえ話⇄論文） | `docs/algorithm-site.html` |

## 主要な主張と、その証拠の場所

1. **素のLLM集団はクローン**（11ラン中10ランで3体の事前判断が完全一致）
   → `output/surg-rep*-raw/`, `output/rep*-raw/` の各 `*_summary.json`
2. **豊かな内面コンテキストは「最も慎重な人への全員一致」を壊す**（固定キャラ設定 5/5 vs Pneuma 0/5）
   → `output/surg-rep*-identity/`, `output/surg-rep*-pneuma/`（+凍結アブレーション `surg-rep*-frozen/`）
3. **内面があると、本音を討議の前から公言する**（朱里の私的評定→第一声: identity 4→6が5/5、pneuma 4→4）
   → 各jsonlの `rating(pre)` と最初の `action` を対照
4. **裏切りはルールが解禁し、キャラクターはほぼ必ず予告してから裏切る**（明確な騙し討ちは1件のみ）
   → `output/deathgame2-v1/`, lesion対照 `output/deathgame2-lesion/`, 手動検証は `docs/report.html` 内
5. **検証と撤回の全過程を公開**（凍結アブレーション・lesion test・コンテクスト非共有の独立AI査読2系統）
   → `docs/report.html` の「正直な限界」、撤回はコミット履歴にも残存

## 再現方法

```bash
uv sync && uv run pytest              # テスト122本（LLM呼び出しなしで完結）
# 実験の再実行（要 Claude Code ログイン。APIキー不要）
uv run python scripts/run_experiment.py --item surgery --arms raw identity_only pure_pneuma frozen_pneuma
uv run python scripts/run_protocols.py --protocol socialgame --scenario lastlamp --arms pure_pneuma
```

- 全実験ランの**送信プロンプト・生応答・心理状態スナップショット**を `output/**/*.jsonl` に完全保存
- 心理計算は乱数なしの決定論（`src/pneuma_lab/psyche.py`）。アーム間の客観情報一致・禁止語彙の不在はテストで機械検査
- 新しいシナリオは `scenarios/socialgames_ja.json` にJSONを1つ足すだけで実行可能

## 正直な注意書き

各条件 n=3〜5 の探索的研究であり、統計的証明ではない。誇張になりうる主張は独立査読（Codex / 別セッションのClaude）を受けて縮約・撤回済みで、その経緯もレポートに記載している。
