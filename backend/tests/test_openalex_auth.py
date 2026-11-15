"""Unit tests: API key reaches OpenAlex only, never third parties."""
from unittest.mock import Mock
from app import config as C
from app.clients import scholarly


def test_openalex_bearer_auth(monkeypatch):
    monkeypatch.setattr(C, 'OPENALEX_API_KEY', 'test-secret-not-real')
    seen = []
    def fake_get(url, **kwargs):
        seen.append((url, kwargs))
        return Mock(status_code=200, json=lambda: {'results': []})
    monkeypatch.setattr(scholarly.requests, 'get', fake_get)
    scholarly.search_works('test')
    url, kwargs = seen[0]
    assert url == 'https://api.openalex.org/works'
    assert kwargs['headers']['Authorization'] == 'Bearer test-secret-not-real'
    assert 'mailto' not in kwargs['params']
    assert 'api_key' not in kwargs['params']


def test_key_not_sent_to_other_domains(monkeypatch):
    monkeypatch.setattr(C, 'OPENALEX_API_KEY', 'test-secret-not-real')
    calls = []
    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return Mock(status_code=404)
    monkeypatch.setattr(scholarly.requests, 'get', fake_get)
    scholarly._get('https://api.crossref.org/works/test')
    scholarly._get('https://www.ebi.ac.uk/europepmc/webservices/rest/search')
    assert all('Authorization' not in x['headers'] for x in calls)


def test_works_without_key(monkeypatch):
    monkeypatch.setattr(C, 'OPENALEX_API_KEY', '')
    calls = []
    monkeypatch.setattr(scholarly.requests, 'get', lambda url, **kw: (calls.append(kw) or Mock(status_code=200)))
    scholarly._get('https://api.openalex.org/works')
    assert 'Authorization' not in calls[0]['headers']
