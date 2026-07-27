import { useEffect, useMemo, useState } from "react";

interface ProviderInfo {
  name: string;
  status: string;
  models: string[];
}

interface ModelsProps {
  setActiveTab: (tab: string) => void;
}

export function Models({ setActiveTab }: ModelsProps) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/v2/providers")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(await response.text());
        }
        return response.json() as Promise<ProviderInfo[]>;
      })
      .then((data) => {
        if (active) setProviders(data);
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

  const models = useMemo(
    () =>
      providers.flatMap((provider) =>
        provider.models.map((model) => ({
          id: `${provider.name}:${model}`,
          name: model,
          provider: provider.name,
          status: provider.status,
        })),
      ),
    [providers],
  );
  const query = search.trim().toLowerCase();
  const visibleModels = query
    ? models.filter(
        (model) =>
          model.name.toLowerCase().includes(query) ||
          model.provider.toLowerCase().includes(query),
      )
    : models;

  return (
    <main style={{ padding: "24px", color: "var(--text-main)" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
          marginBottom: "20px",
        }}
      >
        <div>
          <h1 style={{ margin: 0 }}>Models</h1>
          <p style={{ color: "var(--text-muted)", margin: "6px 0 0" }}>
            Read-only inventory from the canonical Architecture V2 provider registry.
          </p>
        </div>
        <button type="button" className="role-btn" onClick={() => setActiveTab("endpoints")}>
          View providers
        </button>
      </header>

      <input
        aria-label="Search models"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search model or provider"
        style={{
          width: "min(420px, 100%)",
          padding: "10px 12px",
          marginBottom: "16px",
          borderRadius: "8px",
          border: "1px solid var(--border-color)",
          background: "var(--bg-darker)",
          color: "var(--text-main)",
        }}
      />

      {error ? (
        <div role="alert" style={{ color: "var(--color-danger)" }}>
          {error}
        </div>
      ) : (
        <div style={{ display: "grid", gap: "10px" }}>
          {visibleModels.map((model) => (
            <article
              key={model.id}
              style={{
                padding: "14px 16px",
                border: "1px solid var(--border-color)",
                borderRadius: "10px",
                background: "rgba(255,255,255,0.02)",
                display: "flex",
                justifyContent: "space-between",
                gap: "12px",
              }}
            >
              <div>
                <strong>{model.name}</strong>
                <div style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
                  {model.provider}
                </div>
              </div>
              <span style={{ color: "var(--color-success)", fontSize: "0.8rem" }}>
                {model.status}
              </span>
            </article>
          ))}
          {!error && visibleModels.length === 0 && (
            <p style={{ color: "var(--text-muted)" }}>No models found.</p>
          )}
        </div>
      )}
    </main>
  );
}
