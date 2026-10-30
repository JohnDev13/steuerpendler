"""Fetch the official basic health-insurance premium data (BAG, priminfo/opendata.swiss) and the BAG lists of
Gemeinden by premium region. Runs in GitHub Actions (network); writes data/kk/raw/ and data/kk/raw/manifest.json
with the source URL, SHA-256 and size of every file. Standard library only.

    python3 scripts/kk/fetch.py --years 2026 2027
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import zipfile
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


CSV_WANTED = ("Prämien_CH.csv", "Tarife.csv", "Einzugsgebiete.csv", "Eingeschr.-Tät.gebiete.csv", "Versichertenbestand_CH.csv")


def year_of(data: bytes) -> str:
    """Premium year (Geschäftsjahr) of a premium CSV."""
    text = data.decode("utf-8-sig")
    head = text.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if head.count(";") > head.count(",") else ",")
    return str(next(reader)["Geschäftsjahr"]).strip()


def store_csv(name: str, data: bytes, source: str, manifest: list[dict]) -> None:
    sha = hashlib.sha256(data).hexdigest()
    path = OUT / (name + ".gz")
    with gzip.open(path, "wb", mtime=0) as f:
        f.write(data)
    manifest.append({"file": path.name, "source": source, "sha256": sha, "bytes": len(data), "gzipped": True})
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
    print(f"KK resources: {len(resources)}")
    by_name = {}
    for r in resources:
        try:
            name = json.loads(r["name"]).get("en") if r["name"].startswith("{") else r["name"]
        except ValueError:
            name = r["name"]
        by_name[name] = r["url"]
    # Current files (the newest premium year) and the archive of every requested older year.
    current = {n: by_name[n] for n in CSV_WANTED if n in by_name}
    year = year_of(get(current["Prämien_CH.csv"])) if "Prämien_CH.csv" in current else None
    for n, url in current.items():
        data = get(url)
        if year in args.years:
            store_csv(f"{year}-{n.replace('ä', 'ae').replace('Ä', 'Ae')}", data, url, manifest)
    for y in args.years:
        if y == year or f"Archiv_Praemien_{y}.zip" not in by_name:
            continue
        url = by_name[f"Archiv_Praemien_{y}.zip"]
        blob = get(url)
        manifest.append({"file": f"Archiv_Praemien_{y}.zip (not stored)", "source": url, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for info in z.infolist():
                fixed = info.filename.encode("cp437").decode("utf-8") if info.flag_bits & 0x800 == 0 else info.filename
                fixed = fixed.replace("#U00e4", "ä")
                if Path(fixed).name in CSV_WANTED:
                    store_csv(f"{y}-{Path(fixed).name.replace('ä', 'ae')}", z.read(info), f"{url} :: {info.filename}", manifest)
    for year, url in REGION_LISTS.items():
        store(f"praemienregionen-{year}.xlsx", get(url), url, manifest)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
