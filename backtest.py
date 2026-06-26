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
                        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
                        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
                        return df[["date", "open", "high", "low", "close", "volume"]], ex_id, sym
                except Exception as e:
                    last_error = e
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Gagal ambil data. Error terakhir: {last_error}")


def clean_tradingview_csv(uploaded_file):
    df = pd.read_csv(uploaded_file)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={"time": "date", "datetime": "date", "timestamp": "date", "vol": "volume"})
    required = ["date", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV tidak lengkap. Wajib ada date/time, open, high, low, close. Hilang: {missing}")
    if "volume" not in df.columns:
        df["volume"] = 0
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["date", "open", "high", "low", "close"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "open", "high", "low", "close", "volume"]]


def run_backtest(df_raw, initial_capital=1000.0, ma_fast=20, ma_slow=50, ma_trend=200, use_rsi=True, rsi_min=45, rsi_max=70, stop_loss_pct=0.05, take_profit_pct=0.12, use_atr_stop=False, atr_multiplier=2.0, risk_per_trade=0.02, fee_pct=0.001):
    df = add_indicators(df_raw, ma_fast, ma_slow, ma_trend)
    capital = float(initial_capital)
    position = None
    trades, equity_curve, signals = [], [], []

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        price = row["close"]
        golden_cross = prev["ma_fast"] <= prev["ma_slow"] and row["ma_fast"] > row["ma_slow"]
        death_cross = prev["ma_fast"] >= prev["ma_slow"] and row["ma_fast"] < row["ma_slow"]
        trend_ok = row["close"] > row["ma_trend"]
        rsi_ok = (rsi_min <= row["rsi"] <= rsi_max) if use_rsi else True
        buy_signal = golden_cross and trend_ok and rsi_ok

        if position is not None:
            exit_price, reason = None, None
            if row["low"] <= position["sl"]:
                exit_price, reason = position["sl"], "Stop Loss"
            elif row["high"] >= position["tp"]:
                exit_price, reason = position["tp"], "Take Profit"
            elif death_cross:
                exit_price, reason = price, "MA Cross"
            if exit_price is not None:
                gross = position["qty"] * exit_price
                fee = gross * fee_pct
                capital += gross - fee
                pnl = (gross - fee) - position["cost"]
                trades.append({"entry_date": position["entry_date"], "exit_date": row["date"], "entry_price": position["entry_price"], "exit_price": exit_price, "qty": position["qty"], "reason": reason, "pnl": pnl, "return_pct": pnl / position["cost"] * 100})
                signals.append({"date": row["date"], "price": exit_price, "type": "SELL", "reason": reason})
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
            pos_value = min(qty * price, capital / (1 + fee_pct))
            qty = pos_value / price
            fee = pos_value * fee_pct
            cost = pos_value + fee
            if cost <= capital and qty > 0:
                capital -= cost
                position = {"entry_date": row["date"], "entry_price": price, "qty": qty, "cost": cost, "sl": sl_price, "tp": price * (1 + take_profit_pct)}
                signals.append({"date": row["date"], "price": price, "type": "BUY", "reason": "MA Cross + Filter"})

        position_value = position["qty"] * price if position else 0
        equity_curve.append({"date": row["date"], "equity": capital + position_value})

    if position is not None:
        last = df.iloc[-1]
        gross = position["qty"] * last["close"]
        fee = gross * fee_pct
        capital += gross - fee
        pnl = (gross - fee) - position["cost"]
        trades.append({"entry_date": position["entry_date"], "exit_date": last["date"], "entry_price": position["entry_price"], "exit_price": last["close"], "qty": position["qty"], "reason": "End of Data", "pnl": pnl, "return_pct": pnl / position["cost"] * 100})
        signals.append({"date": last["date"], "price": last["close"], "type": "SELL", "reason": "End of Data"})

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)
    signals_df = pd.DataFrame(signals)
    metrics = calculate_metrics(initial_capital, capital, trades_df, equity_df, df)
    return {"df": df, "final_capital": capital, "trades": trades_df, "equity": equity_df, "signals": signals_df, "metrics": metrics}


def calculate_metrics(initial_capital, final_capital, trades_df, equity_df, df):
    total_return = (final_capital - initial_capital) / initial_capital * 100
    num_trades = len(trades_df)
    wins = int((trades_df["pnl"] > 0).sum()) if num_trades else 0
    losses = num_trades - wins
    win_rate = wins / num_trades * 100 if num_trades else 0
    if len(equity_df):
        eq = equity_df.copy()
        eq["peak"] = eq["equity"].cummax()
        eq["drawdown"] = (eq["equity"] - eq["peak"]) / eq["peak"] * 100
        max_drawdown = eq["drawdown"].min()
        returns = eq["equity"].pct_change().dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(365)) if returns.std() != 0 else 0
    else:
        max_drawdown, sharpe = 0, 0
    if num_trades:
        gp = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
        gl = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
        profit_factor = gp / gl if gl > 0 else np.inf
        avg_win = trades_df[trades_df["pnl"] > 0]["pnl"].mean() if wins else 0
        avg_loss = trades_df[trades_df["pnl"] < 0]["pnl"].mean() if losses else 0
    else:
        profit_factor, avg_win, avg_loss = 0, 0, 0
    buy_hold_return = (df["close"].iloc[-1] - df["close"].iloc[0]) / df["close"].iloc[0] * 100
    return {"Final Capital": final_capital, "Total Return %": total_return, "Buy & Hold %": buy_hold_return, "Number of Trades": num_trades, "Wins": wins, "Losses": losses, "Win Rate %": win_rate, "Max Drawdown %": max_drawdown, "Profit Factor": profit_factor, "Sharpe Ratio": sharpe, "Average Win": avg_win, "Average Loss": avg_loss}