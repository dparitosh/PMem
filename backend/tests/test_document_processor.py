from pathlib import Path
import zipfile

import pytest

from backend.Services import document_processor as processor


def test_detect_format_pdf():
    fmt = processor._detect_format(Path('demo.pdf'))
    assert fmt == 'pdf'


def test_chunk_document_returns_non_empty_chunks():
    chunks = processor._chunk_document('Alpha beta gamma. ' * 300)
    assert chunks
    assert all(chunk.strip() for chunk in chunks)


def test_extract_text_file(tmp_path):
    sample = tmp_path / 'requirements.txt'
    sample.write_text('REQ-001 Bearing life shall be validated.', encoding='utf-8')

    extracted = processor.extract_text_from_file(sample)

    assert extracted['file_type'] == 'text'
    assert 'Bearing life' in extracted['text']


def test_extract_html_file_strips_markup(tmp_path):
    sample = tmp_path / 'requirements.html'
    sample.write_text('<html><body><h1>REQ-002</h1><script>ignore()</script><p>Cooling &amp; flow requirement.</p></body></html>', encoding='utf-8')

    extracted = processor.extract_text_from_file(sample)

    assert extracted['file_type'] == 'html'
    assert 'Cooling & flow requirement' in extracted['text']
    assert 'ignore()' not in extracted['text']


def test_process_documents_batch_with_monkeypatched_backend(monkeypatch, tmp_path):
    sample = tmp_path / 'sample.pdf'
    sample.write_text('placeholder', encoding='utf-8')

    monkeypatch.setattr(processor, 'extract_text_from_file', lambda file_path: {
        'path': str(sample),
        'filename': sample.name,
        'file_type': 'pdf',
        'text': 'Requirement REQ-001 relates to bearing life and lubrication.',
    })
    monkeypatch.setattr(processor, '_embed_texts', lambda chunks, **kwargs: [[0.1, 0.2, 0.3] for _ in chunks])
    monkeypatch.setattr(processor, 'EMBEDDING_VECTOR_DIMENSIONS', 3)
    monkeypatch.setattr(processor, 'runtime_status', lambda: {'available': True, 'embedder_available': True, 'errors': []})
    captured = {}

    def fake_upsert(rows):
        captured['rows'] = rows

    monkeypatch.setattr(processor, '_upsert_datasheet_chunks', fake_upsert)

    result = processor.process_documents_batch([str(sample)])
    assert result['summary']['successfully_processed'] == 1
    assert result['processing_results'][0]['chunks_created'] >= 1
    assert captured['rows'][0]['filename'] == sample.name
    assert captured['rows'][0]['source'].startswith('document://')
    assert captured['rows'][0]['document_id']
    assert str(tmp_path) not in captured['rows'][0]['source']
    assert 'path' not in result['processing_results'][0]


def test_process_documents_rejects_embedding_count_mismatch(monkeypatch, tmp_path):
    sample = tmp_path / 'requirements.txt'
    sample.write_text('Requirement content', encoding='utf-8')
    monkeypatch.setattr(processor, 'runtime_status', lambda: {'available': True, 'embedder_available': True, 'errors': []})
    monkeypatch.setattr(processor, '_embed_texts', lambda chunks, **kwargs: [])
    monkeypatch.setattr(processor, '_upsert_datasheet_chunks', lambda rows: pytest.fail('invalid rows must not be written'))

    result = processor.process_documents_batch([str(sample)])

    assert result['summary']['failed_processing'] == 1
    assert 'returned 0 vectors for 1 chunks' in result['processing_results'][0]['error']
    assert 'path' not in result['processing_results'][0]


def test_document_identity_is_stable_across_temporary_directories(monkeypatch, tmp_path):
    first = tmp_path / 'one' / 'manual.txt'
    second = tmp_path / 'two' / 'manual.txt'
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text('Stable extracted content', encoding='utf-8')
    second.write_text('Stable extracted content', encoding='utf-8')
    monkeypatch.setattr(processor, 'runtime_status', lambda: {'available': True, 'embedder_available': True, 'errors': []})
    monkeypatch.setattr(processor, '_embed_texts', lambda chunks, **kwargs: [[0.1, 0.2] for _ in chunks])
    monkeypatch.setattr(processor, 'EMBEDDING_VECTOR_DIMENSIONS', 2)
    captured = []
    monkeypatch.setattr(processor, '_upsert_datasheet_chunks', lambda rows: captured.append(rows))

    processor.process_documents_batch([str(first)])
    processor.process_documents_batch([str(second)])

    assert captured[0][0]['document_id'] == captured[1][0]['document_id']
    assert captured[0][0]['source'] == captured[1][0]['source']
    assert captured[0][0]['char_start'] == 0
    assert captured[0][0]['char_end'] == len('Stable extracted content')


def test_legacy_binary_office_formats_are_not_advertised():
    assert '.doc' not in processor.SUPPORTED_FORMATS['word']
    assert '.ppt' not in processor.SUPPORTED_FORMATS['powerpoint']


def test_embedding_dimension_must_match_vector_index(monkeypatch):
    monkeypatch.setattr(processor, 'EMBEDDING_VECTOR_DIMENSIONS', 3)

    with pytest.raises(RuntimeError, match='does not match configured'):
        processor._validated_embeddings(['chunk'], [[0.1, 0.2]])


def test_chunk_records_preserve_source_offsets():
    text = ('Alpha beta gamma. ' * 200).strip()

    records = processor._chunk_document_records(text)

    assert len(records) > 1
    assert all(text[item['char_start']:item['char_end']] == item['content'] for item in records)


def test_ooxml_expanded_content_limit_blocks_archive_bombs(monkeypatch, tmp_path):
    sample = tmp_path / 'large.docx'
    with zipfile.ZipFile(sample, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', '<document>' + ('x' * 100) + '</document>')
    monkeypatch.setattr(processor, 'MAX_OOXML_EXPANDED_BYTES', 32)

    with pytest.raises(ValueError, match='expanded-content safety limit'):
        processor._validate_ooxml_archive(sample, 'word/')
