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

### Step 3 — Set up a hosted database (required for accounts)

Streamlit Community Cloud's filesystem is **not** persistent across redeploys/restarts —
every account, watchlist, and alert would vanish the next time the app restarts if it lived
on local disk there. A free hosted Postgres database fixes this. [Neon](https://neon.tech)
and [Supabase](https://supabase.com) both have generous free tiers; either works the same way:

1. Create an account at your chosen provider (this is a step only you can do — account
   creation isn't something this assistant can do on your behalf).
2. Create a new Postgres project/database.
3. Copy the connection string it gives you (looks like
   `postgresql://user:password@host/dbname`).

### Step 4 — Set up email verification (optional, but recommended)

New accounts get a 6-digit code emailed via [Resend](https://resend.com) before they can log
in. Without this configured, signup still works but the verification email silently fails to
send (the app tells the user this and lets them retry once it's fixed) — meaning nobody can
actually finish signing up. To enable real verification emails:

1. Create a free Resend account (3,000 emails/month free tier).
2. Get your API key from the Resend dashboard.
3. For real signups (not just testing), verify a sending domain in Resend and use an address
   on that domain as `RESEND_FROM_EMAIL` below — Resend's default test sender
   (`onboarding@resend.dev`) only delivers to the email address on your own Resend account,
   not to arbitrary recipients. This works regardless of where the app itself is hosted —
   if you're also buying a domain for the custom-domain migration below, the same domain
   covers both:
   - In Resend: **Domains → Add Domain**, enter the domain (or a subdomain like
     `mail.yourdomain.com`).
   - Resend shows you the DKIM/SPF/DMARC DNS records to add.
   - Add those records at your registrar (same place you'll add the Render CNAME, if you're
     doing that migration too).
   - Click **Check DNS** in Resend's dashboard. Propagation can take up to 24 hours; status
     goes `not_started` → `pending` → `verified`.
   - Once verified, set `RESEND_FROM_EMAIL` to an address on that domain, e.g.
     `Unstructured Alpha <noreply@yourdomain.com>`.

### Step 5 — Add secrets

In Streamlit Cloud dashboard → **⋮ Settings → Secrets**:

```toml
DATABASE_URL = "postgresql://user:password@host/dbname"
RESEND_API_KEY = "re_your_key_here"
RESEND_FROM_EMAIL = "Unstructured Alpha <noreply@yourdomain.com>"

FRED_API_KEY = "your_key_here"
EIA_API_KEY = "your_key_here"
```

Get a free FRED API key at: https://fred.stlouisfed.org/docs/api/api_key.html
Get a free EIA API key at: https://www.eia.gov/opendata/register.php
(Both take about 2 minutes, completely free, no credit card)

Locally, none of these are required — the app falls back to a local SQLite database (for
accounts/watchlists). FRED/EIA-backed signals are marked unavailable and excluded when
their keys are not set; the application does not generate demo observations.

---

## Custom Domain — Requires Migrating Off Streamlit Cloud

**Correction, checked directly against Streamlit's current docs and community threads
(2026-06-21):** Streamlit Community Cloud's free tier does **not** support a fully custom
domain like `unstructuredalpha.com`. It only lets you customize the subdomain slug under
`streamlit.app` (e.g. `unstructured-alpha.streamlit.app`, which this app already has). A
real custom domain for the whole app requires either Streamlit's enterprise Snowflake
offering (a different product, requires a Snowflake account — not a fit for this project's
scale) or moving hosting elsewhere. The earlier version of this doc claimed otherwise; that
was wrong.

### Recommended target: Render

Render is the best fit for this app specifically: a genuine free tier, 2 free custom domains
included per workspace, and no Docker/system-dependency work needed (verified — `psycopg2-binary`
ships precompiled wheels, so nothing beyond `requirements.txt` is required at build time).
Pricing, checked live against Render's pricing page (2026-06-21):

| Plan | Cost | Behavior |
|---|---|---|
| Free (Hobby) | $0 | Spins down after 15 min idle; ~1 min cold start on the next visit (Streamlit Cloud's free tier already does something similar) |
| Starter | $7/month per service | Always-on, no cold start, 512MB RAM / 0.5 CPU |

Custom domains: 2 included free on a Hobby workspace, additional domains $0.25/month each.

### Step 1 — Buy a domain

From Namecheap or Cloudflare, ~$10–15/year. This one domain covers **both** the app's new
URL and the Resend sending domain below — buy once, use for both.

### Step 2 — Deploy to Render

This repo already has a `render.yaml` blueprint checked in.

1. Go to [render.com](https://render.com) and sign in with GitHub (account creation is a
   step only you can do).
2. Click **New +** → **Blueprint**, select the `unstructured-alpha-dashboard` repo.
3. Render reads `render.yaml` automatically and shows the `unstructured-alpha` web service.
4. It will prompt you to fill in the env vars listed there (`DATABASE_URL`, `RESEND_API_KEY`,
   `RESEND_FROM_EMAIL`, `FRED_API_KEY`, `EIA_API_KEY`) — same values as your
   `.streamlit/secrets.toml` today. Your existing Neon database doesn't need to move; Render
   just connects to it the same way Streamlit Cloud did.
5. Deploy. You'll get a `https://unstructured-alpha.onrender.com`-style URL first — confirm
   the app actually works there before touching DNS.

### Step 3 — Point your domain at Render

1. In the Render dashboard, open the service → **Settings → Custom Domains** → add your
   domain.
2. Render shows you the exact DNS record to add (typically a CNAME for a subdomain like
   `app.yourdomain.com`, or an A/ALIAS record for the bare domain).
3. Add that record at your registrar (Namecheap/Cloudflare). Propagation can take up to a
   few hours.
4. Render auto-provisions a TLS certificate once the DNS record resolves — no separate
   certificate step.

### Step 4 — Decide what happens to the Streamlit Cloud app

Once the Render version is confirmed working on the new domain, you can either leave the
Streamlit Cloud deployment running as a backup (it's free) or delete it. Nothing about this
migration requires deleting it immediately.

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
| Hosted Postgres (Neon/Supabase, accounts) | **Free** tier (low usage) |
| Resend (verification emails) | **Free** tier (3,000/mo) |
| **Total, staying on Streamlit Cloud (no custom domain)** | **~$0/year** |

If migrating to Render for a real custom domain (see above):

| Component | Cost |
|---|---|
| Render hosting | **Free** (cold starts) or **$7/month** (always-on) |
| Domain (covers both Render + Resend) | ~$10–15/year |
| **Total, on Render with custom domain** | **~$10–15/year** (free hosting) or **~$94–99/year** (always-on) |
