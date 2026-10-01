"""
Master Bronze-to-Silver ETL pipeline orchestrator.
Handles multi-source ingestion, Vietnamese NLP normalization, quality assurance,
deduplication, hierarchical chunking, and silver storage.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from src.chunking.hierarchical_chunker import HierarchicalChunker
from src.config import PipelineConfig, DEFAULT_CONFIG
from src.extractors.faq_extractor import FAQExtractor
from src.extractors.html_article_extractor import HTMLArticleExtractor
from src.extractors.pdf_extractor import PDFExtractor
from src.extractors.relational_extractor import RelationalExtractor
from src.models.schemas import (
    BronzeDocument,
    SilverChunk,
    SilverDocument,
    SilverFAQItem,
    SilverReport,
    SilverVehicle,
)
from src.nlp.vietnamese_normalizer import VietnameseNormalizer
from src.nlp.vietnamese_quality import VietnameseQualityScorer, strip_vietnamese_boilerplate
from src.storage.silver_writer import SilverWriter

logger = logging.getLogger(__name__)


class BronzeToSilverPipeline:
    """End-to-end data pipeline transforming raw bronze data into standardized silver datasets."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.normalizer = VietnameseNormalizer()
        self.quality_scorer = VietnameseQualityScorer(
            min_diacritic_ratio=self.config.min_vietnamese_diacritic_ratio,
            min_doc_len=self.config.min_doc_length,
        )
        self.chunker = HierarchicalChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            min_chunk_length=self.config.min_chunk_length,
        )
        self.writer = SilverWriter(silver_dir=self.config.silver_dir)

    def run(self) -> SilverReport:
        """Executes the full Bronze-to-Silver transformation."""
        start_time = time.time()
        start_iso = datetime.now(timezone.utc).isoformat()
        logger.info("Starting Bronze-to-Silver Pipeline execution...")

        # 1. Initialize Extractors
        html_extractor = HTMLArticleExtractor(bronze_dir=self.config.bronze_dir)
        faq_extractor = FAQExtractor(bronze_dir=self.config.bronze_dir)
        relational_extractor = RelationalExtractor(bronze_dir=self.config.bronze_dir)
        pdf_extractor = PDFExtractor(pdf_dir=self.config.pdf_dir)

        # 2. Extract Bronze Documents
        raw_documents: List[BronzeDocument] = []

        logger.info("Extracting HTML articles...")
        raw_documents.extend(list(html_extractor.extract_all()))

        logger.info("Extracting FAQ accordions...")
        raw_documents.extend(list(faq_extractor.extract_all()))
        faq_items: List[SilverFAQItem] = faq_extractor.get_structured_faq_items()

        logger.info("Extracting Relational pricing snapshot...")
        raw_documents.extend(list(relational_extractor.extract_all()))
        vehicles: List[SilverVehicle] = relational_extractor.get_structured_vehicles()
        relational_tables: Dict[str, List[Dict[str, Any]]] = relational_extractor.get_relational_tables(cars_only=False)

        logger.info("Extracting PDF documents...")
        raw_documents.extend(list(pdf_extractor.extract_all()))

        total_bronze_records = len(raw_documents)
        logger.info("Extracted %d raw Bronze documents in total", total_bronze_records)

        # 3. Process, Normalize, Quality Score, and Deduplicate Documents
        silver_documents: List[SilverDocument] = []
        silver_chunks: List[SilverChunk] = []
        seen_hashes = set()
        duplicates_count = 0
        low_quality_count = 0

        source_counter = Counter()
        category_counter = Counter()
        quality_scores = []

        for bronze_doc in raw_documents:
            source_counter[bronze_doc.source_type] += 1
            category_counter[bronze_doc.category or "general"] += 1

            raw_text = bronze_doc.raw_content or ""
            if not raw_text.strip():
                low_quality_count += 1
                continue

            # Strip web boilerplate
            clean_text = strip_vietnamese_boilerplate(raw_text)

            # Apply Vietnamese NLP Normalization (Unicode NFC, Tones, Typography)
            clean_markdown = self.normalizer.normalize(clean_text)

            # Title normalization
            clean_title = self.normalizer.normalize(bronze_doc.title or "Tài liệu không tiêu đề")

            # Check quality
            quality_score, quality_meta = self.quality_scorer.evaluate(clean_markdown, clean_title)
            if not quality_meta["passed"]:
                logger.debug("Filtered out low quality doc: %s (reason: %s)", bronze_doc.raw_id, quality_meta.get("reason"))
                low_quality_count += 1
                continue

            # Deduplication check
            content_checksum = hashlib.sha256(clean_markdown.encode("utf-8")).hexdigest()
            if self.config.enable_deduplication:
                if content_checksum in seen_hashes:
                    duplicates_count += 1
                    continue
                seen_hashes.add(content_checksum)

            quality_scores.append(quality_score)
            doc_id = f"doc_{content_checksum[:16]}"

            # Plain text representation for lexical search
            plain_text = " ".join([line.strip("#* -|>") for line in clean_markdown.split("\n") if line.strip()])

            silver_doc = SilverDocument(
                doc_id=doc_id,
                source_id=bronze_doc.raw_id,
                source_type=bronze_doc.source_type,
                title=clean_title,
                category=bronze_doc.category or "general",
                domain=bronze_doc.domain,
                url=bronze_doc.url,
                language=self.config.target_language,
                content_clean_markdown=clean_markdown,
                content_plain_text=plain_text,
                word_count=len(plain_text.split()),
                char_count=len(clean_markdown),
                token_estimate=len(clean_markdown.split()),
                diacritic_ratio=quality_meta["diacritic_ratio"],
                quality_score=quality_score,
                checksum_sha256=content_checksum,
                metadata=bronze_doc.raw_metadata,
            )
            silver_documents.append(silver_doc)

            # 4. Generate Semantic Hierarchical Chunks
            doc_chunks = self.chunker.chunk_document(
                doc_id=doc_id,
                markdown_text=clean_markdown,
                category=silver_doc.category,
                source_type=silver_doc.source_type,
                url=silver_doc.url,
            )
            silver_chunks.extend(doc_chunks)

        # 5. Normalize FAQ items and Vehicles
        normalized_faq_items: List[SilverFAQItem] = []
        for item in faq_items:
            norm_q = self.normalizer.normalize(item.question)
            norm_a = self.normalizer.normalize(item.answer)
            norm_a_md = self.normalizer.normalize(item.answer_markdown)
            item.question = norm_q
            item.answer = norm_a
            item.answer_markdown = norm_a_md
            normalized_faq_items.append(item)

        normalized_vehicles: List[SilverVehicle] = []
        for v in vehicles:
            v.searchable_markdown = self.normalizer.normalize(v.searchable_markdown)
            normalized_vehicles.append(v)

        # 6. Persist Silver Outputs
        logger.info("Persisting Silver datasets to %s...", self.config.silver_dir)
        self.writer.write_documents(silver_documents)
        self.writer.write_chunks(silver_chunks)
        self.writer.write_faq_items(normalized_faq_items)
        self.writer.write_vehicles(normalized_vehicles)
        self.writer.write_rdb_schema(relational_tables)

        end_time = time.time()
        elapsed = round(end_time - start_time, 2)
        avg_quality = round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else 0.0
        avg_tokens = (
            round(sum(c.token_estimate for c in silver_chunks) / len(silver_chunks), 1)
            if silver_chunks
            else 0.0
        )

        report = SilverReport(
            pipeline_version="1.0.0",
            started_at=start_iso,
            completed_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=elapsed,
            total_bronze_records=total_bronze_records,
            total_silver_documents=len(silver_documents),
            total_silver_chunks=len(silver_chunks),
            total_faq_items=len(normalized_faq_items),
            total_vehicles=len(normalized_vehicles),
            duplicates_filtered=duplicates_count,
            low_quality_filtered=low_quality_count,
            language_distribution={"vi": len(silver_documents)},
            source_distribution=dict(source_counter),
            category_distribution=dict(category_counter),
            average_quality_score=avg_quality,
            average_token_count_per_chunk=avg_tokens,
        )

        self.writer.write_report(report)
        logger.info("Pipeline execution completed in %.2fs!", elapsed)
        return report
