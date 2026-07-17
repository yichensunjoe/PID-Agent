from pathlib import Path

from agentcad.diagnostics import DiagnosticLogger


def test_diagnostic_logger_redacts_content_but_keeps_safe_metadata(tmp_path: Path):
    secret = "sk-diagnostic-secret-value"
    prompt = "confidential process prompt"
    logger = DiagnosticLogger(
        tmp_path / "diagnostics.jsonl",
        service_version="test",
        max_bytes=64 * 1024,
    )

    record = logger.emit(
        "llm.test",
        prompt=prompt,
        prompt_chars=len(prompt),
        api_key=secret,
        api_key_present=True,
        query=f"api_key={secret}&mode=test",
        error=RuntimeError(prompt),
    )

    assert record["prompt"] == f"<redacted:{len(prompt)} chars>"
    assert record["prompt_chars"] == len(prompt)
    assert record["api_key"] == "<redacted>"
    assert record["api_key_present"] is True
    assert secret not in record["query"]
    assert record["error"] == {
        "type": "RuntimeError",
        "message": "<redacted>",
        "message_chars": len(prompt),
    }

    payload = (tmp_path / "diagnostics.jsonl").read_text(encoding="utf-8")
    assert secret not in payload
    assert prompt not in payload
    assert logger.recent(10)[0]["event"] == "llm.test"
