"""
Unit tests for URL Discovery, Filters, and Raw Crawler logic.
"""

from pathlib import Path
import pytest

from src.crawlers.url_discoverer import UrlDiscoverer, SEED_ENTRIES
from src.crawlers.raw_crawler import RawCrawler


def test_url_discoverer_seeds():
    discoverer = UrlDiscoverer()
    urls = discoverer.discover_urls(include_dynamic=False)
    assert len(urls) > 0
    # Ensure no motorbike or external pricing
    for item in urls:
        assert item["category"] != "gia_ca_lan_banh"
        title = item["title"].lower()
        assert not any(k in title for k in ["xe máy", "xe-may", "klara", "feliz", "evo", "scooter"])


def test_url_discoverer_validation():
    # Motorbike rejected
    assert not UrlDiscoverer.is_valid_entry("Bảng giá xe máy điện Klara", "https://vinfastauto.com/klara", "thong_so_ky_thuat")
    # Web pricing rejected (must use API snapshot)
    assert not UrlDiscoverer.is_valid_entry("Giá xe VF 8 lăn bánh tại Hà Nội", "https://oto.com.vn/gia-xe", "gia_ca_lan_banh")
    # Non-vinfast specs rejected
    assert not UrlDiscoverer.is_valid_entry("Thông số VF 8", "https://oto.com.vn/thong-so-vf8", "thong_so_ky_thuat")
    # Valid VinFast specs admitted
    assert UrlDiscoverer.is_valid_entry("Thông số VF 8", "https://vinfastauto.com/vn_vi/dat-coc-xe-vf8", "thong_so_ky_thuat")
    # Valid external review admitted
    assert UrlDiscoverer.is_valid_entry("Đánh giá xe VF 8", "https://xehay.vn/danh-gia-vf8.html", "trai_nghiem_danh_gia")


def test_url_discoverer_export(tmp_path: Path):
    target_csv = tmp_path / "sources.csv"
    discoverer = UrlDiscoverer()
    count = discoverer.export_to_csv(target_csv)
    assert count > 0
    assert target_csv.exists()
