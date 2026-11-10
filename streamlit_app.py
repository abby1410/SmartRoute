import os
import requests
import pandas as pd
import streamlit as st
from app.database import init_db, recent_requests, aggregate_metrics

st.set_page_config(page_title="SmartRoute", page_icon="🧭", layout="wide")
init_db()
API_URL = os.getenv("SMARTROUTE_API_URL", "http://127.0.0.1:8000")
st.title("🧭 SmartRoute")
st.caption("Intelligent LLM gateway · V0–V7")

with st.sidebar:
    st.header("Gateway")
    st.code(API_URL)
    tenant = st.text_input("Tenant ID", "default")
    api_key = st.text_input("API key (optional)", type="password")
    headers = {"X-Tenant-ID": tenant}
    if api_key:
        headers["X-API-Key"] = api_key

tabs = st.tabs(["Playground", "Overview", "Request logs", "Evaluation", "About"])

with tabs[0]:
    st.subheader("Try the gateway")
    prompt = st.text_area("Prompt", height=150, placeholder="Ask something...")
    system_prompt = st.text_input("System prompt", "You are a helpful assistant.")
    c1, c2, c3 = st.columns(3)
    strategy = c1.selectbox("Routing strategy", ["auto", "cheapest", "strongest"])
    use_judge = c2.checkbox("LLM routing judge", False)
    use_cache = c3.checkbox("Use cache", True)
    if st.button("Send to SmartRoute", type="primary"):
        if not prompt.strip():
            st.warning("Enter a prompt first.")
        else:
            try:
                response = requests.post(
                    f"{API_URL}/chat",
                    headers=headers,
                    json={
                        "prompt": prompt,
                        "system_prompt": system_prompt,
                        "strategy": strategy,
                        "use_llm_judge": use_judge,
                        "use_cache": use_cache
                    },
                    timeout=120
                )
                response.raise_for_status()
                data = response.json()
                st.markdown("### Answer")
                st.write(data["answer"])
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Tier", data["tier"])
                m2.metric("Model", data["model"])
                m3.metric("Estimated cost", f"${data['estimated_cost']:.6f}")
                m4.metric("Latency", f"{data['latency_ms']:.0f} ms")
                st.json({
                    "route": data.get("route"),
                    "cache_hit": data["cache_hit"],
                    "fallback_used": data["fallback_used"],
                    "token_usage": [data["input_tokens"], data["output_tokens"]]
                })
            except Exception as exc:
                st.error(f"Gateway request failed: {exc}")

with tabs[1]:
    st.subheader("Gateway overview")
    metrics = aggregate_metrics()
    cols = st.columns(5)
    cols[0].metric("Requests", metrics["requests"])
    cols[1].metric("Estimated spend", f"${metrics['total_cost']:.4f}")
    cols[2].metric("Avg latency", f"{metrics['avg_latency_ms']:.0f} ms")
    cols[3].metric("Cache hit rate", f"{metrics['cache_hit_rate']:.1%}")
    cols[4].metric("Fallback rate", f"{metrics['fallback_rate']:.1%}")
    try:
        health = requests.get(f"{API_URL}/health", timeout=5).json()
        st.success(f"API status: {health['status']} · version {health['version']}")
    except Exception:
        st.warning("API is not reachable. Start FastAPI in another terminal.")

with tabs[2]:
    st.subheader("Recent request logs")
    rows = recent_requests(500, tenant_id=tenant if tenant else None)
    if rows:
        df = pd.DataFrame(rows)
        show = [c for c in ["id", "created_at", "strategy", "tier", "model", "provider",
                            "estimated_cost", "latency_ms", "cache_hit", "fallback_used",
                            "route_reason"] if c in df.columns]
        st.dataframe(df[show], use_container_width=True, hide_index=True)
        st.download_button("Download logs CSV", df.to_csv(index=False), "smartroute_logs.csv")
    else:
        st.info("No logged requests yet.")

with tabs[3]:
    st.subheader("Evaluation results")
    summary_path = "evaluation/results/summary.csv"
    detail_path = "evaluation/results/detail.csv"
    if os.path.exists(summary_path):
        summary = pd.read_csv(summary_path)
        st.dataframe(summary, use_container_width=True, hide_index=True)
    else:
        st.info("Run `python evaluation/run_eval.py` to generate evaluation results.")
    if os.path.exists(detail_path):
        with st.expander("Per-prompt evaluation details"):
            st.dataframe(pd.read_csv(detail_path), use_container_width=True, hide_index=True)

with tabs[4]:
    st.markdown("""
    **SmartRoute** is a learning/portfolio project exploring model routing,
    caching, evaluation, reliability and cost-quality observability.

    - V0: API gateway
    - V1–V3: heuristic and LLM-based routing
    - V4: exact and optional semantic cache
    - V5: benchmark evaluation harness
    - V6: retries, fallback, circuit breaker and basic tenant controls
    - V7: analytics dashboard

    Cost numbers are estimates. Update model IDs and provider pricing before
    drawing conclusions. This is not a production-hardened gateway.
    """)
