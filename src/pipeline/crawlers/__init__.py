"""
Crawlers and Ingestion module for Vietnamese Automotive Pre-RAG Pipeline.
"""

from .url_discoverer import UrlDiscoverer, SEED_ENTRIES
from .raw_crawler import RawCrawler, CrawlReport

__all__ = [
    "UrlDiscoverer",
    "SEED_ENTRIES",
    "RawCrawler",
    "CrawlReport",
]
