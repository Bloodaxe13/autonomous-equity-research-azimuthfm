import fitz

from src.tools.runtime_web import HttpFetchAdapter


class _FakeResponse:
    def __init__(self, *, url: str, status_code: int, headers: dict[str, str], text: str = '', content: bytes = b''):
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.text = text
        self.content = content


def test_http_fetch_adapter_returns_structured_error_on_connect_failure(monkeypatch):
    adapter = HttpFetchAdapter()

    def boom(*args, **kwargs):
        raise OSError('dns failed')

    monkeypatch.setattr('src.tools.runtime_web.httpx.get', boom)
    result = adapter.fetch('https://bad-host.invalid')
    assert result.url == 'https://bad-host.invalid'
    assert result.status_code == 599
    assert 'dns failed' in result.text


def test_http_fetch_adapter_extracts_text_from_pdf(monkeypatch):
    adapter = HttpFetchAdapter()

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'Revenue 105.3 Cash 233.0 Annual Report')
    pdf_bytes = doc.tobytes()
    doc.close()

    def fake_get(*args, **kwargs):
        return _FakeResponse(
            url='https://example.test/report.pdf',
            status_code=200,
            headers={'content-type': 'application/pdf'},
            content=pdf_bytes,
        )

    monkeypatch.setattr('src.tools.runtime_web.httpx.get', fake_get)
    result = adapter.fetch('https://example.test/report.pdf')

    assert result.status_code == 200
    assert result.content_type.startswith('application/pdf')
    assert 'Revenue 105.3 Cash 233.0 Annual Report' in result.text


def test_http_fetch_adapter_marks_low_quality_pdf_extraction(monkeypatch):
    adapter = HttpFetchAdapter()

    doc = fitz.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    def fake_get(*args, **kwargs):
        return _FakeResponse(
            url='https://example.test/scan.pdf',
            status_code=200,
            headers={'content-type': 'application/pdf'},
            content=pdf_bytes,
        )

    monkeypatch.setattr('src.tools.runtime_web.httpx.get', fake_get)
    result = adapter.fetch('https://example.test/scan.pdf')

    assert result.status_code == 200
    assert 'PDF_EXTRACTION_QUALITY: low' in result.text
