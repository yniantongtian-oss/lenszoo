"""Vision-model / OCR fallback for prescription tables that exist only as images.

Status: STUB with a working interface. No OCR model ships with LensZoo 0.1.

How it plugs in
---------------
1. `gpatents.extract_page` lists image-only tables in `ExtractionReport.image_tables`
   (caption such as 'Table 1', the image URL when Google Patents has one, and the
   CNIPA PDF URL, which always contains the page image).
2. An `OCRBackend` turns an image (bytes) into rows of cell strings.
3. The rows go through the *same* `tables.rows_to_surfaces` / `apply_aspheric`
   code as HTML tables, then through `lenszoo.verify`, which is what catches OCR
   typos (sign flips, dropped exponents, swapped digits) via EFL/TTL/ImgH checksums
   and spot-size blow-ups.

Backends you can implement (see docs in README):
* `OpenAICompatibleVLM` - any OpenAI-compatible chat endpoint serving a vision
  model (e.g. Qwen2.5-VL via vLLM, or a hosted API). Sends the image with
  `PROMPT` and expects TSV back.
* PaddleOCR table recognition (PP-Structure) - good on clean CNIPA scans.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Protocol

PROMPT = (
    "This image is a lens prescription table from a Chinese patent. Transcribe it "
    "exactly as tab-separated values, one table row per line, keeping the header "
    "row. Keep empty cells as empty fields. Copy numbers character by character, "
    "including signs and exponents (E-02). Write \u65e0\u7a77 for infinity. Output only TSV."
)


class OCRBackend(Protocol):
    def image_to_rows(self, image: bytes) -> list[list[str]]: ...


class NullBackend:
    """Default backend: refuses, so nothing is silently invented."""

    def image_to_rows(self, image: bytes) -> list[list[str]]:
        raise NotImplementedError(
            "No OCR backend configured. Set LENSZOO_VLM_URL / LENSZOO_VLM_MODEL "
            "(OpenAI-compatible) or pass your own OCRBackend."
        )


def tsv_to_rows(tsv: str) -> list[list[str]]:
    lines = [ln for ln in tsv.strip().splitlines() if ln.strip() and not ln.startswith("```")]
    return [ln.split("\t") for ln in lines]


class OpenAICompatibleVLM:
    """Minimal client for an OpenAI-compatible /chat/completions vision endpoint.

    Untested against a live model in v0.1 (no endpoint was available while
    building); the request shape follows the public OpenAI chat-completions spec.
    """

    def __init__(self, url: str | None = None, model: str | None = None, api_key: str | None = None):
        self.url = url or os.environ.get("LENSZOO_VLM_URL")
        self.model = model or os.environ.get("LENSZOO_VLM_MODEL", "qwen2.5-vl")
        self.api_key = api_key or os.environ.get("LENSZOO_VLM_KEY", "")
        if not self.url:
            raise ValueError("LENSZOO_VLM_URL not set")

    def image_to_rows(self, image: bytes) -> list[list[str]]:
        import requests

        b64 = base64.b64encode(image).decode()
        body = {"model": self.model, "temperature": 0, "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
        r = requests.post(self.url.rstrip("/") + "/chat/completions", data=json.dumps(body),
                          headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                          timeout=120)
        r.raise_for_status()
        return tsv_to_rows(r.json()["choices"][0]["message"]["content"])


def get_backend() -> OCRBackend:
    if os.environ.get("LENSZOO_VLM_URL"):
        return OpenAICompatibleVLM()
    return NullBackend()
