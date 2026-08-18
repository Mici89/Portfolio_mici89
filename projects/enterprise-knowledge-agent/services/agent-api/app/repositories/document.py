import uuid

from sqlalchemy.orm import Session

from app.models.document import Document
from collections.abc import Sequence

from sqlalchemy import select

def create_document(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
    file_name: str,
    content_type: str,
    content_hash: str,
    file_size: int,
    storage_path: str,
) -> Document:
    document = Document(
        knowledge_base_id=knowledge_base_id,
        file_name=file_name,
        content_type=content_type,
        file_size=file_size,
        storage_path=storage_path,
        content_hash=content_hash,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document
def list_documents(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
) -> Sequence[Document]:
    statement = (
        select(Document)
        .where(
            Document.knowledge_base_id == knowledge_base_id
        )
        .order_by(Document.created_at.desc())
    )

    return db.scalars(statement).all()

def get_document_by_id(
    db: Session,
    *,
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document | None:
    statement = select(Document).where(
        Document.id == document_id,
        Document.knowledge_base_id == knowledge_base_id,
    )

    return db.scalar(statement)


def delete_document(
    db: Session,
    *,
    document: Document,
) -> None:
    db.delete(document)
    db.commit()