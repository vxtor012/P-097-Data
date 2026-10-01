"""Unit tests for Vietnamese Normalizer."""

import pytest
import unicodedata
from src.nlp.vietnamese_normalizer import VietnameseNormalizer


def test_unicode_nfc():
    normalizer = VietnameseNormalizer()
    # Decomposed NFD string
    nfd_text = unicodedata.normalize("NFD", "Việt Nam đất nước tuyệt vời")
    # Must normalize to NFC
    nfc_text = normalizer.normalize_unicode(nfd_text)
    assert unicodedata.is_normalized("NFC", nfc_text)
    assert nfc_text == "Việt Nam đất nước tuyệt vời"


def test_tone_standardization():
    normalizer = VietnameseNormalizer()
    old_orthography = "hoà bình, thuỷ điện, khoẻ mạnh, quĩ đầu tư"
    expected = "hòa bình, thủy điện, khỏe mạnh, quỹ đầu tư"
    result = normalizer.standardize_vietnamese_tones(old_orthography)
    assert result == expected


def test_spacing_and_typography():
    normalizer = VietnameseNormalizer()
    dirty_text = "VinFast,một thương hiệu ô tô  điện .“Xe rất tốt” – ông Nam chia sẻ ."
    expected = 'VinFast, một thương hiệu ô tô điện. "Xe rất tốt" - ông Nam chia sẻ.'
    result = normalizer.normalize(dirty_text)
    assert result == expected


def test_numbers_preservation():
    normalizer = VietnameseNormalizer()
    text = "Giá xe là 260.000.000 VNĐ với mức tiêu hao 60,13 kWh."
    result = normalizer.normalize(text)
    assert "260.000.000" in result
    assert "60,13" in result
