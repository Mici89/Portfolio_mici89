from app.services.document_parser import ExtractedBlock
from app.services.text_splitter import split_document


def test_split_document_keeps_heading_and_metadata() -> None:
    chunks = split_document([
        ExtractedBlock(
            text="公司员工每年享有 10 天带薪年假。",
            metadata={"heading_path": ["员工制度", "年假制度"]},
        )
    ])

    assert len(chunks) == 1
    assert chunks[0].metadata["heading_path"] == ["员工制度", "年假制度"]


def test_split_document_splits_long_text_at_sentence_boundaries() -> None:
    chunks = split_document([
        ExtractedBlock(
            text="第一句话说明制度。第二句话说明申请流程。第三句话说明例外情况。",
            metadata={"page_start": 2, "page_end": 2},
        )
    ], max_chars=15, overlap_sentences=1)

    assert len(chunks) >= 2
    assert all(chunk.metadata["page_start"] == 2 for chunk in chunks)
    assert all("。" in chunk.content for chunk in chunks)
