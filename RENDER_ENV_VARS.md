# Render Environment Variables — Setup Checklist

These must be set manually in the **Render dashboard** (Dashboard → Service → Environment).  
They are listed by name only in `render.yaml` (`sync: false`) — **values are never committed to git.**

---

## Web Service: `unstructured-alpha`

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | ✅ Yes | Postgres connection string. Render Postgres → "Connect" → "External Database URL". |
| `RESEND_API_KEY` | ✅ Yes | From [resend.com](https://resend.com) → API Keys. Used for all transactional email. |
| `RESEND_FROM_EMAIL` | ✅ Yes | Verified sender address, e.g. `alerts@unstructuredalpha.com`. Must be verified in Resend. |
| `FRED_API_KEY` | ✅ Yes | From [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html). Free. |
| `EIA_API_KEY` | ✅ Yes | From [eia.gov/opendata](https://www.eia.gov/opendata/register.php). Free. |
| `STRIPE_SECRET_KEY` | ✅ Yes | Stripe Dashboard → Developers → API keys → Secret key (`sk_live_…`). |
| `STRIPE_PRICE_ID` | ✅ Yes | Monthly Pro price ID from Stripe (`price_…`). |
| `STRIPE_ANNUAL_PRICE_ID` | ✅ Yes | Annual Pro price ID from Stripe (`price_…`). |
| `STRIPE_PUBLISHABLE_KEY` | ✅ Yes | Stripe publishable key (`pk_live_…`). Used on the Upgrade page. |
| `RENDER_EXTERNAL_URL` | ✅ Yes | The service's public URL, e.g. `https://unstructuredalpha.onrender.com`. Used to build referral links. Render does NOT set this automatically for web services — set it manually. |
| `ANTHROPIC_API_KEY` | ✅ Yes | From [console.anthropic.com](https://console.anthropic.com). Used for earnings transcript sentiment. |

---

## Cron: `unstructured-alpha-digest`

| Variable | Required |
|---|---|
| `DATABASE_URL` | ✅ |
| `RESEND_API_KEY` | ✅ |
| `RESEND_FROM_EMAIL` | ✅ |
| `FRED_API_KEY` | ✅ |
| `EIA_API_KEY` | ✅ |

---

## Cron: `unstructured-alpha-trial-reminder`

| Variable | Required |
|---|---|
| `DATABASE_URL` | ✅ |
| `RESEND_API_KEY` | ✅ |
| `RESEND_FROM_EMAIL` | ✅ |

---

## Cron: `unstructured-alpha-webhooks`

| Variable | Required |
|---|---|
| `DATABASE_URL` | ✅ |
| `FRED_API_KEY` | ✅ |
| `EIA_API_KEY` | ✅ |

---

## Cron: `unstructured-alpha-watchlist-alerts`

| Variable | Required |
|---|---|
| `DATABASE_URL` | ✅ |
| `RESEND_API_KEY` | ✅ |
| `RESEND_FROM_EMAIL` | ✅ |
| `FRED_API_KEY` | ✅ |
| `EIA_API_KEY` | ✅ |

---

## Cron: `unstructured-alpha-resolve-predictions`

| Variable | Required |
|---|---|
| `DATABASE_URL` | ✅ |
| `FRED_API_KEY` | ✅ |
| `EIA_API_KEY` | ✅ |

---

## Cron: `unstructured-alpha-tweet-flips`

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | ✅ | |
| `FRED_API_KEY` | ✅ | |
| `EIA_API_KEY` | ✅ | |
| `TWITTER_API_KEY` | ✅ | Twitter Developer Portal → App → Keys & Tokens → Consumer Keys. |
| `TWITTER_API_SECRET` | ✅ | Same location as above. |
| `TWITTER_ACCESS_TOKEN` | ✅ | Access Token (must be generated with write permission). |
| `TWITTER_ACCESS_TOKEN_SECRET` | ✅ | Same location as access token. |

---

## Notes

- **Stripe webhook secret** (`STRIPE_WEBHOOK_SECRET`) — if you're using Stripe webhooks for checkout success events, add this to the web service too. Check `utils/billing.py` for where it's consumed.
- **Render auto-deploys** from the Blueprint on every push to `main`. Env vars set in the dashboard persist across deploys and are never overwritten by `render.yaml`.
- All values are encrypted at rest by Render. Never paste them into `render.yaml` or any file that is committed to git.
