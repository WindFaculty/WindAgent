import { useEffect, useState } from "react";

interface ProviderInfo {
  name: string;
  status: string;
  models: string[];
}

export function Endpoints() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [health, setHealth] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch("/api/v2/providers"),
      fetch("/api/v2/providers/health"),
    ])
      .then(async ([providersResponse, healthResponse]) => {
        if (!providersResponse.ok) {
          throw new Error(await providersResponse.text());
        }
        if (!healthResponse.ok) {
          throw new Error(await healthResponse.text());
        }
        return Promise.all([
          providersResponse.json() as Promise<ProviderInfo[]>,
          healthResponse.json() as Promise<Record<string, string>>,
        ]);
      })
      .then(([providerRows, healthRows]) => {
        if (active) {
          setProviders(providerRows);
          setHealth(healthRows);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load providers");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main style={{ padding: "24px", color: "var(--text-main)" }}>
      <h1 style={{ margin: 0 }}>Provider endpoints</h1>
      <p style={{ color: "var(--text-muted)", margin: "6px 0 20px" }}>
        Canonical V2 provider status. Credential and endpoint mutations are intentionally
        unavailable until their V2 contracts are published.
      </p>

      {error ? (
        <div role="alert" style={{ color: "var(--color-danger)" }}>
          {error}
        </div>
      ) : (
        <div style={{ display: "grid", gap: "12px" }}>
          {providers.map((provider) => (
            <article
              key={provider.name}
              style={{
                padding: "16px",
                border: "1px solid var(--border-color)",
                borderRadius: "10px",
                background: "rgba(255,255,255,0.02)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "12px",
                  marginBottom: "8px",
                }}
              >
                <strong>{provider.name}</strong>
                <span style={{ color: "var(--color-success)", fontSize: "0.8rem" }}>
                  {health[provider.name] ?? provider.status}
                </span>
              </div>
              <div style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
                {provider.models.join(", ") || "No models advertised"}
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
