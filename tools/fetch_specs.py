"""Refresh the bundled OIF CMIS specification PDFs in knowledge/specs/.

Standard library only; works on Windows, Linux and macOS. Downloads use HTTP
Range requests in small chunks and stream each chunk to disk, so a slow or
interrupted transfer can be resumed without starting over.

    python tools/fetch_specs.py            # download / resume missing files
    python tools/fetch_specs.py --force   # re-download everything
    python tools/fetch_specs.py --check   # only report local file status

The PDFs are OIF Implementation Agreements, publicly published by the Optical
Internetworking Forum. Copies are bundled for offline reference only; see
knowledge/specs/README.md for provenance, copyright and canonical links.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "knowledge" / "specs"
CHUNK = 512 * 1024
CHUNK_TIMEOUT = 60
USER_AGENT = "CMIScope-spec-fetch/1.0"

SPECS = [
    {
        "name": "OIF-CMIS-05.3.pdf",
        "url": "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.3.pdf",
        "title": "Common Management Interface Specification (CMIS) Rev 5.3",
    },
    {
        "name": "OIF-CMIS-05.4.pdf",
        "url": "https://www.oiforum.com/wp-content/uploads/OIF-CMIS-05.4.pdf",
        "title": "Common Management Interface Specification (CMIS) Rev 5.4",
    },
]


def is_complete_pdf(path: Path) -> bool:
    """Cheap structural check: PDF header and an EOF marker near the tail."""
    if not path.is_file() or path.stat().st_size < 10_000:
        return False
    with path.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            return False
        fh.seek(max(0, path.stat().st_size - 2048))
        return b"%%EOF" in fh.read()


def _request(url: str, headers: dict[str, str], timeout: int):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers}),
        timeout=timeout,
    )


def remote_size(url: str) -> int | None:
    """Return Content-Length if the server advertises byte ranges."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            length = resp.headers.get("Content-Length")
            ranges = resp.headers.get("Accept-Ranges", "")
            return int(length) if length and "bytes" in ranges else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def fetch(spec: dict, force: bool = False, retries: int = 4) -> tuple[bool, str]:
    path = OUT_DIR / spec["name"]
    if not force and is_complete_pdf(path):
        return True, f"up to date ({path.stat().st_size:,} bytes)"

    total = remote_size(spec["url"])
    if force or not path.is_file() or path.read_bytes()[:5] != b"%PDF-":
        path.write_bytes(b"")
    pos = path.stat().st_size
    attempts_left = retries

    with path.open("ab") as fh:
        while total is None or pos < total:
            end = pos + CHUNK - 1 if total is None else min(pos + CHUNK - 1, total - 1)
            try:
                with _request(spec["url"], {"Range": f"bytes={pos}-{end}"},
                              CHUNK_TIMEOUT) as resp:
                    if resp.status != 206:
                        raise OSError(f"server returned HTTP {resp.status} instead of 206")
                    data = resp.read()
                if not data:
                    raise OSError("empty chunk")
                fh.write(data)
                fh.flush()
                pos += len(data)
                attempts_left = retries  # reset the retry budget after progress
                if total:
                    print(f"  {spec['name']}: {pos:,}/{total:,} bytes "
                          f"({pos * 100 // total}%)", flush=True)
                if total is None:
                    break  # single-shot download when ranges are unsupported
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                attempts_left -= 1
                if attempts_left <= 0:
                    return False, f"stopped at {pos:,} bytes: {exc}"
                print(f"  {spec['name']}: retry at {pos:,} bytes ({exc})", flush=True)
                time.sleep(2)

    if is_complete_pdf(path):
        return True, f"downloaded ({path.stat().st_size:,} bytes)"
    return False, f"incomplete or invalid PDF ({path.stat().st_size:,} bytes)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch bundled CMIS specification PDFs")
    parser.add_argument("--force", action="store_true", help="re-download even if complete")
    parser.add_argument("--check", action="store_true", help="report status without downloading")
    parser.add_argument("--retries", type=int, default=4, help="retries per chunk")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for spec in SPECS:
        path = OUT_DIR / spec["name"]
        if args.check:
            status = "complete" if is_complete_pdf(path) else "missing/partial"
            size = path.stat().st_size if path.is_file() else 0
            print(f"{spec['name']:24s} {status:16s} {size:>12,} bytes")
            if status != "complete":
                failed.append(spec["name"])
            continue
        ok, detail = fetch(spec, args.force, args.retries)
        print(f"{'OK  ' if ok else 'FAIL'} {spec['name']:24s} {detail}", flush=True)
        if not ok:
            failed.append(spec["name"])
    if failed:
        print("\nSome files are incomplete. Re-run this script to resume, or use the "
              "canonical links in knowledge/specs/README.md.", file=sys.stderr)
        return 1
    print("\nAll specification copies are complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
