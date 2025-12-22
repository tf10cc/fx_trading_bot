"""
FX バックテストシステム（りょうちゃん75SMA手法）
仕様書どおりに実装
"""

import pandas as pd
import numpy as np
import os
import glob


class BacktestEngine:
    """バックテストエンジン"""
    
    def __init__(self, csv_path, spread_pips=0, slippage_pips=0):
        """
        初期化
        
        Args:
            csv_path: CSVファイルパス
            spread_pips: スプレッド（pips）※将来の拡張用
            slippage_pips: スリッページ（pips）※将来の拡張用
        """
        self.csv_path = csv_path
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        
        # 取引履歴
        self.trades = []
        
        # 現在のポジション
        self.position = None  # None / 'long' / 'short'
        self.entry_price = None
        self.entry_time = None
        
    def load_data(self):
        """CSVデータ読み込み"""
        df = pd.read_csv(self.csv_path)
        df['time'] = pd.to_datetime(df['time'], dayfirst=True)
        return df
    
    def calculate_sma(self, df, period=75):
        """75SMA計算"""
        df['sma75'] = df['close'].rolling(window=period).mean()
        return df
    
    def calculate_heikin_ashi(self, df):
        """平均足計算"""
        ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        
        ha_open = pd.Series(index=df.index, dtype=float)
        ha_open.iloc[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
        
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
        
        ha_high = pd.concat([df['high'], ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([df['low'], ha_open, ha_close], axis=1).min(axis=1)
        
        df['ha_open'] = ha_open
        df['ha_close'] = ha_close
        df['ha_high'] = ha_high
        df['ha_low'] = ha_low
        
        return df
    
    def calculate_ha_color(self, df):
        """平均足の色判定"""
        df['ha_color'] = np.where(df['ha_close'] >= df['ha_open'], 'blue', 'red')
        return df
    
    def calculate_ha_body(self, df):
        """平均足の実体位置"""
        df['body_low'] = df[['ha_open', 'ha_close']].min(axis=1)
        df['body_high'] = df[['ha_open', 'ha_close']].max(axis=1)
        return df
    
    def check_trend(self, df, i):
        """
        トレンド判定
        
        Returns:
            'up': 上昇トレンド
            'down': 下降トレンド
            None: トレンドなし
        """
        if i < 5:
            return None
        
        sma_now = df['sma75'].iloc[i]
        sma_prev = df['sma75'].iloc[i-5]
        
        if pd.isna(sma_now) or pd.isna(sma_prev):
            return None
        
        if sma_now > sma_prev:
            return 'up'
        elif sma_now < sma_prev:
            return 'down'
        else:
            return None
    
    def check_long_entry(self, df, i):
        """
        ロングエントリー条件チェック（足iで判定）
        
        Returns:
            bool: エントリー可否
        """
        if i < 5:
            return False
        
        if self.position is not None:
            return False
        
        trend = self.check_trend(df, i)
        if trend != 'up':
            return False
        
        body_low = df['body_low'].iloc[i]
        sma75 = df['sma75'].iloc[i]
        
        if pd.isna(body_low) or pd.isna(sma75):
            return False
        
        if body_low <= sma75:
            return False
        
        if i < 1:
            return False
        
        prev_color = df['ha_color'].iloc[i-1]
        curr_color = df['ha_color'].iloc[i]
        
        if prev_color == 'red' and curr_color == 'blue':
            return True
        
        return False
    
    def check_short_entry(self, df, i):
        """
        ショートエントリー条件チェック（足iで判定）
        
        Returns:
            bool: エントリー可否
        """
        if i < 5:
            return False
        
        if self.position is not None:
            return False
        
        trend = self.check_trend(df, i)
        if trend != 'down':
            return False
        
        body_high = df['body_high'].iloc[i]
        sma75 = df['sma75'].iloc[i]
        
        if pd.isna(body_high) or pd.isna(sma75):
            return False
        
        if body_high >= sma75:
            return False
        
        if i < 1:
            return False
        
        prev_color = df['ha_color'].iloc[i-1]
        curr_color = df['ha_color'].iloc[i]
        
        if prev_color == 'blue' and curr_color == 'red':
            return True
        
        return False
    
    def check_long_exit(self, df, i):
        """
        ロング決済条件チェック（足iで判定）
        
        Returns:
            bool: 決済可否
        """
        if self.position != 'long':
            return False
        
        if i < 1:
            return False
        
        prev_color = df['ha_color'].iloc[i-1]
        curr_color = df['ha_color'].iloc[i]
        
        if prev_color == 'blue' and curr_color == 'red':
            return True
        
        return False
    
    def check_short_exit(self, df, i):
        """
        ショート決済条件チェック（足iで判定）
        
        Returns:
            bool: 決済可否
        """
        if self.position != 'short':
            return False
        
        if i < 1:
            return False
        
        prev_color = df['ha_color'].iloc[i-1]
        curr_color = df['ha_color'].iloc[i]
        
        if prev_color == 'red' and curr_color == 'blue':
            return True
        
        return False
    
    def enter_position(self, df, i, direction):
        """
        ポジションエントリー（次の足i+1の始値で約定）
        
        Args:
            df: データフレーム
            i: 判定した足のインデックス
            direction: 'long' or 'short'
        """
        if i + 1 >= len(df):
            return
        
        self.position = direction
        self.entry_price = df['open'].iloc[i+1]
        self.entry_time = df['time'].iloc[i+1]
    
    def exit_position(self, df, i):
        """
        ポジション決済（次の足i+1の始値で約定）
        
        Args:
            df: データフレーム
            i: 判定した足のインデックス
        """
        if i + 1 >= len(df):
            return
        
        exit_price = df['open'].iloc[i+1]
        exit_time = df['time'].iloc[i+1]
        
        if self.position == 'long':
            pips = (exit_price - self.entry_price) * 100
        else:
            pips = (self.entry_price - exit_price) * 100
        
        trade = {
            'entry_time': self.entry_time,
            'exit_time': exit_time,
            'direction': self.position,
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'pips': pips
        }
        self.trades.append(trade)
        
        self.position = None
        self.entry_price = None
        self.entry_time = None
    
    def run(self):
        """バックテスト実行"""
        df = self.load_data()
        df = self.calculate_sma(df)
        df = self.calculate_heikin_ashi(df)
        df = self.calculate_ha_color(df)
        df = self.calculate_ha_body(df)
        
        for i in range(len(df)):
            if self.check_long_exit(df, i):
                self.exit_position(df, i)
            elif self.check_short_exit(df, i):
                self.exit_position(df, i)
            
            if self.check_long_entry(df, i):
                self.enter_position(df, i, 'long')
            elif self.check_short_entry(df, i):
                self.enter_position(df, i, 'short')
        
        if self.position is not None and len(df) > 0:
            last_idx = len(df) - 1
            exit_price = df['close'].iloc[last_idx]
            exit_time = df['time'].iloc[last_idx]
            
            if self.position == 'long':
                pips = (exit_price - self.entry_price) * 100
            else:
                pips = (self.entry_price - exit_price) * 100
            
            trade = {
                'entry_time': self.entry_time,
                'exit_time': exit_time,
                'direction': self.position,
                'entry_price': self.entry_price,
                'exit_price': exit_price,
                'pips': pips
            }
            self.trades.append(trade)
    
    def calculate_metrics(self):
        """パフォーマンス指標計算"""
        if len(self.trades) == 0:
            return {
                'total_pips': 0,
                'trade_count': 0,
                'win_rate': 0,
                'max_drawdown': 0,
                'profit_factor': 0
            }
        
        trades_df = pd.DataFrame(self.trades)
        
        total_pips = trades_df['pips'].sum()
        trade_count = len(trades_df)
        wins = (trades_df['pips'] > 0).sum()
        win_rate = (wins / trade_count) * 100 if trade_count > 0 else 0
        
        cumulative = trades_df['pips'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = running_max - cumulative
        max_drawdown = drawdown.max()
        
        gross_profit = trades_df[trades_df['pips'] > 0]['pips'].sum()
        gross_loss = abs(trades_df[trades_df['pips'] < 0]['pips'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            'total_pips': total_pips,
            'trade_count': trade_count,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'profit_factor': profit_factor
        }
    
    def print_results(self):
        """結果表示"""
        metrics = self.calculate_metrics()
        
        print("=" * 60)
        print("バックテスト結果")
        print("=" * 60)
        print(f"総損益: {metrics['total_pips']:.2f} pips")
        print(f"取引回数: {metrics['trade_count']}回")
        print(f"勝率: {metrics['win_rate']:.2f}%")
        print(f"最大ドローダウン: {metrics['max_drawdown']:.2f} pips")
        print(f"プロフィットファクター: {metrics['profit_factor']:.2f}")
        print("=" * 60)
        
        if len(self.trades) > 0:
            print("\n取引一覧:")
            print("-" * 120)
            print(f"{'エントリー日時':<20} {'決済日時':<20} {'方向':<6} {'エントリー価格':<12} {'決済価格':<12} {'獲得pips':<10}")
            print("-" * 120)
            
            for trade in self.trades:
                print(f"{str(trade['entry_time']):<20} "
                      f"{str(trade['exit_time']):<20} "
                      f"{trade['direction']:<6} "
                      f"{trade['entry_price']:<12.3f} "
                      f"{trade['exit_price']:<12.3f} "
                      f"{trade['pips']:<10.2f}")
            print("-" * 120)


def select_csv_file():
    """dataフォルダからCSVファイルを選択"""
    data_dir = "data"
    
    if not os.path.exists(data_dir):
        print(f"エラー: {data_dir} フォルダが見つかりません")
        return None
    
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    
    if len(csv_files) == 0:
        print(f"エラー: {data_dir} フォルダにCSVファイルがありません")
        return None
    
    print("\n利用可能なCSVファイル:")
    for i, file_path in enumerate(csv_files, 1):
        filename = os.path.basename(file_path)
        print(f"{i}. {filename}")
    
    while True:
        try:
            choice = input("\nどのファイルを使いますか？ (番号を入力): ")
            index = int(choice) - 1
            
            if 0 <= index < len(csv_files):
                return csv_files[index]
            else:
                print("無効な番号です。もう一度入力してください。")
        except ValueError:
            print("数字を入力してください。")
        except KeyboardInterrupt:
            print("\n中断しました")
            return None


if __name__ == "__main__":
    csv_path = select_csv_file()
    
    if csv_path:
        print(f"\n選択されたファイル: {os.path.basename(csv_path)}\n")
        bt = BacktestEngine(csv_path)
        bt.run()
        bt.print_results()