#!/usr/bin/env python3
"""Check upstream releases for Sunshine and GNOME Shell 48 extensions and update Dockerfile ARGs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

DOCKERFILE = Path("Dockerfile")
GNOME_SHELL_VERSION = "48"
GNOME_EXTENSIONS = [
    ("extension-list@tu.berry", "EXT_EXTENSION_LIST_TAG", "EXT_EXTENSION_LIST_SHA256"),
    (
        "wack-lockscreen-clock@rinzler69-wastaken.github.com",
        "EXT_WACK_LOCKSCREEN_TAG",
        "EXT_WACK_LOCKSCREEN_SHA256",
    ),
    (
        "system-monitor-next@paradoxxx.zero.gmail.com",
        "EXT_SYSTEM_MONITOR_TAG",
        "EXT_SYSTEM_MONITOR_SHA256",
    ),
]


def _headers(is_github: bool = False) -> dict[str, str]:
    headers = {"User-Agent": "steam-headless-gnome-pin-updater/1.0"}
    if is_github:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json(url: str, is_github: bool = False) -> dict:
    req = urllib.request.Request(url, headers=_headers(is_github=is_github))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_sha256(url: str) -> str:
    req = urllib.request.Request(url, headers=_headers(is_github=False))
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as resp:
        while chunk := resp.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_arg(text: str, name: str) -> str:
    m = re.search(rf"^ARG {re.escape(name)}=(\S+)\s*$", text, re.M)
    if not m:
        raise ValueError(f"ARG {name} not found in {DOCKERFILE}")
    return m.group(1)


def set_arg(text: str, name: str, value: str) -> str:
    updated, count = re.subn(
        rf"^(ARG {re.escape(name)}=)\S+\s*$",
        rf"\g<1>{value}",
        text,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError(f"Failed to update ARG {name} in {DOCKERFILE}")
    return updated


def check_sunshine(text: str) -> list[tuple[str, str]]:
    current_ver = get_arg(text, "SUNSHINE_VERSION")
    release = fetch_json(
        "https://api.github.com/repos/SunshineStream/Sunshine/releases/latest",
        is_github=True,
    )
    tag = str(release.get("tag_name", "")).lstrip("v")
    if not tag or tag == current_ver:
        print(f"Sunshine up to date ({current_ver})")
        return []

    expected_name = f"sunshine_{tag}-1+debiantrixie_amd64.deb"
    asset = next(
        (a for a in release.get("assets", []) if a.get("name") == expected_name),
        None,
    )
    if not asset:
        print(f"Sunshine {tag} has no asset named {expected_name}; skipping.")
        return []

    digest = asset.get("digest") or ""
    if digest.startswith("sha256:") and len(digest) == 71:
        sha = digest.split(":", 1)[1]
    else:
        sha = fetch_sha256(asset["browser_download_url"])

    print(f"Sunshine update: {current_ver} -> {tag} ({sha[:12]}...)")
    return [("SUNSHINE_VERSION", tag), ("SUNSHINE_SHA256", sha)]


def check_gnome_extensions(text: str) -> list[tuple[str, str]]:
    changes: list[tuple[str, str]] = []
    for uuid, tag_arg, sha_arg in GNOME_EXTENSIONS:
        current_tag = get_arg(text, tag_arg)
        q = urllib.parse.urlencode({"uuid": uuid, "shell_version": GNOME_SHELL_VERSION})
        info = fetch_json(f"https://extensions.gnome.org/extension-info/?{q}")
        new_tag = str(info.get("version_tag", ""))
        if not new_tag.isdigit() or new_tag == current_tag:
            print(f"Extension {uuid} up to date (tag {current_tag})")
            continue
        url = f"https://extensions.gnome.org/download-extension/{uuid}.shell-extension.zip?version_tag={new_tag}"
        sha = fetch_sha256(url)
        print(f"Extension {uuid} update: {current_tag} -> {new_tag} ({sha[:12]}...)")
        changes.extend([(tag_arg, new_tag), (sha_arg, sha)])
    return changes


def check_wack_shell(text: str) -> list[tuple[str, str]]:
    current_commit = get_arg(text, "WACK_SHELL_COMMIT")
    commit = fetch_json(
        "https://api.github.com/repos/rinzler69-wastaken/wack-shell/commits/HEAD",
        is_github=True,
    )
    new_commit = str(commit.get("sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", new_commit) or new_commit == current_commit:
        print(f"wack-shell up to date ({current_commit[:12]})")
        return []
    url = f"https://codeload.github.com/rinzler69-wastaken/wack-shell/tar.gz/{new_commit}"
    sha = fetch_sha256(url)
    print(f"wack-shell update: {current_commit[:12]} -> {new_commit[:12]} ({sha[:12]}...)")
    return [("WACK_SHELL_COMMIT", new_commit), ("WACK_SHELL_SHA256", sha)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Update pinned Dockerfile ARGs")
    parser.add_argument("--dry-run", action="store_true", help="Check for updates without modifying Dockerfile")
    args = parser.parse_args()

    text = DOCKERFILE.read_text(encoding="utf-8")
    changes: list[tuple[str, str]] = []
    changes.extend(check_sunshine(text))
    changes.extend(check_gnome_extensions(text))
    changes.extend(check_wack_shell(text))

    if not changes:
        print("All Dockerfile pins are up to date.")
        return 0

    if args.dry_run:
        print(f"DRY RUN: {len(changes) // 2} component(s) have updates available.")
        return 0

    updated = text
    for name, value in changes:
        updated = set_arg(updated, name, value)
    DOCKERFILE.write_text(updated, encoding="utf-8")
    print(f"Updated {len(changes) // 2} component(s) in {DOCKERFILE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
