class KnowledgeChunker:
    """Split normalized documents while preserving useful sentence boundaries."""

    def __init__(self, *, chunk_size: int = 500, overlap: int = 80) -> None:
        if chunk_size <= overlap:
            raise ValueError("chunk_size must be greater than overlap")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> list[str]:
        normalized = "\n".join(
            line.strip() for line in text.splitlines() if line.strip()
        )
        if not normalized:
            return []

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self.chunk_size, len(normalized))
            if end < len(normalized):
                search_start = start + self.overlap + 1
                boundary = max(
                    normalized.rfind(mark, search_start, end)
                    for mark in ("\n", "。", "！", "？", ". ", "; ")
                )
                if boundary >= search_start:
                    end = boundary + 1
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(normalized):
                break
            start = end - self.overlap
        return chunks
