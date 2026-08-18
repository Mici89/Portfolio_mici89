from sqlalchemy.orm import Session
import uuid
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate
from collections.abc import Sequence

from sqlalchemy import select

def create_knowledge_base(
    db: Session,
    data: KnowledgeBaseCreate,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        name=data.name,
        description=data.description,
    )

    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)

    return knowledge_base

def list_knowledge_bases(db: Session) -> Sequence[KnowledgeBase]:
    statement = select(KnowledgeBase).order_by(
        KnowledgeBase.created_at.desc()
    )
    return db.scalars(statement).all()

def get_knowledge_base_by_id(
    db: Session,
    knowledge_base_id: uuid.UUID,
) -> KnowledgeBase | None:
    return db.get(KnowledgeBase, knowledge_base_id)