import ccxt
import pandas as pd
import numpy as np
from indicators import add_indicators


def fetch_data(symbol: str, timeframe: str, limit: int):
    exchanges = ["kraken", "kucoin", "coinbase", "bitfinex"]
    fallback_symbols = [symbol, symbol.replace("/USDT", "/USD")]

    last_error = None

    for ex_id in exchanges:
        try:
            exchange = getattr(ccxt, ex_id)()
            for sym in fallback_symbols:
                try:
                    data = exchange.fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
                    if data and len(data) > 100:
                        df = pd.DataFrame(
                            data,
                            columns=["timestamp", "open", "high", "low", "close", "volume"]
                        )
                        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
                        return df[["date", "open", "high", "low", "close", "volume"]], ex_id, sym
                except Exception as e:
                    last_error = e
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Gagal ambil data. Error terakhir: {last_error}")


def run_backtest(
    df_raw,
    initial_capital=1000.0,
    ma_fast=20,
    ma_slow=50,
    ma_trend=200,
    use_rsi=True,
    rsi_min=45,
    rsi_max=70,
    stop_loss_pct=0.05,
    take_profit_pct=0.12,
    use_atr_stop=False,
    atr_multiplier=2.0,
    risk_per_trade=0.02,
    fee_pct=0.001,
):
    df = add_indicators(df_raw, ma_fast, ma_slow, ma_trend)

    capital = float(initial_capital)
    position = None
    trades = []
    equity_curve = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        price = row["close"]

        golden_cross = prev["ma_fast"] <= prev["ma_slow"] and row["ma_fast"] > row["ma_slow"]
        death_cross = prev["ma_fast"] >= prev["ma_slow"] and row["ma_fast"] < row["ma_slow"]

        trend_ok = row["close"] > row["ma_trend"]
        rsi_ok = (rsi_min <= row["rsi"] <= rsi_max) if use_rsi else True

        buy_signal = golden_cross and trend_ok and rsi_ok

        if position is not None:
            exit_price = None
            reason = None

            if row["low"] <= position["sl"]:
                exit_price = position["sl"]
                reason = "Stop Loss"
            elif row["high"] >= position["tp"]:
                exit_price = position["tp"]
                reason = "Take Profit"
            elif death_cross:
                exit_price = price
                reason = "MA Cross"

            if exit_price is not None:
                gross = position["qty"] * exit_price
                fee = gross * fee_pct
                capital += gross - fee
                pnl = (gross - fee) - position["cost"]

                trades.append({
                    "entry_date": position["entry_date"],
                    "exit_date": row["date"],
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "qty": position["qty"],
                    "reason": reason,
                    "pnl": pnl,
                    "return_pct": pnl / position["cost"] * 100,
                })

                position = None

        if position is None and buy_signal:
            if use_atr_stop:
                stop_distance = row["atr"] * atr_multiplier
                sl_price = price - stop_distance
                sl_pct = stop_distance / price
            else:
                sl_price = price * (1 - stop_loss_pct)
                sl_pct = stop_loss_pct

            if sl_pct <= 0:
                continue

            risk_amount = capital * risk_per_trade
            qty = risk_amount / (price * sl_pct)
            pos_value = qty * price

            max_value = capital / (1 + fee_pct)
            if pos_value > max_value:
                pos_value = max_value
                qty = pos_value / price

            fee = pos_value * fee_pct
            cost = pos_value + fee

            if cost <= capital and qty > 0:
                capital -= cost

                position = {
                    "entry_date": row["date"],
                    "entry_price": price,
                    "qty": qty,
                    "cost": cost,
                    "sl": sl_price,
                    "tp": price * (1 + take_profit_pct),
                }

        position_value = position["qty"] * price if position else 0
        equity_curve.append({
            "date": row["date"],
            "equity": capital + position_value
        })

    if position is not None:
        last = df.iloc[-1]
        gross = position["qty"] * last["close"]
        fee = gross * fee_pct
        capital += gross - fee
        pnl = (gross - fee) - position["cost"]

        trades.append({
            "entry_date": position["entry_date"],
            "exit_date": last["date"],
            "entry_price": position["entry_price"],
            "exit_price": last["close"],
            "qty": position["qty"],
            "reason": "End of Data",
            "pnl": pnl,
            "return_pct": pnl / position["cost"] * 100,
        })

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)

    metrics = calculate_metrics(initial_capital, capital, trades_df, equity_df, df)

    return {
        "df": df,
        "final_capital": capital,
        "trades": trades_df,
        "equity": equity_df,
        "metrics": metrics,
    }


def calculate_metrics(initial_capital, final_capital, trades_df, equity_df, df):
    total_return = (final_capital - initial_capital) / initial_capital * 100

    num_trades = len(trades_df)
    wins = int((trades_df["pnl"] > 0).sum()) if num_trades else 0
    losses = num_trades - wins
    win_rate = wins / num_trades * 100 if num_trades else 0

    if len(equity_df):
        equity_df = equity_df.copy()
        equity_df["peak"] = equity_df["equity"].cummax()
        equity_df["drawdown"] = (equity_df["equity"] - equity_df["peak"]) / equity_df["peak"] * 100
        max_drawdown = equity_df["drawdown"].min()
        daily_returns = equity_df["equity"].pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(365)) if daily_returns.std() != 0 else 0
    else:
        max_drawdown = 0
        sharpe = 0

    if num_trades:
        gross_profit = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        avg_win = trades_df[trades_df["pnl"] > 0]["pnl"].mean() if wins else 0
        avg_loss = trades_df[trades_df["pnl"] < 0]["pnl"].mean() if losses else 0
    else:
        profit_factor = 0
        avg_win = 0
        avg_loss = 0

    buy_hold_return = (df["close"].iloc[-1] - df["close"].iloc[0]) / df["close"].iloc[0] * 100

    return {
        "Final Capital": final_capital,
        "Total Return %": total_return,
        "Buy & Hold %": buy_hold_return,
        "Number of Trades": num_trades,
        "Wins": wins,
        "Losses": losses,
        "Win Rate %": win_rate,
        "Max Drawdown %": max_drawdown,
        "Profit Factor": profit_factor,
        "Sharpe Ratio": sharpe,
        "Average Win": avg_win,
        "Average Loss": avg_loss,
    }
