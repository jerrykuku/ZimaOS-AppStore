#!/usr/bin/env python3
"""Import SVG icons from a Figma node into Apps/<AppName>/icon.svg.

Usage:
  FIGMA_TOKEN=... python3 scripts/import_figma_icons.py \
      --figma-url 'https://www.figma.com/design/...?...node-id=1225-4...'

Or:
  FIGMA_TOKEN=... python3 scripts/import_figma_icons.py \
      --file-key ReveWwbuLaFKLGvDmN1G5N --node-id 1225:4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT / "Apps"
API_BASE = "https://api.figma.com/v1"


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_figma_url(figma_url: str) -> Tuple[str, str]:
    parsed = urllib.parse.urlparse(figma_url)
    parts = [p for p in parsed.path.split("/") if p]
    file_key = ""
    if len(parts) >= 2 and parts[0] in {"design", "file"}:
        file_key = parts[1]
    if not file_key:
        raise ValueError(f"Could not parse file key from URL: {figma_url}")

    qs = urllib.parse.parse_qs(parsed.query)
    node = qs.get("node-id", [""])[0]
    if not node:
        raise ValueError("Missing node-id in Figma URL query")
    return file_key, node.replace("-", ":")


def figma_get_json(path: str, token: str, query: Dict[str, str] | None = None) -> dict:
    url = f"{API_BASE}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"X-Figma-Token": token})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def walk_nodes(node: dict) -> Iterable[dict]:
    yield node
    for child in node.get("children", []) or []:
        yield from walk_nodes(child)


def list_app_dirs() -> List[str]:
    if not APPS_DIR.exists():
        raise FileNotFoundError(f"Apps dir not found: {APPS_DIR}")
    return sorted([p.name for p in APPS_DIR.iterdir() if p.is_dir()])


def build_name_map(app_names: List[str]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    exact = {name: name for name in app_names}
    normalized: Dict[str, List[str]] = {}
    for name in app_names:
        normalized.setdefault(normalize_name(name), []).append(name)
    return exact, normalized


def choose_app_name(figma_name: str, exact: Dict[str, str], normalized: Dict[str, List[str]]) -> str | None:
    if figma_name in exact:
        return figma_name
    n = normalize_name(figma_name)
    matches = normalized.get(n, [])
    if len(matches) == 1:
        return matches[0]
    return None


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def download_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Figma icons into Apps/*/icon.svg")
    parser.add_argument("--figma-url", help="Figma design URL that includes node-id")
    parser.add_argument("--file-key", help="Figma file key")
    parser.add_argument("--node-id", help="Node id, e.g. 1225:4 or 1225-4")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()

    token = os.getenv("FIGMA_TOKEN", "").strip()
    if not token:
        eprint("Missing FIGMA_TOKEN environment variable")
        return 2

    if args.figma_url:
        file_key, node_id = parse_figma_url(args.figma_url)
    else:
        if not args.file_key or not args.node_id:
            eprint("Provide either --figma-url, or both --file-key and --node-id")
            return 2
        file_key = args.file_key
        node_id = args.node_id.replace("-", ":")

    app_names = list_app_dirs()
    exact, normalized = build_name_map(app_names)

    data = figma_get_json(
        f"/files/{file_key}/nodes",
        token,
        query={"ids": node_id, "depth": "8"},
    )

    node_data = data.get("nodes", {}).get(node_id, {}).get("document")
    if not node_data:
        eprint(f"Node not found or inaccessible: {node_id}")
        return 1

    # Pick exportable descendants whose names map to an app directory.
    candidates: Dict[str, str] = {}
    duplicate_hits: Dict[str, List[str]] = {}

    for n in walk_nodes(node_data):
        nid = n.get("id")
        nname = (n.get("name") or "").strip()
        ntype = n.get("type")
        if not nid or not nname or ntype in {"TEXT", "VECTOR"}:
            continue
        app_name = choose_app_name(nname, exact, normalized)
        if not app_name:
            continue
        if app_name in candidates:
            duplicate_hits.setdefault(app_name, []).append(nid)
            continue
        candidates[app_name] = nid

    if not candidates:
        eprint("No matching icon nodes found under the target node")
        return 1

    print(f"Matched {len(candidates)} app icons from Figma node {node_id}")

    id_to_app = {nid: app for app, nid in candidates.items()}
    id_list = list(id_to_app.keys())

    download_urls: Dict[str, str] = {}
    for chunk in chunked(id_list, 100):
        resp = figma_get_json(
            f"/images/{file_key}",
            token,
            query={
                "ids": ",".join(chunk),
                "format": "svg",
                "svg_outline_text": "true",
            },
        )
        download_urls.update(resp.get("images", {}))

    written = 0
    missing_url = []
    for nid, app_name in id_to_app.items():
        url = download_urls.get(nid)
        if not url:
            missing_url.append((app_name, nid))
            continue

        target = APPS_DIR / app_name / "icon.svg"
        if args.dry_run:
            print(f"[dry-run] {app_name}: {nid} -> {target}")
            written += 1
            continue

        svg = download_text(url)
        target.write_text(svg, encoding="utf-8")
        print(f"Wrote {target.relative_to(ROOT)}")
        written += 1

    print(f"Completed: {written} icon(s)")

    if duplicate_hits:
        eprint("\nDuplicate name matches (kept first node id):")
        for app, ids in sorted(duplicate_hits.items()):
            eprint(f"  {app}: extra ids={','.join(ids)}")

    if missing_url:
        eprint("\nFailed to get SVG URL for:")
        for app, nid in missing_url:
            eprint(f"  {app}: {nid}")

    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
