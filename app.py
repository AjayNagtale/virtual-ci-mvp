# app.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import plotly.express as px

st.set_page_config(page_title="Virtual CI Specialist MVP", layout="wide")
st.title("🔧 Virtual CI Specialist — MVP Demo")
st.markdown("Upload your A3 Excel (Week OAE + Loss Entries) or use the sample data. Mobile friendly.")

# -------------------------
# Helpers
# -------------------------
def make_sample_excel(path="sample_data.xlsx"):
    weeks = []
    base = datetime(2025,5,10)
    for i in range(12):
        wk = (base + pd.Timedelta(weeks=i)).strftime("W%U-%Y")
        actual = round(78 + (i%3 -1)*1.2 + (i*0.15),1)
        target = 85.0
        weeks.append({"Week": wk, "Actual OAE": actual, "Target OAE": target})
    df_oae = pd.DataFrame(weeks)
    rows = [
        {"Date":"2025-08-04","Week":"W31-2025","Department":"Maintenance","Reason":"Chiller breakdown","Loss Minutes":180},
        {"Date":"2025-08-04","Week":"W31-2025","Department":"Maintenance","Reason":"Pump failure","Loss Minutes":90},
        {"Date":"2025-08-04","Week":"W31-2025","Department":"Process Engg","Reason":"Wrong setup","Loss Minutes":120},
        {"Date":"2025-07-28","Week":"W30-2025","Department":"Maintenance","Reason":"Chiller breakdown","Loss Minutes":160},
        {"Date":"2025-07-21","Week":"W29-2025","Department":"Maintenance","Reason":"Chiller breakdown","Loss Minutes":170},
        {"Date":"2025-07-14","Week":"W28-2025","Department":"Process Engg","Reason":"Wrong setup","Loss Minutes":130},
    ]
    df_losses = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df_oae.to_excel(writer, sheet_name="Week OAE", index=False)
        df_losses.to_excel(writer, sheet_name="Loss Entries", index=False)
    return path

def parse_uploaded_excel(uploaded):
    try:
        xls = pd.ExcelFile(uploaded)
    except Exception:
        return None, None
    oae_df = None
    losses_df = None
    for s in xls.sheet_names:
        try:
            df = xls.parse(s)
        except Exception:
            continue
        cols = " ".join([c.lower() for c in df.columns.astype(str)])
        if ("oae" in cols or "oee" in cols or "target" in cols) and df.shape[1] >= 2:
            oae_df = df.copy()
        if any(k in cols for k in ["reason","loss","minutes","downtime","duration","department"]):
            losses_df = df.copy()
    return oae_df, losses_df

def ensure_week_col(df):
    if df is None:
        return df
    if "Week" not in df.columns:
        if "Date" in df.columns:
            try:
                df["Week"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("W%U-%Y")
            except:
                df["Week"] = "W??-YYYY"
        else:
            df["Week"] = "W??-YYYY"
    return df

def pareto_level1(df_week, group_col):
    if df_week.empty:
        return pd.DataFrame(columns=[group_col, "Loss Minutes", "Pct", "CumPct"])
    lvl = df_week.groupby(group_col, as_index=False)["Loss Minutes"].sum().sort_values("Loss Minutes", ascending=False)
    total = lvl["Loss Minutes"].sum()
    lvl["Pct"] = (lvl["Loss Minutes"]/total*100).round(2)
    lvl["CumPct"] = lvl["Pct"].cumsum().round(2)
    return lvl

def suggest_solutions(reason):
    r = str(reason).lower()
    if "chill" in r:
        return ["Check condenser & fan; schedule PM; install clog sensor", "Keep spare compressor ready"]
    if "pump" in r:
        return ["Check seals/bearings; lubrication schedule; maintain spare pump"]
    if "material" in r:
        return ["Improve vendor planning; implement kanban; maintain buffer stock"]
    if "rework" in r:
        return ["Review QC checklist; update SOP; operator training"]
    if "plc" in r:
        return ["Check I/O modules; firmware update; keep spare PLC"]
    if "setup" in r or "wrong" in r:
        return ["Standardize setup checklist; operator training; poka-yoke"]
    return ["Containment action; perform 5-Why; assign owner for permanent fix"]

def map_6m(reason):
    r = str(reason).lower()
    if any(k in r for k in ["chill","pump","motor","elect","compressor"]): return "Machine"
    if any(k in r for k in ["operator","man","training","absent","skill"]): return "Man"
    if any(k in r for k in ["material","part","vendor","raw"]): return "Material"
    if any(k in r for k in ["method","setup","procedure","wrong"]): return "Method"
    if any(k in r for k in ["measure","sensor","calib","accuracy"]): return "Measurement"
    return "Environment/Other"

# -------------------------
# Load data (upload or sample)
# -------------------------
st.sidebar.header("Data & Options")
use_sample = st.sidebar.checkbox("Use sample data (recommended)", value=True)
uploaded = st.sidebar.file_uploader("Upload A3 Excel (optional)", type=["xlsx"])

sample_path = "sample_data.xlsx"
try:
    open(sample_path, "rb").close()
except Exception:
    make_sample_excel(sample_path)

if uploaded is not None:
    oae_df, losses_df = parse_uploaded_excel(uploaded)
    if oae_df is None and losses_df is None:
        st.sidebar.warning("Uploaded file not recognized; falling back to sample data.")
        oae_df = pd.read_excel(sample_path, sheet_name="Week OAE")
        losses_df = pd.read_excel(sample_path, sheet_name="Loss Entries")
else:
    if use_sample:
        oae_df = pd.read_excel(sample_path, sheet_name="Week OAE")
        losses_df = pd.read_excel(sample_path, sheet_name="Loss Entries")
    else:
        st.info("Use sample data or upload A3 Excel. Using sample by default.")
        oae_df = pd.read_excel(sample_path, sheet_name="Week OAE")
        losses_df = pd.read_excel(sample_path, sheet_name="Loss Entries")

# Normalize OAE
oae_df = oae_df.rename(columns={oae_df.columns[0]:"Week", oae_df.columns[1]:"Actual OAE"})
if "Target OAE" not in oae_df.columns and oae_df.shape[1] > 2:
    oae_df["Target OAE"] = oae_df.iloc[:,2]
elif "Target OAE" not in oae_df.columns:
    oae_df["Target OAE"] = 85.0

# Normalize losses
losses_df = ensure_week_col(losses_df)
# rename columns heuristically
if "Loss Minutes" not in losses_df.columns:
    for c in losses_df.columns:
        if "loss" in str(c).lower() or "minute" in str(c).lower() or "downtime" in str(c).lower():
            losses_df = losses_df.rename(columns={c:"Loss Minutes"})
            break
if "Department" not in losses_df.columns:
    for c in losses_df.columns:
        if "dept" in str(c).lower() or "department" in str(c).lower() or "area" in str(c).lower():
            losses_df = losses_df.rename(columns={c:"Department"})
            break
if "Reason" not in losses_df.columns:
    for c in losses_df.columns:
        if "reason" in str(c).lower() or "cause" in str(c).lower() or "desc" in str(c).lower():
            losses_df = losses_df.rename(columns={c:"Reason"})
            break

losses_df["Loss Minutes"] = pd.to_numeric(losses_df["Loss Minutes"], errors="coerce").fillna(0)
if "Department" not in losses_df.columns:
    losses_df["Department"] = "Unknown"
if "Reason" not in losses_df.columns:
    losses_df["Reason"] = "Unknown"

# -------------------------
# Tabs (Daily, Weekly A3, Monthly A3, Action Tracker)
# -------------------------
tabs = st.tabs(["Daily", "Weekly A3", "Monthly A3", "Action Tracker"])

# --- Daily ---
with tabs[0]:
    st.header("Daily Loss Entry & Pareto (Module 2A)")
    with st.form("daily_form"):
        d_date = st.date_input("Date", value=date(2025,8,4))
        d_dept = st.text_input("Department", value="Maintenance")
        d_reason = st.text_input("Reason", value="Chiller breakdown")
        d_mins = st.number_input("Loss Minutes", min_value=0, value=60)
        submitted = st.form_submit_button("Add (in-memory)")
        if submitted:
            new = {"Date": d_date.strftime("%Y-%m-%d"), "Week": d_date.strftime("W%U-%Y"), "Department": d_dept, "Reason": d_reason, "Loss Minutes": d_mins}
            losses_df = pd.concat([losses_df, pd.DataFrame([new])], ignore_index=True)
            st.success("Added temporary loss entry (demo only).")

    st.markdown("**Daily Pareto (by Department)**")
    if "Date" in losses_df.columns:
        last_date = losses_df["Date"].dropna().astype(str).max()
        df_day = losses_df[losses_df["Date"]==last_date]
    else:
        df_day = losses_df.tail(5)
    l1_day = df_day.groupby("Department", as_index=False)["Loss Minutes"].sum().sort_values("Loss Minutes", ascending=False)
    if not l1_day.empty:
        fig = px.bar(l1_day, x="Department", y="Loss Minutes", title="Daily Level-1 Pareto")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No daily data available.")

# --- Weekly A3 ---
with tabs[1]:
    st.header("Weekly A3 — One Page View (Module 2B)")
    st.subheader("12-week OAE Trend (Target vs Actual)")
    fig_oae = px.line(oae_df, x="Week", y=["Actual OAE","Target OAE"], markers=True)
    st.plotly_chart(fig_oae, use_container_width=True)

    st.subheader("Level-1 Pareto (Latest Week)")
    latest_week = losses_df["Week"].max()
    st.write(f"Showing data for week: **{latest_week}**")
    df_latest = losses_df[losses_df["Week"]==latest_week]

    grouping_option = st.selectbox("Group Level-1 by", options=["Department","6M (auto)"], index=0)
    if grouping_option == "6M (auto)":
        df_latest["Tag6M"] = df_latest["Reason"].apply(map_6m)
        lvl1 = pareto_level1(df_latest, "Tag6M").rename(columns={"Tag6M":"Category"})
    else:
        lvl1 = pareto_level1(df_latest, "Department").rename(columns={"Department":"Category"})

    st.plotly_chart(px.bar(lvl1, x="Category", y="Loss Minutes", title="Level-1 Pareto"), use_container_width=True)

    st.subheader("Level-2 Pareto (Drilldown)")
    top_cats = lvl1[lvl1["CumPct"]<=80]["Category"].tolist()
    if not top_cats:
        top_cats = lvl1.head(2)["Category"].tolist()
    for cat in top_cats:
        st.markdown(f"**{cat}**")
        if grouping_option == "6M (auto)":
            sub = df_latest[df_latest["Tag6M"]==cat].groupby("Reason", as_index=False)["Loss Minutes"].sum().sort_values("Loss Minutes", ascending=False)
        else:
            sub = df_latest[df_latest["Department"]==cat].groupby("Reason", as_index=False)["Loss Minutes"].sum().sort_values("Loss Minutes", ascending=False)
        if sub.empty:
            st.info("No sub-reasons available for this category this week.")
            continue
        sub["PctOfDept"] = (sub["Loss Minutes"]/sub["Loss Minutes"].sum()*100).round(2)
        st.plotly_chart(px.bar(sub, x="Reason", y="Loss Minutes", title=f"Level-2 Pareto: {cat}"), use_container_width=True)

        # 5-Why & action input for top reason
        top_reason = sub.iloc[0]["Reason"]
        with st.expander(f"5-Why & Actions for: {top_reason}"):
            w1 = st.text_input("Why 1", value=f"What happened? ({top_reason})", key=f"w1_{cat}")
            w2 = st.text_input("Why 2", value="Cause?", key=f"w2_{cat}")
            w3 = st.text_input("Why 3", value="Deeper cause?", key=f"w3_{cat}")
            w4 = st.text_input("Why 4", value="Why did that happen?", key=f"w4_{cat}")
            w5 = st.text_input("Why 5 (root cause)", value="Root cause", key=f"w5_{cat}")
            temp_action = st.text_input("Temporary Action", value="Immediate containment", key=f"temp_{cat}")
            perm_action = st.text_input("Permanent Action", value="Implement PM / SOP", key=f"perm_{cat}")
            owner = st.text_input("Action Owner", value="Rajesh", key=f"owner_{cat}")
            due = st.date_input("Target Date", value=datetime.today()+timedelta(days=7), key=f"due_{cat}")
            if st.button(f"Save 5-Why for {top_reason}", key=f"save_{cat}"):
                st.success("Saved (demo only). In production this saves to DB and triggers alerts.")

# --- Monthly A3 ---
with tabs[2]:
    st.header("Monthly A3 (Separate) — 4-week aggregated view")
    all_weeks = sorted(list(set(losses_df["Week"])), key=lambda w: (int(w.split("-")[1]) if "-" in w else 0, int(w.split("-")[0].replace("W","") if "W" in w else 0)))
    last4 = all_weeks[-4:] if len(all_weeks)>=4 else all_weeks
    st.write(f"Aggregated weeks: {', '.join(last4)}")
    df_4wk = losses_df[losses_df["Week"].isin(last4)]
    if df_4wk.empty:
        st.info("Not enough data for monthly aggregation.")
    else:
        agg = df_4wk.groupby("Department", as_index=False)["Loss Minutes"].sum().sort_values("Loss Minutes", ascending=False)
        agg["Pct"] = (agg["Loss Minutes"]/agg["Loss Minutes"].sum()*100).round(2)
        st.plotly_chart(px.bar(agg, x="Department", y="Loss Minutes", title="4-week Aggregated Level-1 Pareto"), use_container_width=True)
        top = agg.iloc[0]
        st.markdown("**A3 Summary (Auto-suggest)**")
        st.write(f"- Top Department: {top['Department']} ({top['Loss Minutes']} mins, {top['Pct']}%)")
        st.write("- Suggested focus: Perform 5-Why and implement permanent actions for top reasons.")

# --- Action Tracker ---
with tabs[3]:
    st.header("Action Tracker & Alerts")
    lvl2_demo = df_latest.groupby(["Department","Reason"], as_index=False)["Loss Minutes"].sum().sort_values("Loss Minutes", ascending=False)
    actions = st.session_state.get("actions_demo", None)
    if actions is None:
        actions = []
        for i, r in lvl2_demo.head(6).iterrows():
            actions.append({"Department": r["Department"], "Reason": r["Reason"], "Owner":"", "Target":(datetime.today()+timedelta(days=7)).strftime("%Y-%m-%d"), "Type":"Temporary", "Status":"Not Started"})
        st.session_state["actions_demo"] = actions
    actions_df = pd.DataFrame(st.session_state["actions_demo"])
    st.dataframe(actions_df)
    st.markdown("Add / Update action (demo session-only)")
    with st.form("action_form"):
        dept = st.text_input("Department", value="Maintenance")
        reason = st.text_input("Reason", value="Chiller breakdown")
        owner = st.text_input("Owner", value="Rajesh")
        target = st.date_input("Target Date", value=datetime.today()+timedelta(days=3))
        a_type = st.selectbox("Action Type", options=["Temporary","Permanent"])
        submitted = st.form_submit_button("Add Action")
        if submitted:
            new = {"Department":dept, "Reason":reason, "Owner":owner, "Target":target.strftime("%Y-%m-%d"), "Type":a_type, "Status":"Not Started"}
            actions_df = pd.concat([actions_df, pd.DataFrame([new])], ignore_index=True)
            st.session_state["actions_demo"] = actions_df.to_dict(orient="records")
            st.success("Added action to demo tracker (session-only).")

    st.markdown("Simulated Alerts")
    alerts = []
    for idx, a in actions_df.head(20).iterrows():
        try:
            td = datetime.strptime(str(a["Target"]), "%Y-%m-%d")
        except:
            td = datetime.today()+timedelta(days=7)
        days_left = (td - datetime.today()).days
        if a["Status"] != "Completed" and days_left <= 2 and days_left >= 0:
            alerts.append({"type":"due_soon","message":f"Action '{a['Reason']}' assigned to {a['Owner'] or 'Unassigned'} is due in {days_left} day(s)."})
        if a["Status"] != "Completed" and days_left < 0:
            overdue = abs(days_left); escalate = overdue > 1
            alerts.append({"type":"overdue","message":f"Action '{a['Reason']}' is OVERDUE by {overdue} day(s). Escalate: {escalate}", "escalate": escalate})
    if alerts:
        for a in alerts:
            if a.get("escalate"):
                st.error(a["message"])
            else:
                st.warning(a["message"])
    else:
        st.success("No immediate alerts.")

    csv = actions_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Action Tracker CSV", data=csv, file_name="action_tracker.csv", mime="text/csv")

# Footer
st.markdown("---")
st.caption("Demo prototype: session-only persistence. For production, persist to DB and add authentication & notification workers.")
