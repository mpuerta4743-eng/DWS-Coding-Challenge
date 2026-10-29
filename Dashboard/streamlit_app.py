"""DWS daily trade analytics. Run with streamlit run streamlit_app.py."""
from html import escape
from datetime import timedelta
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from trade_analytics import load_trades, resolve_source, summarize

ROOT = Path(__file__).resolve().parent
NAVY, TEAL, BLUE = "#142D43", "#008C95", "#7296BA"
st.set_page_config(page_title="DWS | Trade Analytics", page_icon="◈", layout="wide")
st.markdown("""<style>
.stApp {background:#F5F7FA;color:#142D43}
.block-container {padding-top:4rem;max-width:1600px}
h1,h2,h3 {letter-spacing:-.035em;color:#142D43}
h1 {font-size:2.7rem!important;font-weight:650!important}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid #E2E8EF}
[data-testid="stMetric"] {background:white;border:1px solid #E2E8EF;border-radius:10px;padding:22px 24px;border-top:3px solid #008C95}
[data-testid="stMetricLabel"] {color:#647689;font-size:.85rem}
[data-testid="stMetricValue"] {font-size:2rem;letter-spacing:-.04em}
[data-testid="stTabs"] button {font-weight:600}
.brand {font-size:32px;font-weight:800;letter-spacing:-2px;color:#142D43}
.eyebrow {font-size:11px;letter-spacing:2px;color:#008C95;font-weight:700;margin-bottom:8px}
.subtitle {color:#647689;margin-top:-8px;margin-bottom:24px}
.insight {background:#EAF3F4;border-left:3px solid #008C95;padding:18px 22px;border-radius:0 8px 8px 0;margin:16px 0 24px}
</style>""", unsafe_allow_html=True)


def money(value):
    if pd.isna(value):
        return "Unavailable"
    for threshold, suffix in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.2f}"


@st.cache_data(show_spinner=False)
def cached_load(path, modified):
    return load_trades(Path(path))


def chart(fig):
    fig.update_layout(
        template="plotly_white", font=dict(family="Arial", color=NAVY, size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=15, t=20, b=10), height=340,
        legend=dict(orientation="h", y=1.12, title=None),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E5EBF0", zeroline=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


try:
    data_root = Path(os.environ.get("DWS_DATA_ROOT", str(ROOT.parent / "data_pipeline"))).expanduser().resolve()
    source = resolve_source(data_root, os.environ.get("DWS_TRADES_PATH", ""))
    trades = cached_load(str(source), source.stat().st_mtime_ns)
except (OSError, ValueError, ImportError) as exc:
    st.title("Trade Analytics")
    st.error(str(exc))
    st.caption(f"Python: {sys.executable}")
    st.caption(f"App: {Path(__file__).resolve()}")
    st.code('python -m pip install .\ntrade-dashboard')
    st.stop()

with st.sidebar:
    st.markdown('<div class="brand">DWS</div>', unsafe_allow_html=True)
    st.caption("TRADE ANALYTICS")
    st.divider()
    st.markdown("**Daily workspace**")
    days = sorted(trades["TIMESTAMP_TRADE_DATE"].dt.date.dropna().unique(), reverse=True)
    if not days:
        st.error("No valid trading timestamps in this source.")
        st.stop()
    day = st.selectbox("Trading date · UTC", days, format_func=lambda d: d.strftime("%d %B %Y"))
    filters = {}
    for label, column in (("Securities", "STRING_INSTRUMENT"), ("Traders", "STRING_TRADER_ID"), ("Strategies", "STRING_STRATEGY"), ("Accounts", "STRING_ACCOUNT"), ("Side", "STRING_SIDE")):
        filters[column] = st.multiselect(label, sorted(trades[column].unique()), placeholder="All")
    st.divider()
    st.caption("DATA SOURCE")
    st.write("Silver" if "1_silver" in source.parts else "Custom Parquet")
    st.caption(source.name)
    if "TIMESTAMP_FILE_PROCESSED" in trades:
        processed = pd.to_datetime(trades["TIMESTAMP_FILE_PROCESSED"], utc=True, errors="coerce").max()
        if pd.notna(processed):
            st.caption(f"Processed {processed:%d %b %Y · %H:%M} UTC")
    if st.button("Refresh data", width="stretch"):
        cached_load.clear()
        st.rerun()
    st.caption("Coding challenge · DWS-inspired prototype")

filtered = trades.copy()
for column, selected in filters.items():
    if selected:
        filtered = filtered[filtered[column].isin(selected)]
daily = filtered[filtered["TIMESTAMP_TRADE_DATE"].dt.date.eq(day)].copy()

st.markdown('<div class="eyebrow">DWS GROUP / INVESTMENT OPERATIONS</div>', unsafe_allow_html=True)
st.title("Trade Analytics")
st.markdown(f'<div class="subtitle">Daily trading overview &nbsp; / &nbsp; {day:%A, %d %B %Y} &nbsp; / &nbsp; All times UTC</div>', unsafe_allow_html=True)
if daily.empty:
    st.info("No trades match these filters. Adjust your selections in the sidebar.")
    st.stop()

metric = st.radio("Rank activity by", ["Trade count", "Gross traded value (USD)"], horizontal=True)
value = "Trades" if metric == "Trade count" else "Gross_USD"
value_label = "Trades" if value == "Trades" else "Gross traded value (USD)"
columns = st.columns(4)
gross = daily["FLOAT_GROSS_VALUE_USD"].sum(min_count=1)
for col, label, number in zip(columns, ["Total trades", "Gross value · USD", "Active securities", "Active traders"], [f"{len(daily):,}", money(gross), daily["STRING_ISIN"].nunique(), daily.STRING_TRADER_ID.nunique()]):
    col.metric(label, number)

missing = int(daily.FLOAT_GROSS_VALUE_USD.isna().sum())
BOOLEAN_FLAGGED = int(daily.BOOLEAN_FLAGGED.sum())
undated = int(trades.TIMESTAMP_TRADE_DATE.isna().sum())
st.caption(f"{BOOLEAN_FLAGGED:,} flagged trades included · {missing:,} trades without USD valuation · Gross value sums absolute trade values with available valuations.")
if missing or BOOLEAN_FLAGGED:
    st.warning(f"Quality review: {BOOLEAN_FLAGGED} flagged trades remain included. {missing} trades have no usable USD value and are excluded only from value totals. Totals may be partial.")
if undated:
    st.warning(f"{undated} source trades have no valid timestamp and cannot be assigned to a trading day.")

security = summarize(daily, ["STRING_INSTRUMENT", "STRING_ISIN"]).sort_values([value, "STRING_INSTRUMENT"], ascending=[False, True], na_position="last")
trader = summarize(daily, ["STRING_TRADER_ID"]).sort_values([value, "STRING_TRADER_ID"], ascending=[False, True], na_position="last")
daily["TIMESTAMP_INTERVAL"] = daily.TIMESTAMP_TRADE_DATE.dt.floor("30min")
timeline = summarize(daily, ["TIMESTAMP_INTERVAL", "STRING_SIDE"])
peak = summarize(daily, ["TIMESTAMP_INTERVAL"]).sort_values(value, ascending=False, na_position="last").iloc[0]
peak_start = pd.Timestamp(peak["TIMESTAMP_INTERVAL"]).to_pydatetime()
lead = security.iloc[0]
lead_value = f"{int(lead.Trades)} trades" if value == "Trades" else money(lead.Gross_USD)
if value == "Gross_USD" and pd.isna(gross):
    st.info("USD valuations are unavailable for this selection. Switch to trade count to compare activity.")
else:
    st.markdown(f'<div class="insight"><b>Day in focus</b> &nbsp; {escape(str(lead.STRING_INSTRUMENT))} leads activity with {lead_value}. Peak activity falls in the {peak_start:%H:%M}–{peak_start + timedelta(minutes=30):%H:%M} UTC window.</div>', unsafe_allow_html=True)

overview, securities_tab, traders_tab, explorer = st.tabs(["Daily overview", "Securities", "Traders", "Trade explorer"])
with overview:
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Intraday activity")
        st.caption("Thirty-minute windows · buy and sell activity")
        # Reindex windows so inactive periods appear as zero counts, never fabricated USD values.
        windows = pd.date_range(daily.TIMESTAMP_INTERVAL.min(), daily.TIMESTAMP_INTERVAL.max(), freq="30min")
        index = pd.MultiIndex.from_product([windows, sorted(daily.STRING_SIDE.unique())], names=["TIMESTAMP_INTERVAL", "STRING_SIDE"])
        timeline = timeline.set_index(["TIMESTAMP_INTERVAL", "STRING_SIDE"]).reindex(index).reset_index()
        timeline["Trades"] = timeline["Trades"].fillna(0)
        if value == "Gross_USD":
            timeline.loc[timeline["Missing_USD"].isna(), "Gross_USD"] = 0
        chart(px.bar(timeline, x="TIMESTAMP_INTERVAL", y=value, color="STRING_SIDE", color_discrete_map={"BUY": TEAL, "SELL": BLUE, "UNKNOWN": "#9CA9B5"}, labels={"TIMESTAMP_INTERVAL": "Time · UTC", value: value_label}))
    with right:
        st.subheader("Trade direction")
        st.caption("Distribution by number of trades")
        sides = summarize(daily, ["STRING_SIDE"])
        chart(px.pie(sides, names="STRING_SIDE", values="Trades", hole=.72, color="STRING_SIDE", color_discrete_map={"BUY": TEAL, "SELL": BLUE, "UNKNOWN": "#9CA9B5"}))
    left, right = st.columns(2)
    with left:
        st.subheader("Most active securities")
        top = security.head(8).copy()
        top["Security"] = top.STRING_INSTRUMENT + " · " + top["STRING_ISIN"]
        portions = summarize(daily, ["STRING_INSTRUMENT", "STRING_ISIN", "STRING_SIDE"]).merge(
            top[["STRING_INSTRUMENT", "STRING_ISIN", "Security"]],
            on=["STRING_INSTRUMENT", "STRING_ISIN"], how="inner", validate="many_to_one",
        )
        st.caption("BUY and SELL portions · ranked by total activity")
        chart(px.bar(portions, x=value, y="Security", orientation="h", color="STRING_SIDE", barmode="stack",
                     color_discrete_map={"BUY": TEAL, "SELL": BLUE, "UNKNOWN": "#9CA9B5"},
                     category_orders={"Security": top.Security.tolist(), "STRING_SIDE": ["BUY", "SELL", "UNKNOWN"]},
                     labels={value: value_label, "STRING_SIDE": "Side"}))
    with right:
        st.subheader("Most active traders")
        top = trader.head(8)
        portions = summarize(daily[daily.STRING_TRADER_ID.isin(top.STRING_TRADER_ID)], ["STRING_TRADER_ID", "STRING_SIDE"])
        st.caption("BUY and SELL portions · ranked by total activity")
        chart(px.bar(portions, x=value, y="STRING_TRADER_ID", orientation="h", color="STRING_SIDE", barmode="stack",
                     color_discrete_map={"BUY": TEAL, "SELL": BLUE, "UNKNOWN": "#9CA9B5"},
                     category_orders={"STRING_TRADER_ID": top.STRING_TRADER_ID.tolist(), "STRING_SIDE": ["BUY", "SELL", "UNKNOWN"]},
                     labels={"STRING_TRADER_ID": "Trader", value: value_label, "STRING_SIDE": "Side"}))
    prior_days = [d for d in days if d < day]
    if prior_days:
        previous = filtered[filtered.TIMESTAMP_TRADE_DATE.dt.date.eq(prior_days[0])]
        st.caption(f"Previous available trading date: {prior_days[0]:%d %b %Y} · {len(previous):,} trades under the same filters · Change: {len(daily) - len(previous):+,} trades. Full available days compared.")
    else:
        st.caption("Only one trading day is available. Intraday trends are shown; previous-day comparisons require additional history.")

for tab, title, summary, key in ((securities_tab, "Security activity", security, "STRING_INSTRUMENT"), (traders_tab, "Trader activity", trader, "STRING_TRADER_ID")):
    with tab:
        st.subheader(title)
        st.caption("Rankings respect all sidebar filters. Flagged trades remain included.")
        st.dataframe(summary.rename(columns={"Gross_USD": "Gross USD", "Missing_USD": "Missing USD", "STRING_INSTRUMENT": "Security", "STRING_ISIN": "ISIN", "STRING_TRADER_ID": "Trader"}), hide_index=True, width="stretch", column_config={"Gross USD": st.column_config.NumberColumn(format="$%.2f")})
        selected = st.selectbox("Inspect a security" if key == "STRING_INSTRUMENT" else "Inspect a trader", summary[key].unique(), key=key)
        detail = daily[daily[key].eq(selected)]
        breakdown_key = "STRING_TRADER_ID" if key == "STRING_INSTRUMENT" else "STRING_INSTRUMENT"
        breakdown = summarize(detail, [breakdown_key, "STRING_SIDE"])
        chart(px.bar(breakdown, x=breakdown_key, y=value, color="STRING_SIDE", barmode="group", color_discrete_map={"BUY": TEAL, "SELL": BLUE}, labels={value: value_label, breakdown_key: "Trader" if key == "STRING_INSTRUMENT" else "Security"}))

with explorer:
    st.subheader("Trade explorer")
    search = st.text_input("Search trades", placeholder="Trade ID, security, ISIN, trader, account…")
    records = daily.drop(columns=["FLOAT_GROSS_VALUE_USD", "BOOLEAN_FLAGGED", "TIMESTAMP_INTERVAL"]).sort_values("TIMESTAMP_TRADE_DATE")
    if search:
        mask = records.astype("string").apply(lambda s: s.str.contains(search, case=False, regex=False, na=False)).any(axis=1)
        records = records[mask]
    st.caption(f"{len(records):,} matching trades")
    st.dataframe(records, hide_index=True, width="stretch")
    st.download_button("Download filtered trades", records.to_csv(index=False).encode("utf-8"), file_name=f"dws_trades_{day}.csv", mime="text/csv")

st.divider()
st.caption("DWS Trade Analytics · Coding challenge prototype · Source-based analytics, all times UTC · USD conversions supplied by [https://api.frankfurter.dev/v2/rates](https://api.frankfurter.dev/v2/rates)")




