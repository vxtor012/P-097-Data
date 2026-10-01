"""
Vietnamese sentence boundary detection (sentence splitter).
Handles Vietnamese abbreviations, numbered lists, legal document sections,
decimals, and currencies without incorrectly splitting.
"""

import re
from typing import List


class VietnameseSentenceSplitter:
    """Accurate sentence splitter tuned specifically for Vietnamese texts."""

    # Honorifics and title abbreviations that precede names and do NOT terminate a sentence
    HONORIFICS = {
        "pgs.ts", "gs.ts", "pgs.", "gs.", "ts.", "ths.", "bs.", "cn.",
        "th.s", "mr.", "ms.", "mrs.", "dr.", "k/g.", "đ/c."
    }

    # Internal abbreviations that shouldn't split when followed immediately by letter or slash
    # e.g., 'TP.HCM', 'km/h', '1.500.000'
    def __init__(self):
        self._legal_marker_regex = re.compile(
            r"^(Điều|Khoản|Điểm|Mục|Chương)\s+\d+[\w.]*", re.IGNORECASE
        )

    def split_sentences(self, text: str) -> List[str]:
        """Split a Vietnamese text block into clean sentences."""
        if not text or not text.strip():
            return []

        text = text.strip()

        # If text contains paragraphs or bullet points, first split by paragraphs
        raw_paragraphs = text.split("\n")
        sentences: List[str] = []

        for paragraph in raw_paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            # If it's a markdown heading, bullet point, or table row, keep as its own unit
            if paragraph.startswith(("#", "-", "*", ">", "|", "```")):
                sentences.append(paragraph)
                continue

            # Split paragraph into candidate sentences
            para_sentences = self._split_paragraph(paragraph)
            sentences.extend(para_sentences)

        return sentences

    def _split_paragraph(self, paragraph: str) -> List[str]:
        """Split a single paragraph into sentences taking abbreviations into account."""
        length = len(paragraph)
        if length == 0:
            return []

        sentences = []
        start_idx = 0
        i = 0

        while i < length:
            char = paragraph[i]

            # Check if this character could be a sentence boundary
            if char in ".!?…":
                # Look ahead for repeated punctuation (e.g. '...', '!?')
                end_punct_idx = i
                while end_punct_idx + 1 < length and paragraph[end_punct_idx + 1] in ".!?…":
                    end_punct_idx += 1

                # 1. Check if dot is part of a number: e.g. 1.500 or 3.14
                prev_char = paragraph[i - 1] if i > 0 else ""
                next_char = paragraph[end_punct_idx + 1] if end_punct_idx + 1 < length else ""

                if prev_char.isdigit() and next_char.isdigit():
                    i = end_punct_idx + 1
                    continue

                # 2. Check if dot is inside an acronym like TP.HCM (dot followed immediately by letters)
                if char == "." and next_char.isalpha():
                    i = end_punct_idx + 1
                    continue

                # 3. Check if preceded by honorific (e.g. PGS. TS. Nguyễn Văn A)
                word_match = re.search(r"([\w./]+)$", paragraph[start_idx:i])
                if word_match:
                    candidate_abbr = (word_match.group(1) + paragraph[i:end_punct_idx + 1]).lower()
                    if candidate_abbr in self.HONORIFICS or candidate_abbr.rstrip(".") in self.HONORIFICS:
                        i = end_punct_idx + 1
                        continue

                # 4. Check if at end of paragraph or followed by space + uppercase letter/quote/number
                if end_punct_idx + 1 >= length:
                    sentence = paragraph[start_idx:length].strip()
                    if sentence:
                        sentences.append(sentence)
                    start_idx = length
                    break
                else:
                    after_punct = paragraph[end_punct_idx + 1:]
                    # Check if followed by whitespace
                    if after_punct.startswith((" ", "\t")):
                        after_stripped = after_punct.lstrip()
                        # If followed by capital letter, quote, or list digit
                        if not after_stripped or re.match(r"^([A-Z\u00C0-\u1EF9\"'\(“‘0-9]|$)", after_stripped):
                            sentence = paragraph[start_idx:end_punct_idx + 1].strip()
                            if sentence:
                                sentences.append(sentence)

                            # Advance start_idx past the spaces
                            spaces_len = len(after_punct) - len(after_stripped)
                            start_idx = end_punct_idx + 1 + spaces_len
                            i = start_idx
                            continue

                i = end_punct_idx + 1
            else:
                i += 1

        # Residual trailing sentence
        if start_idx < length:
            tail = paragraph[start_idx:length].strip()
            if tail:
                sentences.append(tail)

        return sentences
