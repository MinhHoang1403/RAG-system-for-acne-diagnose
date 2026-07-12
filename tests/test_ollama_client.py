from src.agent.llm.ollama_client import build_ollama_chat_payload


def test_ollama_payload_uses_bounded_generation_options(monkeypatch):
    monkeypatch.setenv("OLLAMA_THINK", "false")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "30m")
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "192")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "0.2")
    monkeypatch.setenv("OLLAMA_TOP_K", "20")
    monkeypatch.setenv("OLLAMA_TOP_P", "0.9")

    payload = build_ollama_chat_payload(
        model="qwen3:8b",
        messages=[{"role": "user", "content": "mụn là gì?"}],
        temperature=0.7,
    )

    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["keep_alive"] == "30m"
    assert payload["options"] == {
        "num_predict": 192,
        "num_ctx": 4096,
        "temperature": 0.2,
        "top_k": 20,
        "top_p": 0.9,
    }
    assert "num_predict" not in {key for key in payload if key != "options"}
