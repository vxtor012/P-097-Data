"""
Silver-to-Gold Pipeline Orchestrator.
Screens out non-automotive legalities, general traffic regulations, and penalties,
extracting a curated, high-precision Gold knowledge base specialized in
Car Purchasing Consultation (Tư vấn Mua bán xe & Pháp lý sở hữu xe).
"""

from collections import Counter
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from src.config import PipelineConfig, DEFAULT_CONFIG
from src.extractors.relational_extractor import RelationalExtractor
from src.filters.gold_filter import GoldConsultationFilter
from src.models.schemas import SilverChunk, SilverDocument, SilverFAQItem, SilverVehicle
from src.storage.gold_writer import GoldWriter

logger = logging.getLogger(__name__)


class SilverToGoldPipeline:
    """Pipeline transforming Silver dataset into car-purchasing specialized Gold layer."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.gold_filter = GoldConsultationFilter()
        self.writer = GoldWriter(gold_dir=self.config.gold_dir)

    def run(self) -> Dict[str, Any]:
        """Runs the Silver to Gold filtering and curation."""
        start_time = time.time()
        start_iso = datetime.now(timezone.utc).isoformat()
        logger.info("Starting Silver-to-Gold Pipeline execution...")

        silver_dir = self.config.silver_dir
        chunks_file = silver_dir / "silver_chunks.jsonl"
        docs_file = silver_dir / "silver_documents.jsonl"
        faq_file = silver_dir / "silver_faq.jsonl"
        vehicles_file = silver_dir / "silver_vehicles.jsonl"

        if not chunks_file.exists():
            raise FileNotFoundError(f"Silver chunks file missing at {chunks_file}. Run Silver pipeline first.")

        # 1. Load Silver Chunks
        silver_chunks: List[SilverChunk] = []
        with open(chunks_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    silver_chunks.append(SilverChunk(**data))
        logger.info("Loaded %d Silver chunks", len(silver_chunks))

        # 2. Filter and Tag Gold Chunks
        gold_chunks: List[SilverChunk] = []
        dropped_reasons = Counter()
        topic_distribution = Counter()

        for chunk in silver_chunks:
            admitted, topic, score, reason = self.gold_filter.evaluate_chunk(chunk)
            if admitted:
                # Enrich chunk metadata with gold annotations
                chunk.metadata["gold_topic"] = topic
                chunk.metadata["consultation_score"] = score
                gold_chunks.append(chunk)
                topic_distribution[topic] += 1
            else:
                dropped_reasons[reason] += 1

        logger.info(
            "Admitted %d Gold chunks, filtered out %d irrelevant chunks",
            len(gold_chunks),
            len(silver_chunks) - len(gold_chunks),
        )

        # 3. Load and Filter Silver Documents
        admitted_doc_ids = set(c.doc_id for c in gold_chunks)
        gold_documents: List[SilverDocument] = []
        if docs_file.exists():
            with open(docs_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        doc_data = json.loads(line)
                        doc = SilverDocument(**doc_data)
                        if doc.doc_id in admitted_doc_ids:
                            gold_documents.append(doc)
                        else:
                            # Evaluate document directly
                            admitted, topic, score, reason = self.gold_filter.evaluate_document(doc)
                            if admitted:
                                gold_documents.append(doc)

        logger.info("Admitted %d Gold documents", len(gold_documents))

        # 4. Load FAQ items (100% relevant to customer consultation)
        gold_faq: List[SilverFAQItem] = []
        if faq_file.exists():
            with open(faq_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        gold_faq.append(SilverFAQItem(**json.loads(line)))

        # 5. Load Vehicles (100% relevant to pricing & quotes)
        gold_vehicles: List[SilverVehicle] = []
        if vehicles_file.exists():
            with open(vehicles_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        gold_vehicles.append(SilverVehicle(**json.loads(line)))

        # 6. Persist Gold Datasets
        self.writer.write_chunks(gold_chunks)
        self.writer.write_documents(gold_documents)
        self.writer.write_faq_items(gold_faq)
        self.writer.write_vehicles(gold_vehicles)

        # 7. Persist Gold Relational RDB Schema (Electric Cars only)
        relational_extractor = RelationalExtractor(bronze_dir=self.config.bronze_dir)
        gold_rdb_tables = relational_extractor.get_relational_tables(cars_only=True)
        self.writer.write_rdb_schema(gold_rdb_tables)

        end_time = time.time()
        elapsed = round(end_time - start_time, 2)

        report = {
            "pipeline_stage": "silver_to_gold",
            "target_domain": "Tư vấn mua bán xe & pháp lý sở hữu xe (Car Purchasing Consultation)",
            "started_at": start_iso,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed,
            "total_silver_chunks": len(silver_chunks),
            "total_gold_chunks": len(gold_chunks),
            "filtered_out_chunks": len(silver_chunks) - len(gold_chunks),
            "retention_rate_percent": round(len(gold_chunks) / len(silver_chunks) * 100, 2),
            "total_gold_documents": len(gold_documents),
            "total_gold_faq": len(gold_faq),
            "total_gold_vehicles": len(gold_vehicles),
            "gold_topic_distribution": dict(topic_distribution),
            "top_filter_reasons": dict(dropped_reasons.most_common(10)),
        }

        self.writer.write_report(report)
        logger.info("Silver-to-Gold completed in %.2fs!", elapsed)
        return report
