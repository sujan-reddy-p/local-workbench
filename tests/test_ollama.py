from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from local_workbench.ollama import OllamaClient, OllamaError


def test_client_accepts_valid_structured_result() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            body = json.dumps({"message": {"content": json.dumps({
                "category": "animals", "summary": "A dog outdoors", "confidence": 0.91, "notes": "clear"
            })}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = OllamaClient(model="test-model", host=f"http://127.0.0.1:{server.server_port}")
        result = client.inspect("classify by scene", "photos/dog.jpg", b"local-image-bytes")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert result == {
        "category": "animals",
        "summary": "A dog outdoors",
        "confidence": 0.91,
        "notes": "clear",
    }


@pytest.mark.parametrize(
    ("model", "host"),
    [
        ("gemma4:cloud", "http://127.0.0.1:11434"),
        ("gpt-oss:120b-cloud", "http://127.0.0.1:11434"),
        ("qwen3-coder:480b-cloud", "http://127.0.0.1:11434"),
        ("glm-5.2:cloud", "http://127.0.0.1:11434"),
        ("GEMMA3:4B-CLOUD", "http://127.0.0.1:11434"),
        ("gemma3:4b", "https://example.com"),
    ],
)
def test_client_rejects_cloud_models_and_non_loopback_hosts(model: str, host: str) -> None:
    with pytest.raises(ValueError):
        OllamaClient(model=model, host=host)


def test_client_rejects_malformed_structured_response() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.dumps({"message": {"content": "not-json"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = OllamaClient(model="test-model", host=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(OllamaError, match="did not match the result schema"):
            client.inspect("classify", "notes.md", "text")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize(
    "result",
    [
        {"category": 3, "summary": "ok", "confidence": 0.5, "notes": "ok"},
        {"category": "ok", "summary": [], "confidence": 0.5, "notes": "ok"},
        {"category": "ok", "summary": "ok", "confidence": True, "notes": "ok"},
        {"category": "ok", "summary": "ok", "confidence": "0.5", "notes": "ok"},
        {"category": "ok", "summary": "ok", "confidence": -0.1, "notes": "ok"},
        {"category": "ok", "summary": "ok", "confidence": 1.1, "notes": "ok"},
        {"category": "ok", "summary": "ok", "confidence": float("nan"), "notes": "ok"},
    ],
)
def test_client_rejects_invalid_result_field_types_and_ranges(
    result: dict[str, object],
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.dumps({"message": {"content": json.dumps(result)}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = OllamaClient(model="test-model", host=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(OllamaError):
            client.inspect("classify", "notes.md", "text")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
