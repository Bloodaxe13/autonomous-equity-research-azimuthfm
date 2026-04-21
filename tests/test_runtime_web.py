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


def test_http_fetch_adapter_rejects_pdf_and_directs_caller_to_document_query(monkeypatch):
    adapter = HttpFetchAdapter()

    def fake_get(*args, **kwargs):
        return _FakeResponse(
            url='https://example.test/report.pdf',
            status_code=200,
            headers={'content-type': 'application/pdf'},
            content=b'%PDF-1.7 fake bytes',
        )

    monkeypatch.setattr('src.tools.runtime_web.httpx.get', fake_get)
    result = adapter.fetch('https://example.test/report.pdf')

    assert result.status_code == 415
    assert result.content_type.startswith('application/pdf')
    assert 'document_query' in result.text
    assert 'deprecated' in result.text.lower()


def test_http_fetch_adapter_rejects_pdf_by_content_type_even_without_pdf_suffix(monkeypatch):
    adapter = HttpFetchAdapter()

    def fake_get(*args, **kwargs):
        return _FakeResponse(
            url='https://example.test/download?id=123',
            status_code=200,
            headers={'content-type': 'application/pdf'},
            content=b'%PDF-1.7 fake bytes',
        )

    monkeypatch.setattr('src.tools.runtime_web.httpx.get', fake_get)
    result = adapter.fetch('https://example.test/download?id=123')

    assert result.status_code == 415
    assert 'document_query' in result.text
