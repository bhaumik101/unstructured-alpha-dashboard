"""Offline production-readiness audit for deploy-critical contracts.

The regular regression suite proves application behavior.  This module covers
the operational seams that are otherwise easy to review separately and forget:
route registration, Render configuration, cron cost bounds, external-call
timeouts, and bounded Streamlit caches.

The audit is deliberately static and network-free so it is deterministic in CI
and safe to run before every deployment.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Iterable

import yaml


MIN_ACTIVE_ROUTES = 25
MAX_CRON_SERVICES = 13
MAX_SCORE_RSS_MB = 512
MAX_EXTERNAL_TIMEOUT_SECONDS = 30

REQUIRED_WEB_ENV = {
    "DATABASE_URL",
    "REDIS_URL",
    "RESEND_API_KEY",
    "FRED_API_KEY",
    "EIA_API_KEY",
}
REQUIRED_SCORE_ENV = {
    "DATABASE_URL",
    "FRED_API_KEY",
    "EIA_API_KEY",
    "SCORE_MAX_RSS_MB",
}


@dataclass(frozen=True)
class AuditFinding:
    check: str
    message: str
    file: str = ""
    line: int | None = None


@dataclass(frozen=True)
class AuditReport:
    ok: bool
    checks: dict[str, dict[str, int | str]]
    findings: tuple[AuditFinding, ...]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": self.checks,
            "findings": [asdict(item) for item in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _finding(check: str, message: str, path: Path | None = None, line: int | None = None) -> AuditFinding:
    return AuditFinding(
        check=check,
        message=message,
        file=str(path) if path else "",
        line=line,
    )


def _env_keys(service: dict) -> set[str]:
    return {
        str(row.get("key", "")).strip()
        for row in service.get("envVars", [])
        if isinstance(row, dict)
    }


def _check_routes(root: Path) -> tuple[list[AuditFinding], dict[str, int | str]]:
    path = root / "app.py"
    source = path.read_text(encoding="utf-8")
    routes = re.findall(
        r'st\.Page\(\s*["\'](?P<file>pages/[^"\']+\.py)["\'](?P<args>.*?)\)',
        source,
        flags=re.DOTALL,
    )
    findings: list[AuditFinding] = []
    files = [file_name for file_name, _args in routes]
    url_paths = [
        match
        for _file_name, args in routes
        for match in re.findall(r'url_path\s*=\s*["\']([^"\']+)["\']', args)
    ]

    if len(routes) < MIN_ACTIVE_ROUTES:
        findings.append(_finding(
            "routes",
            f"only {len(routes)} active routes were detected; expected at least {MIN_ACTIVE_ROUTES}",
            path,
        ))
    for file_name in files:
        if not (root / file_name).is_file():
            findings.append(_finding("routes", f"registered page does not exist: {file_name}", path))
    duplicate_files = sorted({name for name in files if files.count(name) > 1})
    duplicate_urls = sorted({name for name in url_paths if url_paths.count(name) > 1})
    if duplicate_files:
        findings.append(_finding("routes", f"duplicate routed page files: {', '.join(duplicate_files)}", path))
    if duplicate_urls:
        findings.append(_finding("routes", f"duplicate URL paths: {', '.join(duplicate_urls)}", path))

    return findings, {
        "status": "pass" if not findings else "fail",
        "active_routes": len(routes),
        "unique_url_paths": len(set(url_paths)),
    }


def _check_blueprint(root: Path) -> tuple[list[AuditFinding], dict[str, int | str]]:
    path = root / "render.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    services = payload.get("services") or []
    findings: list[AuditFinding] = []

    names = [str(service.get("name", "")) for service in services]
    duplicates = sorted({name for name in names if name and names.count(name) > 1})
    if duplicates:
        findings.append(_finding("blueprint", f"duplicate service names: {', '.join(duplicates)}", path))

    web = next((service for service in services if service.get("name") == "unstructured-alpha"), None)
    if not web:
        findings.append(_finding("blueprint", "primary web service is missing", path))
    else:
        if web.get("healthCheckPath") != "/_stcore/health":
            findings.append(_finding("blueprint", "web liveness path must be /_stcore/health", path))
        missing = sorted(REQUIRED_WEB_ENV - _env_keys(web))
        if missing:
            findings.append(_finding("blueprint", f"web service is missing env declarations: {', '.join(missing)}", path))

    crons = [service for service in services if service.get("type") == "cron"]
    if len(crons) > MAX_CRON_SERVICES:
        findings.append(_finding(
            "cron_cost",
            f"{len(crons)} cron services exceed the cost budget of {MAX_CRON_SERVICES}",
            path,
        ))

    commands = [str(service.get("startCommand", "")).strip() for service in crons]
    duplicate_commands = sorted({cmd for cmd in commands if cmd and commands.count(cmd) > 1})
    if duplicate_commands:
        findings.append(_finding("cron_cost", f"duplicate cron commands: {', '.join(duplicate_commands)}", path))

    score_crons = [service for service in crons if "score_universe" in str(service.get("startCommand", ""))]
    for service in score_crons:
        name = str(service.get("name", "unnamed"))
        command = str(service.get("startCommand", ""))
        if "--budget " not in command or "--deadline-min " not in command:
            findings.append(_finding("cron_cost", f"{name} must declare item and runtime budgets", path))
        missing = sorted(REQUIRED_SCORE_ENV - _env_keys(service))
        if missing:
            findings.append(_finding("cron_cost", f"{name} is missing env declarations: {', '.join(missing)}", path))
        values = {
            str(row.get("key")): row.get("value")
            for row in service.get("envVars", [])
            if isinstance(row, dict)
        }
        try:
            rss_mb = int(values.get("SCORE_MAX_RSS_MB"))
        except (TypeError, ValueError):
            findings.append(_finding("cron_cost", f"{name} has no numeric SCORE_MAX_RSS_MB", path))
        else:
            if rss_mb > MAX_SCORE_RSS_MB:
                findings.append(_finding(
                    "cron_cost",
                    f"{name} memory budget {rss_mb}MB exceeds {MAX_SCORE_RSS_MB}MB",
                    path,
                ))

    return findings, {
        "status": "pass" if not findings else "fail",
        "services": len(services),
        "cron_services": len(crons),
        "score_crons": len(score_crons),
    }


def _python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for directory in paths:
        if not directory.exists():
            continue
        yield from sorted(
            path for path in directory.rglob("*.py")
            if "__pycache__" not in path.parts
        )


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return ""


def _timeout_seconds(value: ast.expr, defaults: dict[str, ast.expr]) -> float | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
        return float(value.value)
    if isinstance(value, ast.Name) and value.id in defaults:
        return _timeout_seconds(defaults[value.id], {})
    return None


class _NetworkCallVisitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.defaults: dict[str, ast.expr] = {}
        self.calls = 0
        self.max_timeout = 0.0
        self.findings: list[AuditFinding] = []
        self.call_names = {"requests.get", "requests.post", "resilient_get", "resilient_post"}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.defaults
        positional = list(node.args.posonlyargs) + list(node.args.args)
        default_names = positional[len(positional) - len(node.args.defaults):]
        self.defaults = {
            argument.arg: default
            for argument, default in zip(default_names, node.args.defaults)
        }
        self.defaults.update({
            argument.arg: default
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
            if default is not None
        })
        self.generic_visit(node)
        self.defaults = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in self.call_names:
            self.calls += 1
            timeout = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "timeout"),
                None,
            )
            if timeout is None:
                self.findings.append(_finding(
                    "network_bounds",
                    f"{name} has no explicit timeout",
                    self.path,
                    node.lineno,
                ))
            else:
                seconds = _timeout_seconds(timeout, self.defaults)
                if seconds is None:
                    self.findings.append(_finding(
                        "network_bounds",
                        f"{name} timeout is not statically bounded",
                        self.path,
                        node.lineno,
                    ))
                else:
                    self.max_timeout = max(self.max_timeout, seconds)
                    if seconds > MAX_EXTERNAL_TIMEOUT_SECONDS:
                        self.findings.append(_finding(
                            "network_bounds",
                            f"{name} timeout {seconds:g}s exceeds "
                            f"{MAX_EXTERNAL_TIMEOUT_SECONDS}s budget",
                            self.path,
                            node.lineno,
                        ))
        self.generic_visit(node)


def _check_network_timeouts(root: Path) -> tuple[list[AuditFinding], dict[str, int | float | str]]:
    findings: list[AuditFinding] = []
    checked = 0
    max_timeout = 0.0
    for path in _python_files((root / "utils", root / "cron", root / "seo")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(_finding("network_bounds", f"cannot parse Python: {exc.msg}", path, exc.lineno))
            continue
        visitor = _NetworkCallVisitor(path)
        visitor.visit(tree)
        checked += visitor.calls
        max_timeout = max(max_timeout, visitor.max_timeout)
        findings.extend(visitor.findings)
    return findings, {
        "status": "pass" if not findings else "fail",
        "external_calls_checked": checked,
        "max_timeout_seconds": max_timeout,
        "timeout_budget_seconds": MAX_EXTERNAL_TIMEOUT_SECONDS,
    }


def _is_streamlit_cache(decorator: ast.expr) -> bool:
    call = decorator if isinstance(decorator, ast.Call) else None
    target = call.func if call else decorator
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "cache_data"
        and isinstance(target.value, ast.Name)
        and target.value.id == "st"
    )


def _check_cache_bounds(root: Path) -> tuple[list[AuditFinding], dict[str, int | str]]:
    path = root / "utils" / "fetchers.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[AuditFinding] = []
    checked = 0
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not _is_streamlit_cache(decorator):
                continue
            checked += 1
            keywords = {
                keyword.arg
                for keyword in getattr(decorator, "keywords", [])
                if keyword.arg
            }
            missing = {"ttl", "max_entries"} - keywords
            if missing:
                findings.append(_finding(
                    "cache_bounds",
                    f"{node.name} cache is missing bounds: {', '.join(sorted(missing))}",
                    path,
                    node.lineno,
                ))
    if checked == 0:
        findings.append(_finding("cache_bounds", "no provider caches were detected", path))
    return findings, {
        "status": "pass" if not findings else "fail",
        "provider_caches_checked": checked,
    }


def _check_provider_health(root: Path) -> tuple[list[AuditFinding], dict[str, int | str]]:
    # Imports are local so importing this audit module remains side-effect free.
    from utils.config import SIGNALS
    from utils.product_metrics import PRIMARY_SOURCES
    from utils.provider_health import canonical_provider, provider_health_snapshot

    findings: list[AuditFinding] = []
    rows = {row["provider"]: row for row in provider_health_snapshot()}
    advertised = set(PRIMARY_SOURCES)
    missing_rows = sorted(advertised - rows.keys())
    if missing_rows:
        findings.append(_finding(
            "provider_health",
            f"advertised providers missing health rows: {', '.join(missing_rows)}",
            root / "utils" / "provider_health.py",
        ))

    missing_cadence = sorted(
        provider
        for provider in advertised
        if not str(rows.get(provider, {}).get("expected_cadence", "")).strip()
        or rows.get(provider, {}).get("expected_cadence") == "Provider dependent"
    )
    if missing_cadence:
        findings.append(_finding(
            "provider_health",
            f"providers missing explicit freshness cadence: {', '.join(missing_cadence)}",
            root / "utils" / "provider_health.py",
        ))

    signal_sources = {
        canonical_provider(config.get("source"))
        for config in SIGNALS.values()
    }
    untracked_sources = sorted(signal_sources - advertised)
    if untracked_sources:
        findings.append(_finding(
            "provider_health",
            f"active signal sources lack an advertised health contract: {', '.join(untracked_sources)}",
            root / "utils" / "config.py",
        ))

    # The check above enforces active ⊆ advertised (no untracked source). The
    # reverse gap is what actually shipped a false claim: the Signal Dashboard
    # hand-listed SEC EDGAR and FINRA as signal sources while zero signals used
    # them. Surface it as a metric so the divergence is visible in CI output
    # rather than silently passing. It is reported, not failed, because a
    # provider can legitimately power a non-signal feature (SEC EDGAR and FINRA
    # really do drive Ticker Deep Dive) -- what must never happen is a UI
    # claiming one of them as a source of the macro signals, which
    # tests/test_signal_source_claims.py pins directly.
    advertised_not_sourcing_signals = sorted(advertised - signal_sources)

    return findings, {
        "status": "pass" if not findings else "fail",
        "advertised_providers": len(advertised),
        "active_signal_sources": len(signal_sources),
        "advertised_not_sourcing_signals": len(advertised_not_sourcing_signals),
        "non_signal_providers": ",".join(advertised_not_sourcing_signals) or "none",
        "health_rows": len(rows),
    }


def run_production_audit(root: str | Path) -> AuditReport:
    """Run every deterministic production contract against ``root``."""
    base = Path(root).resolve()
    checks: dict[str, dict[str, int | str]] = {}
    findings: list[AuditFinding] = []
    for name, runner in (
        ("routes", _check_routes),
        ("blueprint", _check_blueprint),
        ("network_bounds", _check_network_timeouts),
        ("cache_bounds", _check_cache_bounds),
        ("provider_health", _check_provider_health),
    ):
        result_findings, summary = runner(base)
        checks[name] = summary
        findings.extend(result_findings)
    return AuditReport(ok=not findings, checks=checks, findings=tuple(findings))
