# External source checkouts

This directory is reserved for vendored third-party source checkouts that
WindAgent does not own.

No production Architecture V2 package imports code from this directory. Any
future integration must be represented by a canonical package dependency and
must pass the architecture and secret-exposure gates.

The historical Agent-S3 adapter and its installer were retired together with
the legacy backend runtime. Historical evidence remains under `artifacts/`.
