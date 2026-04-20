import streamlit as st
import pandas as pd
import json
import os
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
    }
    .status-up { background-color: #059669; color: white; }
    .status-warn { background-color: #D97706; color: white; }
    .status-down { background-color: #DC2626; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- DATA LOADING ---
LOG_FILE = "data/logs.jsonl"

@st.cache_data(ttl=30)
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

# --- PROCESSING ---
df_raw = load_data()

if df_raw.empty:
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

st.sidebar.info(f"Loaded {len(df_raw)} records")

# --- APP LAYOUT ---
tab1, tab2, tab3 = st.tabs(["🏛️ Layer 1: Executive Overview", "⚙️ Layer 2: Engineering Detail", "🔍 Layer 3: Debug Investigation"])

# --- LAYER 1: EXECUTIVE ---
with tab1:
    st.header("Global System Health")
    
    # Health Calculation
    error_rate = (len(df_raw[df_raw['level'] == 'error']) / len(df_raw)) * 100
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
        st.metric("Total Requests", f"{len(df_raw):,}")
    with c2:
        uptime_min = (df_raw['ts'].max() - df_raw['ts'].min()).total_seconds() / 60
        st.metric("Session Uptime", f"{uptime_min:.1f}m")
    with c3:
        total_cost = df_raw['cost_usd'].sum() if 'cost_usd' in df_raw.columns else 0.0
        st.metric("Total API Cost", f"${total_cost:.4f}")
    with c4:
        avg_latency = df_raw['latency_ms'].mean() if 'latency_ms' in df_raw.columns else 0
        st.metric("Avg Latency", f"{avg_latency:.1f}ms")

    st.subheader("Business Impact & Usage")
    usage_chart = alt.Chart(df_raw).mark_area(
        line={'color':'#3B82F6'},
        color=alt.Gradient(
            gradient='linear',
            stops=[alt.GradientStop(color='#3B82F6', offset=0),
                   alt.GradientStop(color='rgba(59, 130, 246, 0.1)', offset=1)],
            x1=1, x2=1, y1=1, y2=0
        )
    ).encode(
        x='ts:T',
        y='count():Q',
    ).properties(height=300)
    st.altair_chart(usage_chart, use_container_width=True)

# --- LAYER 2: ENGINEERING ---
with tab2:
    st.header("4 Golden Signals & SLOs")
    
    # SLO Thresholds
    LATENCY_SLO = 500
    ERROR_SLO = 5.0
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. Latency (P95)")
        if 'latency_ms' in df_raw.columns:
            # Latency Chart with SLO line
            l_chart = alt.Chart(df_raw[df_raw['latency_ms'].notnull()]).mark_line(color='#3B82F6').encode(
                x='ts:T',
                y=alt.Y('latency_ms:Q', title="Latency (ms)")
            )
            slo_line = alt.Chart(pd.DataFrame({'y': [LATENCY_SLO]})).mark_rule(color='red', strokeDash=[5,5]).encode(y='y:Q')
            st.altair_chart(l_chart + slo_line, use_container_width=True)
            st.caption(f"Red dashed line: SLO Threshold ({LATENCY_SLO}ms)")
    
    with col2:
        st.subheader("2. Traffic (Throughput)")
        t_chart = alt.Chart(df_raw).mark_bar(color='#60A5FA').encode(
            x=alt.X('ts:T', bin=alt.Bin(maxbins=30)),
            y='count():Q'
        )
        st.altair_chart(t_chart, use_container_width=True)

    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("3. Errors (Rate %)")
        # Calculate hourly error rate
        err_df = df_raw.copy()
        err_df['is_error'] = err_df['level'] == 'error'
        err_trend = err_df.set_index('ts').resample('1min')['is_error'].mean() * 100
        err_trend = err_trend.reset_index()
        
        e_chart = alt.Chart(err_trend).mark_line(color='#EF4444').encode(
            x='ts:T',
            y=alt.Y('is_error:Q', title="Error Rate (%)")
        )
        slo_err_line = alt.Chart(pd.DataFrame({'y': [ERROR_SLO]})).mark_rule(color='red', strokeDash=[5,5]).encode(y='y:Q')
        st.altair_chart(e_chart + slo_err_line, use_container_width=True)
        st.caption(f"Red dashed line: Error Budget ({ERROR_SLO}%)")

    with col4:
        st.subheader("4. Saturation & Efficiency")
        if 'tokens_in' in df_raw.columns:
            token_chart = alt.Chart(df_raw).mark_circle(color='#F97316').encode(
                x='tokens_in:Q',
                y='tokens_out:Q',
                size='latency_ms:Q',
                tooltip=['correlation_id', 'tokens_in', 'tokens_out', 'latency_ms']
            )
            st.altair_chart(token_chart, use_container_width=True)
        else:
            st.info("Saturation data (tokens) requires load test.")

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
        st.altair_chart(f_chart, use_container_width=True)

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
