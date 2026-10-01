"""Unit tests for Vietnamese Sentence Splitter."""

import pytest
from pipeline.nlp.sentence_splitter import VietnameseSentenceSplitter


def test_abbreviations_not_split():
    splitter = VietnameseSentenceSplitter()
    text = "Trụ sở công ty đặt tại TP.HCM. Ông Nguyễn Văn A là đại diện pháp luật."
    sentences = splitter.split_sentences(text)
    assert len(sentences) == 2
    assert "TP.HCM." in sentences[0]
    assert sentences[1].startswith("Ông Nguyễn Văn A")


def test_numbers_and_currency_not_split():
    splitter = VietnameseSentenceSplitter()
    text = "Mức ưu đãi lên đến 260.000.000 VNĐ trong tháng 6. Khách hàng nhận xe ngay."
    sentences = splitter.split_sentences(text)
    assert len(sentences) == 2
    assert "260.000.000 VNĐ trong tháng 6." in sentences[0]
    assert sentences[1] == "Khách hàng nhận xe ngay."


def test_markdown_elements_preserved():
    splitter = VietnameseSentenceSplitter()
    text = "# Tiêu đề chính\n- Điểm 1: Xe chạy êm.\n- Điểm 2: Tiết kiệm pin."
    sentences = splitter.split_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "# Tiêu đề chính"
    assert sentences[1] == "- Điểm 1: Xe chạy êm."
