import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.service import run_knowledge_agent
from app.db.session import get_db
from app.repositories.knowledge_base import get_knowledge_base_by_id
from app.schemas.qa import AgentTrace, QuestionRequest, QuestionResponse
from app.services.llm_service import GenerationError


router = APIRouter(
    prefix="/knowledge-bases/{knowledge_base_id}/ask",
    tags=["Question Answering"],
)


@router.post("", response_model=QuestionResponse)
def ask_knowledge_base(
    knowledge_base_id: uuid.UUID,
    data: QuestionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> QuestionResponse:
    if get_knowledge_base_by_id(db, knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    try:
        result = run_knowledge_agent(
            db=db,
            knowledge_base_id=knowledge_base_id,
            question=data.question,
            top_k=data.top_k,
        )
    except GenerationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge agent is unavailable",
        ) from error

    return QuestionResponse(
        answer=result.answer,
        sources=result.sources,
        agent_trace=AgentTrace(
            intent=result.state.intent,
            steps=result.state.step_count,
            tools=[item["name"] for item in result.state.tool_calls],
        ),
    )
