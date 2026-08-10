"""Production audit behavior and CI wiring."""

from __future__ import annotations

import json
from pathlib import Path

from utils.production_audit import (MAX_CRON_SERVICES, _check_network_timeouts,
                                    run_production_audit)


DASHBOARD = Path(__file__).resolve().parent.parent
WORKFLOW = DASHBOARD.parent / ".github" / "workflows" / "quality-gate.yml"


def test_current_repository_passes_production_audit():
    report = run_production_audit(DASHBOARD)
    assert report.ok, report.to_json()
    assert report.checks["routes"]["active_routes"] >= 25
    # Reference the constant rather than repeating the number. This literal was
    # a third copy of the budget — the audit module, test_cron_cost_controls and
    # here — so adding one cron meant three separate edits and two red tests
    # before anyone noticed the duplication.
    assert report.checks["blueprint"]["cron_services"] <= MAX_CRON_SERVICES
    assert report.checks["network_bounds"]["external_calls_checked"] > 0
    assert report.checks["network_bounds"]["max_timeout_seconds"] <= 30
    assert report.checks["cache_bounds"]["provider_caches_checked"] > 0
    assert report.checks["provider_health"]["advertised_providers"] >= 10


def test_audit_json_is_machine_readable():
    payload = json.loads(run_production_audit(DASHBOARD).to_json())
    assert payload["ok"] is True
    assert payload["findings"] == []
    assert set(payload["checks"]) == {
        "routes", "blueprint", "network_bounds", "cache_bounds", "provider_health",
    }


def test_network_audit_rejects_unbounded_external_calls(tmp_path):
    utils = tmp_path / "utils"
    utils.mkdir()
    bad = utils / "bad_provider.py"
    bad.write_text(
        "import requests\n"
        "def fetch():\n"
        "    return requests.get('https://example.com')\n",
        encoding="utf-8",
    )
    findings, summary = _check_network_timeouts(tmp_path)
    assert summary["status"] == "fail"
    assert len(findings) == 1
    assert findings[0].line == 3
    assert "no explicit timeout" in findings[0].message


def test_network_audit_rejects_timeout_over_budget(tmp_path):
    utils = tmp_path / "utils"
    utils.mkdir()
    bad = utils / "slow_provider.py"
    bad.write_text(
        "import requests\n"
        "def fetch():\n"
        "    return requests.get('https://example.com', timeout=60)\n",
        encoding="utf-8",
    )
    findings, summary = _check_network_timeouts(tmp_path)
    assert summary["status"] == "fail"
    assert summary["max_timeout_seconds"] == 60
    assert "exceeds 30s budget" in findings[0].message


def test_quality_gate_runs_production_audit_before_regressions():
    source = WORKFLOW.read_text(encoding="utf-8")
    audit = "python scripts/production_audit.py --json"
    regression = "python -m pytest -q"
    assert audit in source
    assert source.index(audit) < source.index(regression)
