"""
Gold Chunk Deduplicator.
Performs exact text deduplication and near-duplicate filtering (Jaccard similarity on word shingles).
Preserves provenance and prioritizes chunks with the richest breadcrumb context.
"""

from dataclasses import dataclass, field
import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple
from ..models.schemas import SilverChunk


@dataclass
class DeduplicationResult:
    """Statistics report of chunk deduplication."""
    unique_chunks: List[SilverChunk]
    exact_duplicates_count: int
    near_duplicates_count: int
    total_dropped: int
    retained_ratio_percent: float


class ChunkDeduplicator:
    """Removes redundant exact-duplicate and near-duplicate chunks at the Gold layer."""

    def __init__(
        self,
        enable_exact: bool = True,
        enable_near: bool = True,
        similarity_threshold: float = 0.90,
        shingle_k: int = 3,
    ):
        self.enable_exact = enable_exact
        self.enable_near = enable_near
        self.similarity_threshold = similarity_threshold
        self.shingle_k = shingle_k

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalizes text for hash comparison: lowercases, strips markdown tokens & excess whitespace."""
        if not text:
            return ""
        # Strip markdown headers, bullets, or table delimiters
        cleaned = re.sub(r"^[\s#*\->|]+", "", text)
        cleaned = re.sub(r"\s+", " ", cleaned.strip().lower())
        return cleaned

    def get_shingles(self, text: str) -> Set[str]:
        """Extracts k-word shingles for Jaccard similarity."""
        words = re.findall(r"\w+", text.lower())
        if len(words) < self.shingle_k:
            return {" ".join(words)} if words else set()
        return {" ".join(words[i : i + self.shingle_k]) for i in range(len(words) - self.shingle_k + 1)}

    @staticmethod
    def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
        """Computes Jaccard similarity between two shingle sets."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def deduplicate(self, chunks: List[SilverChunk]) -> DeduplicationResult:
        """
        Executes exact and near-duplicate filtering.
        Prioritizes keeping the chunk with the most specific heading context and highest consultation score.
        """
        if not chunks:
            return DeduplicationResult([], 0, 0, 0, 100.0)

        # -------------------------------------------------------------
        # Phase 1: Exact Duplicate Detection (SHA-256 on normalized text)
        # -------------------------------------------------------------
        exact_seen: Dict[str, SilverChunk] = {}
        exact_duplicates_dropped = 0

        if self.enable_exact:
            for chunk in chunks:
                raw_text = chunk.raw_chunk_text or chunk.content
                norm = self.normalize_text(raw_text)
                if not norm:
                    continue

                text_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()

                if text_hash in exact_seen:
                    existing = exact_seen[text_hash]
                    exact_duplicates_dropped += 1

                    # Compare quality / breadcrumb depth
                    cur_score = float(chunk.metadata.get("consultation_score", 0.0))
                    ex_score = float(existing.metadata.get("consultation_score", 0.0))
                    cur_path_len = len(chunk.heading_path) if chunk.heading_path else 0
                    ex_path_len = len(existing.heading_path) if existing.heading_path else 0

                    # Merge doc source provenance
                    sources = existing.metadata.get("duplicate_doc_sources", [existing.doc_id])
                    if chunk.doc_id not in sources:
                        sources.append(chunk.doc_id)

                    if (cur_score > ex_score) or (cur_score == ex_score and cur_path_len > ex_path_len):
                        # Current chunk has better context: replace existing
                        chunk.metadata["duplicate_doc_sources"] = sources
                        chunk.metadata["duplicate_count"] = existing.metadata.get("duplicate_count", 0) + 1
                        exact_seen[text_hash] = chunk
                    else:
                        existing.metadata["duplicate_doc_sources"] = sources
                        existing.metadata["duplicate_count"] = existing.metadata.get("duplicate_count", 0) + 1
                else:
                    chunk.metadata["duplicate_doc_sources"] = [chunk.doc_id]
                    chunk.metadata["duplicate_count"] = 0
                    exact_seen[text_hash] = chunk

            candidates_after_exact = list(exact_seen.values())
        else:
            candidates_after_exact = chunks

        # -------------------------------------------------------------
        # Phase 2: Near-Duplicate Detection (Jaccard on shingles per topic)
        # -------------------------------------------------------------
        final_unique: List[SilverChunk] = []
        near_duplicates_dropped = 0

        if self.enable_near and len(candidates_after_exact) > 1:
            from collections import defaultdict
            topic_groups = defaultdict(list)
            for chunk in candidates_after_exact:
                topic = chunk.metadata.get("gold_topic") or chunk.category or "all"
                topic_groups[topic].append(chunk)

            for topic, group in topic_groups.items():
                shingle_map = []
                for chunk in group:
                    raw_text = chunk.raw_chunk_text or chunk.content
                    norm = self.normalize_text(raw_text)
                    shingles = self.get_shingles(norm)
                    shingle_map.append((chunk, norm, shingles))

                kept_in_topic: List[Tuple[SilverChunk, str, Set[str]]] = []

                for chunk, norm, shingles in shingle_map:
                    is_near_dup = False
                    if len(shingles) >= 5:
                        for kept_chunk, kept_norm, kept_shingles in kept_in_topic:
                            if len(kept_shingles) < 5:
                                continue
                            # Fast length-ratio filter
                            len_ratio = min(len(shingles), len(kept_shingles)) / max(len(shingles), len(kept_shingles))
                            if len_ratio < 0.80:
                                continue

                            sim = self.jaccard_similarity(shingles, kept_shingles)
                            if sim >= self.similarity_threshold:
                                is_near_dup = True
                                near_duplicates_dropped += 1
                                # Merge provenance
                                sources = kept_chunk.metadata.get("duplicate_doc_sources", [])
                                if chunk.doc_id not in sources:
                                    sources.append(chunk.doc_id)
                                kept_chunk.metadata["duplicate_doc_sources"] = sources
                                kept_chunk.metadata["near_duplicate_merged"] = kept_chunk.metadata.get("near_duplicate_merged", 0) + 1
                                break

                    if not is_near_dup:
                        kept_in_topic.append((chunk, norm, shingles))

                final_unique.extend([item[0] for item in kept_in_topic])
        else:
            final_unique = candidates_after_exact

        total_dropped = exact_duplicates_dropped + near_duplicates_dropped
        ratio = round(len(final_unique) / len(chunks) * 100, 2) if chunks else 100.0

        return DeduplicationResult(
            unique_chunks=final_unique,
            exact_duplicates_count=exact_duplicates_dropped,
            near_duplicates_count=near_duplicates_dropped,
            total_dropped=total_dropped,
            retained_ratio_percent=ratio,
        )
