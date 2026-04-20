import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
import altair as alt

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="OpsVision Enterprise | Observability",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- DESIGN SYSTEM (CSS) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Fira Sans', sans-serif;
    }
    code, pre {
        font-family: 'Fira Code', monospace;
    }
    .main {
        background-color: #0F172A;
    }
    .stMetric {
        background-color: #1E293B;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    h1, h2, h3 {
        color: #F8FAFC !important;
        font-family: 'Fira Code', monospace;
    }
    .health-badge {
        padding: 10px 20px;
        border-radius: 50px;
        font-weight: bold;
        text-align: center;
        display: inline-block;
        margin-bottom: 20px;
    }
    .status-up { background-color: #059669; color: white; }
    .status-warn { background-color: #D97706; color: white; }
    .status-down { background-color: #DC2626; color: white; }
    
    /* Premium accents */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0 0;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E293B;
        border-bottom: 2px solid #3B82F6 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- DATA LOADING ---
LOG_FILE = "data/logs.jsonl"

@st.cache_data(ttl=15)
def load_data():
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame()
    
    data = []
    with open(LOG_FILE, 'r') as f:
        for line in f:
            try:
                data.append(json.loads(line))
            except:
                continue
    
    df = pd.DataFrame(data)
    if not df.empty and 'ts' in df.columns:
        df['ts'] = pd.to_datetime(df['ts'])
        df = df.sort_values('ts', ascending=False)
    return df

# --- SIDEBAR & FILTERS ---
st.sidebar.title("OpsVision Enterprise")
st.sidebar.markdown("---")

# Auto-refresh
auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (30s)", value=True)
if auto_refresh:
    st.components.v1.html(
        """
        <script>
        setTimeout(function(){
            window.parent.location.reload();
        }, 30000);
        </script>
        """,
        height=0
    )
    st.sidebar.caption("Next refresh in 30s")

# Time Range Filter
time_range = st.sidebar.selectbox(
    "⏳ Time Range",
    options=["Last 15 Minutes", "Last 1 Hour", "Last 3 Hours", "Last 24 Hours", "All Time"],
    index=1 # Default to 1 Hour
)

# --- PROCESSING ---
df_all = load_data()

if df_all.empty:
    st.error("No logs found. Ensure the system is running and generating logs.")
    st.stop()

# Guard: ensure columns that may be absent in early/startup logs exist
for _col in ["feature", "correlation_id", "latency_ms", "cost_usd",
              "tokens_in", "tokens_out", "quality_score"]:
    if _col not in df_raw.columns:
        df_raw[_col] = None

# Normalise: rows without feature (startup logs, etc.) → label as "system"
df_raw["feature"] = df_raw["feature"].fillna("system")

# --- SIDEBAR ---
st.sidebar.title("OpsVision Enterprise")
st.sidebar.markdown("---")
refresh = st.sidebar.button("🔄 Refresh Data")
if refresh:
    st.cache_data.clear()

st.sidebar.info(f"Showing {len(df_raw)} of {len(df_all)} records")

# --- APP LAYOUT ---
tab1, tab2, tab3 = st.tabs(["🏛️ Layer 1: Executive Overview", "⚙️ Layer 2: Engineering Detail", "🔍 Layer 3: Debug Investigation"])

# --- LAYER 1: EXECUTIVE ---
with tab1:
    st.header("Global System Health")
    
    # Health Calculation
    total_reqs = len(df_raw)
    error_count = len(df_raw[df_raw['level'] == 'error'])
    error_rate = (error_count / total_reqs) * 100 if total_reqs > 0 else 0
    
    if error_rate < 1:
        status_class = "status-up"
        status_text = "HEALTHY"
    elif error_rate < 5:
        status_class = "status-warn"
        status_text = "DEGRADED"
    else:
        status_class = "status-down"
        status_text = "CRITICAL"
    
    st.markdown(f'<div class="health-badge {status_class}">SYSTEM STATUS: {status_text} ({100-error_rate:.1f}% Availability)</div>', unsafe_allow_html=True)
    
    st.divider()
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Requests", f"{total_reqs:,}")
    with c2:
        if not df_raw.empty and 'latency_ms' in df_raw.columns:
            p99_latency = df_raw['latency_ms'].quantile(0.99)
            st.metric("P99 Latency", f"{p99_latency:.0f}ms", delta=f"{p99_latency-500:.0f}ms" if p99_latency > 500 else None, delta_color="inverse")
        else:
            st.metric("P99 Latency", "0ms")
    with c3:
        total_cost = df_raw['cost_usd'].sum() if 'cost_usd' in df_raw.columns else 0.0
        st.metric("Total Cost", f"${total_cost:.4f}")
    with c4:
        avg_quality = df_raw['quality_score'].mean() if 'quality_score' in df_raw.columns else 0
        st.metric("Avg Quality", f"{avg_quality:.2f}/1.0")

    st.subheader("Traffic Velocity")
    usage_chart = alt.Chart(df_raw).mark_area(
        line={'color':'#3B82F6'},
        color=alt.Gradient(
            gradient='linear',
            stops=[alt.GradientStop(color='#3B82F6', offset=0),
                   alt.GradientStop(color='rgba(59, 130, 246, 0.1)', offset=1)],
            x1=1, x2=1, y1=1, y2=0
        )
    ).encode(
        x=alt.X('ts:T', title="Time"),
        y=alt.Y('count():Q', title="Request Count"),
    ).properties(height=300)
    st.altair_chart(usage_chart, use_container_width=True)

# --- LAYER 2: ENGINEERING ---
with tab2:
    st.header("4 Golden Signals & SLOs")
    
    # SLO Thresholds
    LATENCY_SLO = 500
    ERROR_SLO = 5.0
    
    # 1. LATENCY (P50, P95, P99)
    st.subheader("1. Latency Distribution (P50/P95/P99)")
    if 'latency_ms' in df_raw.columns and not df_raw.empty:
        # Prepare percentile data
        df_lat = df_raw[df_raw['latency_ms'].notnull()].copy()
        df_lat = df_lat.set_index('ts').resample('1min')['latency_ms'].agg(['median', lambda x: x.quantile(0.95), lambda x: x.quantile(0.99)]).reset_index()
        df_lat.columns = ['ts', 'P50', 'P95', 'P99']
        
        # Melt for plotting
        df_lat_melted = df_lat.melt('ts', var_name='Metric', value_name='ms')
        
        l_chart = alt.Chart(df_lat_melted).mark_line().encode(
            x=alt.X('ts:T', title="Time"),
            y=alt.Y('ms:Q', title="Latency (ms)"),
            color=alt.Color('Metric:N', scale=alt.Scale(range=['#60A5FA', '#3B82F6', '#2563EB']))
        ).properties(height=300)
        
        slo_line = alt.Chart(pd.DataFrame({'y': [LATENCY_SLO]})).mark_rule(color='#EF4444', strokeDash=[5,5]).encode(y='y:Q')
        st.altair_chart(l_chart + slo_line, use_container_width=True)
        st.caption(f"Red dashed line: SLO Threshold ({LATENCY_SLO}ms)")
    else:
        st.info("Insufficient latency data for the selected window.")

    col1, col2 = st.columns(2)
    
    with col1:
        # 2. TRAFFIC (QPS)
        st.subheader("2. Traffic (Throughput & QPS)")
        if not df_raw.empty:
            df_qps = df_raw.set_index('ts').resample('1s').size().reset_index()
            df_qps.columns = ['ts', 'requests']
            # Smooth QPS with rolling average
            df_qps['qps'] = df_qps['requests'].rolling(window=5).mean()
            
            t_chart = alt.Chart(df_qps).mark_line(color='#10B981').encode(
                x=alt.X('ts:T', title="Time"),
                y=alt.Y('qps:Q', title="QPS (smoothed)")
            )
            st.altair_chart(t_chart, use_container_width=True)
            st.caption("Requests Per Second (smoothed over 5s)")
    
    with col2:
        # 3. ERROR RATE & BREAKDOWN
        st.subheader("3. Error Rate & Breakdown")
        err_df = df_raw.copy()
        err_df['is_error'] = err_df['level'] == 'error'
        err_trend = err_df.set_index('ts').resample('1min')['is_error'].mean() * 100
        err_trend = err_trend.reset_index()
        
        e_chart = alt.Chart(err_trend).mark_line(color='#EF4444').encode(
            x=alt.X('ts:T', title="Time"),
            y=alt.Y('is_error:Q', title="Error Rate (%)")
        )
        slo_err_line = alt.Chart(pd.DataFrame({'y': [ERROR_SLO]})).mark_rule(color='#EF4444', strokeDash=[5,5]).encode(y='y:Q')
        st.altair_chart(e_chart + slo_err_line, use_container_width=True)
        
        # Error Breakdown by Feature
        if error_count > 0:
            err_breakdown = df_raw[df_raw['level'] == 'error'].groupby('feature').size().reset_index(name='count')
            eb_chart = alt.Chart(err_breakdown).mark_bar(color='#EF4444').encode(
                x='count:Q',
                y=alt.Y('feature:N', sort='-x')
            ).properties(height=100)
            st.altair_chart(eb_chart, use_container_width=True)

    st.divider()
    
    col3, col4 = st.columns(2)
    
    with col3:
        # 4. COST OVER TIME
        st.subheader("4. Cost Trend (USD)")
        if 'cost_usd' in df_raw.columns:
            cost_trend = df_raw.set_index('ts').resample('1min')['cost_usd'].sum().reset_index()
            c_chart = alt.Chart(cost_trend).mark_area(
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#F59E0B', offset=0),
                           alt.GradientStop(color='rgba(245, 158, 11, 0.1)', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('ts:T', title="Time"),
                y=alt.Y('cost_usd:Q', title="Cost (USD)")
            )
            st.altair_chart(c_chart, use_container_width=True)
        else:
            st.info("Cost data unavailable.")

    with col4:
        # 5. TOKENS IN/OUT
        st.subheader("5. Token Throughput")
        if 'tokens_in' in df_raw.columns:
            token_trend = df_raw.set_index('ts').resample('1min')[['tokens_in', 'tokens_out']].sum().reset_index()
            token_melted = token_trend.melt('ts', var_name='Type', value_name='count')
            
            tk_chart = alt.Chart(token_melted).mark_line().encode(
                x=alt.X('ts:T', title="Time"),
                y=alt.Y('count:Q', title="Tokens"),
                color=alt.Color('Type:N', scale=alt.Scale(range=['#F97316', '#FB923C']))
            )
            st.altair_chart(tk_chart, use_container_width=True)
        else:
            st.info("Token data unavailable.")

    st.divider()
    st.subheader("Cost & Quality Metrics")
    q1, q2 = st.columns(2)
    with q1:
        if 'cost_usd' in df_raw.columns:
            cost_by_feature = df_raw.groupby('feature')['cost_usd'].sum().reset_index()
            c_pie = alt.Chart(cost_by_feature).mark_arc().encode(
                theta='cost_usd:Q',
                color='feature:N',
                tooltip=['feature', 'cost_usd']
            )
            st.altair_chart(c_pie, use_container_width=True)
    with q2:
        feature_dist = df_raw['feature'].value_counts().rename_axis('feature').reset_index(name='count')
        f_chart = alt.Chart(feature_dist).mark_bar().encode(
            x='count:Q',
            y=alt.Y('feature:N', sort='-x'),
            color='feature:N'
        )
        st.altair_chart(q_chart, use_container_width=True)
        st.caption("Quality score calculated from latency, docs availability, and answer length.")
    else:
        st.warning("Quality data not found in logs. Check if main.py is updated to log quality_score.")

# --- LAYER 3: DEBUG ---
with tab3:
    st.header("Deep Investigation & Traces")
    
    search = st.text_input("🔍 Search Logs (Message, ID, Feature...)", "")
    
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        level_opts = sorted(df_raw['level'].dropna().unique())
        f_level = st.multiselect("Filter Level", level_opts, default=level_opts)
    with filter_col2:
        feat_opts = sorted(df_raw['feature'].dropna().unique())
        f_feat = st.multiselect("Filter Feature", feat_opts, default=feat_opts)
    
    df_debug = df_raw[(df_raw['level'].isin(f_level)) & (df_raw['feature'].isin(f_feat))]
    
    if search:
        df_debug = df_debug[df_debug.apply(lambda r: search.lower() in str(r).lower(), axis=1)]
    
    st.dataframe(
        df_debug,
        column_config={
            "ts": st.column_config.DatetimeColumn("Time", format="HH:mm:ss.SSS"),
            "payload": st.column_config.JsonColumn("Payload"),
            "cost_usd": st.column_config.NumberColumn("Cost", format="$%.4f"),
            "quality_score": st.column_config.NumberColumn("Quality", format="%.2f"),
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()
    st.subheader("Correlation Explorer")
    cid_options = [""] + sorted([c for c in df_raw['correlation_id'].dropna().unique() if c])
    cid = st.selectbox("Select Correlation ID to trace flow", cid_options)
    
    if cid:
        flow = df_raw[df_raw['correlation_id'] == cid].sort_values('ts')
        for idx, row in flow.iterrows():
            with st.container():
                st.markdown(f"**[{row['ts'].strftime('%H:%M:%S.%f')[:-3]}]** `{row['event']}` | Level: `{row['level']}`")
                payload = row.get('payload') or {}
                if isinstance(payload, dict):
                    st.json(payload)
                else:
                    st.code(str(payload))

# --- FOOTER ---
st.markdown("---")
st.markdown("🛡️ **OpsVision Enterprise** | 2026 Observability Standard")
