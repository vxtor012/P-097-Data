"""
Raw Ingestion Crawler for Vietnamese Automotive Data (Bronze & PDF Layers).
Collects official VinFast API pricing, FAQ HTML, promotional news, brochures, and external verified sources.
"""

from __future__ import annotations

import csv
import http.cookiejar
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.crawlers.url_discoverer import DEFAULT_USER_AGENT, MOTORBIKE_KEYWORDS, SEED_ENTRIES

logger = logging.getLogger(__name__)

VINFAST_ROLLING_API = (
    "https://shop.vinfastauto.com/on/demandware.store/Sites-app_vinfast_vn-Site/vi_VN/"
    "RollingUpCost-GetInfoRolling"
)
VINFAST_ROLLING_PAGE = "https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh"
VINFAST_FAQ_PAGE = "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap"

VINFAST_BROCHURE_TARGETS = [
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 3",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/16062026-Brochure-VF-3.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf3.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 6",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/14052026/VF%206_Brochure_Final_130526%20(12AM)_compressed.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf6.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 7",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/10042026-Brochur-%20VF-7.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf7.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 8",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF8_Brochure_03022026.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf8.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 8 The All New",
        "url": "https://static-cms-prod.vinfastauto.com/brochure/26052026/VF%208%20The%20he%20moi_Brochure_final%2020.05.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf8_the_all_new.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 9",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF%209_%20Brochure.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf9.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast EC Van",
        "url": "https://static-cms-prod.vinfastauto.com/brochure-ec-van-040726-e.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_ecvan.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF MPV 7",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/05022026-Brochure-VF-MPV-7.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf_mpv7.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast Herio Green",
        "url": "https://static-cms-prod.vinfastauto.com/06082025-brochure-herio.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_herio_green.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast Limo Green",
        "url": "https://static-cms-prod.vinfastauto.com/09012026-brochure-limo-green.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_limo_green.pdf",
    },
]

VINFAST_POLICY_PAGES = [
    "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/",
    "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-oto",
]


@dataclass
class CrawlReport:
    relational_status: str = "skipped"
    relational_bytes: int = 0
    faq_status: str = "skipped"
    faq_bytes: int = 0
    promos_crawled: int = 0
    pdf_count: int = 0
    sources_crawled: int = 0
    elapsed_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


class RawCrawler:
    """Manages downloading and updating Bronze layer raw artifacts and PDF documents."""

    def __init__(self, bronze_dir: Path, pdf_dir: Path):
        self.bronze_dir = Path(bronze_dir)
        self.pdf_dir = Path(pdf_dir)

        self.vinfast_dir = self.bronze_dir / "vinfast"
        self.webscraping_dir = self.bronze_dir / "web_scraping"
        self.relational_dir = self.vinfast_dir / "relational"
        self.faq_dir = self.vinfast_dir / "faq"
        self.vinfast_articles_dir = self.vinfast_dir / "articles"
        self.webscraping_html_dir = self.webscraping_dir / "raw_html"

        self.pdf_legal_dir = self.pdf_dir / "thu_tuc_phap_ly"
        self.pdf_specs_dir = self.pdf_dir / "thong_so_ky_thuat"
        self.pdf_promo_dir = self.pdf_dir / "chinh_sach_uu_dai"

    @staticmethod
    def fetch_url(url: str, timeout: int = 10) -> str:
        """Downloads text from URL using curl if available, otherwise urllib."""
        cmd = [
            "curl.exe", "-4", "-sL", "--http1.1", "--compressed",
            "-m", str(timeout), url,
            "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
            "-H", "Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        ]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout + 2
            )
            if res.returncode == 0 and res.stdout and len(res.stdout) > 100:
                return res.stdout
        except Exception:
            pass

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("urllib request to %s failed: %s", url, e)
            return ""

    @staticmethod
    def download_pdf(url: str, target_path: Path, timeout: int = 20) -> bool:
        """Downloads a binary PDF and verifies %PDF header."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        clean_url = urllib.parse.quote(url, safe=":/%?=&+")
        cmd = [
            "curl.exe", "-4", "-sL", "--http1.1",
            "-m", str(timeout), clean_url,
            "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
            "-o", str(target_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=timeout + 3)
            if target_path.exists() and target_path.stat().st_size > 1000:
                with open(target_path, "rb") as f:
                    header = f.read(10)
                if header.startswith(b"%PDF"):
                    return True
            target_path.unlink(missing_ok=True)
        except Exception:
            if target_path.exists():
                target_path.unlink(missing_ok=True)
        return False

    def crawl_relational_pricing(self) -> Dict[str, Any]:
        """Queries VinFast rolling cost API and saves snapshot into Bronze."""
        self.relational_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = self.relational_dir / "vinfast_rolling_raw_snapshot.json"

        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": VINFAST_ROLLING_PAGE,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        try:
            handshake = urllib.request.Request(VINFAST_ROLLING_PAGE, headers={"User-Agent": DEFAULT_USER_AGENT})
            with opener.open(handshake, timeout=12) as _:
                pass
        except Exception as e:
            logger.debug("Handshake to rolling page notice: %s", e)

        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(VINFAST_ROLLING_API, headers=headers)
                with opener.open(req, timeout=20) as resp:
                    content = resp.read().decode("utf-8")
                    data = json.loads(content)
                    if isinstance(data, dict) and ("vehicles" in data or "objects" in data):
                        with open(snapshot_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        logger.info("Successfully fetched live VinFast pricing API (%d bytes)", len(content))
                        return {"status": "success", "bytes": len(content), "file": str(snapshot_file)}
            except Exception as err:
                logger.warning("VinFast pricing API attempt %d failed: %s", attempt, err)
                time.sleep(1)

        if snapshot_file.exists():
            logger.info("Using cached relational snapshot: %s", snapshot_file.name)
            return {"status": "cached", "bytes": snapshot_file.stat().st_size, "file": str(snapshot_file)}

        return {"status": "failed", "bytes": 0}

    def crawl_faq(self) -> Dict[str, Any]:
        """Downloads official VinFast FAQ HTML."""
        self.faq_dir.mkdir(parents=True, exist_ok=True)
        faq_file = self.faq_dir / "vinfast_faq_raw.html"

        html = self.fetch_url(VINFAST_FAQ_PAGE, timeout=15)
        if html and len(html) > 500:
            with open(faq_file, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("Saved raw VinFast FAQ HTML (%d chars)", len(html))
            return {"status": "success", "bytes": len(html), "file": str(faq_file)}

        if faq_file.exists():
            return {"status": "cached", "bytes": faq_file.stat().st_size, "file": str(faq_file)}

        return {"status": "failed", "bytes": 0}

    def crawl_promotions(self, max_pages: int = 2) -> List[Dict[str, Any]]:
        """Downloads official EV promotion articles into Bronze."""
        self.vinfast_articles_dir.mkdir(parents=True, exist_ok=True)
        entries: List[Dict[str, Any]] = []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not installed, skipping promotion crawl")
            return entries

        promo_links: List[Dict[str, str]] = []
        for page in range(0, max_pages):
            page_url = f"https://vinfastauto.com/vn_vi/uu-dai?page={page}" if page > 0 else "https://vinfastauto.com/vn_vi/uu-dai"
            html = self.fetch_url(page_url, timeout=12)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                title = a.get_text(strip=True)
                if any(k in href.lower() or k in title.lower() for k in MOTORBIKE_KEYWORDS):
                    continue
                if any(k in href for k in ["uu-dai", "khuyen-mai", "chuong-trinh", "vi-tuong-lai-xanh"]) and href not in ["/vn_vi/uu-dai", "https://vinfastauto.com/vn_vi/uu-dai"]:
                    full_url = f"https://vinfastauto.com{href}" if href.startswith("/") else href
                    promo_links.append({"url": full_url, "title": title or href.split("/")[-1]})

        for item in promo_links:
            url = item["url"]
            title = item["title"]
            slug = re.sub(r"[^a-zA-Z0-9_]+", "_", url.split("/")[-1].replace(".html", "")).strip("_")
            filename = f"vinfastauto_com_vn_vi_{slug}.html"
            dest = self.vinfast_articles_dir / filename

            if not dest.exists():
                art_html = self.fetch_url(url, timeout=12)
                if art_html and len(art_html) > 500:
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(art_html)
                    entries.append({"title": title, "url": url, "file": filename, "bytes": len(art_html)})
                    time.sleep(0.3)
            else:
                entries.append({"title": title, "url": url, "file": filename, "bytes": dest.stat().st_size})

        # Update manifest
        manifest_file = self.vinfast_dir / "vinfast_sources_manifest.json"
        existing = []
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        seen_files = {e.get("file") for e in existing}
        for item in entries:
            if item["file"] not in seen_files:
                existing.append({
                    "title": item["title"],
                    "url": item["url"],
                    "category": "chinh_sach_uu_dai",
                    "domain": "vinfastauto.com",
                    "file": item["file"],
                    "bytes": item["bytes"],
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                })
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        return entries

    def crawl_brochures_and_policies(self) -> Dict[str, Any]:
        """Downloads vehicle brochures and updates the PDF manifest."""
        self.pdf_specs_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_promo_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_legal_dir.mkdir(parents=True, exist_ok=True)

        # Download missing vehicle brochures
        downloaded_brochures = 0
        for item in VINFAST_BROCHURE_TARGETS:
            dest = self.pdf_specs_dir / item["filename"]
            if not dest.exists():
                if self.download_pdf(item["url"], dest, timeout=20):
                    downloaded_brochures += 1

        # Recompile PDF manifest
        manifest: List[Dict[str, Any]] = []
        for f in sorted(self.pdf_legal_dir.glob("*.pdf")):
            if f.stat().st_size > 1000:
                manifest.append({
                    "title": f.stem.replace("_", " ").title(),
                    "category": "thu_tuc_phap_ly",
                    "relative_path": f"dataset/pdf/thu_tuc_phap_ly/{f.name}",
                    "size_bytes": f.stat().st_size,
                    "type": "legal_document",
                })
        for f in sorted(self.pdf_specs_dir.glob("*.pdf")):
            if f.stat().st_size > 1000:
                manifest.append({
                    "title": f.stem.replace("_", " ").title(),
                    "category": "thong_so_ky_thuat",
                    "relative_path": f"dataset/pdf/thong_so_ky_thuat/{f.name}",
                    "size_bytes": f.stat().st_size,
                    "type": "vehicle_brochure",
                })
        for f in sorted(self.pdf_promo_dir.glob("*.pdf")):
            if f.stat().st_size > 1000:
                manifest.append({
                    "title": f.stem.replace("_", " ").title(),
                    "category": "chinh_sach_uu_dai",
                    "relative_path": f"dataset/pdf/chinh_sach_uu_dai/{f.name}",
                    "size_bytes": f.stat().st_size,
                    "type": "policy_document_2026_ev",
                })

        with open(self.pdf_dir / "pdf_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        vinfast_manifest = self.vinfast_dir / "vinfast_pdf_manifest.json"
        with open(vinfast_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return {"total_pdfs": len(manifest), "new_brochures": downloaded_brochures}

    def crawl_sources(self, sources_csv: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Downloads external verified articles and saves into Bronze."""
        self.vinfast_articles_dir.mkdir(parents=True, exist_ok=True)
        self.webscraping_html_dir.mkdir(parents=True, exist_ok=True)

        records: List[Dict[str, str]] = []
        if sources_csv and sources_csv.exists():
            with open(sources_csv, "r", encoding="utf-8-sig", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = (row.get("title") or row.get("Title") or "").strip()
                    url = (row.get("url") or row.get("Url") or "").strip()
                    cat = (row.get("category") or row.get("Category") or "trai_nghiem_danh_gia").strip()
                    if url and title:
                        records.append({"title": title, "url": url, "category": cat})
        else:
            records = [s for s in SEED_ENTRIES if s.get("category") != "thong_so_ky_thuat" or "vinfast" in s.get("url", "")]

        crawled: List[Dict[str, Any]] = []
        for idx, item in enumerate(records, 1):
            title = item["title"]
            url = item["url"]
            category = item["category"]

            # Skip external pricing to avoid conflicts
            if category == "gia_ca_lan_banh":
                continue

            # Skip external law sites (authentic legal PDFs are manually managed in dataset/pdf/thu_tuc_phap_ly)
            if "luatvietnam" in url.lower() or "thuvienphapluat" in url.lower():
                continue

            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.replace("www.", "").lower()
            path_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", parsed.path.strip("/")).strip("_")
            domain_slug = domain.replace(".", "_")
            slug = f"{domain_slug}_{path_slug}" if path_slug else domain_slug

            is_vinfast = "vinfast" in domain
            dest_dir = self.vinfast_articles_dir if is_vinfast else self.webscraping_html_dir
            dest_file = dest_dir / f"{slug}.html"

            if not dest_file.exists():
                html = self.fetch_url(url, timeout=12)
                if html and len(html) > 300:
                    with open(dest_file, "w", encoding="utf-8") as f:
                        f.write(html)
                    crawled.append({"title": title, "url": url, "file": dest_file.name, "category": category})
                    time.sleep(0.3)
            else:
                crawled.append({"title": title, "url": url, "file": dest_file.name, "category": category})

        return crawled

    def crawl_all(self, sources_csv: Optional[Path] = None) -> CrawlReport:
        """Executes all ingestion stages and returns summary report."""
        start_time = time.time()
        report = CrawlReport()

        logger.info("Ingesting VinFast API pricing snapshot...")
        rel = self.crawl_relational_pricing()
        report.relational_status = rel.get("status", "failed")
        report.relational_bytes = rel.get("bytes", 0)

        logger.info("Ingesting VinFast FAQ...")
        faq = self.crawl_faq()
        report.faq_status = faq.get("status", "failed")
        report.faq_bytes = faq.get("bytes", 0)

        logger.info("Ingesting EV promotions...")
        promos = self.crawl_promotions(max_pages=2)
        report.promos_crawled = len(promos)

        logger.info("Updating vehicle brochures and PDF manifest...")
        pdfs = self.crawl_brochures_and_policies()
        report.pdf_count = pdfs.get("total_pdfs", 0)

        logger.info("Ingesting verified sources...")
        sources = self.crawl_sources(sources_csv)
        report.sources_crawled = len(sources)

        report.elapsed_seconds = round(time.time() - start_time, 2)
        return report
