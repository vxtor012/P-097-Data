"""
Unified Pre-RAG Orchestrator.
Coordinates the entire lifecycle:
[Raw Crawl] -> Bronze Ingestion -> Silver Normalization & Hierarchical Chunking -> Gold Consultation Filtering.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DEFAULT_CONFIG, PipelineConfig
from .crawlers.raw_crawler import CrawlReport, RawCrawler
from .crawlers.url_discoverer import UrlDiscoverer
from .bronze_to_silver import BronzeToSilverPipeline
from .silver_to_gold import SilverToGoldPipeline

logger = logging.getLogger(__name__)


class PreRAGPipeline:
    """Master orchestrator for the Vietnamese Automotive Pre-RAG pipeline."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.crawler = RawCrawler(
            bronze_dir=self.config.bronze_dir,
            pdf_dir=self.config.pdf_dir,
        )
        self.url_discoverer = UrlDiscoverer()
        self.silver_pipeline = BronzeToSilverPipeline(config=self.config)
        self.gold_pipeline = SilverToGoldPipeline(config=self.config)

    def crawl(
        self,
        include_dynamic_urls: bool = False,
        sources_csv: Optional[Path] = None,
    ) -> CrawlReport:
        """Executes raw crawling stage into Bronze and PDF directories."""
        target_csv = sources_csv or self.config.sources_csv
        if not target_csv.exists():
            logger.info("Generating default sources CSV at %s...", target_csv)
            self.url_discoverer.export_to_csv(target_csv, include_dynamic=include_dynamic_urls)

        logger.info("Crawling raw assets into Bronze (%s) and PDF (%s)...", self.config.bronze_dir, self.config.pdf_dir)
        report = self.crawler.crawl_all(sources_csv=target_csv)
        return report

    def run_silver(self):
        """Runs the Bronze-to-Silver transformation and hierarchical chunking."""
        logger.info("Executing Bronze-to-Silver transformation...")
        return self.silver_pipeline.run()

    def run_gold(self) -> Dict[str, Any]:
        """Runs the Silver-to-Gold car purchasing consultation filtering."""
        logger.info("Executing Silver-to-Gold consultation filtering...")
        return self.gold_pipeline.run()

    def run_all(
        self,
        crawl_first: bool = False,
        include_dynamic_urls: bool = False,
    ) -> Dict[str, Any]:
        """Runs the complete end-to-end Pre-RAG pipeline: [Crawl ->] Silver -> Gold."""
        start_time = time.time()
        start_iso = datetime.now(timezone.utc).isoformat()
        logger.info("Starting complete Pre-RAG pipeline...")

        crawl_summary = None
        if crawl_first:
            crawl_summary = self.crawl(include_dynamic_urls=include_dynamic_urls)

        silver_report = self.run_silver()
        gold_report = self.run_gold()

        elapsed = round(time.time() - start_time, 2)
        summary = {
            "pipeline": "WeKnora Pre-RAG Complete Pipeline",
            "started_at": start_iso,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed,
            "crawl_report": crawl_summary.__dict__ if crawl_summary else "skipped (used existing Bronze/PDF)",
            "silver_documents": silver_report.total_silver_documents,
            "silver_chunks": silver_report.total_silver_chunks,
            "gold_documents": gold_report.get("total_gold_documents", 0),
            "gold_chunks": gold_report.get("total_gold_chunks", 0),
            "filtered_out_chunks": gold_report.get("filtered_out_chunks", 0),
            "retention_rate_percent": gold_report.get("retention_rate_percent", 0.0),
        }
        logger.info("Pre-RAG Pipeline completed in %.2fs!", elapsed)
        return summary
