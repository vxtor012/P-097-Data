"""
Pipeline configuration module.
Contains paths, hyperparameters, quality thresholds, and defaults.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def find_workspace_root() -> Path:
    """Dynamically resolves workspace root containing the dataset/ directory."""
    curr = Path(__file__).resolve().parent
    for _ in range(5):
        if (curr / "dataset").is_dir():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent
    # Fallback: src/pipeline/config.py -> parents[2] is workspace root
    return Path(__file__).resolve().parents[2]


@dataclass
class PipelineConfig:
    # Workspace root and default directories
    base_dir: Path = field(default_factory=find_workspace_root)
    bronze_dir: Path = field(default=None)
    pdf_dir: Path = field(default=None)
    silver_dir: Path = field(default=None)
    gold_dir: Path = field(default=None)
    sources_csv: Path = field(default=None)

    # Chunking parameters (aligned with WeKnora chunker defaults: 512 tokens/chars, 80 overlap)
    chunk_size: int = 512
    chunk_overlap: int = 80
    min_chunk_length: int = 40
    max_chunk_length: int = 1000

    # Vietnamese Quality Gates
    min_doc_length: int = 50
    min_vietnamese_diacritic_ratio: float = 0.03  # At least 3% of alpha chars have VN diacritics for VN docs
    # Deduplication Gates
    enable_deduplication: bool = True  # Document-level deduplication in Silver
    dedup_threshold: float = 0.95

    # Gold Chunk Deduplication
    enable_gold_chunk_deduplication: bool = True
    gold_dedup_exact: bool = True
    gold_dedup_near: bool = True
    gold_dedup_similarity_threshold: float = 0.90

    # Target language
    target_language: str = "vi"

    # Export formats
    export_jsonl: bool = True
    export_parquet_if_available: bool = True

    def __post_init__(self):
        if self.bronze_dir is None:
            self.bronze_dir = self.base_dir / "dataset" / "bronze"
        else:
            self.bronze_dir = Path(self.bronze_dir)

        if self.pdf_dir is None:
            self.pdf_dir = self.base_dir / "dataset" / "pdf"
        else:
            self.pdf_dir = Path(self.pdf_dir)

        if self.silver_dir is None:
            self.silver_dir = self.base_dir / "dataset" / "silver"
        else:
            self.silver_dir = Path(self.silver_dir)

        if self.gold_dir is None:
            self.gold_dir = self.base_dir / "dataset" / "gold"
        else:
            self.gold_dir = Path(self.gold_dir)

        if self.sources_csv is None:
            self.sources_csv = self.base_dir / "dataset" / "sources.csv"
        else:
            self.sources_csv = Path(self.sources_csv)


DEFAULT_CONFIG = PipelineConfig()
