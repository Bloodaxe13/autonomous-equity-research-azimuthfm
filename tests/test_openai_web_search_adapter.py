from types import SimpleNamespace

from src.tools.runtime_web import OpenAIWebSearchAdapter


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.output_text = ''

    def model_dump(self):
        return self._payload


class _FakeClient:
    class _Responses:
        def __init__(self, payload):
            self._payload = payload

        def create(self, **kwargs):
            return _FakeResponse(self._payload)

    def __init__(self, payload):
        self.responses = self._Responses(payload)


def test_openai_web_search_adapter_extracts_urls_from_message_annotations(monkeypatch):
    payload = {
        'output': [
            {'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'search', 'query': 'CUV ASX announcements'}},
            {
                'type': 'message',
                'content': [
                    {
                        'type': 'output_text',
                        'text': 'Here is the announcements hub.',
                        'annotations': [
                            {
                                'type': 'url_citation',
                                'title': 'ASX Announcements - CLINUVEL',
                                'url': 'https://www.clinuvel.com/investor/asx-announcements/'
                            }
                        ]
                    }
                ]
            }
        ]
    }
    adapter = OpenAIWebSearchAdapter(api_key='x', model='gpt-5.4-mini')
    adapter.client = _FakeClient(payload)
    results = adapter.search('CUV ASX announcements', limit=5)
    assert len(results.results) == 1
    assert results.results[0].title == 'ASX Announcements - CLINUVEL'
    assert results.results[0].url == 'https://www.clinuvel.com/investor/asx-announcements/'
