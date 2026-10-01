"""
Vietnamese text normalizer.
Handles:
- Unicode NFC normalization
- Vietnamese tone placement standardization (quy tắc đặt dấu thanh chuẩn mới)
- Typography and punctuation spacing normalization
- Numeric and currency protection
"""

import re
import unicodedata
from typing import Dict


class VietnameseNormalizer:
    """Specialized text normalizer for Vietnamese language in RAG and search pipelines."""

    # Map old-style tone placement to modern standard tone placement
    # Example: hoà -> hòa, thuỷ -> thủy, khoẻ -> khỏe, quĩ -> quỹ
    OLD_TO_NEW_TONE_MAP: Dict[str, str] = {
        # oa / oà / oá / oả / oã / oạ -> oà -> hòa
        "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
        "Oà": "Òa", "Oá": "Óa", "Oả": "Ỏa", "Oã": "Õa", "Oạ": "Ọa",
        # oe / oè / oé / oẻ / oẽ / oẹ -> oè -> hòe
        "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
        "Oè": "Òe", "Oé": "Óe", "Oẻ": "Ỏe", "Oẽ": "Õe", "Oẹ": "Ọe",
        # uy / uỳ / uý / uỷ / uỹ / uỵ -> uỳ -> thùy, uý -> thúy
        "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
        "Uỳ": "Ùy", "Uý": "Úy", "Uỷ": "Ủy", "Uỹ": "Ũy", "Uỵ": "Ụy",
        # i / y standard in certain words (quĩ -> quỹ, kĩ -> kỹ, mĩ -> mỹ, v.v.)
        "quĩ": "quỹ", "quì": "quỳ", "quý": "quý", "kĩ": "kỹ", "mĩ": "mỹ",
        "Quĩ": "Quỹ", "Quì": "Quỳ", "Kĩ": "Kỹ", "Mĩ": "Mỹ",
    }

    # Common typographical replacements
    TYPO_REPLACEMENTS = [
        # Non-breaking and zero-width spaces
        ("\u00a0", " "),
        ("\u200b", ""),
        ("\ufeff", ""),
        ("\u200e", ""),
        ("\u200f", ""),
        # Fancy quotation marks
        ("“", '"'),
        ("”", '"'),
        ("„", '"'),
        ("«", '"'),
        ("»", '"'),
        ("‘", "'"),
        ("’", "'"),
        ("‚", "'"),
        # Dashes
        ("–", "-"),
        ("—", "-"),
        ("―", "-"),
        ("…", "..."),
    ]

    def __init__(self):
        # Regex to fix space before punctuation: 'xe điện .' -> 'xe điện.'
        self._space_before_punct = re.compile(r"\s+([,.:;?!%])")
        # Regex to fix missing space after punctuation: 'VinFast,xe' -> 'VinFast, xe'
        # Must not match numbers like 1,5 or 1.500.000 or website URLs
        self._missing_space_after_comma = re.compile(r"([a-zA-Z\u00C0-\u1EF9])([,;:])([a-zA-Z\u00C0-\u1EF9])")
        self._missing_space_after_dot = re.compile(r"([a-zA-Z\u00C0-\u1EF9]{2,})\.([A-Z\u00C0-\u1EF9][a-z\u00C0-\u1EF9])")
        # Multiple spaces (excluding newlines)
        self._multi_spaces = re.compile(r"[^\S\r\n]+")
        # Multiple blank lines
        self._multi_newlines = re.compile(r"\n{3,}")

    def normalize_unicode(self, text: str) -> str:
        """Ensure standard Unicode NFC (precomposed) representation."""
        if not text:
            return ""
        return unicodedata.normalize("NFC", text)

    def standardize_vietnamese_tones(self, text: str) -> str:
        """Convert traditional/inconsistent tone placement to modern standard."""
        if not text:
            return ""
        for old_pattern, new_pattern in self.OLD_TO_NEW_TONE_MAP.items():
            if old_pattern in text:
                text = text.replace(old_pattern, new_pattern)
        return text

    def clean_typography_and_spacing(self, text: str) -> str:
        """Clean quotation marks, dashes, invisible spaces, and standardize spacing."""
        if not text:
            return ""

        # Replace typographical symbols
        for src, dst in self.TYPO_REPLACEMENTS:
            text = text.replace(src, dst)

        # Fix space before punctuation: 'xe điện .' -> 'xe điện.'
        # Avoid breaking markdown bullet lists (' - ')
        text = self._space_before_punct.sub(r"\1", text)

        # Fix missing space after punctuation
        text = self._missing_space_after_comma.sub(r"\1\2 \3", text)
        text = self._missing_space_after_dot.sub(r"\1. \2", text)
        # Ensure space before opening quote following punctuation: e.g. 'điện."Xe' -> 'điện. "Xe'
        text = re.sub(r'([.,:;?!])(["\'])', r'\1 \2', text)

        # Collapse horizontal whitespace
        text = self._multi_spaces.sub(" ", text)

        # Clean trailing whitespace per line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # Collapse excess empty lines
        text = self._multi_newlines.sub("\n\n", text)

        return text.strip()

    def normalize(self, text: str) -> str:
        """Full end-to-end normalization pipeline for Vietnamese text."""
        if not text:
            return ""
        text = self.normalize_unicode(text)
        text = self.standardize_vietnamese_tones(text)
        text = self.clean_typography_and_spacing(text)
        return text
