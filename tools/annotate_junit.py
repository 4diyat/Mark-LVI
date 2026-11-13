"""Turn a pytest junit XML into GitHub annotations.

WHY THIS IS A FILE AND NOT A HEREDOC IN THE WORKFLOW
    The first version was inline: `python - <<'REPORT' ... REPORT`. It worked on
    Linux and macOS, passed on the pull request, and failed on Windows — where
    the default shell for `run:` is PowerShell, which has no heredoc. The job
    then went red for a reason that had nothing to do with the code, which is
    the worst kind of red: it teaches people to ignore the check.

    A file has no shell in it. It is also the only way this can be tested, and
    a reporter that is wrong in silence is worse than no reporter at all — the
    whole point is that a failure names itself.

    Usage (in CI):      python tools/annotate_junit.py "$RUNNER_TEMP/junit.xml"
    Usage (locally):    python tools/annotate_junit.py junit.xml
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# GitHub truncates annotation text anyway; a stack trace in an annotation is
# unreadable and every runner has a per-step limit on the number emitted.
MAX_MESSAGE = 250
MAX_ANNOTATIONS = 40


def _escape(text: str) -> str:
    """The three characters the workflow-command syntax reserves.

    `%` first, or the escapes for `\\r`/`\\n` get double-escaped.
    """
    return (text.replace("%", "%25")
                .replace("\r", "%0D")
                .replace("\n", "%0A"))


def annotations(path: str | Path) -> list[str]:
    """One `::error ...::` line per failing test, in file order."""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    lines: list[str] = []
    for suite in suites:
        for case in suite.iter("testcase"):
            for kind in ("failure", "error", "skipped"):
                node = case.find(kind)
                if node is None or (kind == "skipped" and not node.get("message")):
                    continue
                detail = (node.get("message") or node.text or kind).strip()
                detail = detail.splitlines()[0][:MAX_MESSAGE] if detail else kind
                where = case.get("file") or "unknown"
                line = case.get("line") or "1"
                title = f"{case.get('classname') or ''}.{case.get('name') or ''}"
                lines.append(
                    f"::error file={where},line={line},"
                    f"title={_escape(title.lstrip('.'))}::{_escape(detail)}")
            if len(lines) >= MAX_ANNOTATIONS:
                lines.append(f"::warning::stopped at {MAX_ANNOTATIONS} "
                             "annotations — the rest are in the log")
                return lines
    return lines


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: annotate_junit.py <junit.xml>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        # Not a failure: the suite may have died before pytest could write the
        # file, and this step runs with `if: always()`.
        print(f"::warning::no {path.name} — the suite did not get far enough "
              "to write one; whatever failed is above this line")
        return 0
    try:
        lines = annotations(path)
    except ET.ParseError as e:
        print(f"::warning::{path.name} is not valid XML ({e})")
        return 0
    for line in lines:
        print(line)
    print(f"{len(lines)} annotation(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
