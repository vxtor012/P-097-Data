"""
Extractor for VinFast FAQ accordions.
Parses 400 FAQ items into categorized Markdown knowledge documents and structured SilverFAQItem records.
"""

import hashlib
import logging
from pathlib import Path
from typing import Generator, List, Tuple
from bs4 import BeautifulSoup
from markdownify import markdownify

from src.extractors.base import BaseExtractor
from src.models.schemas import BronzeDocument, SilverFAQItem

logger = logging.getLogger(__name__)

VEHICLE_KEYWORDS = [
    "VF 3", "VF 5", "VF 6", "VF 7", "VF 8", "VF 9",
    "EC Van", "Herio Green", "Limo Green", "Minio Green", "Nerio Green",
    "Evo200", "Evo Grand", "Feliz", "Feliz S", "Flazz",
    "Klara", "Theon", "Vento", "Vero X", "ZGoo"
]


class FAQExtractor(BaseExtractor):
    """Extracts raw FAQ HTML into structured QA pairs and hierarchical markdown."""

    def __init__(self, bronze_dir: Path):
        self.bronze_dir = Path(bronze_dir)
        self.faq_html_path = self.bronze_dir / "vinfast" / "faq" / "vinfast_faq_raw.html"
        self._cached_faq_items: List[SilverFAQItem] = []

    def get_structured_faq_items(self) -> List[SilverFAQItem]:
        """Returns individual extracted and normalized FAQ Q&A items."""
        if not self._cached_faq_items:
            # Trigger extraction to populate cache
            list(self.extract_all())
        return self._cached_faq_items

    def extract_all(self) -> Generator[BronzeDocument, None, None]:
        """Extract FAQ as structured bronze documents grouped by subcategory."""
        if not self.faq_html_path.exists():
            logger.warning("FAQ HTML file not found at %s", self.faq_html_path)
            return

        try:
            with open(self.faq_html_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            soup = BeautifulSoup(content, "html.parser")
            posts = soup.find_all("div", class_="post")
            logger.info("Found %d FAQ posts in raw HTML", len(posts))

            # Group items by (category, subcategory)
            grouped_faqs = {}
            self._cached_faq_items = []

            for idx, post in enumerate(posts):
                title_el = post.find("h2", class_="post-title")
                content_el = post.find("div", class_="post-content")

                if not title_el or not content_el:
                    continue

                question = title_el.get_text(strip=True)
                # Convert content HTML to clean Markdown
                answer_html = str(content_el)
                answer_md = markdownify(answer_html, heading_style="ATX").strip()
                answer_plain = content_el.get_text(separator=" ", strip=True)

                # Determine category and subcategory from previous DOM headers
                cat_el = post.find_previous("h2", class_="cat-name")
                sub_el = post.find_previous("h3", class_=lambda c: c and "child-name" in c)

                category = cat_el.get_text(strip=True) if cat_el else "VinFast"
                subcategory = sub_el.get_text(strip=True) if sub_el else "Hỏi đáp chung"

                # Tag vehicles mentioned in question or subcategory
                tags = []
                for kw in VEHICLE_KEYWORDS:
                    if kw.lower() in question.lower() or kw.lower() in subcategory.lower():
                        tags.append(kw)

                faq_id = f"faq_{hashlib.md5(question.encode('utf-8')).hexdigest()[:12]}"
                faq_item = SilverFAQItem(
                    faq_id=faq_id,
                    question=question,
                    answer=answer_plain,
                    answer_markdown=answer_md,
                    category=category,
                    subcategory=subcategory,
                    vehicle_tags=tags,
                    source_url="https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap",
                    quality_score=1.0,
                )
                self._cached_faq_items.append(faq_item)

                group_key = (category, subcategory)
                if group_key not in grouped_faqs:
                    grouped_faqs[group_key] = []
                grouped_faqs[group_key].append(faq_item)

            # Yield one BronzeDocument per subcategory group
            for (category, subcategory), items in grouped_faqs.items():
                doc_title = f"Hỏi đáp VinFast: {category} - {subcategory}"
                safe_slug = f"{category}_{subcategory}".replace(" ", "_").lower()
                doc_id = f"faq_doc_{hashlib.md5(safe_slug.encode('utf-8')).hexdigest()[:10]}"

                md_blocks = [f"# {category}\n## {subcategory}\n"]
                for item in items:
                    md_blocks.append(f"### {item.question}\n\n{item.answer_markdown}\n")
                    item.doc_id = doc_id

                full_markdown = "\n".join(md_blocks)

                yield BronzeDocument(
                    raw_id=doc_id,
                    source_type="faq",
                    source_file=str(self.faq_html_path),
                    title=doc_title,
                    url="https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap",
                    category="faq",
                    domain="vinfastauto.com",
                    raw_content=full_markdown,
                    raw_metadata={
                        "category": category,
                        "subcategory": subcategory,
                        "total_questions": len(items),
                    },
                )

        except Exception as e:
            logger.error("Failed to extract FAQ HTML: %s", e)
