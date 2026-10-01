"""
Hierarchical context-aware chunker.
Implements heading hierarchy tracking (HeaderTracker) and protected blocks preservation,
coupled with Vietnamese sentence boundary awareness.
"""

import re
from typing import List, Tuple, Optional
from ..nlp.sentence_splitter import VietnameseSentenceSplitter
from ..models.schemas import SilverChunk


class HierarchicalChunker:
    """
    Chunks documents while tracking Markdown heading hierarchy.
    Prepends breadcrumbs to chunks so downstream retrieval retains full contextual relevance.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 80,
        min_chunk_length: int = 40,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_length = min_chunk_length
        self.sentence_splitter = VietnameseSentenceSplitter()
        self.header_regex = re.compile(r"^(#{1,6})\s+(.+)$")
        # Match legal headings like 'Chương I', 'Điều 12'
        self.legal_heading_regex = re.compile(
            r"^(Chương\s+[IVXLCDM\d]+.*?|Điều\s+\d+.*?|Mục\s+\d+.*?)$",
            re.IGNORECASE,
        )

    def _parse_sections(self, markdown_text: str) -> List[Tuple[List[str], str]]:
        """
        Parses markdown text into sections, tracking heading hierarchy.
        Returns a list of (heading_path, block_text).
        """
        lines = markdown_text.split("\n")
        sections: List[Tuple[List[str], str]] = []

        # Current stack of headings: list of (level, heading_text)
        heading_stack: List[Tuple[int, str]] = []
        current_block_lines: List[str] = []

        def flush_current_block():
            nonlocal current_block_lines
            text = "\n".join(current_block_lines).strip()
            if text:
                path = [h[1] for h in heading_stack]
                sections.append((path, text))
            current_block_lines = []

        i = 0
        in_code_block = False
        in_table = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Handle code block fences
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                current_block_lines.append(line)
                i += 1
                continue

            if in_code_block:
                current_block_lines.append(line)
                i += 1
                continue

            # Check for Markdown heading: '# Title', '## Section'
            header_match = self.header_regex.match(stripped)
            if header_match:
                flush_current_block()
                level = len(header_match.group(1))
                title = header_match.group(2).strip()

                # Pop headings of equal or deeper level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))
                i += 1
                continue

            # Check for legal doc chapter / article heading
            legal_match = self.legal_heading_regex.match(stripped)
            if legal_match and len(stripped) < 80:
                flush_current_block()
                title = legal_match.group(1).strip()
                level = 2 if title.lower().startswith("chương") else 3

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))
                i += 1
                continue

            current_block_lines.append(line)
            i += 1

        flush_current_block()
        return sections

    def chunk_document(
        self,
        doc_id: str,
        markdown_text: str,
        category: str = "general",
        source_type: str = "document",
        url: Optional[str] = None,
    ) -> List[SilverChunk]:
        """
        Splits markdown document into semantic chunks with breadcrumbs and overlap.
        """
        sections = self._parse_sections(markdown_text)
        chunks: List[SilverChunk] = []
        chunk_idx = 0

        for heading_path, section_text in sections:
            breadcrumb = " > ".join(heading_path) if heading_path else ""

            # Check if section text is a markdown table
            is_table = any(line.strip().startswith("|") for line in section_text.split("\n"))

            # If small enough or is table, keep as single chunk if possible
            if len(section_text) <= self.chunk_size or is_table:
                if len(section_text.strip()) >= self.min_chunk_length:
                    context_prefix = f"[{breadcrumb}]\n" if breadcrumb else ""
                    full_content = f"{context_prefix}{section_text}"
                    chunk = SilverChunk(
                        chunk_id=f"{doc_id}_{chunk_idx}",
                        doc_id=doc_id,
                        chunk_index=chunk_idx,
                        heading_path=heading_path,
                        heading_context=breadcrumb,
                        content=full_content,
                        raw_chunk_text=section_text,
                        token_estimate=len(full_content.split()),
                        char_count=len(full_content),
                        category=category,
                        source_type=source_type,
                        url=url,
                    )
                    chunks.append(chunk)
                    chunk_idx += 1
                continue

            # Otherwise, split section by Vietnamese sentences
            sentences = self.sentence_splitter.split_sentences(section_text)
            current_chunk_sentences: List[str] = []
            current_len = 0

            s_idx = 0
            while s_idx < len(sentences):
                sentence = sentences[s_idx]
                sentence_len = len(sentence)

                if current_len + sentence_len > self.chunk_size and current_chunk_sentences:
                    # Flush current chunk
                    raw_text = " ".join(current_chunk_sentences).strip()
                    if len(raw_text) >= self.min_chunk_length:
                        context_prefix = f"[{breadcrumb}]\n" if breadcrumb else ""
                        full_content = f"{context_prefix}{raw_text}"
                        chunk = SilverChunk(
                            chunk_id=f"{doc_id}_{chunk_idx}",
                            doc_id=doc_id,
                            chunk_index=chunk_idx,
                            heading_path=heading_path,
                            heading_context=breadcrumb,
                            content=full_content,
                            raw_chunk_text=raw_text,
                            token_estimate=len(full_content.split()),
                            char_count=len(full_content),
                            category=category,
                            source_type=source_type,
                            url=url,
                        )
                        chunks.append(chunk)
                        chunk_idx += 1

                    # Compute overlap from end of current sentences
                    overlap_sentences: List[str] = []
                    overlap_len = 0
                    for prev_s in reversed(current_chunk_sentences):
                        if overlap_len + len(prev_s) <= self.chunk_overlap:
                            overlap_sentences.insert(0, prev_s)
                            overlap_len += len(prev_s)
                        else:
                            break

                    current_chunk_sentences = overlap_sentences
                    current_len = overlap_len

                current_chunk_sentences.append(sentence)
                current_len += sentence_len
                s_idx += 1

            # Flush any remaining sentences in this section
            if current_chunk_sentences:
                raw_text = " ".join(current_chunk_sentences).strip()
                if len(raw_text) >= self.min_chunk_length:
                    context_prefix = f"[{breadcrumb}]\n" if breadcrumb else ""
                    full_content = f"{context_prefix}{raw_text}"
                    chunk = SilverChunk(
                        chunk_id=f"{doc_id}_{chunk_idx}",
                        doc_id=doc_id,
                        chunk_index=chunk_idx,
                        heading_path=heading_path,
                        heading_context=breadcrumb,
                        content=full_content,
                        raw_chunk_text=raw_text,
                        token_estimate=len(full_content.split()),
                        char_count=len(full_content),
                        category=category,
                        source_type=source_type,
                        url=url,
                    )
                    chunks.append(chunk)
                    chunk_idx += 1

        return chunks
