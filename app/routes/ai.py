"""AI routes: HTTP only. The service owns everything else."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.config import Settings
from app.context import UserContext
from app.deps import get_db, require_roles
from app.schemas import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(prefix="/ai", tags=["ai"])

DbSession = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[UserContext, Depends(require_roles("admin", "hr", "employee"))]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest, ctx: AnyRole, request: Request, session: DbSession
) -> ChatResponse:
    """One chat turn. The agent only has this user's allowed tools."""
    settings: Settings = request.app.state.settings
    result = await chat_service.chat(session, ctx, settings, body.message)
    return ChatResponse(**result)
