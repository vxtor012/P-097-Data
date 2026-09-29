"""src/data_pipeline/normalize/docling_converter.py
Tích hợp IBM Docling để trích xuất, chuyển đổi và chuẩn hóa cấu trúc văn bản (PDF, HTML, Text, JSON raw_content) sang Markdown chuẩn.
"""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False


class DoclingService:
    """Dịch vụ chuẩn hóa văn bản sử dụng IBM Docling DocumentConverter."""

    def __init__(self, use_ocr: bool = False, max_threads: int = 4) -> None:
        self.use_ocr = use_ocr
        self.max_threads = max_threads
        self._converter: Optional[Any] = None

    @property
    def converter(self) -> Any:
        """Khởi tạo DocumentConverter theo chế độ lazy loading."""
        if self._converter is None:
            if not DOCLING_AVAILABLE:
                raise RuntimeError(
                    "Docling chưa được cài đặt. Vui lòng cài đặt qua `pip install docling`."
                )
            
            # Cấu hình pipeline tối ưu
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = self.use_ocr
            pipeline_options.do_table_structure = True
            
            format_options = {
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
            
            self._converter = DocumentConverter(
                format_options=format_options
            )
        return self._converter

    def convert_pdf_file(self, pdf_path: Path) -> str:
        """Chuyển đổi tệp PDF sang nội dung Markdown chuẩn bằng Docling."""
        result = self.converter.convert(str(pdf_path))
        markdown = result.document.export_to_markdown()
        return self._post_clean_markdown(markdown)

    def convert_raw_content(
        self,
        raw_content: str,
        title: str = "",
        format_hint: str = "html",
    ) -> str:
        """Chuẩn hóa nội dung thô (HTML / text cào từ website) bằng Docling sang Markdown.
        
        Sử dụng cơ chế temp file / document stream để Docling phân tích cú pháp HTML, bảng,
        danh sách, tiêu đề một cách chính xác.
        """
        if not raw_content or not raw_content.strip():
            return ""

        content = raw_content.strip()

        # Nếu nội dung có cấu trúc HTML hoặc text dài, đóng gói thành HTML hợp lệ để Docling parse
        if "<" not in content or ">" not in content:
            # Chuyển đổi text thuần sang HTML đoạn văn để Docling dựng cây tài liệu
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            html_parts = []
            if title:
                html_parts.append(f"<h1>{title}</h1>")
            for p in paragraphs:
                if "\n" in p:
                    lines = [line.strip() for line in p.split("\n") if line.strip()]
                    html_parts.append("<p>" + "<br/>".join(lines) + "</p>")
                else:
                    html_parts.append(f"<p>{p}</p>")
            html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{''.join(html_parts)}</body></html>"
        else:
            # Đã có HTML tags
            if "<html" not in content.lower():
                html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{content}</body></html>"
            else:
                html_content = content

        # Ghi file tạm để Docling chuyển đổi chuẩn xác nhất
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            encoding="utf-8",
            delete=False,
        ) as tmp:
            tmp.write(html_content)
            tmp_path = Path(tmp.name)

        try:
            result = self.converter.convert(str(tmp_path))
            markdown = result.document.export_to_markdown()
            return self._post_clean_markdown(markdown)
        except Exception as e:
            # Fallback nếu docling gặp lỗi bất thường với stream
            return self._fallback_clean_text(raw_content)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _post_clean_markdown(self, markdown: str) -> str:
        """Hậu xử lý Markdown sau khi xuất từ Docling (loại bỏ khoảng trắng thừa, căn chỉnh)."""
        if not markdown:
            return ""

        # Chuẩn hóa khoảng trắng nhiều dòng
        text = re.sub(r"\n{3,}", "\n\n", markdown)
        
        # Bỏ khoảng trắng cuối dòng
        lines = [line.rstrip() for line in text.split("\n")]
        text = "\n".join(lines).strip()
        return text

    def _fallback_clean_text(self, text: str) -> str:
        """Dự phòng làm sạch nếu bộ chuyển đổi gặp sự cố."""
        import html
        clean = html.unescape(text)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\n\s*\n", "\n\n", clean)
        return clean.strip()
