"""
Gold dataset writer.
Saves filtered, consultation-specialized Gold artifacts and audit report.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from src.models.schemas import (
    SilverChunk,
    SilverDocument,
    SilverFAQItem,
    SilverVehicle,
)

logger = logging.getLogger(__name__)


class GoldWriter:
    """Manages the persistence of clean, specialized Gold data layers."""

    def __init__(self, gold_dir: Path):
        self.gold_dir = Path(gold_dir)
        self.gold_dir.mkdir(parents=True, exist_ok=True)

    def write_documents(self, documents: List[SilverDocument]) -> Path:
        """Writes Gold documents to gold_documents.jsonl."""
        out_path = self.gold_dir / "gold_documents.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Saved %d Gold documents to %s", len(documents), out_path)
        return out_path

    def write_chunks(self, chunks: List[SilverChunk]) -> Path:
        """Writes Gold chunks to gold_chunks.jsonl."""
        out_path = self.gold_dir / "gold_chunks.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Saved %d Gold chunks to %s", len(chunks), out_path)
        return out_path

    def write_faq_items(self, faq_items: List[SilverFAQItem]) -> Path:
        """Writes Gold FAQ items to gold_faq.jsonl."""
        out_path = self.gold_dir / "gold_faq.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for item in faq_items:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Saved %d Gold FAQ items to %s", len(faq_items), out_path)
        return out_path

    def write_vehicles(self, vehicles: List[SilverVehicle]) -> Path:
        """Writes Gold vehicles to gold_vehicles.jsonl."""
        out_path = self.gold_dir / "gold_vehicles.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for v in vehicles:
                f.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Saved %d Gold vehicles to %s", len(vehicles), out_path)
        return out_path

    def write_report(self, report_dict: Dict[str, Any]) -> Path:
        """Writes audit metrics to gold_report.json."""
        out_path = self.gold_dir / "gold_report.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)
        logger.info("Saved Gold pipeline report to %s", out_path)
        return out_path

    def write_rdb_schema(self, tables: Dict[str, List[Dict[str, Any]]]) -> Path:
        """Writes structured relational tables as CSV files into rdb_schema/."""
        import csv
        rdb_dir = self.gold_dir / "rdb_schema"
        rdb_dir.mkdir(parents=True, exist_ok=True)

        for table_name, rows in tables.items():
            if not rows:
                continue
            csv_path = rdb_dir / f"{table_name}.csv"
            fieldnames = list(rows[0].keys())
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            logger.info("Saved %d rows to %s", len(rows), csv_path)

        return rdb_dir
