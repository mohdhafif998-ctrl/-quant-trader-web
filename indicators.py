import pandas as pd
import numpy as np


def add_indicators(df: pd.DataFrame, ma_fast: int, ma_slow: int, ma_trend: int, rsi_period: int = 14, atr_period: int = 14) -> pd.DataFrame:
    df = df.copy()

    df["ma_fast"] = df["close"].rolling(ma_fast).mean()
    df["ma_slow"] = df["close"].rolling(ma_slow).mean()
    df["ma_trend"] = df["close"].rolling(ma_trend).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(atr_period).mean()

    return df.dropna().reset_index(drop=True)
