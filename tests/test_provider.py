import json

import httpx
import pytest

from app.llm import GeminiLLM, GroqLLM, ProviderError
from app.models import Section
from app.retrieval import Hit

HITS = [
    Hit(
        Section(id="night", title="Night shift escort", text="Drops after 8 PM require a security escort."), 1
    )
]


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (429, {"error": "quota"}, "quota"),
        (500, {"error": "internal"}, "llm_unavailable"),
        (200, {"candidates": []}, "invalid_output"),
        (
            200,
            {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]},
            "incomplete_output",
        ),
        (
            200,
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not-json"}]}}]},
            "invalid_output",
        ),
    ],
)
async def test_http_failures_have_no_hidden_retries(settings, status, body, expected):
    settings.gemini_api_key = "fake-key-only-for-test"
    provider = GeminiLLM(settings)
    await provider.client.aclose()
    count = 0

    def handle(request):
        nonlocal count
        count += 1
        assert request.headers["x-goog-api-key"] == settings.gemini_api_key
        assert "fake-key" not in str(request.url)
        payload = json.loads(request.content)
        assert "responseJsonSchema" in payload["generationConfig"]
        assert payload["generationConfig"]["maxOutputTokens"] <= 512
        prompt = payload["systemInstruction"]["parts"][0]["text"]
        assert "A satisfied approval condition does not waive an independent" in prompt
        return httpx.Response(status, json=body)

    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError, match=expected):
        await provider.respond("When is an escort required?", HITS)
    assert count == 1
    await provider.aclose()


async def test_successful_provider_output_is_validated(settings):
    settings.gemini_api_key = "fake-key-only-for-test"
    provider = GeminiLLM(settings)
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {
                                        "text": '{"verdict":"information","points":[{"text":"An escort is required after 8 PM.","section_ids":["night"]}]}'
                                    }
                                ]
                            },
                        }
                    ]
                },
            )
        )
    )
    result = await provider.respond("When is an escort required?", HITS)
    assert result.section_ids == ["night"]
    await provider.aclose()


@pytest.mark.parametrize("status", [200, 429, 503])
async def test_groq_structured_selection_and_single_request(settings, status):
    settings.groq_api_key = "groq-test-key-never-real"
    provider = GroqLLM(settings)
    await provider.client.aclose()
    count = 0

    def handle(request):
        import json

        nonlocal count
        count += 1
        assert request.headers["Authorization"] == "Bearer " + settings.groq_api_key
        body = json.loads(request.content)
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"]["properties"]["points"]["items"]["properties"]["section_ids"]["items"][
            "enum"
        ] == ["night"]
        return httpx.Response(
            status,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"verdict":"information","points":[{"text":"An escort is required after 8 PM.","section_ids":["night"]}]}'
                        },
                    }
                ]
            },
        )

    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    if status == 200:
        assert (await provider.respond("When is an escort required?", HITS)).section_ids == ["night"]
    else:
        with pytest.raises(ProviderError, match="quota" if status == 429 else "llm_unavailable"):
            await provider.respond("When is an escort required?", HITS)
    assert count == 1
    await provider.aclose()
