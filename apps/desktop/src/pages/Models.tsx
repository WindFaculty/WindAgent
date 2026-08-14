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
    <main className="p-6 bg-background text-on-surface min-h-screen space-y-6">
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-outline-variant/10">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-on-surface flex items-center gap-3">
            <span className="material-symbols-outlined text-primary text-3xl">cpu</span>
            Danh sách Mô hình AI (Models)
          </h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Danh sách mô hình đăng ký từ hệ thống Provider Registry chuẩn V2.
          </p>
        </div>
        <button
          type="button"
          className="px-4 py-2 bg-primary text-on-primary font-semibold rounded-lg hover:bg-primary-container transition-all flex items-center gap-2 text-sm w-fit"
          onClick={() => setActiveTab("endpoints")}
        >
          <span className="material-symbols-outlined text-sm">hub</span>
          Xem Endpoints & Providers
        </button>
      </header>

      <div className="relative max-w-md">
        <span className="material-symbols-outlined absolute left-3 top-2.5 text-on-surface-variant text-sm">
          search
        </span>
        <input
          aria-label="Search models"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Tìm kiếm mô hình hoặc nhà cung cấp..."
          className="w-full pl-9 pr-4 py-2 text-sm bg-surface-container-low border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary transition-all"
        />
      </div>

      {error ? (
        <div role="alert" className="p-4 rounded-lg bg-error-container/20 border border-error/30 text-error text-sm">
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {visibleModels.map((model) => (
            <article
              key={model.id}
              className="p-4 rounded-xl bg-surface-container-low border border-outline-variant/15 hover:border-primary/40 transition-all flex justify-between items-start"
            >
              <div>
                <div className="font-bold text-on-surface text-base">{model.name}</div>
                <div className="text-xs text-on-surface-variant mt-1 flex items-center gap-1">
                  <span className="material-symbols-outlined text-xs">dns</span>
                  {model.provider}
                </div>
              </div>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-secondary/10 text-secondary uppercase">
                {model.status}
              </span>
            </article>
          ))}
          {!error && visibleModels.length === 0 && (
            <div className="col-span-full p-8 text-center text-on-surface-variant bg-surface-container-low rounded-xl border border-outline-variant/10">
              Không tìm thấy mô hình AI nào.
            </div>
          )}
        </div>
      )}
    </main>
  );
}
