import ollama

from app.core.config import get_settings


class EmbeddingError(RuntimeError):
    pass


settings = get_settings()

client = ollama.Client(
    host=settings.ollama_base_url,
)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    try:
        response = client.embed(
            model=settings.embedding_model,
            input=texts,
        )
    except Exception as error:
        raise EmbeddingError(
            "Failed to generate embeddings"
        ) from error

    embeddings = [
        list(embedding)
        for embedding in response.embeddings
    ]

    if len(embeddings) != len(texts):
        raise EmbeddingError(
            "Embedding count does not match input count"
        )

    if any(
        len(embedding) != settings.embedding_dimension
        for embedding in embeddings
    ):
        raise EmbeddingError(
            "Unexpected embedding dimension"
        )

    return embeddings


def generate_embedding(text: str) -> list[float]:
    embeddings = generate_embeddings([text])
    return embeddings[0]