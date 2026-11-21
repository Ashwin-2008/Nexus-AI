"""Authorization helpers shared by RAG APIs and specialist agents.

The organization boundary is mandatory and never derived from client input.
Document-level scopes are additive: an admin may read admin-scoped documents,
a member may read organization/member-scoped documents.
"""
from __future__ import annotations

from app.models.document import Document
from app.models.user import User
from app.rag.exceptions import ConfigurationError
from app.rag.types import RagScope

ROLE_SCOPES: dict[str, tuple[str, ...]] = {
    "admin": ("organization", "member", "admin"),
    "member": ("organization", "member"),
}


def scope_from_user(user: User) -> RagScope:
    role = user.role.name if getattr(user, "role", None) else "member"
    scopes = ROLE_SCOPES.get(role)
    if scopes is None:
        # Unknown roles get the least privilege default rather than broad access.
        scopes = ("organization",)
    return RagScope(
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        role=role,
        access_scopes=tuple(scopes),
    )


def require_knowledge_access(user: User) -> RagScope:
    if not getattr(user, "is_active", False):
        raise ConfigurationError("inactive users cannot access knowledge")
    return scope_from_user(user)


def can_manage_document(user: User, document: Document | None) -> bool:
    """Admins or the uploader may re-index/delete a document's index."""
    if document is None or document.organization_id != user.organization_id:
        return False
    role = user.role.name if getattr(user, "role", None) else "member"
    return role == "admin" or document.uploaded_by == user.id


def allowed_for_scope(access_scope: str | None, scope: RagScope) -> bool:
    value = access_scope or "organization"
    if value in scope.access_scopes:
        return True
    return scope.role == "admin" and value in {"organization", "member", "admin"}
