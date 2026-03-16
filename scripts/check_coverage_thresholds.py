#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _norm_path(path: str) -> str:
    return path.replace("\\", "/")


def _to_repo_path(path: str) -> str:
    """
    Normalize cobertura paths to repo-style paths.

    In CI we run `pytest --cov=app` and coverage.xml usually reports filenames
    relative to the `app/` directory (e.g. "security/sanitizer.py"). This helper
    maps them back to repo paths (e.g. "app/security/sanitizer.py") so the
    workflow can use intuitive prefixes.
    """
    path = _norm_path(path).lstrip("./")

    # If coverage emits an absolute path, try to make it relative to repo root.
    if os.path.isabs(path):
        try:
            path = _norm_path(os.path.relpath(path, start=os.getcwd()))
        except Exception:
            pass

    # If it's already repo-root relative, keep it.
    if path.startswith("app/"):
        return path

    candidate = Path("app") / path
    if candidate.exists():
        return _norm_path(str(candidate))

    return path


def _iter_file_line_counts(xml_path: Path) -> list[tuple[str, int, int]]:
    root = ET.parse(xml_path).getroot()

    files: list[tuple[str, int, int]] = []
    for cls in root.findall(".//class"):
        filename = cls.attrib.get("filename")
        if not filename:
            continue

        lines_el = cls.find("lines")
        if lines_el is None:
            continue

        lines = lines_el.findall("line")
        total = len(lines)
        if total == 0:
            # No measured lines (e.g. __init__.py with 0 statements).
            continue

        covered = 0
        for line_el in lines:
            hits_raw = line_el.attrib.get("hits", "0")
            try:
                hits = int(hits_raw)
            except ValueError:
                hits = 0
            if hits > 0:
                covered += 1

        files.append((_to_repo_path(filename), covered, total))

    return files


def _compute_prefix_coverage(
    files: list[tuple[str, int, int]],
    prefix: str,
) -> tuple[int, int, int]:
    prefix = _norm_path(prefix).rstrip("/")
    path = Path(prefix)
    is_dir = prefix.endswith("/") or path.is_dir()

    if is_dir:
        needle = prefix.rstrip("/") + "/"
        matched = [(c, t) for f, c, t in files if f.startswith(needle)]
    else:
        matched = [(c, t) for f, c, t in files if f == prefix]

    covered = sum(c for c, _t in matched)
    total = sum(t for _c, t in matched)
    return covered, total, len(matched)


def _parse_min_arg(raw: str) -> tuple[str, float]:
    if "=" not in raw:
        raise ValueError("Expected PATH=MIN_PERCENT")
    path, value_raw = raw.split("=", 1)
    return path.strip(), float(value_raw.strip())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce coverage thresholds for specific repo path prefixes.",
    )
    parser.add_argument(
        "--xml",
        default="coverage.xml",
        help="Path to cobertura XML file (default: coverage.xml).",
    )
    parser.add_argument(
        "--min",
        dest="mins",
        action="append",
        default=[],
        metavar="PATH=MIN_PERCENT",
        help='Minimum line coverage for a path prefix, e.g. "app/security=35".',
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail if a prefix matches zero measured lines.",
    )

    args = parser.parse_args(argv)

    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"coverage xml not found: {xml_path}", file=sys.stderr)
        return 2

    files = _iter_file_line_counts(xml_path)
    if not files:
        print("No measured lines found in coverage xml.", file=sys.stderr)
        return 2

    if not args.mins:
        root = ET.parse(xml_path).getroot()
        try:
            total_rate = float(root.attrib.get("line-rate", "0")) * 100.0
        except ValueError:
            total_rate = 0.0
        print(f"Total line coverage: {total_rate:.2f}%")
        return 0

    failures: list[str] = []
    for raw in args.mins:
        try:
            prefix, min_percent = _parse_min_arg(raw)
        except Exception as exc:
            failures.append(f"Invalid --min argument {raw!r}: {exc}")
            continue

        covered, total, matched_files = _compute_prefix_coverage(files, prefix)
        if total == 0:
            msg = (
                f"{prefix}: no measured lines found (matched {matched_files} files)."
            )
            if args.allow_empty:
                print(f"SKIP {msg}")
                continue
            failures.append(msg)
            print(f"FAIL {msg}")
            continue

        rate = (covered / total) * 100.0
        ok = rate >= min_percent
        status = "PASS" if ok else "FAIL"
        line = (
            f"{status} {prefix}: {rate:.2f}% ({covered}/{total}) "
            f"min={min_percent:.2f}%"
        )
        print(line)
        if not ok:
            failures.append(line)

    if failures:
        print("\nCoverage thresholds not met.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

