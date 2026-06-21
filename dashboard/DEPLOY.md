# Unstructured Alpha Dashboard — Deployment Guide

## Running Locally (First Test)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
streamlit run app.py
```

Opens at `http://localhost:8501` in your browser.

---

## Deploying as a Public Website (Streamlit Cloud — Free)

This is the fastest path to a live, public URL. **Free tier** supports unlimited public apps.

### Step 1 — Push to GitHub

```bash
# From the dashboard/ directory
git init
git add .
git commit -m "Initial Unstructured Alpha dashboard"

# Create a new repo on github.com (call it: unstructured-alpha-dashboard)
# Then:
git remote add origin https://github.com/YOUR_USERNAME/unstructured-alpha-dashboard.git
git push -u origin main
```

### Step 2 — Deploy on Streamlit Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub
2. Click **"New app"**
3. Select your repo: `unstructured-alpha-dashboard`
4. Set main file: `app.py`
5. Click **"Deploy"**

Your app will be live at:
```
https://YOUR_USERNAME-unstructured-alpha-dashboard-app-XXXX.streamlit.app
```

### Step 3 — Add API Keys (for real data)

In Streamlit Cloud dashboard → **⋮ Settings → Secrets**:

```toml
FRED_API_KEY = "your_key_here"
```

Get a free FRED API key at: https://fred.stlouisfed.org/docs/api/api_key.html
(Takes 2 minutes, completely free, no credit card)

---

## Custom Domain (Optional — makes it look professional)

Streamlit Cloud supports custom domains on all plans.

1. Buy a domain (e.g., `unstructuredalpha.com`) from Namecheap or Cloudflare (~$10/year)
2. In Streamlit Cloud: Settings → Custom domain → enter your domain
3. Add a CNAME record in your domain registrar pointing to Streamlit's URL

Result: `https://dashboard.unstructuredalpha.com`

---

## Password Protection (For Paid Subscribers)

To gate the dashboard behind a password for Substack subscribers:

### Option A: Streamlit built-in secrets check (simplest)

Add to `app.py` before any other content:

```python
import streamlit as st

def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input("Password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("Incorrect password")
    return False

if not check_password():
    st.stop()
```

Add to Streamlit Cloud secrets:
```toml
APP_PASSWORD = "your-subscriber-password"
```

### Option B: Individual subscriber tokens

For paid tier where each subscriber gets a unique token:
```python
VALID_TOKENS = set(st.secrets.get("subscriber_tokens", "").split(","))
token = st.text_input("Enter your access token:")
if token not in VALID_TOKENS:
    st.stop()
```

---

## Updating the App

Any push to the `main` branch auto-deploys to Streamlit Cloud. No manual action needed.

```bash
# Make changes locally, then:
git add .
git commit -m "Add new signal / update data"
git push origin main
# Streamlit Cloud redeploys automatically in ~30 seconds
```

---

## Data Refresh Schedule

| Data Source | Update Frequency | Streamlit Cache TTL |
|---|---|---|
| FRED (trucking, rail, jobless claims) | Weekly/Monthly | 1 hour |
| yfinance (stock/commodity prices) | Daily | 30 min |
| CFTC COT | Weekly (Friday) | 24 hours |
| USASpending.gov (federal contracts) | Real-time | 2 hours |
| SEC EDGAR (insider trades) | Within 48h of filing | 1 hour |
| arXiv paper velocity | Daily | 24 hours |
| EIA (crude inventories, gas storage) | Weekly | 1 hour |
| openFDA (drug approvals) | Real-time | 24 hours |
| FINRA (short interest, exchange-listed) | Bi-monthly (~2-3wk publish lag) | 12 hours |

Data is **cached** using `@st.cache_data` with these TTLs — the app won't re-fetch on every page load.
Users can force a refresh by pressing Ctrl+R.

---

## Embedding in Substack / Ghost

You can embed the dashboard in a newsletter post using an iframe.
Most hosted newsletter platforms support iframe embeds in posts.

```html
<iframe
  src="https://YOUR_APP.streamlit.app"
  width="100%"
  height="900"
  frameborder="0"
  allow="fullscreen">
</iframe>
```

Or just link to it: *"Access the live dashboard at dashboard.unstructuredalpha.com →"*

---

## Cost

| Component | Cost |
|---|---|
| Streamlit Cloud (app hosting) | **Free** |
| FRED API key | **Free** |
| yfinance | **Free** |
| CFTC data | **Free** |
| USASpending.gov API | **Free** |
| SEC EDGAR | **Free** |
| arXiv API | **Free** |
| EIA API key | **Free** |
| openFDA | **Free** |
| FINRA API | **Free** |
| Custom domain | ~$10–15/year |
| **Total** | **~$0–15/year** |
