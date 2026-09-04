import { useQuery } from "@tanstack/react-query";
import { createApiClient } from "@windagent/api-sdk";
import { StatusPill, type StatusLevel } from "@windagent/ui";

const api = createApiClient({ baseUrl: "" });

function levelFor(status: string | undefined): StatusLevel {
  if (status === "ok") return "ok";
  if (status === undefined) return "idle";
  return "error";
}

export function FoundationShell() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    retry: false,
  });

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "var(--windagent-color-bg)",
        color: "var(--windagent-color-text)",
        fontFamily: "var(--windagent-font-sans)",
        display: "grid",
        placeItems: "center",
      }}
    >
      <section aria-label="Foundation status">
        <h1>WindAgent V2 foundation</h1>
        <StatusPill
          level={levelFor(health.data?.status)}
          label={
            health.isPending
              ? "Checking API health…"
              : health.isError
                ? "API unreachable"
                : `API healthy (v${health.data?.version ?? "?"})`
          }
        />
      </section>
    </main>
  );
}
