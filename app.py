import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from backtest import fetch_data, clean_tradingview_csv, run_backtest
from optimizer import run_optimizer

st.set_page_config(page_title="Quant Trader Web V2", page_icon="📈", layout="wide")
st.title("📈 Quant Trader Web V2")
st.caption("Backtest crypto spot trading. Versi belajar. Bukan financial advice.")

with st.sidebar:
    st.header("Data")
    data_source = st.radio("Sumber data", ["Exchange API", "TradingView CSV Upload"])
    symbol = st.selectbox("Coin", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"])
    timeframe = st.selectbox("Timeframe", ["1d", "4h", "1h"])
    limit = st.slider("Jumlah candle/data", 300, 1500, 1000)
    csv_file = None
    if data_source == "TradingView CSV Upload":
        csv_file = st.file_uploader("Upload CSV TradingView", type=["csv"])
        st.caption("CSV wajib ada: time/date, open, high, low, close.")
    st.divider()
    st.header("Strategi")
    initial_capital = st.number_input("Modal awal USD", value=1000.0, step=100.0)
    ma_fast = st.slider("MA Fast", 5, 50, 20)
    ma_slow = st.slider("MA Slow", 20, 250, 50)
    ma_trend = st.slider("MA Trend Filter", 50, 300, 200)
    use_rsi = st.checkbox("Guna RSI Filter", value=True)
    rsi_min = st.slider("RSI Minimum", 20, 60, 45)
    rsi_max = st.slider("RSI Maximum", 50, 90, 70)
    st.divider()
    st.header("Risk")
    use_atr_stop = st.checkbox("Guna ATR Stop Loss", value=False)
    atr_multiplier = st.slider("ATR Multiplier", 1.0, 5.0, 2.0)
    stop_loss_pct = st.slider("Stop Loss %", 1.0, 20.0, 5.0) / 100
    take_profit_pct = st.slider("Take Profit %", 1.0, 50.0, 12.0) / 100
    risk_per_trade = st.slider("Risk per trade %", 0.5, 10.0, 2.0) / 100
    fee_pct = st.slider("Trading fee %", 0.01, 0.50, 0.10) / 100
    st.divider()
    run_btn = st.button("Run Backtest", use_container_width=True)
    optimize_btn = st.button("Run Optimization", use_container_width=True)

@st.cache_data(ttl=3600)
def cached_fetch(symbol, timeframe, limit):
    return fetch_data(symbol, timeframe, limit)

def load_data():
    if data_source == "TradingView CSV Upload":
        if csv_file is None:
            st.warning("Upload fail CSV TradingView dahulu.")
            st.stop()
        return clean_tradingview_csv(csv_file), "TradingView CSV", "CSV Upload"
    df_raw, exchange_used, symbol_used = cached_fetch(symbol, timeframe, limit)
    return df_raw, exchange_used, symbol_used

def show_metrics(metrics):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modal Akhir", f"${metrics['Final Capital']:,.2f}")
    c2.metric("Total Return", f"{metrics['Total Return %']:.2f}%")
    c3.metric("Buy & Hold", f"{metrics['Buy & Hold %']:.2f}%")
    c4.metric("Max Drawdown", f"{metrics['Max Drawdown %']:.2f}%")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Jumlah Trade", metrics["Number of Trades"])
    c6.metric("Win Rate", f"{metrics['Win Rate %']:.2f}%")
    c7.metric("Profit Factor", f"{metrics['Profit Factor']:.2f}")
    c8.metric("Sharpe Ratio", f"{metrics['Sharpe Ratio']:.2f}")

def show_price_chart(result):
    df = result["df"]
    signals = result["signals"]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Price"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["ma_fast"], mode="lines", name="MA Fast"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["ma_slow"], mode="lines", name="MA Slow"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["ma_trend"], mode="lines", name="MA Trend"))
    if len(signals):
        buys = signals[signals["type"] == "BUY"]
        sells = signals[signals["type"] == "SELL"]
        fig.add_trace(go.Scatter(x=buys["date"], y=buys["price"], mode="markers", marker=dict(symbol="triangle-up", size=13), name="BUY"))
        fig.add_trace(go.Scatter(x=sells["date"], y=sells["price"], mode="markers", marker=dict(symbol="triangle-down", size=13), name="SELL"))
    fig.update_layout(title="Candlestick + MA + Buy/Sell Signal", xaxis_title="Date", yaxis_title="Price", xaxis_rangeslider_visible=False, height=650)
    st.plotly_chart(fig, use_container_width=True)

try:
    if run_btn or optimize_btn:
        with st.spinner("Ambil dan proses data..."):
            df_raw, source_text, symbol_text = load_data()
        st.success(f"Data digunakan: {source_text} / {symbol_text}")
        if run_btn:
            with st.spinner("Jalankan backtest..."):
                result = run_backtest(df_raw=df_raw, initial_capital=initial_capital, ma_fast=ma_fast, ma_slow=ma_slow, ma_trend=ma_trend, use_rsi=use_rsi, rsi_min=rsi_min, rsi_max=rsi_max, stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct, use_atr_stop=use_atr_stop, atr_multiplier=atr_multiplier, risk_per_trade=risk_per_trade, fee_pct=fee_pct)
            show_metrics(result["metrics"])
            st.subheader("Carta Harga + Signal")
            show_price_chart(result)
            st.subheader("Equity Curve")
            equity_df = result["equity"]
            if len(equity_df):
                fig = px.line(equity_df, x="date", y="equity", title="Equity Curve")
                st.plotly_chart(fig, use_container_width=True)
            st.subheader("Trade Journal")
            trades = result["trades"]
            if len(trades):
                trades_show = trades.copy()
                trades_show["entry_date"] = trades_show["entry_date"].dt.strftime("%Y-%m-%d")
                trades_show["exit_date"] = trades_show["exit_date"].dt.strftime("%Y-%m-%d")
                st.dataframe(trades_show, use_container_width=True)
                st.download_button("Download Trade Journal CSV", data=trades_show.to_csv(index=False).encode("utf-8"), file_name="trade_journal.csv", mime="text/csv")
            else:
                st.warning("Tiada trade dijana.")
        if optimize_btn:
            with st.spinner("Optimizer sedang uji banyak setting..."):
                opt_df = run_optimizer(df_raw=df_raw, initial_capital=initial_capital, fee_pct=fee_pct, risk_per_trade=risk_per_trade)
            st.subheader("Keputusan Optimization")
            if len(opt_df):
                st.dataframe(opt_df, use_container_width=True)
                st.download_button("Download Optimization CSV", data=opt_df.to_csv(index=False).encode("utf-8"), file_name="optimization_result.csv", mime="text/csv")
                st.info("Jangan pilih result paling tinggi secara buta. Pastikan drawdown rendah dan jumlah trade mencukupi.")
            else:
                st.warning("Tiada keputusan optimizer.")
    else:
        st.info("Pilih tetapan di sidebar, kemudian tekan Run Backtest atau Run Optimization.")
        st.markdown("""
### Cara guna ringkas
1. Pilih sumber data: Exchange API atau TradingView CSV.
2. Tetapkan MA, RSI, stop loss dan take profit.
3. Tekan **Run Backtest**.
4. Lihat signal BUY/SELL atas carta.
5. Semak Trade Journal untuk faham setiap trade.
""")
except Exception as e:
    st.error(str(e))