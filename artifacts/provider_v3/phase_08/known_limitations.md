# Known Limitations Phase 8
- Scoring placeholders for latency, cost, region, recent success rate, recent 429.
- Production should replace InMemoryEndpointStateManager with distributed backend (Redis/SQL).
- Credential decryption not implemented; ciphertext checked for presence only.
