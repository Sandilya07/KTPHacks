#!/usr/bin/env python3
"""Download CMS NCCI PTP edits, MUE tables and the Medicare Physician Fee Schedule RVU file.

The quarter is pinned in audit/cms_data/config.json. Resolved URLs and download dates are written
to audit/cms_data/manifest.json. If cms.gov is unreachable the script fails loudly, says where to
put manually downloaded files, and keeps going with whatever is already on disk.

AMA license: the NCCI PTP files are served through an AMA (CPT) license click-through on cms.gov.
This script will NOT accept that license for you. Read it on the CMS page, then either download the
files yourself into the manual folder, or re-run with --accept-ama-license to confirm you have
accepted it and want the script to fetch them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
CMS_DIR = ROOT / "audit" / "cms_data"
FILES = CMS_DIR / "files"
UA = {"User-Agent": "medbill-auditor-research/0.2"}


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def zip_links(page_url: str) -> list[str]:
    html = http_get(page_url).decode("utf-8", "replace")
    links = re.findall(r'href="([^"]+\.zip[^"]*)"', html)
    out = []
    for link in links:
        link = re.sub(r"^/license/ama\?file=", "", link)  # direct path behind the license gate
        out.append(urljoin("https://www.cms.gov", link))
    return list(dict.fromkeys(out))


def safe_extract(data: bytes, dest: Path) -> list[str]:
    import io
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for m in z.infolist():
            target = (dest / m.filename).resolve()
            if m.is_dir() or not str(target).startswith(str(dest.resolve())):
                continue  # skip directories and path-traversal members
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(m))
            names.append(str(target.relative_to(ROOT)))
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accept-ama-license", action="store_true",
                    help="confirm you accepted the AMA/CPT license on cms.gov; fetch NCCI PTP files")
    args = ap.parse_args()
    cfg = json.loads((CMS_DIR / "config.json").read_text())
    slug, manual = cfg["quarter_slug"], ROOT / cfg["manual_folder"]
    jobs = {  # kind -> (page, url filter)
        "mue_practitioner": (cfg["pages"]["mue"], lambda u: slug in u and "practitioner" in u and "mue-table" in u),
        "mue_outpatient": (cfg["pages"]["mue"], lambda u: slug in u and "outpatient-hospital" in u and "mue-table" in u),
        "pfs": (cfg["pages"]["pfs"], lambda u: "rvu" in u.lower()),
    }
    if args.accept_ama_license:
        q = slug.replace("-", "")
        jobs["ncci_practitioner"] = (cfg["pages"]["ncci"], lambda u: q in u.replace("-", "") and "practitioner-ptp-edits" in u)
        jobs["ncci_hospital"] = (cfg["pages"]["ncci"], lambda u: q in u.replace("-", "") and "hospital-ptp-edits" in u)
    else:
        print("NOTE: skipping NCCI PTP files (AMA license click-through). See --help.\n")

    manifest = {"quarter": cfg["quarter"], "downloaded": dt.date.today().isoformat(), "datasets": {}}
    failed = False
    for kind, (page, keep) in jobs.items():
        try:
            urls = [u for u in zip_links(page) if keep(u)]
            if not urls:
                raise RuntimeError(f"no matching download links found on {page}")
            files = []
            for u in urls:
                print(f"[{kind}] {u}")
                files += safe_extract(http_get(u, timeout=300), FILES / kind)
            manifest["datasets"][kind] = {"source_page": page, "source_urls": urls, "files": files}
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:  # fail loudly, keep going
            failed = True
            print(f"\n!! FAILED to download '{kind}': {exc}", file=sys.stderr)
            print(f"   Download it manually from {page}\n   and unzip into: {FILES / kind}\n"
                  f"   (or drop the files in {manual}). Continuing.\n", file=sys.stderr)
    if not args.accept_ama_license:
        manifest["datasets"]["ncci_note"] = ("NCCI PTP files not fetched: AMA license not accepted via this "
                                             "script. Place manually downloaded files in files/ncci_practitioner/.")
    (CMS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Manifest written to {CMS_DIR / 'manifest.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
