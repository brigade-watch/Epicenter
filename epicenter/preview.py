"""Preview the site locally: python -m epicenter.preview [--data demo-data]"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
from pathlib import Path


def build(data_dir: Path, out: Path = Path("_site")) -> Path:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree("site", out)
    shutil.copytree(data_dir, out / "data", ignore=shutil.ignore_patterns(".local", "history.enc"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()
    out = build(args.data)
    if args.build_only:
        print(f"Built {out}/")
        return
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    print(f"Serving {args.data} at http://localhost:{args.port}  (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
