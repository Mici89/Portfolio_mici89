import uuid

from pathlib import Path
from typing import Annotated
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from app.core.config import get_settings
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.document import Document
from app.repositories.knowledge_base import get_knowledge_base_by_id
from app.schemas.document import DocumentRead
from app.services.file_storage import FileTooLargeError, save_upload_file
from app.repositories.document import (
    create_document,
    list_documents,
    delete_document,
    get_document_by_id,
)
from app.services.document_processing import process_document
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/knowledge-bases/{knowledge_base_id}/documents",
    tags=["Documents"],
)

allowed_extensions = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}

@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    knowledge_base_id: uuid.UUID,
    file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> Document:
    knowledge_base = get_knowledge_base_by_id(
        db,
        knowledge_base_id,
    )

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    suffix = Path(file.filename or "").suffix.lower()
    content_type = allowed_extensions.get(suffix)

    if content_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only TXT, Markdown and PDF files are supported",
        )

    try:
        stored_file = await save_upload_file(
            file,
            knowledge_base_id,
        )
    except FileTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File exceeds the 10 MB limit",
        ) from error

    if stored_file.size == 0:
        stored_file.path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    try:
        document = create_document(
            db,
            knowledge_base_id=knowledge_base_id,
            file_name=file.filename or "unnamed",
            content_type=content_type,
            file_size=stored_file.size,
            storage_path=str(stored_file.path),
            content_hash=stored_file.content_hash,
        )
    except IntegrityError as error:
        db.rollback()
        stored_file.path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The same file already exists in this knowledge base",
        ) from error
    except SQLAlchemyError as error:
        logger.exception(
            "Failed to save document metadata for knowledge base %s",
            knowledge_base_id,
        )
        db.rollback()
        stored_file.path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save document",
        ) from error

    document.status = "processing"
    document.error_message = None
    db.commit()
    db.refresh(document)
    background_tasks.add_task(process_document, document.id)
    return document
@router.get(
    "",
    response_model=list[DocumentRead],
)
def list_knowledge_base_documents(
    knowledge_base_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    if get_knowledge_base_by_id(db, knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    return list(
        list_documents(
            db,
            knowledge_base_id=knowledge_base_id,
        )
    )


@router.post(
    "/{document_id}/retry",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_knowledge_base_document(
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> Document:
    document = get_document_by_id(
        db,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.status not in {"failed", "uploaded"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed or uploaded documents can be retried",
        )
    if document.retry_count >= get_settings().max_document_retries:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document retry limit has been reached",
        )

    document.status = "processing"
    document.error_message = None
    db.commit()
    db.refresh(document)
    background_tasks.add_task(process_document, document.id)
    return document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_knowledge_base_document(
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    document = get_document_by_id(
        db,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    storage_path = Path(document.storage_path)

    try:
        delete_document(
            db,
            document=document,
        )
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        ) from error

    try:
        storage_path.unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Failed to delete stored file %s",
            storage_path,
        )
