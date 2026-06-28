from pathlib import Path

from backend.Services import document_processor as processor


def test_detect_format_pdf():
    fmt = processor._detect_format(Path('demo.pdf'))
    assert fmt == 'pdf'


def test_chunk_document_returns_non_empty_chunks():
    chunks = processor._chunk_document('Alpha beta gamma. ' * 300)
    assert chunks
    assert all(chunk.strip() for chunk in chunks)


def test_process_documents_batch_with_monkeypatched_backend(monkeypatch, tmp_path):
    sample = tmp_path / 'sample.pdf'
    sample.write_text('placeholder', encoding='utf-8')

    monkeypatch.setattr(processor, 'extract_text_from_file', lambda file_path: {
        'path': str(sample),
        'filename': sample.name,
        'file_type': 'pdf',
        'text': 'Requirement REQ-001 relates to bearing life and lubrication.',
    })
    monkeypatch.setattr(processor, '_embed_texts', lambda chunks: [[0.1, 0.2, 0.3] for _ in chunks])
    monkeypatch.setattr(processor, 'runtime_status', lambda: {'available': True, 'embedder_available': True, 'errors': []})
    captured = {}

    def fake_upsert(rows):
        captured['rows'] = rows

    monkeypatch.setattr(processor, '_upsert_datasheet_chunks', fake_upsert)

    result = processor.process_documents_batch([str(sample)])
    assert result['summary']['successfully_processed'] == 1
    assert result['processing_results'][0]['chunks_created'] >= 1
    assert captured['rows'][0]['filename'] == sample.name
