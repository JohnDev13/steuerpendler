"""Fetch the official basic health-insurance premium data (BAG, priminfo/opendata.swiss) and the BAG lists of
Gemeinden by premium region. Runs in GitHub Actions (network); writes data/kk/raw/ and data/kk/raw/manifest.json
with the source URL, SHA-256 and size of every file. Standard library only.

    python3 scripts/kk/fetch.py --years 2026 2027
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/kk/raw"
CKAN = "https://ckan.opendata.swiss/api/3/action/package_show?id=health-insurance-premiums"
REGION_LISTS = {
    "2026": "https://www.bag.admin.ch/dam/de/sd-web/IvHRHXKH3eYG/Anhang%20EDI%20Ver.%20%C3%BCber%20die%20PrReg_Mut_2026.xlsx",
    "2027": "https://www.bag.admin.ch/dam/de/sd-web/Xm8w51dMKXLP/Pr%C3%A4mienregionen%20%28g%C3%BCltig%20ab%201.1.2027%29.xlsx",
}
MAX_PLAIN = 40 * 1024 * 1024  # larger files are stored gzipped


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "steuerpendler-kk/1"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def store(name: str, data: bytes, url: str, manifest: list[dict]) -> None:
    sha = hashlib.sha256(data).hexdigest()
    path = OUT / name
    if len(data) > MAX_PLAIN:
        path = path.with_name(path.name + ".gz")
        with gzip.open(path, "wb", mtime=0) as f:
            f.write(data)
    else:
        path.write_bytes(data)
    manifest.append({"file": path.name, "url": url, "sha256": sha, "bytes": len(data), "gzipped": path.suffix == ".gz"})
    print(f"::notice title=KK fetch::{path.name} {len(data)} bytes sha256={sha[:16]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", default=["2026", "2027"])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    package = json.loads(get(CKAN))["result"]
    resources = [{"name": (r.get("name") if isinstance(r.get("name"), str) else json.dumps(r.get("name"), ensure_ascii=False)),
                  "url": r.get("url") or r.get("download_url"), "format": r.get("format")} for r in package["resources"]]
    (OUT / "resources.json").write_text(json.dumps(resources, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("::notice title=KK resources::" + " | ".join(f"{r['name']}" for r in resources)[:3900])
    for r in resources:
        label = f"{r['name']} {urllib.parse.unquote(r['url'] or '')}"
        wanted = re.search(r"Erl(ä|ae)uterung", label) or (
            any(y in label for y in args.years) and not re.search(r"_EU|EU\.|CHEU|Bestand|Einzug|Eingeschr", label))
        if not wanted or not r["url"]:
            continue
        data = get(r["url"])
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(urllib.parse.unquote(urllib.parse.urlparse(r["url"]).query or r["url"])).name)
        name = name if "." in name else re.sub(r"[^A-Za-z0-9._-]+", "_", r["name"]) + "." + (r["format"] or "bin").lower()
        store(name, data, r["url"], manifest)
    for year, url in REGION_LISTS.items():
        store(f"praemienregionen-{year}.xlsx", get(url), url, manifest)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
