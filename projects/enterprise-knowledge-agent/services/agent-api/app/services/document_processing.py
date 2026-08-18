import logging
import uuid
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models.document import Document
from app.repositories.document_chunk import replace_document_chunks
from app.services.document_parser import DocumentParseError, extract_document
from app.services.embedding_service import EmbeddingError, generate_embeddings
from app.services.pii_redactor import redact_personal_information
from app.services.text_splitter import split_document

logger = logging.getLogger(__name__)


def _set_status(document: Document, status: str, *, error: str | None = None) -> None:
    document.status = status
    document.error_message = error


def process_document(document_id: uuid.UUID) -> None:
    """Run indexing outside the upload request using a fresh database session."""
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("Document %s disappeared before processing", document_id)
            return

        try:
            _set_status(document, "parsing")
            db.commit()
            blocks = extract_document(Path(document.storage_path))

            _set_status(document, "chunking")
            db.commit()
            redacted_blocks = [
                type(block)(
                    text=redact_personal_information(block.text),
                    metadata=block.metadata,
                )
                for block in blocks
            ]
            chunks = split_document(redacted_blocks)
            if not chunks:
                raise DocumentParseError("Document contains no usable chunks")

            _set_status(document, "embedding")
            db.commit()
            embeddings = generate_embeddings([chunk.content for chunk in chunks])
            replace_document_chunks(
                db,
                document=document,
                chunks=chunks,
                embeddings=embeddings,
            )
        except (DocumentParseError, EmbeddingError, SQLAlchemyError, OSError, ValueError) as error:
            db.rollback()
            document = db.get(Document, document_id)
            if document is None:
                return
            document.retry_count += 1
            _set_status(document, "failed", error=str(error)[:1000])
            db.commit()
            logger.exception("Document processing failed for %s", document_id)


def retry_document(document_id: uuid.UUID) -> None:
    process_document(document_id)
