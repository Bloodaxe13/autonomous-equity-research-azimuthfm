import fitz
import pytest

from src.tools.runtime_documents import OpenAIDocumentToolkit


class _FakeHttpResponse:
    def __init__(self, *, url: str, content: bytes, content_type: str = 'application/pdf'):
        self.url = url
        self.content = content
        self.headers = {'content-type': content_type}
        self.status_code = 200

    def raise_for_status(self):
        return None


class _FakeFilesAPI:
    def __init__(self):
        self.calls = []
        self.counter = 0

    def create(self, *, file, purpose):
        self.counter += 1
        payload = file.read()
        self.calls.append({'purpose': purpose, 'bytes': len(payload)})
        return type('UploadedFile', (), {'id': f'file_{self.counter}'})()


class _FakeVectorStoreFilesAPI:
    def __init__(self):
        self.create_calls = []
        self.list_calls = []
        self.statuses = ['completed']

    def create(self, *, vector_store_id, file_id):
        self.create_calls.append({'vector_store_id': vector_store_id, 'file_id': file_id})
        return type('VectorStoreFile', (), {'id': f'vsf_{len(self.create_calls)}', 'status': 'in_progress'})()

    def list(self, *, vector_store_id):
        self.list_calls.append(vector_store_id)
        status = self.statuses[min(len(self.list_calls) - 1, len(self.statuses) - 1)]
        item = type('VectorStoreFileItem', (), {'status': status})()
        return type('VectorStoreFileList', (), {'data': [item]})()


class _FakeVectorStoresAPI:
    def __init__(self):
        self.calls = []
        self.files = _FakeVectorStoreFilesAPI()

    def create(self, *, name):
        self.calls.append({'name': name})
        return type('VectorStore', (), {'id': f'vector_{len(self.calls)}'})()


class _FakeResponsesAPI:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type('Response', (), {'output_text': 'answer text', 'id': f'resp_{len(self.calls)}'})()


class _FakeOpenAIClient:
    def __init__(self):
        self.files = _FakeFilesAPI()
        self.vector_stores = _FakeVectorStoresAPI()
        self.responses = _FakeResponsesAPI()


def _pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_document_toolkit_uses_direct_pdf_mode_for_single_pdf(monkeypatch, tmp_path):
    client = _FakeOpenAIClient()
    toolkit = OpenAIDocumentToolkit(client=client, cache_dir=tmp_path, direct_model='gpt-5.4', retrieval_model='gpt-5.4-mini')
    pdf_bytes = _pdf_bytes('Annual report revenue and risk discussion')

    monkeypatch.setattr(
        'src.tools.runtime_documents.httpx.get',
        lambda *args, **kwargs: _FakeHttpResponse(url='https://example.test/report.pdf', content=pdf_bytes),
    )

    result = toolkit.analyze(
        question='Summarize the document',
        document_urls=['https://example.test/report.pdf'],
        mode='auto',
        task_type='summarize',
    )

    assert result['mode_used'] == 'direct_pdf'
    assert result['answer'] == 'answer text'
    assert client.files.calls[0]['purpose'] == 'user_data'
    request = client.responses.calls[0]
    assert request['model'] == 'gpt-5.4'
    assert request['input'][0]['content'][0] == {'type': 'input_file', 'file_id': 'file_1'}
    assert request['input'][0]['content'][1]['type'] == 'input_text'


def test_document_toolkit_uses_file_search_for_multi_pdf(monkeypatch, tmp_path):
    client = _FakeOpenAIClient()
    toolkit = OpenAIDocumentToolkit(client=client, cache_dir=tmp_path, direct_model='gpt-5.4', retrieval_model='gpt-5.4-mini')
    pdf_one = _pdf_bytes('First PDF')
    pdf_two = _pdf_bytes('Second PDF')

    def fake_get(url, *args, **kwargs):
        payload = pdf_one if 'one' in url else pdf_two
        return _FakeHttpResponse(url=url, content=payload)

    monkeypatch.setattr('src.tools.runtime_documents.httpx.get', fake_get)

    result = toolkit.analyze(
        question='Compare the revenue drivers',
        document_urls=['https://example.test/one.pdf', 'https://example.test/two.pdf'],
        mode='auto',
        task_type='qa',
        debug=True,
        max_num_results=7,
    )

    assert result['mode_used'] == 'file_search'
    assert result['vector_store_id'] == 'vector_1'
    assert [call['purpose'] for call in client.files.calls] == ['assistants', 'assistants']
    assert len(client.vector_stores.files.create_calls) == 2
    request = client.responses.calls[0]
    assert request['model'] == 'gpt-5.4-mini'
    assert request['tools'][0]['type'] == 'file_search'
    assert request['tools'][0]['vector_store_ids'] == ['vector_1']
    assert request['tools'][0]['max_num_results'] == 7
    assert request['include'] == ['file_search_call.results']


def test_document_toolkit_reuses_cached_upload_for_same_pdf(monkeypatch, tmp_path):
    client = _FakeOpenAIClient()
    toolkit = OpenAIDocumentToolkit(client=client, cache_dir=tmp_path, direct_model='gpt-5.4', retrieval_model='gpt-5.4-mini')
    pdf_bytes = _pdf_bytes('Same PDF twice')

    monkeypatch.setattr(
        'src.tools.runtime_documents.httpx.get',
        lambda *args, **kwargs: _FakeHttpResponse(url='https://example.test/reused.pdf', content=pdf_bytes),
    )

    first = toolkit.analyze(
        question='Summarize once',
        document_urls=['https://example.test/reused.pdf'],
        mode='auto',
        task_type='summarize',
    )
    second = toolkit.analyze(
        question='Summarize twice',
        document_urls=['https://example.test/reused.pdf'],
        mode='auto',
        task_type='summarize',
    )

    assert first['document_file_ids'] == ['file_1']
    assert second['document_file_ids'] == ['file_1']
    assert len(client.files.calls) == 1


def test_document_toolkit_raises_immediately_on_failed_vector_store_file(monkeypatch, tmp_path):
    client = _FakeOpenAIClient()
    client.vector_stores.files.statuses = ['failed']
    toolkit = OpenAIDocumentToolkit(client=client, cache_dir=tmp_path, direct_model='gpt-5.4', retrieval_model='gpt-5.4-mini')
    pdf_one = _pdf_bytes('First PDF')
    pdf_two = _pdf_bytes('Second PDF')

    def fake_get(url, *args, **kwargs):
        payload = pdf_one if 'one' in url else pdf_two
        return _FakeHttpResponse(url=url, content=payload)

    monkeypatch.setattr('src.tools.runtime_documents.httpx.get', fake_get)

    with pytest.raises(RuntimeError) as exc_info:
        toolkit.analyze(
            question='Compare the revenue drivers',
            document_urls=['https://example.test/one.pdf', 'https://example.test/two.pdf'],
            mode='file_search',
            task_type='qa',
        )

    assert 'failed' in str(exc_info.value).lower()
