"""
Pydantic and Dataclass schemas for Bronze and Silver entities.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class BronzeDocument:
    """Represents an unprocessed raw bronze record."""
    raw_id: str
    source_type: str  # 'html_article', 'faq', 'pdf', 'relational_snapshot'
    source_file: str
    title: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    domain: Optional[str] = None
    raw_content: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    crawled_at: Optional[str] = None


@dataclass
class SilverDocument:
    """Standardized, normalized, and validated document in Silver layer."""
    doc_id: str
    source_id: str
    source_type: str
    title: str
    category: str
    domain: Optional[str]
    url: Optional[str]
    language: str
    content_clean_markdown: str
    content_plain_text: str
    word_count: int
    char_count: int
    token_estimate: int
    diacritic_ratio: float
    quality_score: float
    checksum_sha256: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    processed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SilverChunk:
    """Semantic chunk with hierarchical breadcrumb context ready for Pre-RAG retrieval and indexing."""
    chunk_id: str
    doc_id: str
    chunk_index: int
    heading_path: List[str]
    heading_context: str
    content: str
    raw_chunk_text: str
    token_estimate: int
    char_count: int
    category: str
    source_type: str
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SilverFAQItem:
    """Extracted and normalized Q&A pair from FAQ accordions."""
    faq_id: str
    question: str
    answer: str
    answer_markdown: str
    category: str
    subcategory: str
    vehicle_tags: List[str]
    source_url: Optional[str] = None
    doc_id: Optional[str] = None
    quality_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SilverVehicle:
    """Clean relational vehicle product, pricing, and specs."""
    vehicle_id: str
    model_name: str
    vehicle_type: str  # 'car' or 'bike'
    trims: List[Dict[str, Any]]
    battery_options: List[Dict[str, Any]]
    specifications: Dict[str, Any]
    promotions: List[str]
    rolling_costs: Dict[str, Any]
    searchable_markdown: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SilverReport:
    """Execution statistics and quality audit report for pipeline execution."""
    pipeline_version: str
    started_at: str
    completed_at: str
    elapsed_seconds: float
    total_bronze_records: int
    total_silver_documents: int
    total_silver_chunks: int
    total_faq_items: int
    total_vehicles: int
    duplicates_filtered: int
    low_quality_filtered: int
    language_distribution: Dict[str, int]
    source_distribution: Dict[str, int]
    category_distribution: Dict[str, int]
    average_quality_score: float
    average_token_count_per_chunk: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
