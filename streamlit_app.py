import streamlit as st
import os
import json
import glob
import pandas as pd

from main import run_pipeline

st.set_page_config(
    page_title="FocusChain LeadGen",
    page_icon="⚡",
    layout="wide"
)

# --- Sidebar ---
with st.sidebar:
    st.title("⚡ FocusChain LeadGen")
    st.caption("AI-powered B2B lead generation")
    st.divider()

    # ICP selector
    config_files = glob.glob("config/*.json")
    if not config_files:
        st.error("No ICP config files found in /config/")
        st.stop()

    config_labels = {f.split("/")[-1].replace(".json", ""): f for f in config_files}
    selected_label = st.selectbox("Select ICP", list(config_labels.keys()))
    selected_config = config_labels[selected_label]

    # Show ICP summary
    with open(selected_config) as f:
        icp_preview = json.load(f)
    st.caption(f"Client: {icp_preview.get('client', '')}")
    st.caption(f"Locations: {', '.join(icp_preview.get('locations', []))}")

    st.divider()

    # Exclusion list
    exclusion_file = st.file_uploader(
        "Exclusion list (Excel, optional)",
        type=["xlsx"],
        help="Upload a list of companies already contacted. One column: company_name"
    )

    # Max leads
    max_leads = st.number_input(
        "Max leads to find", min_value=1, max_value=50, value=10
    )

    st.divider()

    # API Status
    with st.expander("API Status"):
        apis = {
            "Gemini": "GEMINI_API_KEY",
            "Serper": "SERPER_API_KEY",
            "Apollo": "APOLLO_API_KEY",
            "ProxyCurl": "PROXYCURL_API_KEY",
            "Tracxn": "TRACXN_API_KEY"
        }
        for name, env_key in apis.items():
            status = "🟢" if os.getenv(env_key) else "🔴"
            required = "" if env_key in ["PROXYCURL_API_KEY", "TRACXN_API_KEY"] else " (required)"
            st.write(f"{status} {name}{required}")

    st.divider()
    run_button = st.button("▶ Run Agent", type="primary", use_container_width=True)


# --- Main area ---
tab1, tab2, tab3 = st.tabs(["📋 Live Log", "📊 Results", "⬇️ Download"])

if run_button:
    # Save exclusion file if uploaded
    exclusion_path = None
    if exclusion_file:
        os.makedirs("output", exist_ok=True)
        exclusion_path = "output/exclusion_upload.xlsx"
        with open(exclusion_path, "wb") as f:
            f.write(exclusion_file.read())

    with tab1:
        st.info("Agent running... check the Results tab when complete.")

    try:
        output_path = run_pipeline(
            icp_config_path=selected_config,
            exclusion_list_path=exclusion_path,
            max_leads=int(max_leads)
        )
        st.session_state["output_path"] = output_path
        with tab1:
            st.success(f"Pipeline complete. Output: {output_path}")
    except Exception as e:
        with tab1:
            st.error(f"Pipeline error: {e}")

with tab2:
    if "output_path" in st.session_state:
        df = pd.read_excel(st.session_state["output_path"])
        display_cols = [
            c for c in ["Rank", "Company", "Total Score", "Contact Name",
                         "Email", "Primary Signal", "Opening Line"]
            if c in df.columns
        ]
        st.dataframe(df[display_cols], use_container_width=True)
    else:
        st.info("Run the agent to see results here.")

with tab3:
    if "output_path" in st.session_state:
        path = st.session_state["output_path"]
        with open(path, "rb") as f:
            data = f.read()
        st.download_button(
            label="⬇️ Download Excel",
            data=data,
            file_name=os.path.basename(path),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.caption(f"File: {path} | Size: {round(len(data)/1024, 1)} KB")
    else:
        st.info("Run the agent first.")
