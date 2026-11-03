"""
Audit service — business-facing API for recording immutable audit events.

This service is the ONLY correct way to write audit records. It handles:
  - Actor normalization (User object → id + name)
  - Before/after data serialization
  - Event type validation (should come from AuditEventType constants)

The repository handles raw persistence. This service handles meaning.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from broast_pos.data.repositories.audit_repository import AuditEntry, AuditRepository

if TYPE_CHECKING:
    from broast_pos.core.models.user import User

logger = logging.getLogger(__name__)


class AuditService:
    """Business-facing audit logging.

    Usage::

        audit_service.log(
            event_type=AuditEventType.ORDER_CANCELLED,
            user_id=manager.id,
            user_name=manager.display_name,
            order_id=order.id,
            reason="Customer changed mind",
            before={"status": "new", "total": 300},
            after={"status": "cancelled"},
        )
    """

    def __init__(
        self, audit_repo: AuditRepository | None = None,
    ) -> None:
        self._audit = audit_repo or AuditRepository()

    # ------------------------------------------------------------------
    # Primary logging API
    # ------------------------------------------------------------------

    def log(
        self,
        event_type: str,
        user_id: int,
        user_name: str,
        order_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
        reason: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Record a business audit event.

        Parameters
        ----------
        event_type:
            Use constants from AuditEventType (e.g. AuditEventType.ORDER_CANCELLED).
        user_id, user_name:
            The actor who performed the action.
        order_id:
            If the event is order-related, provide the order's primary key.
        entity_type:
            Category of the affected entity: 'order', 'trip', 'customer', 'user', 'shift'.
        entity_id:
            Primary key of the affected entity.
        action:
            Optional human-readable description (e.g. "Applied 50 EGP discount").
        reason:
            Why the action was taken (required for cancellations/overrides).
        before, after:
            Snapshots of relevant state before and after the change.
        details:
            Legacy compatibility dict — also stored in the `details` JSON column.
        """
        try:
            return self._audit.log(
                event_type=event_type,
                user_id=user_id,
                user_name=user_name,
                order_id=order_id,
                details=details,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                reason=reason,
                before_data=before,
                after_data=after,
            )
        except Exception as exc:
            # Audit failures must NEVER crash the application.
            logger.error("Audit log failed for %s: %s", event_type, exc)
            return AuditEntry(event_type=event_type, user_id=user_id, user_name=user_name)

    def log_from_user(
        self,
        event_type: str,
        actor: User,
        order_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        action: str | None = None,
        reason: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Convenience method — accepts a User object instead of id/name separately."""
        return self.log(
            event_type=event_type,
            user_id=actor.id or 0,
            user_name=actor.display_name or actor.username or "",
            order_id=order_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            reason=reason,
            before=before,
            after=after,
            details=details,
        )

    # ------------------------------------------------------------------
    # Query methods (delegate to repository)
    # ------------------------------------------------------------------

    def get_logs_for_date(self, date_str: str) -> list:
        return self._audit.get_logs_for_date(date_str)

    def get_logs_for_order(self, order_id: int) -> list:
        return self._audit.get_logs_for_order(order_id)

    def get_logs_by_user(self, user_id: int, limit: int = 50) -> list:
        return self._audit.get_logs_by_user(user_id, limit)

    def get_logs_by_event_type(
        self, event_type: str, date_str: str | None = None,
    ) -> list:
        return self._audit.get_logs_by_event_type(event_type, date_str)

    def get_logs_filtered(
        self,
        date_str: str | None = None,
        user_id: int | None = None,
        event_type: str | None = None,
        order_id: int | None = None,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list:
        return self._audit.get_logs_filtered(
            date_str=date_str,
            user_id=user_id,
            event_type=event_type,
            order_id=order_id,
            entity_type=entity_type,
            limit=limit,
        )
