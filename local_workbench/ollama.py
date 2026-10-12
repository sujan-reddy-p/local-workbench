"""Small, dependency-free client for Ollama's local chat endpoint."""

from __future__ import annotations

import base64
import ipaddress
import json
import math
import urllib.error
import urllib.request
from urllib.parse import urlparse

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "summary": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": {"type": "string"},
    },
    "required": ["category", "summary", "confidence", "notes"],
}


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, model: str = "gemma3:4b", host: str = "http://127.0.0.1:11434", timeout: int = 180) -> None:
        parsed = urlparse(host)
        hostname = parsed.hostname or ""
        is_loopback = hostname == "localhost"
        try:
            is_loopback = is_loopback or ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
        if parsed.scheme != "http" or not is_loopback:
            raise ValueError("Local Workbench only connects to an HTTP Ollama server on loopback")
        if model.strip().casefold().endswith(("-cloud", ":cloud")):
            raise ValueError("Cloud models are disabled; choose a model running locally in Ollama")
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def inspect(self, goal: str, relative_path: str, content: str | bytes) -> dict[str, object]:
        prompt = (
            "Perform the user's requested analysis of this one file. Do not claim to change files. "
            "Use only the supplied content. If evidence is insufficient, say so and lower confidence. "
            "Return a concise category, summary, confidence from 0 to 1, and notes.\n\n"
            f"USER TASK: {goal}\nFILE: {relative_path}\n"
        )
        user: dict[str, object] = {"role": "user", "content": prompt}
        if isinstance(content, bytes):
            user["images"] = [base64.b64encode(content).decode("ascii")]
        else:
            user["content"] += "\nFILE CONTENT:\n" + content
        payload = {
            "model": self.model,
            "stream": False,
            "format": RESULT_SCHEMA,
            "messages": [
                {"role": "system", "content": "You are a careful local batch-work analyst. Return only the requested structured result."},
                user,
            ],
            "options": {"temperature": 0.1, "num_ctx": 4096},
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaError(f"Cannot reach Ollama at {self.host}: {reason}") from exc
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama returned an invalid or timed-out response: {exc}") from exc
        try:
            result = json.loads(body["message"]["content"])
            category = result["category"]
            summary = result["summary"]
            confidence = result["confidence"]
            notes = result["notes"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama response did not match the result schema: {exc}") from exc
        if not isinstance(category, str) or not isinstance(summary, str) or not isinstance(notes, str):
            raise OllamaError("Ollama returned non-text result fields")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise OllamaError("Ollama returned a non-numeric confidence")
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise OllamaError("Ollama returned confidence outside [0, 1]")
        return {"category": category[:120], "summary": summary[:4000], "confidence": confidence, "notes": notes[:1000]}
