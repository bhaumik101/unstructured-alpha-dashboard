"""Customers' email addresses stay out of the logs.

Render logs are kept and readable by anyone with dashboard access. The email
module and the digest used to print every recipient in full (Nov 2026: the
digest log named each customer it mailed). They now print a masked form that
still tells two recipients apart.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.email import mask_email

ROOT = Path(__file__).resolve().parents[1]


def test_the_mask_keeps_the_domain_and_hides_the_person():
    assert mask_email("ann.smith@example.com") == "a***@example.com"
    assert mask_email("") == "***" and mask_email(None) == "***" and mask_email("nonsense") == "***"


def test_no_log_line_prints_a_recipient_in_full():
    for rel in ("utils/email.py", "cron/send_digest.py", "cron/send_exposure_weekly.py", "utils/public_weekly.py",
                "seo/subscribe_api.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        for line in src.splitlines():
            if "print(" in line or "logger." in line:
                bare = re.findall(r"\{(to_email|email_addr|admin_email|email)(?:!r)?\}", line)
                assert not bare, f"{rel}: {line.strip()}"
