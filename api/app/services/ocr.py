"""OCR provider protocol + Mistral implementation + layout-aware chunker."""

from typing import Protocol, runtime_checkable

import tiktoken

from app.core.config import settings

_enc = tiktoken.get_encoding("cl100k_base")
_CHUNK_TOKENS = 500
_CHUNK_OVERLAP = 50


class OcrResult:
    def __init__(self, text: str, page_count: int, pages: list[str]) -> None:
        self.text = text
        self.page_count = page_count
        self.pages = pages


@runtime_checkable
class OcrProvider(Protocol):
    async def extract(self, file_bytes: bytes, mime_type: str) -> OcrResult: ...


class MistralOcr:
    """Primary OCR via Mistral document understanding API."""

    async def extract(self, file_bytes: bytes, mime_type: str) -> OcrResult:
        import base64

        from mistralai.client.sdk import Mistral

        client = Mistral(api_key=settings.MISTRAL_API_KEY)
        b64 = base64.b64encode(file_bytes).decode()

        response = await client.ocr.process_async(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": f"data:{mime_type};base64,{b64}",
            },
        )
        pages = [p.markdown for p in response.pages]
        full_text = "\n\n---PAGE---\n\n".join(pages)
        return OcrResult(text=full_text, page_count=len(pages), pages=pages)


class PaddleOcrStub:
    """Fallback — placeholder until PaddleOCR is wired in."""

    async def extract(self, file_bytes: bytes, mime_type: str) -> OcrResult:
        placeholder = "[OCR fallback: PaddleOCR not configured]"
        return OcrResult(text=placeholder, page_count=1, pages=[placeholder])


def chunk_markdown(pages: list[str]) -> list[dict[str, object]]:
    """Split markdown pages into ~500-token chunks with 50-token overlap.

    Each chunk carries the 1-based source page number.
    """
    chunks: list[dict[str, object]] = []

    for page_num, page_text in enumerate(pages, start=1):
        paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [page_text]

        buffer: list[str] = []
        buffer_tokens = 0

        for para in paragraphs:
            para_tokens = len(_enc.encode(para))
            if buffer_tokens + para_tokens > _CHUNK_TOKENS and buffer:
                chunks.append(
                    {
                        "content": "\n\n".join(buffer),
                        "page": page_num,
                        "token_count": buffer_tokens,
                    }
                )
                overlap_buf: list[str] = []
                overlap_tok = 0
                for p in reversed(buffer):
                    t = len(_enc.encode(p))
                    if overlap_tok + t > _CHUNK_OVERLAP:
                        break
                    overlap_buf.insert(0, p)
                    overlap_tok += t
                buffer = overlap_buf
                buffer_tokens = overlap_tok

            buffer.append(para)
            buffer_tokens += para_tokens

        if buffer:
            chunks.append(
                {
                    "content": "\n\n".join(buffer),
                    "page": page_num,
                    "token_count": buffer_tokens,
                }
            )

    return chunks
