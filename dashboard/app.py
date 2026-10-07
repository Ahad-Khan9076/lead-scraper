"""
Streamlit Dashboard for Lead Scraper
====================================
Run with:  streamlit run dashboard/app.py
or via:    python main.py dashboard
"""
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database.models import (
    init_db, get_session, get_all_leads, upsert_lead, delete_lead, Lead
)
from scrapers.website_scraper import WebsiteContactScraper
from utils.validators import clean_email, normalize_phone
from utils.exporters import export_csv, export_excel, default_export_name

st.set_page_config(
    page_title="Lead Scraper Dashboard",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ───────────────────────── Helpers ─────────────────────────
@st.cache_resource
def get_db_session():
    init_db()
    return get_session()


def load_leads_df(status=None) -> pd.DataFrame:
    session = get_db_session()
    leads = get_all_leads(session, status=status)
    if not leads:
        return pd.DataFrame()
    return pd.DataFrame([l.to_dict() for l in leads])


def refresh():
    st.cache_data.clear()
    st.rerun()


# ───────────────────────── Sidebar ─────────────────────────
st.sidebar.title("📞 Lead Scraper")
st.sidebar.markdown("Public contact data for **call centres** & **email marketing** teams.")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Scrape New Leads", "Leads Table", "Export", "Settings & Compliance"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**Compliance reminder**\n\n"
    "• Only scrape publicly accessible pages\n"
    "• Respect robots.txt & rate limits\n"
    "• Verify emails before outreach\n"
    "• Honour opt-outs & local laws (GDPR, CAN-SPAM…)"
)

# ───────────────────────── Pages ─────────────────────────
if page == "Dashboard":
    st.title("📊 Lead Overview")
    df = load_leads_df()

    if df.empty:
        st.warning("No leads in the database yet. Go to **Scrape New Leads** to get started.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Leads", len(df))
        col2.metric("With Email", int(df["email"].notna().sum()))
        col3.metric("With Phone", int(df["phone"].notna().sum()))
        col4.metric("Companies", df["company"].nunique())

        st.markdown("### Status breakdown")
        if "status" in df.columns:
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["status", "count"]
            fig = px.pie(status_counts, names="status", values="count", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Confidence distribution")
        if "confidence" in df.columns:
            conf = df["confidence"].value_counts().reset_index()
            conf.columns = ["confidence", "count"]
            fig2 = px.bar(conf, x="confidence", y="count", color="confidence")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("### Recent leads")
        st.dataframe(
            df.head(15)[["id", "email", "phone", "company", "confidence", "status", "scraped_at"]],
            use_container_width=True,
        )


elif page == "Scrape New Leads":
    st.title("🔍 Scrape Public Contact Data")
    st.markdown(
        "Enter one or more **public websites / domains**. "
        "The tool will visit common contact & about pages and extract emails & phones."
    )

    with st.form("scrape_form"):
        urls_text = st.text_area(
            "URLs or domains (one per line)",
            height=150,
            placeholder="example.com\nhttps://another-company.com\nacme.io",
        )
        col_a, col_b, col_c = st.columns(3)
        delay = col_a.number_input("Delay (sec)", min_value=0.5, max_value=10.0, value=1.5, step=0.5)
        max_pages = col_b.number_input("Max pages / domain", min_value=1, max_value=20, value=6)
        workers = col_c.number_input("Parallel workers", min_value=1, max_value=5, value=2)
        respect_robots = st.checkbox("Respect robots.txt (recommended)", value=True)
        submitted = st.form_submit_button("Start Scraping", type="primary")

    if submitted:
        targets = [u.strip() for u in urls_text.splitlines() if u.strip()]
        if not targets:
            st.error("Please enter at least one URL or domain.")
        else:
            progress = st.progress(0)
            status_text = st.empty()
            results_box = st.empty()

            scraper = WebsiteContactScraper(
                delay=delay,
                max_pages_per_domain=max_pages,
                respect_robots=respect_robots,
            )

            all_contacts = []
            for i, t in enumerate(targets):
                status_text.info(f"Scraping {t} … ({i+1}/{len(targets)})")
                try:
                    contacts = scraper.scrape(t)
                    all_contacts.extend(contacts)
                except Exception as e:
                    st.warning(f"Failed on {t}: {e}")
                progress.progress((i + 1) / len(targets))

            # Clean
            cleaned = []
            for c in all_contacts:
                d = c.to_dict()
                if d.get("email"):
                    d["email"] = clean_email(d["email"])
                if d.get("phone"):
                    d["phone"] = normalize_phone(d["phone"])
                if d.get("email") or d.get("phone"):
                    cleaned.append(d)

            if cleaned:
                session = get_db_session()
                from database.models import bulk_upsert
                count = bulk_upsert(session, cleaned)
                status_text.success(f"Done! Extracted & stored **{count}** contacts.")
                results_box.dataframe(pd.DataFrame(cleaned), use_container_width=True)
                st.balloons()
            else:
                status_text.warning("No contacts found on the given sites.")


elif page == "Leads Table":
    st.title("📋 All Leads")
    df = load_leads_df()

    if df.empty:
        st.info("Database is empty.")
    else:
        # Filters
        col1, col2, col3 = st.columns(3)
        status_filter = col1.multiselect("Status", options=sorted(df["status"].dropna().unique()), default=[])
        conf_filter = col2.multiselect("Confidence", options=sorted(df["confidence"].dropna().unique()), default=[])
        search = col3.text_input("Search (email / company / phone)")

        filtered = df.copy()
        if status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]
        if conf_filter:
            filtered = filtered[filtered["confidence"].isin(conf_filter)]
        if search:
            mask = (
                filtered["email"].fillna("").str.contains(search, case=False)
                | filtered["company"].fillna("").str.contains(search, case=False)
                | filtered["phone"].fillna("").str.contains(search, case=False)
            )
            filtered = filtered[mask]

        st.caption(f"Showing {len(filtered)} of {len(df)} leads")
        st.dataframe(
            filtered[[
                "id", "email", "phone", "name", "title", "company",
                "website", "confidence", "status", "source_url", "scraped_at"
            ]],
            use_container_width=True,
            height=500,
        )

        # Quick status update
        st.markdown("### Update lead status")
        with st.form("update_status"):
            lead_id = st.number_input("Lead ID", min_value=1, step=1)
            new_status = st.selectbox(
                "New status",
                ["new", "contacted", "qualified", "unsubscribed", "invalid"],
            )
            if st.form_submit_button("Update"):
                session = get_db_session()
                lead = session.query(Lead).filter(Lead.id == lead_id).first()
                if lead:
                    lead.status = new_status
                    lead.updated_at = datetime.utcnow()
                    session.commit()
                    st.success(f"Lead {lead_id} → {new_status}")
                    st.rerun()
                else:
                    st.error("Lead not found")


elif page == "Export":
    st.title("⬇️ Export Leads")
    df = load_leads_df()
    if df.empty:
        st.warning("Nothing to export.")
    else:
        status = st.selectbox("Filter by status (optional)", ["All"] + sorted(df["status"].dropna().unique().tolist()))
        fmt = st.radio("Format", ["CSV", "Excel"], horizontal=True)

        if st.button("Generate & Download", type="primary"):
            export_df = df if status == "All" else df[df["status"] == status]
            data = export_df.to_dict(orient="records")
            name = default_export_name()
            if fmt == "CSV":
                path = export_csv(data, ROOT / "data" / f"{name}.csv")
                mime = "text/csv"
            else:
                path = export_excel(data, ROOT / "data" / f"{name}.xlsx")
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            with open(path, "rb") as f:
                st.download_button(
                    label=f"Download {path.name}",
                    data=f,
                    file_name=path.name,
                    mime=mime,
                )
            st.success(f"Ready: {len(data)} records")


elif page == "Settings & Compliance":
    st.title("⚙️ Settings & Compliance Guide")

    st.markdown("""
### How this tool works
1. You supply public domains / URLs.
2. The scraper visits a small set of common contact & about pages.
3. It extracts emails (mailto + regex) and phone numbers.
4. Results are cleaned, deduplicated and stored in a local SQLite database.
5. You can filter, update status, and export for your call-centre or email platform.

### Legal & ethical checklist (do this before any outreach)
| Check | Why it matters |
|-------|----------------|
| ✅ Only public pages | Never log in or bypass access controls |
| ✅ robots.txt respected | Default is ON – keep it that way |
| ✅ Rate limiting | Default 1.5 s delay – do not lower aggressively |
| ✅ Business context data | Prefer work emails over personal Gmail/Hotmail |
| ✅ Lawful basis documented | Consent or legitimate interest + balancing test (GDPR) |
| ✅ Easy opt-out | Every email must contain a working unsubscribe |
| ✅ Email verification | High bounce rates destroy sender reputation |
| ✅ Data minimisation | Collect only what you actually need |
| ✅ Secure storage | This SQLite file lives on your machine – protect it |
| ✅ Honour deletion requests | Provide a simple way to remove records |

### Recommended next steps for production use
- Add an email verification service (NeverBounce, ZeroBounce, etc.)
- Connect to your CRM / dialer via API
- Implement suppression lists (do-not-call / unsubscribed)
- Add scheduling (cron or APScheduler) for recurring scrapes of target lists
- Run behind a proper logging & monitoring setup

### Disclaimer
This software is provided for **educational and internal research purposes**.  
You are solely responsible for complying with all applicable laws, regulations, and website terms of service in your jurisdiction.
""")

    st.markdown("---")
    st.caption(f"Lead Scraper Dashboard • Local SQLite DB • {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
