# CLAUDE.md — fx_trading_bot

## ユーザー指示

- 「Obsidianに書いといて」と言われたら、`C:\Users\tf10c\Dropbox\ObsidianVault\EA.md` の `## やったこと` セクションの今日の日付（`## YYYY-MM-DD`）に箇条書きで追記する

## プロジェクト概要
R氏の「平均足 + 75SMA」手法のバックテスト・シグナル検出システム。

## ファイル構成と役割

| ファイル | 役割 |
|--------|------|
| `streamlit_app_lightweight.py` | **メインUI**。TradingView Lightweight Charts使用。これが最新のバックテスト画面 |
| `backtest2.py` | CLIバックテスト。Excel/PineScript出力あり |
| `backtest2_with_streamlit.py` | 旧Streamlit版（Plotly使用）。現在は非推奨 |
| `entry_logic.py` | OANDAライブAPI接続・リアルタイムシグナル判定 |
| `heikin_ashi.py` | 平均足計算（entry_logic.pyから使用） |
| `get_price.py` | OANDA現在価格取得 |
| `data/` | バックテスト用CSVデータ置き場 |
| `output/` | バックテスト結果出力先 |

## 注意：BacktestEngineが複数存在する
`backtest2.py` と `streamlit_app_lightweight.py` にそれぞれ `BacktestEngine` クラスがある（重複）。
- `backtest2.py` 版: `ha_color` が `'blue'/'red'` 文字列、pip計算は `* 100` 固定
- `streamlit_app_lightweight.py` 版: `ha_color` が `1/-1` 整数、`pip_multiplier` パラメータあり（銘柄対応済み）

修正は基本的に `streamlit_app_lightweight.py` を対象にすること。

## 取引ロジック（共通）
- **BUY**: 価格 > 75SMA ＋ SMA上昇トレンド ＋ 平均足 赤→青
- **SELL**: 価格 < 75SMA ＋ SMA下降トレンド ＋ 平均足 青→赤
- **エントリー**: シグナル発生の次の足の始値
- **決済**: 平均足の色が逆転した次の足の始値

## pip換算の仕様（streamlit版）
銘柄によって換算倍率が異なる。ファイル名から自動判定：

| 銘柄 | 倍率 | 単位 | 判定キーワード |
|------|------|------|--------------|
| Gold/Silver/原油など | × 1 | USD | gold, xau, silver, xag, oil, wti, cl |
| USD/JPY等 JPYペア | × 100 | pips | jpy |
| EUR/USD等 その他 | × 100 | pips | （デフォルト） |

## CSVフォーマット対応
- **Forex Tester形式**: `TICKER`, `DTYYYYMMDD`, `TIME` カラムあり
- **OANDA形式**: `UTC` カラムあり
- **標準形式**: `time` カラムあり

## 実行方法
```bash
# メインUI（推奨）
streamlit run streamlit_app_lightweight.py

# CLIバックテスト
python backtest2.py

# ライブシグナル
python entry_logic.py
```

または `.bat` ファイル（`■run_streamlit_lightweight.bat` 等）を使用。

## 環境設定
`.env` をこのフォルダ直下に作成：
```
OANDA_DEMO_API_TOKEN=your_token
OANDA_DEMO_ACCOUNT_ID=your_account_id
```

## コーディング規約（streamlit_app_lightweight.py）

### 定数
ファイル先頭の定数を使うこと。ハードコードしない。

| 定数 | 値 | 用途 |
|------|-----|------|
| `SMA_PERIOD` | `75` | SMA期間 |
| `COLOR_PROFIT` | `#4CAF50` | 利益・プラス表示（緑） |
| `COLOR_LOSS` | `#f23645` | 損失・マイナス表示（赤） |
| `COLOR_LONG` | `#26a69a` | ロング・エントリー方向（緑） |
| `COLOR_SHORT` | `#ef5350` | ショート・決済方向（赤） |
| `COLOR_ENTRY_MARKER` | `#2196F3` | エントリーマーカー（青） |
| `COLOR_CLICK_LINE` | `#ffff00` | クリック縦線（黄） |

### タイムスタンプ変換
`calendar.timegm(ts.timetuple())` を使う。`.timestamp()` はタイムゾーンの影響を受けるので使わない。

### ループ
取引データ（trades）のループは1つにまとめる。テーブルHTML生成とJS用JSONデータ生成は同じループ内で行う。

### デバッグコード
`console.log` はコミット前に削除する。デバッグ用のサイドバーセクションも残さない。
