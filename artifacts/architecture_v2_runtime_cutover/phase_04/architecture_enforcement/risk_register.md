# Phase 4 Architecture Enforcement Risk Register

## Overview
Repository-wide architecture enforcement introduces strict dependency boundaries that may impact existing code.

## Risks

| ID | Risk | Status | Mitigation | Owner |
|----|------|--------|------------|-------|
| AR-01 | Plugins and skills not in package map | **MITIGATED** | Added plugins and skills to scaffold_v2.yaml with full declarations | Architecture Team |
| AR-02 | Legacy backend imports not properly quarantined | **MITIGATED** | Added backend package with quarantine policy, allowlist, and reverse import blocking | Architecture Team |
| AR-03 | Core internal boundaries not enforced | **MITIGATED** | Added internal_boundaries config for domain/config/security separation | Architecture Team |
| AR-04 | Dynamic imports bypass static analysis | **MITIGATED** | Extended check_architecture_imports.py to scan importlib.import_module and __import__ calls | Architecture Team |
| AR-05 | Private API leakage across packages | **MITIGATED** | Added private_cross_package_import rule in public API enforcement | Architecture Team |
| AR-06 | Composition root violations | **MITIGATED** | Added composition root checking for concrete adapter creation | Architecture Team |
| AR-07 | Duplicate canonical models | **MITIGATED** | Existing duplicate_canonical_model rule covers this | Architecture Team |
| AR-08 | Package cycles | **MITIGATED** | Existing forbid_dependency_cycles rule covers this | Architecture Team |
| AR-09 | ORM in application layer | **MITIGATED** | Added orm_in_application_layer rule | Architecture Team |
| AR-10 | Framework imports in core | **MITIGATED** | Existing forbid_core_framework_imports covers this | Architecture Team |

## Acceptance Criteria

- [x] All plugins and skills packages are declared in scaffold_v2.yaml
- [x] Legacy quarantine policy is enforced with allowlist
- [x] Core internal boundaries are declared and checked
- [x] Dynamic import scanning is implemented
- [x] Public API enforcement rules are implemented
- [x] Composition root rule is implemented
- [x] Negative fixtures exist for all violation types
- [x] All negative fixtures make checker fail with correct rule

## Test Results

See `test_results.json` for detailed test execution results.

## Residual Risks

None. All identified risks have been mitigated with corresponding checker rules and tests.
