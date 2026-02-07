## fx_trading_bot

### 何が入っているか
- `backtest2.py`: CSV（`data/`）でバックテスト → 結果を `output/` に保存
- `backtest2_with_streamlit.py`: Streamlitでバックテスト可視化（CSVは `data/`）
- `entry_logic.py`: OANDA Practice API からデータ取得してエントリー判定（平均足/75SMA）

### セットアップ
PowerShell 例：

```powershell
cd C:\Users\tf10c\project\fx_trading_bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### OANDA（Practice）設定
`entry_logic.py` / `get_price.py` / `test_connection.py` は環境変数を使います。

- `OANDA_DEMO_API_TOKEN`
- `OANDA_DEMO_ACCOUNT_ID`

`.env` はこのフォルダ（`fx_trading_bot`）直下に作ってください（例）：

```env
OANDA_DEMO_API_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
OANDA_DEMO_ACCOUNT_ID=001-001-1234567-001
```

### 実行
#### バックテスト（CLI）

```powershell
python .\backtest2.py
```

出力は `output/` に作られます（実行場所が変わっても崩れません）。

#### バックテスト（Streamlit）

```powershell
streamlit run .\backtest2_with_streamlit.py
```

#### エントリー判定（OANDA Practice）

```powershell
python .\entry_logic.py
```

