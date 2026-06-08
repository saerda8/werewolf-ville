from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[1] / "ui" / "templates" / "index.html"


def test_llm_provider_switch_keeps_provider_fields_isolated():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'onchange="switchLlmProvider()"' in html
    assert "const llmProviderDrafts = {};" in html
    assert "llmProviderDrafts[activeLlmProvider] = readLlmFieldDraft(activeLlmProvider);" in html
    assert "applyLlmFieldDraft(draft || {provider: activeLlmProvider});" in html
    assert 'saved.provider === "chat2api" && knownRemoteBases.has(saved.api_base)' in html
