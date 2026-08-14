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
    <main className="p-6 bg-background text-on-surface min-h-screen space-y-6">
      <header className="pb-4 border-b border-outline-variant/10">
        <h1 className="text-3xl font-extrabold tracking-tight text-on-surface flex items-center gap-3">
          <span className="material-symbols-outlined text-primary text-3xl">hub</span>
          Provider Endpoints & Connections
        </h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Trạng thái kết nối các nhà cung cấp mô hình V2. Thay đổi cấu hình endpoint/API Keys sẽ sẵn sàng ở các bản cập nhật tiếp theo.
        </p>
      </header>

      {error ? (
        <div role="alert" className="p-4 rounded-lg bg-error-container/20 border border-error/30 text-error text-sm">
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {providers.map((provider) => (
            <article
              key={provider.name}
              className="p-5 rounded-xl bg-surface-container-low border border-outline-variant/15 hover:border-primary/40 transition-all space-y-3"
            >
              <div className="flex justify-between items-center">
                <div className="font-bold text-on-surface text-lg flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary">dns</span>
                  {provider.name}
                </div>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-secondary/10 text-secondary uppercase">
                  {health[provider.name] ?? provider.status}
                </span>
              </div>
              <div className="text-xs text-on-surface-variant bg-surface-container-high/50 p-3 rounded-lg border border-outline-variant/10">
                <span className="font-semibold text-on-surface block mb-1">Mô hình khả dụng:</span>
                {provider.models.join(", ") || "Chưa có danh sách mô hình"}
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
