#!/usr/bin/env python3
"""Bulk-import a folder of audio files into Shadow Listens through its public API.

    pip install -r scripts/requirements.txt
    python scripts/import_folder.py ~/Music --username ada --license "Personal library" --i-own-the-rights

* Works against any deployment (local compose, the Oracle VM, ...): it only needs the gateway URL.
* Re-runnable: each file's SHA-256 is checked with the server first, so files that were already
  uploaded are skipped without re-sending them (a 2.5 GB folder is not uploaded twice).
* Titles/artists/albums come from the files' ID3/Vorbis tags (read by the server); untagged files
  fall back to the filename and "Unknown Artist".
* Server-side, FFmpeg transcoding happens in the background; tracks flip to "ready" as they finish.
"""
import argparse
import getpass
import hashlib
import os
import sys
import time
from pathlib import Path

import httpx

EXTS = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


class Client:
    def __init__(self, base: str, identifier: str, password: str):
        self.base, self.identifier, self.password = base.rstrip("/"), identifier, password
        self.http = httpx.Client(timeout=httpx.Timeout(900, connect=15))
        self.token = ""
        self.login()

    def login(self) -> None:
        r = self.http.post(f"{self.base}/api/auth/login", json={"identifier": self.identifier, "password": self.password})
        if r.status_code != 200:
            sys.exit(f"Login failed ({r.status_code}): {r.text}")
        self.token = r.json()["access_token"]

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        """Authenticated request; access tokens last 15 min, so re-login transparently on 401."""
        for attempt in range(2):
            kw_headers = {"Authorization": f"Bearer {self.token}"}
            files = kw.get("files")
            if files:  # file handles must be rewound for the retry
                for _, v in files.items():
                    v[1].seek(0)
            r = self.http.request(method, f"{self.base}{path}", headers=kw_headers, **kw)
            if r.status_code == 401 and attempt == 0:
                self.login()
                continue
            return r
        return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--base-url", default=os.environ.get("LISTENS_URL", "http://localhost:8080"))
    ap.add_argument("--username", "-u", required=True, help="username or email")
    ap.add_argument("--password", default=os.environ.get("LISTENS_PASSWORD"), help="or set LISTENS_PASSWORD, or you'll be prompted")
    ap.add_argument("--license", required=True, help='e.g. "CC BY 4.0", "Personal library", "Own work"')
    ap.add_argument("--i-own-the-rights", action="store_true", required=True,
                    help="confirm you own or are licensed to use every file in the folder")
    ap.add_argument("--dry-run", action="store_true", help="list what would be uploaded, upload nothing")
    args = ap.parse_args()

    if not args.folder.is_dir():
        sys.exit(f"Not a folder: {args.folder}")
    files = sorted(p for p in args.folder.rglob("*") if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith("."))
    total = sum(p.stat().st_size for p in files)
    print(f"Found {len(files)} audio files ({total / 1e9:.2f} GB) in {args.folder}")
    if not files:
        return 0

    client = None if args.dry_run else Client(args.base_url, args.username, args.password or getpass.getpass("Password: "))
    uploaded = skipped = 0
    failed: list[tuple[Path, str]] = []
    done_bytes, t0 = 0, time.monotonic()
    for i, path in enumerate(files, 1):
        size = path.stat().st_size
        label = f"[{i}/{len(files)}] {path.relative_to(args.folder)}"
        if args.dry_run:
            print(f"{label}  ({size / 1e6:.1f} MB)  would upload")
            continue
        try:
            digest = sha256_of(path)
            exists = client.request("GET", "/api/catalogue/uploads/exists", params={"sha256": digest})
            if exists.status_code == 200 and exists.json()["exists"]:
                print(f"{label}  already imported, skipping")
                skipped += 1
                continue
            with path.open("rb") as fh:
                r = client.request(
                    "POST", "/api/catalogue/upload",
                    data={"license": args.license, "rights_confirmed": "true"},
                    files={"file": (path.name, fh, "application/octet-stream")},
                )
            if r.status_code not in (200, 201):
                raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
            t = r.json()["track"]
            uploaded += 1
            done_bytes += size
            rate = done_bytes / max(time.monotonic() - t0, 1e-6)
            print(f"{label}  -> \"{t['title']}\" by {t['artist']['name']}  ({rate / 1e6:.1f} MB/s)")
        except Exception as exc:  # noqa: BLE001 - keep going; report at the end
            failed.append((path, str(exc)))
            print(f"{label}  FAILED: {exc}")

    print(f"\nDone: {uploaded} uploaded, {skipped} skipped, {len(failed)} failed.")
    for path, why in failed:
        print(f"  {path}: {why}")
    if uploaded:
        print("Transcoding runs in the background; watch progress on the Upload page.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
