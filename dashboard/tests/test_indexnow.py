"""IndexNow: announcing the weekly re-measured pages to search engines.

What must hold:
  * the key file the engines fetch is served from the landing's public/
    folder and holds exactly the key we submit with;
  * only our own host's URLs, from our own sitemap, are ever submitted;
  * a refusal or an unreadable sitemap is a failed run, not a silent pass;
  * it runs after the library is re-measured, so announced pages are fresh.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils import indexnow as ix

WEB = Path(__file__).resolve().parents[1] / "unstructured-alpha-web"

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.unstructuredalpha.com/</loc></url>
<url><loc>https://www.unstructuredalpha.com/exposure/XOM</loc></url>
<url><loc>https://www.unstructuredalpha.com/exposure/XOM</loc></url>
<url><loc>https://evil.example/exposure/XOM</loc></url>
<url><loc>https://www.unstructuredalpha.com.evil.example/x</loc></url>
</urlset>"""


def test_the_key_file_is_served_and_matches():
    assert re.fullmatch(r"[0-9a-f]{32}", ix.KEY)
    f = WEB / "public" / f"{ix.KEY}.txt"
    assert f.is_file() and f.read_text() == ix.KEY
    assert ix.KEY_LOCATION == f"https://{ix.HOST}/{ix.KEY}.txt"


def test_only_our_own_urls_are_taken_once_each():
    assert ix.urls_from_sitemap(SITEMAP) == ["https://www.unstructuredalpha.com/",
                                            "https://www.unstructuredalpha.com/exposure/XOM"]


class _Resp:
    def __init__(self, code):
        self.status_code = code


def _run(code=202, xml=SITEMAP, fail_fetch=False):
    import cron.ping_indexnow as job
    posted = []

    def fetch(url):
        assert url == ix.SITEMAP
        if fail_fetch:
            raise OSError("down")
        return xml

    def post(url, json, timeout, headers):
        posted.append((url, json))
        return _Resp(code)
    return job.main(fetch=fetch, post=post), posted


def test_an_accepted_submission_names_our_host_key_and_pages():
    rc, posted = _run(202)
    assert rc == 0 and len(posted) == 1
    url, body = posted[0]
    assert url == "https://api.indexnow.org/indexnow"
    assert body == {"host": ix.HOST, "key": ix.KEY, "keyLocation": ix.KEY_LOCATION,
                    "urlList": ["https://www.unstructuredalpha.com/", "https://www.unstructuredalpha.com/exposure/XOM"]}


def test_a_refusal_or_a_missing_sitemap_is_a_failed_run():
    assert _run(403)[0] == 1
    rc, posted = _run(fail_fetch=True)
    assert rc == 1 and posted == []
    rc, posted = _run(xml="<urlset></urlset>")
    assert rc == 1 and posted == []


def test_it_runs_after_the_library_is_re_measured():
    from cron.run_group import GROUPS
    g = GROUPS["weekly-universe"]
    assert g.index("cron.ping_indexnow") > g.index("cron.measure_library")
