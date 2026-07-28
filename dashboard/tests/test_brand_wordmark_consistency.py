"""The global nav and page wordmarks must share one ALPHA treatment."""

from pathlib import Path


HEADER = (Path(__file__).resolve().parents[1] / "utils" / "header.py").read_text(
    encoding="utf-8"
)


def test_alpha_wordmarks_share_brand_gradient_tokens():
    for token in (
        "--ua-brand-alpha-1:",
        "--ua-brand-alpha-2:",
        "--ua-brand-alpha-3:",
    ):
        assert HEADER.count(token) == 2  # explicit dark and light values

    for selector in (".ua-wordmark span {", ".ua-tnav-brand-text em {"):
        rules = HEADER.split(selector)[1:]
        assert rules
        assert any(
            all(f"var(--ua-brand-alpha-{index})" in rule.split("}", 1)[0]
                for index in (1, 2, 3))
            for rule in rules
        )


def test_alpha_wordmark_no_longer_uses_green_or_gold_accent():
    nav_rule = HEADER.split(".ua-tnav-brand-text em {", 1)[1].split("}", 1)[0]
    assert "--ua-green" not in nav_rule
    assert "--ua-gold" not in nav_rule
    assert "-webkit-text-fill-color: transparent" in nav_rule
