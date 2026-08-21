"""A small, media-aware CSS cascade resolver for the BUILT stylesheet.

Consolidating button CSS safely needs one thing first: the ability to say what
a declaration actually resolves to today, so a change can be proven not to alter
it. Reading the source files cannot answer that -- the same selector is declared
in utils/header.py and utils/theme.py, the blocks are concatenated at build
time, and `!important` plus source order decide the winner.

It also has to respect @media. Flattening those makes
`@media (prefers-reduced-motion: reduce) { transition: none !important }` look
like the winner for every button, which is how a "consolidation" would quietly
delete every transition in the app. That mistake has been made in this codebase
before (#150) and was made again in the first pass of this analysis.

Deliberately NOT a browser. It models: specificity, !important, source order,
and @media context as a filter. That is enough to compare BEFORE and AFTER of a
refactor; it is not enough to certify a design, which is what the browser check
after deployment is for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Declaration:
    prop: str
    value: str
    important: bool
    specificity: tuple[int, int, int]
    order: int
    selector: str
    media: tuple[str, ...]

    @property
    def rank(self) -> tuple:
        return (self.important, self.specificity, self.order)


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def specificity(selector: str) -> tuple[int, int, int]:
    """(ids, classes+attributes+pseudo-classes, elements+pseudo-elements)."""
    s = re.sub(r"::[a-z-]+", " ", selector)          # pseudo-elements counted below
    ids = len(re.findall(r"#[\w-]+", s))
    cls = len(re.findall(r"\.[\w-]+|\[[^\]]+\]|:(?!:)[a-z-]+(?:\([^)]*\))?", s))
    ele = len(re.findall(r"(?:^|[\s>+~])([a-z][\w-]*)", s))
    ele += len(re.findall(r"::[a-z-]+", selector))
    return (ids, cls, ele)


def iter_rules(css: str):
    """Yield (media_stack, selector_group, body) preserving @-block context."""
    src = strip_comments(css)
    i, stack, order = 0, [], 0
    while True:
        brace = src.find("{", i)
        if brace == -1:
            return
        prelude = src[i:brace]
        # close any blocks that ended before this rule
        for _ in range(prelude.count("}")):
            if stack:
                stack.pop()
        prelude = prelude.split("}")[-1].strip()
        if prelude.startswith("@"):
            if prelude.startswith(("@media", "@supports")):
                stack.append(prelude)
                i = brace + 1
                continue
            # @font-face / @keyframes: skip the whole block
            depth, j = 1, brace + 1
            while j < len(src) and depth:
                depth += (src[j] == "{") - (src[j] == "}")
                j += 1
            i = j
            continue
        depth, j = 1, brace + 1
        while j < len(src) and depth:
            depth += (src[j] == "{") - (src[j] == "}")
            j += 1
        yield tuple(stack), prelude, src[brace + 1 : j - 1], order
        order += 1
        i = j


def declarations_for(
    css: str,
    selector_predicate,
    *,
    media: tuple[str, ...] = (),
) -> dict[str, Declaration]:
    """Resolve the winning declaration per property for one element state.

    `media` is the set of at-rule preludes considered ACTIVE. A rule inside a
    media query the caller has not activated is skipped, so the default state
    and the reduced-motion state are resolved separately rather than merged.
    """
    winners: dict[str, Declaration] = {}
    for stack, group, body, order in iter_rules(css):
        if any(q not in media for q in stack):
            continue
        for selector in group.split(","):
            selector = " ".join(selector.split())
            if not selector or not selector_predicate(selector):
                continue
            for raw in body.split(";"):
                if ":" not in raw:
                    continue
                prop, value = raw.split(":", 1)
                prop, value = prop.strip(), value.strip()
                if not prop or prop.startswith("--"):
                    continue
                decl = Declaration(
                    prop=prop,
                    value=value.replace("!important", "").strip(),
                    important="!important" in value,
                    specificity=specificity(selector),
                    order=order,
                    selector=selector,
                    media=stack,
                )
                if prop not in winners or decl.rank > winners[prop].rank:
                    winners[prop] = decl
    return winners


def resolved_values(css: str, predicate, *, media=()) -> dict[str, str]:
    return {p: d.value for p, d in declarations_for(css, predicate, media=media).items()}
