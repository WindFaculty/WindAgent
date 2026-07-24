# WindAgent Core Security Boundary & Secret Hygiene Specification

## 1. Overview

`windagent_core/security/` owns security policy types, principal/permission definitions, and audit structures.
It DOES NOT contain cryptographic implementations (Fernet, AES), environment loaders, or OS keychain logic.

---

## 2. Core Security Domain Types

```python
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ApprovalRequirement(str, Enum):
    NONE = "NONE"
    USER_APPROVAL = "USER_APPROVAL"
    ADMIN_APPROVAL = "ADMIN_APPROVAL"

class Principal(BaseModel):
    id: str
    roles: list[str] = Field(default_factory=list)
    
    model_config = ConfigDict(frozen=True, extra="forbid")

class PermissionEvaluationRequest(BaseModel):
    principal: Principal
    action: str
    resource: str
    risk_level: RiskLevel
    context: Dict[str, Any] = Field(default_factory=dict)

class PermissionDecision(BaseModel):
    outcome: str  # ALLOW, REQUIRE_APPROVAL, DENY
    risk_level: RiskLevel
    reason_code: str
    human_reason: str
    policy_version: str
    matched_rule: Optional[str] = None
    audit_metadata: Dict[str, Any] = Field(default_factory=dict)
```

---

## 3. Secret Hygiene & Encryption Isolation Rules

1. **Secret Reference Isolation**: Secret values are referenced via `SecretRef`. Raw plaintext strings must never appear in `ModelRequest`, `EventEnvelope`, or logs.
2. **Infrastructure Encryption**: Fernet ciphering, Windows Credential Manager, and environment key loading live in `windagent_storage` or `apps/backend/services/secret_service.py`.
3. **No Plaintext Fallbacks**: Hard-coded fallback reads from unencrypted `key.txt` files are prohibited in production.
4. **Secret Migration CLI**: Secret conversion is performed via `windagent security migrate-plaintext-secrets` with audit receipts.
5. **Mandatory Redaction**: `EventDeduplicator` and logging processors sanitize any sensitive keys matching regex `(?i)(key|secret|token|password|auth)`.
