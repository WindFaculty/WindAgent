"""Model gateway module (Phase 11): the single routing and provider authority.

Rewritten from the frozen sources ``providers/*`` and
``intelligence/model_router/*`` of the old WindAgent (migration matrix
``modules.model_gateway``).  The duplicate legacy scoring authority is
intentionally not carried over: this module is the only place that decides
which model serves a scope and which endpoint serves a model.
"""
