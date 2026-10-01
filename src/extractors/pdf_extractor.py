"""
PDF extractor for Vietnamese legal, technical, and promotional documents.
Uses PyMuPDF to extract text, detect document structures, and clean page noise.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Generator, List, Optional
import pymupdf

from src.extractors.base import BaseExtractor
from src.models.schemas import BronzeDocument

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """Extracts text and hierarchical headings from Vietnamese PDF documents."""

    def __init__(self, pdf_dir: Path):
        self.pdf_dir = Path(pdf_dir)
        self.manifest_path = self.pdf_dir / "pdf_manifest.json"

        # Regex for page numbering noise: 'Trang 1 / 10', 'Page 2 of 5', '- 3 -'
        self.page_number_regex = re.compile(
            r"^(Trang\s+\d+(\s*/\s*\d+)?|Page\s+\d+(\s*of\s*\d+)?|-\s*\d+\s*-|\d+/\d+)$",
            re.IGNORECASE,
        )
        # Regex for browser print header/footer noise: '9/30/26, 12:16 PM about: blank'
        self.print_noise_regex = re.compile(
            r"(\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(?:AM|PM)\s*about:\s*blank|about:\s*blank)",
            re.IGNORECASE,
        )

        # Regex for legal / policy headers
        self.chapter_regex = re.compile(r"^(Chương\s+[IVXLCDM\d]+[^\n]*)$", re.IGNORECASE)
        self.article_regex = re.compile(r"^(Điều\s+\d+\.[^\n]*)$", re.IGNORECASE)

    def extract_all(self) -> Generator[BronzeDocument, None, None]:
        """Iterates over manifest items and extracts documents."""
        if not self.manifest_path.exists():
            logger.warning("PDF manifest missing at %s", self.manifest_path)
            return

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception as e:
            logger.error("Failed to read PDF manifest: %s", e)
            return

        for item in entries:
            rel_path = item.get("relative_path", "")
            fname = os.path.basename(rel_path)
            category = item.get("category", "general")
            file_path = self.pdf_dir / category / fname

            if not file_path.exists():
                # Try relative to pdf_dir without category
                file_path = self.pdf_dir / fname
                if not file_path.exists():
                    continue

            try:
                extracted_md = self._extract_pdf_content(file_path, item.get("title", ""))
                if not extracted_md or len(extracted_md.strip()) < 100:
                    continue

                title = item.get("title") or fname.replace(".pdf", "").replace("_", " ").title()
                raw_id = f"pdf_{category}_{fname}"

                yield BronzeDocument(
                    raw_id=raw_id,
                    source_type="pdf",
                    source_file=str(file_path),
                    title=title,
                    url=None,
                    category=category,
                    domain="local_pdf",
                    raw_content=extracted_md,
                    raw_metadata=item,
                )

            except Exception as e:
                logger.error("Error reading PDF %s: %s", file_path, e)

    def _extract_pdf_content(self, file_path: Path, doc_title: str) -> Optional[str]:
        """Extracts text page-by-page, strips page numbers, and structures markdown headings."""
        doc = pymupdf.open(str(file_path))
        num_pages = len(doc)
        if num_pages == 0:
            return None

        markdown_lines = []
        if doc_title:
            markdown_lines.append(f"# {doc_title}\n")

        for page_idx in range(num_pages):
            page = doc[page_idx]
            page_text = page.get_text("text")
            if not page_text or not page_text.strip():
                continue

            lines = page_text.split("\n")
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                # Filter out pure page numbers
                if self.page_number_regex.match(stripped):
                    continue

                # Strip or filter browser print noise
                if self.print_noise_regex.search(stripped):
                    stripped = self.print_noise_regex.sub("", stripped).strip()
                    if not stripped:
                        continue

                # Format legal chapters as ## Chương ...
                if self.chapter_regex.match(stripped):
                    markdown_lines.append(f"\n## {stripped}\n")
                    continue

                # Format legal articles as ### Điều ...
                if self.article_regex.match(stripped):
                    markdown_lines.append(f"\n### {stripped}\n")
                    continue

                markdown_lines.append(stripped)

            markdown_lines.append("")  # Page boundary separator

        return "\n".join(markdown_lines).strip()
