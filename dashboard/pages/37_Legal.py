# pages/37_Legal.py
# Unstructured Alpha — Privacy Policy & Terms of Service
#
# Combined legal page. Keeps everything in one place rather than two separate
# pages that are harder to navigate. Covers:
#   - Privacy Policy (GDPR / CCPA compliant for a SaaS)
#   - Terms of Service (no investment advice disclaimer, subscription terms,
#     acceptable use, IP, account termination, dispute resolution)
#   - Refund Policy (Stripe 30-day policy)
#
# Keep this page in plain, readable English. Legalese reduces trust.

import streamlit as st

st.set_page_config(
    page_title="Privacy & Terms — Unstructured Alpha",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css

render_header("Legal")
_legal_section = render_sidebar_base(
    page_title="Privacy & Terms",
    sections=("Privacy Policy", "Terms of Service", "Refund Policy"),
    section_key="legal_section_rail",
)
inject_premium_css()

render_page_header(
    "Privacy & Terms",
    "What we collect, how we use it, and the rules of the road.",
    icon="",
)

# ── Privacy Policy ────────────────────────────────────────────────────────────
if _legal_section == "Privacy Policy":
    st.markdown("""
<div style="font-family:Inter,sans-serif;color:#C5CCDE;line-height:1.75;max-width:800px;">

<p style="font-size:0.78rem;color:#8892AA;">Last updated: July 7, 2026 &nbsp;·&nbsp; Unstructured Alpha</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">What we collect</h3>
<p>
When you create an account, we store your <strong>email address</strong> and a
<strong>salted hash of your password</strong> — we never store your password in plain text.
We also record your subscription tier, email verification status, and the timestamps of
account creation and most recent login.
</p>
<p>
If you subscribe to Pro, Stripe processes your payment. We receive only a Stripe customer ID
and subscription status — not your card number, bank details, or billing address.
</p>
<p>
When you use the platform, our hosting provider (Render) may retain standard web server logs
including IP addresses, browser type, and page-request timestamps for up to 30 days. We do
not store or process these logs ourselves beyond what Render retains operationally.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">What we don't collect</h3>
<p>
We do not use tracking cookies, ad pixels, or behavioral analytics. We do not sell or share
your data with third parties for marketing purposes. We do not collect your real name, phone
number, or mailing address. We do not collect financial account numbers or trading history.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Why we collect it</h3>
<p>
Your email is used to: (1) identify your account and restore sessions, (2) send transactional
messages you have requested (verification codes, digest emails, price alerts), and (3) notify
you of material changes to these policies. We do not send marketing emails unless you
explicitly opt in.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Legal basis for processing (GDPR)</h3>
<p>
For users in the European Economic Area, our legal bases for processing personal data are:
<strong>contract performance</strong> (to provide the account and subscription you signed up for),
<strong>legitimate interests</strong> (security, fraud prevention, service reliability), and
<strong>consent</strong> (for optional digest emails and alerts, which you can withdraw at any time).
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Cookies</h3>
<p>
We set one first-party cookie (<code>ua_remember</code>) only when you check "Remember me"
at login. This cookie stores a secure session token — not your password — and expires after
30 days. It is used solely to restore your session without requiring a new login. You can
delete it at any time by logging out. We do not set any advertising, analytics, or third-party
cookies.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Third-party services</h3>
<p>
We use <strong>Resend</strong> to send transactional emails (verification codes, digests, alerts).
We use <strong>Stripe</strong> for payment processing. We use <strong>Render</strong> to host
the application and database. Each operates under its own privacy policy and data processing
agreements. We do not share your email with any of these parties beyond what is required to
deliver the service you requested.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Data residency</h3>
<p>
Your data is stored on servers located in the United States. If you are accessing the service
from outside the US, your data will be transferred to and processed in the US. By using the
service, you consent to this transfer.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Data retention</h3>
<p>
Account data is retained for as long as your account is active. You can request deletion at
any time by emailing <a href="mailto:privacy@unstructuredalpha.com" style="color:#00C8E0;">privacy@unstructuredalpha.com</a>.
We will delete your account, email address, and all associated watchlist, alert, and digest
data within 7 business days of receiving a verified deletion request. Stripe may retain
billing records independently in accordance with their legal obligations.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Your rights</h3>
<p>
Under GDPR and CCPA, you have the right to:
</p>
<ul style="color:#C5CCDE;margin-top:4px;">
<li><strong>Access</strong> — request a copy of the personal data we hold about you</li>
<li><strong>Correct</strong> — ask us to fix inaccurate data</li>
<li><strong>Export</strong> — receive your data in a portable format</li>
<li><strong>Delete</strong> — request erasure of your account and associated data</li>
<li><strong>Restrict</strong> — ask us to limit processing of your data while a dispute is resolved</li>
<li><strong>Object</strong> — object to processing based on legitimate interests</li>
<li><strong>Withdraw consent</strong> — opt out of digest emails or alerts at any time from your profile settings</li>
</ul>
<p>
To exercise any of these rights, contact
<a href="mailto:privacy@unstructuredalpha.com" style="color:#00C8E0;">privacy@unstructuredalpha.com</a>.
GDPR users also have the right to lodge a complaint with a supervisory authority in their
country of residence.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Age restriction</h3>
<p>
Unstructured Alpha is intended for users 13 years of age and older. If you are under 13,
do not create an account. If we become aware that a user under 13 has created an account,
we will delete it promptly.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Changes to this policy</h3>
<p>
If we make material changes, we'll send an email to your registered address at least 14 days
before the change takes effect. Non-material changes (such as formatting or clarifications)
may be made without prior notice. The "Last updated" date at the top of this page always
reflects the current version.
</p>

<p style="margin-top:24px;">
Questions? Email <a href="mailto:privacy@unstructuredalpha.com" style="color:#00C8E0;">privacy@unstructuredalpha.com</a>.
</p>

</div>
""", unsafe_allow_html=True)

# ── Terms of Service ──────────────────────────────────────────────────────────
if _legal_section == "Terms of Service":
    st.markdown("""
<div style="font-family:Inter,sans-serif;color:#C5CCDE;line-height:1.75;max-width:800px;">

<p style="font-size:0.78rem;color:#8892AA;">Last updated: July 7, 2026 &nbsp;·&nbsp; Unstructured Alpha</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">1. Not financial advice</h3>
<p>
<strong style="color:#FF4D6A;">Unstructured Alpha is a research and signal intelligence tool,
not a registered investment adviser.</strong> Nothing on this platform constitutes investment
advice, a recommendation to buy or sell any security, a solicitation to invest, or a
guarantee of any financial outcome. Confluence Scores, signal analyses, macro indicators,
sector percentile rankings, and AI-generated summaries are informational tools only.
</p>
<p>
Past signal performance does not guarantee future results. Markets can and do move against
any indicator. <strong>You are solely responsible for your own investment decisions.</strong>
You should consult a licensed financial adviser before making investment decisions.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">2. Eligibility and accounts</h3>
<p>
By creating an account, you confirm that you are at least 13 years old and have the legal
capacity to enter into this agreement. You are responsible for maintaining the confidentiality
of your login credentials. Notify us immediately at
<a href="mailto:support@unstructuredalpha.com" style="color:#00C8E0;">support@unstructuredalpha.com</a>
if you believe your account has been compromised. One account per person; sharing accounts
or credentials is not permitted.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">3. Acceptable use</h3>
<p>
You agree to use Unstructured Alpha for lawful purposes only. Prohibited conduct includes:
</p>
<ul style="color:#C5CCDE;margin-top:4px;">
<li>Scraping, crawling, or automated bulk retrieval of data from the platform</li>
<li>Redistributing, reselling, or sublicensing any data, signals, or content from the platform</li>
<li>Attempting to reverse-engineer, decompile, or access the platform's source code</li>
<li>Overloading, disrupting, or attacking the service or its infrastructure</li>
<li>Circumventing or attempting to circumvent authentication, access controls, or paywalls</li>
<li>Using the platform in any manner that violates applicable law or regulation</li>
</ul>
<p>
We reserve the right to terminate accounts that violate these restrictions without refund.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">4. Intellectual property</h3>
<p>
The Unstructured Alpha platform, including its design, signals, scoring methodology,
AI-generated content, and software, is owned by Unstructured Alpha and protected by
copyright and other intellectual property laws. Your subscription grants you a personal,
non-transferable license to access and use the platform for your own informational purposes.
</p>
<p>
Your account data (watchlist tickers, alert settings, digest preferences) remains yours. We
do not claim ownership of any data you input into the platform.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">5. Pro subscription and billing</h3>
<p>
Pro subscriptions are billed monthly or annually via Stripe. Prices are displayed in USD on
the Upgrade page. We reserve the right to change pricing with at least 30 days' written
notice to current subscribers; price changes will not affect you until your next renewal.
</p>
<p>
Trials begin on the date you start checkout; you will not be charged until the trial period
ends. You can cancel at any time from your profile page and access will continue until the
end of the current billing period. Cancellation stops future charges; it does not erase your
account or data.
</p>
<p>
Annual subscriptions are billed upfront for the full year. If you cancel an annual
subscription within 30 days, you are eligible for a full refund (see Refund Policy).
After 30 days, the annual period is non-refundable.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">6. Data accuracy and sources</h3>
<p>
Signal data is sourced from FRED (Federal Reserve Bank of St. Louis), SEC EDGAR, FINRA, EIA,
and public market data feeds. We make no warranties — express or implied — about the accuracy,
completeness, or timeliness of this data. Some signals may lag official publication dates by
hours or days. Data quality warnings are displayed when a signal has insufficient history or
falls below our standard threshold. You should independently verify any data before relying
on it for financial decisions.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">7. Service availability and changes</h3>
<p>
We strive for high availability but do not guarantee uninterrupted access. We may modify,
suspend, or discontinue features or the service as a whole at any time. If we discontinue
a material feature included in your Pro plan, we will notify you by email and offer a
prorated refund for the affected period.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">8. Account termination</h3>
<p>
You may close your account at any time by emailing
<a href="mailto:support@unstructuredalpha.com" style="color:#00C8E0;">support@unstructuredalpha.com</a>.
We may suspend or terminate your account, with or without notice, for violations of these
terms, suspected fraud, abuse, or conduct we reasonably determine to be harmful to the
service or other users. Terminated accounts are not entitled to refunds beyond what is
provided in our Refund Policy.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">9. Disclaimer of warranties</h3>
<p>
The service is provided "as is" and "as available" without warranties of any kind, express
or implied, including but not limited to merchantability, fitness for a particular purpose,
or non-infringement. We do not warrant that the service will be error-free, uninterrupted,
or that signals or scores will meet your expectations or produce any particular financial
outcome.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">10. Limitation of liability</h3>
<p>
To the maximum extent permitted by applicable law, Unstructured Alpha shall not be liable
for any investment losses, financial damages, indirect, incidental, special, or consequential
damages arising from your use of — or inability to use — this platform. Our total liability
to you for any claim arising out of or related to these terms or the service is limited to the
amount you paid us in the 12 months preceding the claim.
</p>
<p>
Your sole remedy for dissatisfaction with the service is to cancel your subscription and
request a refund under our Refund Policy.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">11. Dispute resolution</h3>
<p>
We prefer to resolve disputes informally. If you have a concern, email
<a href="mailto:legal@unstructuredalpha.com" style="color:#00C8E0;">legal@unstructuredalpha.com</a>
and we will respond within 5 business days. If informal resolution fails, disputes will be
resolved by binding arbitration under the rules of the American Arbitration Association
(AAA), conducted in English. You waive any right to participate in a class action lawsuit
or class-wide arbitration against Unstructured Alpha.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">12. Governing law</h3>
<p>
These terms are governed by the laws of the State of Delaware, United States, without regard
to conflict of law principles. Any dispute not subject to arbitration will be resolved
exclusively in the courts of Delaware.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">13. Changes to these terms</h3>
<p>
We may update these terms from time to time. Material changes will be communicated by email
at least 14 days before they take effect. Continued use of the service after the effective
date constitutes acceptance of the updated terms.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">14. Contact</h3>
<p>
Questions about these terms:
<a href="mailto:legal@unstructuredalpha.com" style="color:#00C8E0;">legal@unstructuredalpha.com</a>
</p>

</div>
""", unsafe_allow_html=True)

# ── Refund Policy ─────────────────────────────────────────────────────────────
if _legal_section == "Refund Policy":
    st.markdown("""
<div style="font-family:Inter,sans-serif;color:#C5CCDE;line-height:1.75;max-width:800px;">

<p style="font-size:0.78rem;color:#8892AA;">Last updated: July 7, 2026 &nbsp;·&nbsp; Unstructured Alpha</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">30-day money-back guarantee</h3>
<p>
If you are not satisfied with Pro for any reason within the first 30 days of your initial
purchase, email <a href="mailto:support@unstructuredalpha.com" style="color:#00C8E0;">support@unstructuredalpha.com</a>
with the subject line "Refund Request" and we will issue a full refund within 5 business days.
No questions asked. The 30-day window begins on the date of your first charge (not the start
of any free trial).
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">After 30 days — monthly plans</h3>
<p>
After the 30-day window, monthly subscriptions are non-refundable for the current billing
period. You can cancel at any time and your Pro access will continue through the end of the
period you've already paid for. We do not issue partial-period refunds on monthly plans.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">After 30 days — annual plans</h3>
<p>
Annual subscriptions are non-refundable after the 30-day window. If you cancel an annual
plan after 30 days, your Pro access continues until the end of the annual period you paid
for, but no refund is issued. If you downgrade mid-year, no partial credit is applied to
future billing periods.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Trials</h3>
<p>
Free trials are not charged if cancelled before the trial period ends. If you are charged
after a trial due to a technical error on our end, contact us and we will refund the charge
within 2 business days, no verification required.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">Exceptional circumstances</h3>
<p>
If we discontinue a material feature included in your active Pro plan, or if the service
experiences extended downtime (more than 72 consecutive hours) during your billing period,
you may be eligible for a prorated refund for the affected period regardless of the 30-day
window. Contact us to discuss.
</p>

<h3 style="color:#E8EEFF;font-size:1.0rem;margin-top:24px;">How to request a refund</h3>
<p>
Email <a href="mailto:support@unstructuredalpha.com" style="color:#00C8E0;">support@unstructuredalpha.com</a>
from the email address associated with your account. Include "Refund Request" in the subject
line. We typically respond within 1 business day and process approved refunds within 5
business days. Refunds are returned to the original payment method via Stripe.
</p>

</div>
""", unsafe_allow_html=True)
