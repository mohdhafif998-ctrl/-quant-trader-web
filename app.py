as st
import plotly.express as px

from backtest import fetch_data, run_backtest
from optimizer import run_optimizer

st.set_page_config(
    page_title="Quant Trader Web",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Quant Trader Web")
st.caption("Backtest crypto spot trading. Bukan financial advice. Jangan guna untuk auto trade dulu.")

with st.sidebar:
    st.header("Tetapan")

    symbol = st.selectbox(
        "Coin",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    )

    timeframe = st.selectbox("Timeframe", ["1d", "4h", "1h"])
    limit = st.slider("Jumlah candle/data", 300, 1500, 1000)

    initial_capital = st.number_input("Modal awal USD", value=1000.0, step=100.0)

    st.divider()

    ma_fast = st.slider("MA Fast", 5, 50, 20)
    ma_slow = st.slider("MA Slow", 20, 250, 50)
    ma_trend = st.slider("MA Trend Filter", 50, 300, 200)

    use_rsi = st.checkbox("Guna RSI Filter", value=True)
    rsi_min = st.slider("RSI Minimum", 20, 60, 45)
    rsi_max = st.slider("RSI Maximum", 50, 90, 70)

    st.divider()

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


def show_metrics(metrics):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Modal Akhir", f"${metrics['Final Capital']:,.2f}")
    col2.metric("Total Return", f"{metrics['Total Return %']:.2f}%")
    col3.metric("Buy & Hold", f"{metrics['Buy & Hold %']:.2f}%")
    col4.metric("Max Drawdown", f"{metrics['Max Drawdown %']:.2f}%")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Jumlah Trade", metrics["Number of Trades"])
    col6.metric("Win Rate", f"{metrics['Win Rate %']:.2f}%")
    col7.metric("Profit Factor", f"{metrics['Profit Factor']:.2f}")
    col8.metric("Sharpe Ratio", f"{metrics['Sharpe Ratio']:.2f}")


try:
    if run_btn or optimize_btn:
        with st.spinner("Ambil data dari exchange..."):
            df_raw, exchange_used, symbol_used = cached_fetch(symbol, timeframe, limit)

        st.success(f"Data digunakan: {exchange_used} / {symbol_used}")

        if run_btn:
            with st.spinner("Jalankan backtest..."):
                result = run_backtest(
                    df_raw=df_raw,
                    initial_capital=initial_capital,
                    ma_fast=ma_fast,
                    ma_slow=ma_slow,
                    ma_trend=ma_trend,
                    use_rsi=use_rsi,
                    rsi_min=rsi_min,
                    rsi_max=rsi_max,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    use_atr_stop=use_atr_stop,
                    atr_multiplier=atr_multiplier,
                    risk_per_trade=risk_per_trade,
                    fee_pct=fee_pct,
                )

            show_metrics(result["metrics"])

            st.subheader("Equity Curve")
            equity_df = result["equity"]
            if len(equity_df):
                fig = px.line(equity_df, x="date", y="equity", title="Equity Curve")
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Harga + Moving Average")
            chart_df = result["df"][["date", "close", "ma_fast", "ma_slow", "ma_trend"]]
            fig2 = px.line(chart_df, x="date", y=["close", "ma_fast", "ma_slow", "ma_trend"])
            st.plotly_chart(fig2, use_container_width=True)

            st.subheader("Senarai Trade")
            trades = result["trades"]
            if len(trades):
                trades_show = trades.copy()
                trades_show["entry_date"] = trades_show["entry_date"].dt.strftime("%Y-%m-%d")
                trades_show["exit_date"] = trades_show["exit_date"].dt.strftime("%Y-%m-%d")
                st.dataframe(trades_show, use_container_width=True)
            else:
                st.warning("Tiada trade dijana.")

        if optimize_btn:
            with st.spinner("Optimizer sedang uji banyak setting..."):
                opt_df = run_optimizer(
                    df_raw=df_raw,
                    initial_capital=initial_capital,
                    fee_pct=fee_pct,
                    risk_per_trade=risk_per_trade,
                )

            st.subheader("Keputusan Optimization")
            if len(opt_df):
                st.dataframe(opt_df, use_container_width=True)
                st.info("Jangan pilih result paling tinggi secara buta. Pastikan drawdown rendah dan trade mencukupi.")
            else:
                st.warning("Tiada keputusan optimizer.")

    else:
        st.info("Pilih tetapan di sidebar, kemudian tekan Run Backtest atau Run Optimization.")

except Exception as e:
    st.error(str(e))
