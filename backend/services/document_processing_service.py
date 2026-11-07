from __future__ import annotations
from typing import List

from backend.core.config import settings
from backend.core.exceptions import ValidationException


class DocumentProcessingService:
    """Extracts plain text from uploaded fact-sheet files and splits it into retrieval-sized chunks."""

    @staticmethod
    def extract_text(*, filename: str, raw_bytes: bytes) -> str:
        lower_name = filename.lower()
        if lower_name.endswith(".pdf"):
            return DocumentProcessingService._extract_pdf_text(raw_bytes)
        if lower_name.endswith(".txt") or lower_name.endswith(".md"):
            try:
                return raw_bytes.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValidationException("File is not valid UTF-8 text") from e
        raise ValidationException("Unsupported document type. Only PDF and text (.txt/.md) files are accepted.")

    @staticmethod
    def _extract_pdf_text(raw_bytes: bytes) -> str:
        import io
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
        except Exception as e:
            raise ValidationException("Unable to read PDF file") from e

        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
        return "\n\n".join(pages_text)

    @staticmethod
    def chunk_text(text: str) -> List[str]:
        """
        Fixed-size character chunking with overlap. Collapses whitespace and
        skips chunks that are empty/whitespace-only (e.g. blank PDF pages).
        """
        normalized = " ".join(text.split())
        if not normalized:
            raise ValidationException("Document contains no extractable text")

        size = settings.KNOWLEDGE_CHUNK_SIZE_CHARS
        overlap = settings.KNOWLEDGE_CHUNK_OVERLAP_CHARS
        step = max(size - overlap, 1)

        chunks: List[str] = []
        start = 0
        length = len(normalized)
        while start < length:
            end = min(start + size, length)
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == length:
                break
            start += step
        return chunks
