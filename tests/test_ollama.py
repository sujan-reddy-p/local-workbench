from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from local_workbench.ollama import OllamaClient


def test_client_sends_file_payload_to_localhost_and_validates_structured_result() -> None:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
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
        image = b"local-image-bytes"
        client = OllamaClient(model="test-model", host=f"http://127.0.0.1:{server.server_port}")
        result = client.inspect("classify by scene", "photos/dog.jpg", image)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert result["category"] == "animals"
    assert result["confidence"] == 0.91
    request = requests[0]
    assert request["model"] == "test-model"
    assert request["options"]["num_ctx"] == 4096
    assert request["messages"][1]["images"] == [base64.b64encode(image).decode()]
    assert "classify by scene" in request["messages"][1]["content"]


@pytest.mark.parametrize(
    ("model", "host"),
    [("gemma4:cloud", "http://127.0.0.1:11434"), ("gemma3:4b", "https://example.com")],
)
def test_client_rejects_cloud_models_and_non_loopback_hosts(model: str, host: str) -> None:
    with pytest.raises(ValueError):
        OllamaClient(model=model, host=host)
