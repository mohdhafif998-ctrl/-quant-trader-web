import pandas as pd
from backtest import run_backtest


def run_optimizer(df_raw, initial_capital, fee_pct, risk_per_trade):
    results = []
    for ma_fast in [10, 15, 20, 30]:
        for ma_slow in [50, 100, 150, 200]:
            if ma_fast >= ma_slow:
                continue
            for sl in [0.03, 0.05, 0.08]:
                for tp in [0.08, 0.12, 0.20]:
                    try:
                        result = run_backtest(df_raw=df_raw, initial_capital=initial_capital, ma_fast=ma_fast, ma_slow=ma_slow, ma_trend=200, use_rsi=True, rsi_min=45, rsi_max=70, stop_loss_pct=sl, take_profit_pct=tp, risk_per_trade=risk_per_trade, fee_pct=fee_pct)
                        m = result["metrics"]
                        results.append({"ma_fast": ma_fast, "ma_slow": ma_slow, "stop_loss_%": sl * 100, "take_profit_%": tp * 100, "total_return_%": m["Total Return %"], "buy_hold_%": m["Buy & Hold %"], "max_drawdown_%": m["Max Drawdown %"], "win_rate_%": m["Win Rate %"], "profit_factor": m["Profit Factor"], "sharpe": m["Sharpe Ratio"], "trades": m["Number of Trades"]})
                    except Exception:
                        continue
    df = pd.DataFrame(results)
    if len(df):
        df = df.sort_values(by=["total_return_%", "profit_factor", "sharpe"], ascending=False).reset_index(drop=True)
    return df
