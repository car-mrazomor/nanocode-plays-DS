import json
import urllib.request

import pytest

import agent


class FakeCompletions:
    def __init__(self):
        self.calls = []
        self.response = object()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self):
        self.completions = FakeCompletions()
        self.chat = self


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(agent, "client", client)
    return client.completions


def content_of(call):
    messages = call["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    return messages[0]["content"]


# ---- client setup -------------------------------------------------------------

def test_client_points_at_nanocode():
    assert str(agent.client.base_url).rstrip("/") == agent.URL.rstrip("/")
    assert agent.client.api_key == agent.KEY


# ---- act --------------------------------------------------------------------

def test_act_uses_nanocode_model(fake):
    agent.act("hello")
    assert fake.calls[0]["model"] == "nanocode"


def test_act_default_session(fake):
    agent.act("hello")
    assert fake.calls[0]["extra_headers"] == {"X-Nanocode-Session-Id": "1"}


def test_act_custom_session(fake):
    agent.act("hello", chat="42")
    assert fake.calls[0]["extra_headers"] == {"X-Nanocode-Session-Id": "42"}


def test_act_text_only_sends_only_text_part(fake):
    agent.act("start playing")
    assert content_of(fake.calls[0]) == [{"type": "text", "text": "start playing"}]


def test_act_with_image_sends_text_and_image(fake):
    agent.act("current screen", image="QUJD")
    assert content_of(fake.calls[0]) == [
        {"type": "text", "text": "current screen"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
    ]


def test_act_content_parts_are_all_valid(fake):
    agent.act("hello")
    agent.act("hello", image="QUJD")
    for call in fake.calls:
        for part in content_of(call):
            assert isinstance(part, dict) and part.get("type") in ("text", "image_url"), part


def test_act_returns_client_response(fake):
    assert agent.act("hi") is fake.response


# ---- look -------------------------------------------------------------------

class FakeHTTPResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_look_returns_image_from_emulator(monkeypatch):
    seen = []

    def fake_urlopen(req, *args, **kwargs):
        seen.append(req.full_url)
        return FakeHTTPResponse({"image": "QUJD"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert agent.look() == "QUJD"
    assert seen == ["http://127.0.0.1:8341/look"]
