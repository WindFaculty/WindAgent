# Risk Register — Phase 13

## Risks and Mitigations

1. **Self-Package False Positive**: AST scan flags a package importing itself as an undeclared dependency.
   - *Mitigation*: `_undeclared_imports()` excludes the package's own name (`source_dir.name`), treating intra-package imports as legitimate.

2. **Checker/Policy Drift**: Hardcoding the config path in tests while the checker uses a different default.
   - *Mitigation*: `test_checker_uses_scaffold_v2_yaml` loads the checker module and asserts `DEFAULT_CONFIG` resolves to `configs/architecture/scaffold_v2.yaml` — single source of truth enforced.

3. **Importlib Load Side Effects**: Loading `scripts/check_architecture_imports.py` as a module could trigger top-level side effects.
   - *Mitigation*: Loaded via `importlib.util.spec_from_file_location` at test time only; module has no executable side effects at import.
