"""Fail when the SecGuard manuscript drifts from its evidence package."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "paper" / "main.tex"
BIB = ROOT / "paper" / "references.bib"
RESULTS = ROOT / "artifacts" / "research_validation.json"


def _citation_keys(text: str) -> set[str]:
    return {
        key.strip()
        for group in re.findall(r"\\cite\{([^}]+)\}", text)
        for key in group.split(",")
    }


def _bib_keys(text: str) -> set[str]:
    return set(re.findall(r"@\w+\{([^,]+),", text))


def _assert_balanced_braces(text: str) -> None:
    depth = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = re.split(r"(?<!\\)%", line, maxsplit=1)[0]
        for index, character in enumerate(line):
            if character in "{}" and (index == 0 or line[index - 1] != "\\"):
                depth += 1 if character == "{" else -1
                if depth < 0:
                    raise AssertionError(f"extra closing brace at line {line_number}")
    if depth:
        raise AssertionError(f"unbalanced LaTeX braces: final depth {depth}")


def main() -> None:
    tex = TEX.read_text(encoding="utf-8")
    bib = BIB.read_text(encoding="utf-8")
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    _assert_balanced_braces(tex)

    cited = _citation_keys(tex)
    bibliography = _bib_keys(bib)
    assert cited == bibliography, (
        f"citation mismatch: missing={sorted(cited - bibliography)}, "
        f"uncited={sorted(bibliography - cited)}"
    )

    for image_name in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", tex):
        assert (ROOT / "artifacts" / image_name).exists(), f"missing figure: {image_name}"

    learned = results["test"]["learned"]
    fixed = results["test"]["fixed"]
    static = results["test"]["static"]
    oracle = results["test"]["oracle"]
    expected_claims = {
        f"{100 * (learned['profit']['mean'] - fixed['profit']['mean']) / fixed['profit']['mean']:.2f}\\%",
        f"{100 * learned['profit']['mean'] / static['profit']['mean']:.2f}\\%",
        f"{100 * (static['exposure']['mean'] - learned['exposure']['mean']) / static['exposure']['mean']:.2f}\\%",
        f"{100 * (oracle['profit']['mean'] - learned['profit']['mean']) / oracle['profit']['mean']:.2f}\\%",
    }
    missing_claims = sorted(claim for claim in expected_claims if claim not in tex)
    assert not missing_claims, f"result claims missing or stale: {missing_claims}"

    for declaration in (
        "Data availability",
        "Ethics",
        "Author contributions",
        "Funding and conflicts of interest",
        "AI-assisted work",
    ):
        assert declaration in tex, f"missing declaration: {declaration}"

    print(
        f"paper check passed: {len(cited)} citations, "
        f"{len(expected_claims)} synchronized headline claims"
    )


if __name__ == "__main__":
    main()
