#!/usr/bin/env python3
"""AI code reviewer for caselaw-downloader PRs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent

_CODEBASE_FILES = [
    "pyproject.toml",
    "src/caselaw_downloader/api.py",
    "src/caselaw_downloader/downloader.py",
    "src/caselaw_downloader/cli.py",
    "tests/test_api.py",
    "tests/test_downloader.py",
    "tests/test_cli.py",
]

_TESTER_SYSTEM = """\
You are a senior QA engineer specialising in Python CLI tools. Your job is to review \
caselaw-downloader, a tool that downloads UK case law from The National Archives Find \
Case Law service.

When reviewing a pull request diff, focus on:
- Test coverage: are new code paths covered by tests?
- Edge cases: what scenarios are missing or under-tested?
- Error handling: are failure modes tested (HTTP errors, invalid input, empty results)?
- Test quality: are tests meaningful rather than superficial?
- Regression risk: could this change silently break existing behaviour?

When reviewing the codebase overall, provide a holistic assessment of test quality, \
coverage gaps, and risk areas.

Be specific. Cite file names and line numbers. Suggest concrete test cases where \
coverage is lacking. If the change is well-tested, say so briefly and explain why.

Format your review as markdown suitable for a GitHub PR comment."""

_PRODUCT_OWNER_SYSTEM = """\
You are a product owner reviewing caselaw-downloader, a CLI tool that downloads UK case \
law from The National Archives Find Case Law service. It targets legal researchers and \
tax practitioners who need offline access to tribunal decisions.

When reviewing a pull request diff, focus on:
- User value: does this change benefit the end user?
- CLI usability: are new options intuitive? Do defaults make sense?
- Help text and discoverability: are new features explained clearly?
- Scope: is this a focused, coherent change or does it mix concerns?
- Risk: could this change frustrate or confuse users?

When reviewing the codebase overall, assess the tool from a user perspective: is it \
complete, intuitive, and fit for purpose?

You are NOT reviewing code quality or test coverage — that is the tester's job. \
Focus entirely on user-facing behaviour and product value.

Be concise. If the change is good, say so. If something needs attention, explain \
the user impact.

Format your review as markdown suitable for a GitHub PR comment."""


def _read_codebase() -> str:
    parts = []
    for rel in _CODEBASE_FILES:
        path = ROOT / rel
        if path.exists():
            parts.append(f"### {rel}\n```\n{path.read_text()}\n```")
    return "\n\n".join(parts)


def _get_pr_diff(pr_number: int) -> str:
    result = subprocess.run(
        ["gh", "pr", "diff", str(pr_number)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _post_comment(pr_number: int, body: str) -> None:
    subprocess.run(
        ["gh", "pr", "comment", str(pr_number), "--body", body],
        check=True,
    )


def _run_review(role: str, pr_number: int | None) -> str:
    system = _TESTER_SYSTEM if role == "tester" else _PRODUCT_OWNER_SYSTEM
    role_label = "QA Tester" if role == "tester" else "Product Owner"

    codebase = _read_codebase()

    if pr_number is not None:
        diff = _get_pr_diff(pr_number)
        user_content = [
            {
                "type": "text",
                "text": f"## Current Codebase\n\n{codebase}",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    f"## Pull Request #{pr_number} Diff\n\n```diff\n{diff}\n```\n\n"
                    f"Please review this pull request as the {role_label}."
                ),
            },
        ]
    else:
        user_content = [
            {
                "type": "text",
                "text": f"## Codebase\n\n{codebase}",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    f"Please review the current state of this codebase as the {role_label}. "
                    "Provide a comprehensive assessment."
                ),
            },
        ]

    client = anthropic.Anthropic()

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        message = stream.get_final_message()

    text_parts = [block.text for block in message.content if block.type == "text"]
    return "\n".join(text_parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI code reviewer for caselaw-downloader")
    parser.add_argument(
        "--role",
        choices=["tester", "product-owner"],
        required=True,
        help="Review persona to use",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="PR number to review (omit for standalone codebase review)",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="Post the review as a PR comment (requires --pr)",
    )
    args = parser.parse_args()

    if args.post and args.pr is None:
        parser.error("--post requires --pr")

    review = _run_review(args.role, args.pr)

    role_label = "AI QA Tester" if args.role == "tester" else "AI Product Owner"
    full_comment = f"## {role_label} Review\n\n{review}"

    if args.post:
        _post_comment(args.pr, full_comment)
        print(f"Review posted to PR #{args.pr}", file=sys.stderr)
    else:
        print(full_comment)


if __name__ == "__main__":
    main()
