from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseRead
from app.repositories.knowledge_base import (
    create_knowledge_base,
    list_knowledge_bases,
)

router = APIRouter(
    prefix="/knowledge-bases",
    tags=["Knowledge Bases"],
)


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base_endpoint(
    data: KnowledgeBaseCreate,
    db: Annotated[Session, Depends(get_db)],
) -> KnowledgeBase:
    try:
        return create_knowledge_base(db, data)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge base name already exists",
        ) from error

@router.get(
    "",
    response_model=list[KnowledgeBaseRead],
)
def list_knowledge_bases_endpoint(
    db: Annotated[Session, Depends(get_db)],
) -> list[KnowledgeBase]:
    return list(list_knowledge_bases(db))