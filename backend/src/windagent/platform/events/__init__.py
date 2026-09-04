"""Event + outbox foundation: registry, dispatch, transactional outbox.

``contracts.py`` stays infrastructure-free (architecture gate).  The pure
runtime pieces (envelope re-export, registry, dispatcher, subscriptions)
and the SQL adapters (outbox, publisher) live alongside it — the same
contract/adapter split as ``platform/persistence`` (ADR-0002).
"""

from .contracts import EventBus, EventHandler, EventPublisher, EventSubscription
from .dispatcher import EventDispatchError, InProcessEventBus
from .envelope import EventEnvelope
from .outbox import (
    CHECKPOINT_AFTER_EVENT_WRITE,
    DEFAULT_BACKOFF_S,
    DEFAULT_LEASE_S,
    DEFAULT_MAX_ATTEMPTS,
    OUTBOX_STATUS_DEAD_LETTER,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    OUTBOX_STATUS_PUBLISHING,
    OutboxRecord,
    OutboxStore,
    TransactionalOutbox,
    events_table,
    outbox_table,
)
from .publisher import OutboxPublisher, PublishReport
from .registry import (
    EventTypeRegistry,
    EventVersionMismatchError,
    UnknownEventTypeError,
)
from .subscriptions import Subscription, SubscriptionSet

__all__ = [
    "CHECKPOINT_AFTER_EVENT_WRITE",
    "DEFAULT_BACKOFF_S",
    "DEFAULT_LEASE_S",
    "DEFAULT_MAX_ATTEMPTS",
    "OUTBOX_STATUS_DEAD_LETTER",
    "OUTBOX_STATUS_PENDING",
    "OUTBOX_STATUS_PUBLISHED",
    "OUTBOX_STATUS_PUBLISHING",
    "EventBus",
    "EventDispatchError",
    "EventHandler",
    "EventPublisher",
    "EventSubscription",
    "EventVersionMismatchError",
    "EventTypeRegistry",
    "InProcessEventBus",
    "OutboxPublisher",
    "OutboxRecord",
    "OutboxStore",
    "PublishReport",
    "Subscription",
    "SubscriptionSet",
    "TransactionalOutbox",
    "UnknownEventTypeError",
    "events_table",
    "outbox_table",
]
