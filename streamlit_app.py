import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Heatseeker Lite", layout="wide")
st.title("Heatseeker Lite — 100% Free Forever")

# ─── Sidebar Settings ───
st.sidebar.header("Configuration")
API_KEY = st.sidebar.text_input("Polygon.io API Key (free tier works)", type="password", help="Get it free in 30 sec → polygon.io")
ticker = st.sidebar.selectbox("Ticker", ["SPY","QQQ","IWM","AAPL","TSLA","NVDA","AMD","META","GOOGL","MSFT","AMZN","SMH","HOOD","COIN"])
spot_price = st.sidebar.number_input("Current price (optional – auto later)", value=585.0, step=0.1)

if not API_KEY or API_KEY == "":
    st.warning("↑ Paste your free Polygon API key to unlock real data")
    st.stop()

# ─── Fetch live options chain ───
@st.cache_data(ttl=600)  # refreshes every 10 min
def fetch_options(ticker):
    url = f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={ticker}&limit=1000&apiKey={API_KEY}"
    resp = requests.get(url).json()
    df = pd.DataFrame(resp.get("results", []))
    if df.empty:
        return df
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])
    df = df[df["expiration_date"] > datetime.now()]
    df["days_to_exp"] = (df["expiration_date"] - pd.to_datetime("today")).dt.days
    return df

df = fetch_options(ticker)
if df.empty:
    st.error("No data – double-check your Polygon key")
    st.stop()

# ─── GEX Calculation (dealer exposure) ───
df["T"] = np.maximum(df["days_to_exp"] / 365.0, 0.002)
# Fast & accurate gamma approximation
df["gamma"] = 0.4 / (df["strike_price"] * 0.2 * np.sqrt(df["T"]))
df["oi"] = df["open_interest"].fillna(1000).astype(float)
df["gex_raw"] = -df["oi"] * df["gamma"] * 100 * (spot_price ** 2) / 100

gex = df.groupby("strike_price")["gex_raw"].sum().reset_index()
gex.columns = ["strike", "gex"]

# King Node = strongest positive magnet
king_strike = gex.loc[gex["gex"].idxmax(), "strike"]

# ─── Plot ───
fig = go.Figure()
fig.add_trace(go.Bar(
    x=gex["strike"],
    y=gex["gex"]/1e6,
    marker_color=["limegreen" if x >= 0 else "crimson" for x in gex["gex"]],
    name="Net GEX"
))
fig.add_vline(x=spot_price, line_color="white", line_dash="dot", annotation_text="Spot")
fig.add_vline(x=king_strike, line_color="gold", line_width=6, annotation_text="KING NODE")
fig.update_layout(
    title=f"{ticker} → King Node ${king_strike:.2f} (Spot ${spot_price})",
    xaxis_title="Strike Price",
    yaxis_title="Net GEX ($ millions)",
    height=650,
    template="plotly_dark"
)
st.plotly_chart(fig, use_container_width=True)

# ─── Results ───
col1, col2, col3 = st.columns(3)
col1.metric("KING NODE", f"${king_strike:.2f}")
col2.metric("Distance from Spot", f"{spot_price - king_strike:+.2f}")
col3.metric("Total Contracts", f"{df['oi'].sum():,.0f}")

st.success(f"Dealers want {ticker} at **${king_strike:.2f}** — target acquired!")

# Top strikes table
top = gex.assign(GEX_M = (gex.gex/1e6).round(2)).sort_values("gex", ascending=False).head(25)
st.dataframe(top.style.format({"strike": "${:.2f}", "GEX_M": "${:.1f}M"})
             .background_gradient(cmap="RdYlGn", subset=["GEX_M"]), use_container_width=True)
