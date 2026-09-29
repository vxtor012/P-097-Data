"""Package chứa các module crawler cho dữ liệu VinFast Auto, V-GREEN và External Sources."""

from __future__ import annotations

from src.data_pipeline.crawlers.external_sources_crawler import run_external_sources_crawl
from src.data_pipeline.crawlers.faq_crawler import run_faq_crawl
from src.data_pipeline.crawlers.news_crawler import run_news_crawl
from src.data_pipeline.crawlers.policy_crawler import run_policy_crawl
from src.data_pipeline.crawlers.relational_crawler import run_relational_crawl
from src.data_pipeline.crawlers.specs_crawler import run_specs_crawl
from src.data_pipeline.crawlers.vgreen_crawler import run_vgreen_crawl

__all__ = [
    "run_relational_crawl",
    "run_faq_crawl",
    "run_policy_crawl",
    "run_news_crawl",
    "run_specs_crawl",
    "run_vgreen_crawl",
    "run_external_sources_crawl",
]
