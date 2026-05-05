import pandas as pd


class BacktestEngine:
    """バックテストエンジン"""

    def __init__(self, csv_path, logic_module, spread_pips=0, slippage_pips=0, pip_multiplier=100, pip_unit="pips"):
        """
        初期化

        Args:
            csv_path: CSVファイルパス
            spread_pips: スプレッド (pips) ※将来の拡張用
            slippage_pips: スリッページ (pips) ※将来の拡張用
            pip_multiplier: pips換算倍率（JPYペア=100, Gold=1, EURペア=10000）
            pip_unit: 表示単位
        """
        self.csv_path = csv_path
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.pip_multiplier = pip_multiplier
        self.pip_unit = pip_unit
        self.logic_module = logic_module

        # データ
        self.df = None

        # トレード記録
        self.trades = []
        self.current_position = None  # None, 'long', 'short'
        self.entry_time = None
        self.entry_price = None

        # パフォーマンス指標
        self.total_pips = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_win_pips = 0
        self.total_loss_pips = 0

    def load_data(self):
        """CSVファイルを読み込み、標準フォーマットに変換"""
        self.df = pd.read_csv(self.csv_path)

        # 列名を標準化（<>を除去、小文字に統一）
        self.df.columns = self.df.columns.str.replace('<', '').str.replace('>', '').str.lower()

        # フォーマット判定と変換
        if 'ticker' in self.df.columns and 'dtyyyymmdd' in self.df.columns:
            # Forex Tester形式
            self.df = self._convert_forex_tester_format()
        elif 'utc' in self.df.columns:
            # 既存ドル円形式
            self.df = self._convert_standard_format()
        elif 'time' in self.df.columns:
            # 標準形式（そのまま使用）
            self.df['time'] = pd.to_datetime(self.df['time'], dayfirst=True)
        else:
            raise ValueError("不明なCSVフォーマットです")

    def _convert_forex_tester_format(self):
        """Forex Tester形式を標準フォーマットに変換"""
        df_converted = pd.DataFrame()

        # DTYYYYMMDD + TIME を datetime に変換
        date_str = self.df['dtyyyymmdd'].astype(str)
        time_str = self.df['time'].astype(str).str.zfill(4)  # 4桁に0埋め
        datetime_str = date_str + ' ' + time_str

        df_converted['datetime'] = pd.to_datetime(datetime_str, format='%Y%m%d %H%M')
        df_converted['open'] = self.df['open']
        df_converted['high'] = self.df['high']
        df_converted['low'] = self.df['low']
        df_converted['close'] = self.df['close']
        df_converted['volume'] = self.df['vol']

        # timeカラムにリネーム（既存ロジック互換性）
        df_converted = df_converted.rename(columns={'datetime': 'time'})

        return df_converted

    def _convert_standard_format(self):
        """既存ドル円形式を標準フォーマットに変換"""
        df_converted = pd.DataFrame()

        # UTCカラムをdatetimeに変換
        df_converted['time'] = pd.to_datetime(self.df['utc'], dayfirst=True)
        df_converted['open'] = self.df['open']
        df_converted['high'] = self.df['high']
        df_converted['low'] = self.df['low']
        df_converted['close'] = self.df['close']
        df_converted['volume'] = self.df['volume']

        return df_converted

    def check_long_entry(self, idx):
        return self.logic_module.check_long_entry(self.df, idx)

    def check_short_entry(self, idx):
        return self.logic_module.check_short_entry(self.df, idx)

    def check_long_exit(self, idx):
        return self.logic_module.check_long_exit(self.df, idx)

    def check_short_exit(self, idx):
        return self.logic_module.check_short_exit(self.df, idx)

    def enter_position(self, idx, direction):
        """エントリー"""
        if idx + 1 >= len(self.df):
            return

        self.current_position = direction
        self.entry_time = self.df['time'].iloc[idx + 1]
        self.entry_price = self.df['open'].iloc[idx + 1]

    def exit_position(self, idx):
        """決済"""
        if idx + 1 >= len(self.df):
            return

        exit_time = self.df['time'].iloc[idx + 1]
        exit_price = self.df['open'].iloc[idx + 1]

        # 損益計算
        if self.current_position == 'long':
            pips = (exit_price - self.entry_price) * self.pip_multiplier
        else:  # short
            pips = (self.entry_price - exit_price) * self.pip_multiplier

        # トレード記録
        self.trades.append({
            'entry_time': self.entry_time,
            'exit_time': exit_time,
            'direction': self.current_position,
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'pips': pips
        })

        # 統計更新
        self.total_pips += pips
        if pips > 0:
            self.win_count += 1
            self.total_win_pips += pips
        else:
            self.loss_count += 1
            self.total_loss_pips += abs(pips)

        # ポジションクリア
        self.current_position = None
        self.entry_time = None
        self.entry_price = None

    def run(self):
        """バックテスト実行"""
        self.load_data()
        self.df = self.logic_module.populate_indicators(self.df)

        # 1本ずつ処理（ライブ版と同じ順序：決済→次の足でエントリー）
        for idx in range(len(self.df)):
            # 決済チェック（先に決済）
            just_exited = False
            if self.current_position == 'long' and self.check_long_exit(idx):
                self.exit_position(idx)
                just_exited = True
            elif self.current_position == 'short' and self.check_short_exit(idx):
                self.exit_position(idx)
                just_exited = True

            # エントリーチェック（決済した足ではエントリーしない）
            if self.current_position is None and not just_exited:
                if self.check_long_entry(idx):
                    self.enter_position(idx, 'long')
                elif self.check_short_entry(idx):
                    self.enter_position(idx, 'short')

        # 未決済ポジションの強制決済
        if self.current_position is not None and len(self.df) > 0:
            last_idx = len(self.df) - 1
            exit_price = self.df['close'].iloc[last_idx]
            exit_time = self.df['time'].iloc[last_idx]

            if self.current_position == 'long':
                pips = (exit_price - self.entry_price) * self.pip_multiplier
            else:
                pips = (self.entry_price - exit_price) * self.pip_multiplier

            trade = {
                'entry_time': self.entry_time,
                'exit_time': exit_time,
                'direction': self.current_position,
                'entry_price': self.entry_price,
                'exit_price': exit_price,
                'pips': pips
            }
            self.trades.append(trade)

            # 統計更新
            self.total_pips += pips
            if pips > 0:
                self.win_count += 1
                self.total_win_pips += pips
            else:
                self.loss_count += 1
                self.total_loss_pips += abs(pips)

            # ポジションクリア
            self.current_position = None
            self.entry_time = None
            self.entry_price = None

    def calculate_metrics(self):
        """パフォーマンス指標を計算"""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0

        avg_win = self.total_win_pips / self.win_count if self.win_count > 0 else 0
        avg_loss = self.total_loss_pips / self.loss_count if self.loss_count > 0 else 0

        profit_factor = self.total_win_pips / self.total_loss_pips if self.total_loss_pips > 0 else float('inf')

        # 最大ドローダウン
        cumulative_pips = []
        cum_sum = 0
        for trade in self.trades:
            cum_sum += trade['pips']
            cumulative_pips.append(cum_sum)

        max_dd = 0
        peak = cumulative_pips[0] if cumulative_pips else 0
        for pips in cumulative_pips:
            if pips > peak:
                peak = pips
            dd = peak - pips
            if dd > max_dd:
                max_dd = dd

        return {
            'total_pips': self.total_pips,
            'total_trades': total_trades,
            'win_count': self.win_count,
            'loss_count': self.loss_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_dd
        }
