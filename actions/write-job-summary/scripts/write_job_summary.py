#!/usr/bin/env python3
"""Write GitHub Actions job summary markdown from structured report JSON files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write job summary from report JSON files")
    parser.add_argument("--title", default="AppStore Workflow Summary")
    parser.add_argument("--report-jsons", required=True, help="Newline-separated report JSON paths")
    return parser.parse_args()


def safe_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def issue_line(issue: dict) -> str:
    severity = safe_text(issue.get("severity", "info")).upper()
    code = safe_text(issue.get("code", "UNKNOWN"))
    message = safe_text(issue.get("message", ""))
    suggestion = safe_text(issue.get("suggestion", ""))
    file_path = safe_text(issue.get("file", ""))

    line = f"- `{severity}` `{code}`"
    if file_path:
        line += f" in `{file_path}`"
    if message:
        line += f": {message}"
    if suggestion:
        line += f" Fix: {suggestion}"
    return line


def summarize_report(report_path: Path) -> str:
    if not report_path.exists():
        return f"## Missing Report\n- `{report_path}` was not found.\n"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    title = safe_text(report.get("title") or report.get("kind") or report_path.name)
    status = safe_text(report.get("status") or "unknown").upper()
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), list) else []

    lines = [f"## {title}", f"- Status: `{status}`"]

    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: `{value}`")

    if issues:
        lines.append("- Top issues:")
        for issue in issues[:5]:
            if isinstance(issue, dict):
                lines.append(issue_line(issue))
    else:
        lines.append("- Top issues: none")

    if artifacts:
        lines.append("- Artifacts:")
        for artifact in artifacts[:5]:
            if isinstance(artifact, dict):
                name = safe_text(artifact.get("name") or artifact.get("path") or "artifact")
                path = safe_text(artifact.get("path") or "")
                lines.append(f"- `{name}` -> `{path}`" if path else f"- `{name}`")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        raise RuntimeError("GITHUB_STEP_SUMMARY is not set")

    report_paths = [Path(line.strip()) for line in args.report_jsons.splitlines() if line.strip()]
    content = [f"# {args.title}\n"]
    for report_path in report_paths:
        content.append(summarize_report(report_path))

    Path(summary_path).write_text("\n".join(content), encoding="utf-8")
    print(f"Wrote job summary to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
