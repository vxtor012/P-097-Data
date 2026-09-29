"""src/data_pipeline/normalize/processor.py
Xử lý dữ liệu Bronze từ data/landing (PDF, JSON chứa raw_content & metadata)
và chuẩn hóa sang Markdown tại data/standardized sử dụng Docling.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data_pipeline.normalize.docling_converter import DoclingService
from src.data_pipeline.normalize.metadata_utils import (
    build_yaml_frontmatter,
    compute_content_hash,
    compute_file_sha256,
    count_words_and_chars,
    extract_pdf_metadata,
)

logger = logging.getLogger("NormalizePipeline")


class NormalizationProcessor:
    """Bộ điều phối chuẩn hóa dữ liệu từ Bronze (data/landing) sang Silver (data/standardized)."""

    def __init__(
        self,
        landing_dir: Path,
        standardized_dir: Path,
        overwrite: bool = True,
        use_ocr: bool = False,
    ) -> None:
        self.landing_dir = landing_dir.resolve()
        self.standardized_dir = standardized_dir.resolve()
        self.overwrite = overwrite
        self.docling_service = DoclingService(use_ocr=use_ocr)
        
        # Thống kê
        self.stats = {
            "total_source_files": 0,
            "processed_files": 0,
            "generated_markdown_files": 0,
            "skipped_files": 0,
            "errors": 0,
            "error_details": [],
        }

    def run(self) -> dict[str, Any]:
        """Thực thi toàn bộ pipeline chuẩn hóa cho toàn bộ dữ liệu landing."""
        self.standardized_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Quét tất cả các thư mục trong data/landing (trừ relational)
        categories = ["faqs", "legal", "news", "policies", "specs"]
        
        for category in categories:
            cat_dir = self.landing_dir / category
            if not cat_dir.exists():
                continue
            
            logger.info(f"📂 Bắt đầu chuẩn hóa danh mục: {category}")
            self._process_category(cat_dir, category)

        return self.stats

    def _process_category(self, cat_dir: Path, category: str) -> None:
        """Xử lý từng danh mục cụ thể."""
        # Lấy danh sách file (JSON và PDF)
        all_files = sorted(cat_dir.rglob("*.*"))
        for file_path in all_files:
            if file_path.suffix.lower() not in [".json", ".pdf"]:
                continue
            
            # Bỏ qua các file summary tổng hợp
            if file_path.name.endswith("_summary.json") or file_path.name == "extracted_summary.json":
                continue

            self.stats["total_source_files"] += 1
            try:
                if file_path.suffix.lower() == ".pdf":
                    self._process_pdf_file(file_path, category)
                elif file_path.suffix.lower() == ".json":
                    self._process_json_file(file_path, category)
                self.stats["processed_files"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                err_msg = f"Lỗi xử lý file {file_path.relative_to(self.landing_dir)}: {str(e)}"
                logger.error(err_msg, exc_info=True)
                self.stats["error_details"].append(err_msg)

    def _process_pdf_file(self, pdf_path: Path, category: str) -> None:
        """Xử lý tệp PDF bằng Docling và xuất sang Markdown kèm frontmatter."""
        logger.info(f"📄 Đang xử lý PDF: {pdf_path.name}")
        
        # Chuyển đổi PDF sang Markdown bằng Docling
        docling_markdown = self.docling_service.convert_pdf_file(pdf_path)
        
        # Trích xuất metadata
        meta = extract_pdf_metadata(pdf_path, docling_markdown)
        meta["normalized_at"] = datetime.now(timezone.utc).isoformat()
        
        # Ghép frontmatter + markdown
        frontmatter = build_yaml_frontmatter(meta)
        full_markdown = f"{frontmatter}{docling_markdown}"
        
        # Đường dẫn đích
        clean_stem = re.sub(r"[^\w\-_]", "_", pdf_path.stem).strip("_")
        out_file = self.standardized_dir / category / f"{clean_stem}.md"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(full_markdown)
            
        self.stats["generated_markdown_files"] += 1
        logger.info(f"✅ Đã xuất: {out_file.relative_to(self.standardized_dir)}")

    def _process_json_file(self, json_path: Path, category: str) -> None:
        """Xử lý tệp JSON (chứa metadata và raw_content) bằng Docling."""
        logger.info(f"📝 Đang xử lý JSON: {json_path.name}")
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Trường hợp 1: JSON là danh sách (List of documents)
        if isinstance(data, list):
            self._process_json_list(data, json_path, category)
        # Trường hợp 2: JSON là một document đơn lẻ (Dict)
        elif isinstance(data, dict):
            self._process_json_dict(data, json_path, category)

    def _process_json_list(self, items: list[dict[str, Any]], source_file: Path, category: str) -> None:
        """Xử lý danh sách các bản ghi JSON."""
        # Xác định thư mục con phù hợp
        rel_sub = source_file.relative_to(self.landing_dir / category).parent
        
        # Nếu là file tổng hợp (_all.json hoặc external_sources_*.json), xuất từng item thành file riêng
        is_aggregate = "_all" in source_file.stem or "external_sources" in source_file.stem or source_file.name == "vinfast_car_specifications.json"

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            
            # Trích xuất metadata
            raw_meta = item.get("metadata", {})
            if not isinstance(raw_meta, dict):
                raw_meta = {}

            # Xác định tiêu đề, slug, doc_id
            title = item.get("title") or raw_meta.get("title") or item.get("question") or f"{source_file.stem}_{idx+1}"
            slug = item.get("slug") or item.get("faq_id") or raw_meta.get("doc_id") or f"{source_file.stem}_{idx+1}"
            slug = re.sub(r"[^\w\-_]", "_", str(slug)).strip("_")

            # Chuẩn bị raw_content và chuyển đổi bằng Docling
            raw_content = self._extract_raw_content_from_item(item, category)
            
            # Chuẩn hóa qua Docling
            docling_markdown = self.docling_service.convert_raw_content(raw_content, title=str(title))
            
            # Cập nhật metadata hoàn chỉnh
            char_count, word_count = count_words_and_chars(docling_markdown)
            meta = {
                **raw_meta,
                "title": title,
                "doc_id": raw_meta.get("doc_id") or f"doc_{category}_{slug}",
                "category": raw_meta.get("category") or category.capitalize(),
                "pipeline_stage": "silver_standardized",
                "normalized_at": datetime.now(timezone.utc).isoformat(),
                "char_count": char_count,
                "word_count": word_count,
                "token_estimate": int(word_count * 1.3),
            }
            if "published_date" in item and "published_date" not in meta:
                meta["published_date"] = item["published_date"]
            if "source_url" in item and "source_url" not in meta:
                meta["source_url"] = item["source_url"]

            frontmatter = build_yaml_frontmatter(meta)
            full_markdown = f"{frontmatter}{docling_markdown}"

            # Đường dẫn đích
            out_dir = self.standardized_dir / category / rel_sub
            out_file = out_dir / f"{slug}.md"
            out_file.parent.mkdir(parents=True, exist_ok=True)

            with open(out_file, "w", encoding="utf-8") as f:
                f.write(full_markdown)

            self.stats["generated_markdown_files"] += 1

    def _process_json_dict(self, data: dict[str, Any], source_file: Path, category: str) -> None:
        """Xử lý một bản ghi JSON dạng Dict."""
        raw_meta = data.get("metadata", {})
        if not isinstance(raw_meta, dict):
            raw_meta = {}

        title = data.get("title") or raw_meta.get("title") or data.get("model_name") or source_file.stem
        slug = data.get("slug") or raw_meta.get("doc_id") or source_file.stem
        slug = re.sub(r"[^\w\-_]", "_", str(slug)).strip("_")

        # Trích xuất raw_content
        raw_content = self._extract_raw_content_from_item(data, category)
        
        # Chuẩn hóa qua Docling
        docling_markdown = self.docling_service.convert_raw_content(raw_content, title=str(title))

        char_count, word_count = count_words_and_chars(docling_markdown)
        meta = {
            **raw_meta,
            "title": title,
            "doc_id": raw_meta.get("doc_id") or f"doc_{category}_{slug}",
            "category": raw_meta.get("category") or category.capitalize(),
            "pipeline_stage": "silver_standardized",
            "normalized_at": datetime.now(timezone.utc).isoformat(),
            "char_count": char_count,
            "word_count": word_count,
            "token_estimate": int(word_count * 1.3),
        }
        if "segment" in data and "segment" not in meta:
            meta["segment"] = data["segment"]
        if "seats" in data and "seats" not in meta:
            meta["seats"] = data["seats"]

        frontmatter = build_yaml_frontmatter(meta)
        full_markdown = f"{frontmatter}{docling_markdown}"

        # Xác định relative path từ landing
        rel_path = source_file.relative_to(self.landing_dir)
        out_file = self.standardized_dir / rel_path.with_suffix(".md")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        with open(out_file, "w", encoding="utf-8") as f:
            f.write(full_markdown)

        self.stats["generated_markdown_files"] += 1

    def _extract_raw_content_from_item(self, item: dict[str, Any], category: str) -> str:
        """Tổng hợp raw_content từ các trường cấu trúc của item."""
        parts = []

        # 1. Trường raw_content chính thức
        if "raw_content" in item and item["raw_content"]:
            parts.append(str(item["raw_content"]).strip())

        # 2. Xử lý trường hợp FAQ (question, answer)
        if "question" in item and "answer" in item:
            q = item["question"]
            a = item["answer"]
            faq_html = f"<h3>Câu hỏi: {q}</h3><div><p><strong>Trả lời:</strong></p><p>{a}</p></div>"
            parts.append(faq_html)

        # 3. Xử lý trường hợp có sections danh sách (ví dụ chính sách bảo hành, dịch vụ pin)
        if "sections" in item and isinstance(item["sections"], list) and not parts:
            for sec in item["sections"]:
                if isinstance(sec, dict):
                    sec_title = sec.get("title", "")
                    sec_content = sec.get("content", "")
                    parts.append(f"<h2>{sec_title}</h2>\n<p>{sec_content}</p>")

        # 4. Xử lý trường hợp specs (thông số kỹ thuật dạng bảng)
        if category == "specs":
            spec_html = self._format_specs_as_html(item)
            if spec_html:
                parts.append(spec_html)

        return "\n\n".join(parts)

    def _format_specs_as_html(self, item: dict[str, Any]) -> str:
        """Định dạng thông số kỹ thuật xe thành bảng HTML để Docling dựng bảng Markdown chuẩn."""
        html_out = []
        
        if "description" in item and item["description"]:
            html_out.append(f"<p>{item['description']}</p>")

        if "key_features" in item and isinstance(item["key_features"], list) and item["key_features"]:
            html_out.append("<h3>Đặc điểm nổi bật</h3><ul>")
            for feat in item["key_features"]:
                html_out.append(f"<li>{feat}</li>")
            html_out.append("</ul>")

        if "specifications" in item and isinstance(item["specifications"], dict) and item["specifications"]:
            html_out.append("<h3>Thông số kỹ thuật chi tiết</h3>")
            html_out.append("<table border='1'><thead><tr><th>Hạng mục</th><th>Giá trị</th></tr></thead><tbody>")
            for k, v in item["specifications"].items():
                html_out.append(f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>")
            html_out.append("</tbody></table>")

        return "".join(html_out)
