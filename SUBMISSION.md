# 審査員の方へ — 提出物とリポジトリの対応表

**作品名**: 心理学ハーネス — AIエージェントに人間らしい心理を与える(プロジェクト名: Pneuma Lab)
**参加形態**: 個人(参加者番号 0153 ／ 水谷享平)
**一言で**: 性格・感情・関係の数理モデルで毎ターン心理状態を計算し、構造化した文脈としてLLMに渡すハーネス。ハーネスなしのAIと同一条件で比較し、駆け引きゲームと1年間の共同生活で「物語の人間らしさ」がどう変わるかを検証した。

## 提出物がどのファイルに当たるか

| スライドで触れたもの | リポジトリ内の場所 |
|---|---|
| 心理エンジン本体(Big Five・PAD・関係値の計算) | `src/pneuma_lab/psyche.py` |
| 心理状態→日本語の「文脈」への翻訳 | `src/pneuma_lab/appraisal.py`, `src/pneuma_lab/prompts.py` |
| 発言が感情・関係を動かす仕組み(発話評価) | `src/pneuma_lab/appraiser.py` |
| 駆け引きゲーム(ラストランプ改)の実装 | `src/pneuma_lab/protocols/socialgame.py`, `deathgame.py` |
| 1年間の共同生活シミュレーション | `src/pneuma_lab/protocols/yearlife.py` |
| 心理学実験(討議・分配交渉・同調・サンクコスト等) | `src/pneuma_lab/protocols/` 各ファイル |
| シナリオ定義(JSONを足すだけで新シナリオ) | `scenarios/*.json` |
| キャラクター定義(性格数値+核となる不安) | `characters/*.json` |
| リプレイビューワ(会話と本音とパラメータを同時再生) | `output/theater_deathgame2.html` をブラウザで開く |
| 仕組みの解説サイト(たとえ話⇄数式の5段階) | `docs/algorithm-site.html` をブラウザで開く |
| スライドの原本 | `slides/slides.html`(ブラウザで開くとプレゼン表示・Cmd+PでPDF) |

## 実験の生ログ(すべて公開)

| 実験 | 場所 |
|---|---|
| 1年の共同生活・ハーネスなし | `output/yearlife-identity/` |
| 1年の共同生活・ハーネスあり(修正前の関係力学) | `output/yearlife-pneuma/` |
| 1年の共同生活・ハーネスあり(修正後。スライドで使用) | `output/yearlife-pneuma-v3/` |
| 駆け引きゲーム | `output/deathgame2-v1/` ほか `output/` 配下 |
| 心理学実験(討議・同調・分配交渉・サンクコスト等) | `output/` 配下の各ラン |

各ランの `*.jsonl` に、AIへ送った指示文の全文・生の応答・心理状態のスナップショットが1行1イベントで残っています。`manifest.json` に使用モデル・コミットIDを記録しています。1年ランは `*_summary.json` に日記(週次×52)と月次まとめがまとまっています。

## 5分で確かめる手順

```bash
uv sync && uv run pytest   # テスト132本(LLM呼び出しなしで完結)
```

- 心理計算は乱数なしの決定論。条件間で課題文が1文字も違わないことをテストが機械検査します
- 実験の再実行はClaude Codeのログインのみで可能(APIキー不要)。例:
  `uv run python scripts/run_protocols.py --protocol yearlife --scenario flatmates-year-v3 --arms pure_pneuma --model sonnet --days 7`

## 正直な注意書き

各実験は条件ごとに1〜5回の探索的研究で、統計的証明ではありません。効かなかったこと(同調・サンクコストなどの非合理な判断は再現されない)も、修正の経緯(1年ランで関係値が飽和→仲直りの力学を追加して回し直し)も、そのまま公開しています。
