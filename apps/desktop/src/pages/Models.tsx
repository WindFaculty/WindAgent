import { useState, useEffect } from "react";
import {
  fetchRoutingRules as fetchRoutingRulesApi,
  patchRoutingRule,
  fetchRoutingStats,
} from "../lib/routerApi";

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  providerId: string;
  apiSource: string;
  modelId: string;
  baseUrl: string;
  type: "Local" | "API";
  billingMode: string;
  context: string;
  status: "Running" | "Ready" | "Loading" | "Idle" | "Offline";
  hasKey: boolean;
  roles: string;
  rt: string;
  sr: string;
  sparkPoints: string;
  description: string;
  deployment: string;
  quantization: string | null;
  vram: string;
  vramVal: string;
  vramMax: string;
  vramPct: number;
  ramVal: string;
  ramMax: string;
  ramPct: number;
  contextVal: string;
  contextMax: string;
  contextPct: number;
  tokensPerSec: string;
  uptime: string;
  assignedRoles: Array<{ name: string; type: string }>;
  tags: string[];
  capabilities: string[];
  latencyP50Ms: number | null;
  latencyP90Ms: number | null;
  successRate: number | null;
  quota: {
    mode: string;
    rpmLimit: number | null;
    rpdLimit: number | null;
    tpmLimit: number | null;
    dailyTokenLimit: number | null;
    monthlyTokenLimit: number | null;
    remainingRequestsToday: number | null;
    remainingTokensToday: number | null;
    remainingCredit: number | null;
    resetAt: string | null;
    source: string;
  } | null;
}

interface ModelsProps {
  setActiveTab: (tab: string) => void;
}

export function Models({ setActiveTab: _ }: ModelsProps) {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");
  const [hideNoKey, setHideNoKey] = useState<boolean>(true);
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [showProviderDrop, setShowProviderDrop] = useState<boolean>(false);

  // Inline-editing States
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [tempModelId, setTempModelId] = useState<string>("");
  const [editingApiKey, setEditingApiKey] = useState<string | null>(null);
  const [tempApiKey, setTempApiKey] = useState<string>("");

  const handleSaveModelId = async (id: string, newId: string) => {
    try {
      const res = await fetch(`/api/v1/models/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: newId }),
      });
      if (res.ok) {
        setEditingModelId(null);
        await fetchAllData();
      } else {
        const body = await res.json();
        alert("Failed to update Model ID: " + body.detail);
      }
    } catch (err) {
      alert("Error: " + err);
    }
  };

  const handleSaveApiKey = async (providerId: string, newKey: string) => {
    try {
      const res = await fetch(`/api/v1/models/providers/${providerId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: newKey }),
      });
      if (res.ok) {
        setEditingApiKey(null);
        await fetchAllData();
        alert("API Key updated successfully in database!");
      } else {
        const body = await res.json();
        alert("Failed to update API Key: " + body.detail);
      }
    } catch (err) {
      alert("Error: " + err);
    }
  };

  // Routing and Activity States
  const [activities, setActivities] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [routingStats, setRoutingStats] = useState<{ avgLatencyMs: number | null }>({ avgLatencyMs: null });

  // Custom connection & checklist states
  interface FetchedModel {
    model_id: string;
    display_name: string;
    capabilities?: string[];
  }
  const [fetchedModels, setFetchedModels] = useState<FetchedModel[]>([]);
  const [checkedModelIds, setCheckedModelIds] = useState<string[]>([]);
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [showEditApiKey, setShowEditApiKey] = useState<boolean>(false);
  const [connectionStatus, setConnectionStatus] = useState({ text: "", type: "success" });
  const [editConnectionStatus, setEditConnectionStatus] = useState({ text: "", type: "success" });
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [isFetchingModels, setIsFetchingModels] = useState<boolean>(false);

  // Modal States
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [isEditRulesOpen, setIsEditRulesOpen] = useState<boolean>(false);

  // Form Fields
  const [providerForm, setProviderForm] = useState({
    id: "",
    name: "",
    api_source: "openai",
    base_url: "https://api.openai.com/v1",
    api_key: "",
  });
  const [editProviderForm, setEditProviderForm] = useState({
    provider_id: "",
    name: "",
    api_source: "openai",
    base_url: "",
    api_key: "",
  });
  const [editedRules, setEditedRules] = useState<Record<string, {
    primary: string;
    fallback: string;
    finalFallback: string;
    description: string;
    status: string;
    tags: string[];
    name: string;
  }>>({});

  const fetchAllData = async () => {
    try {
      const [modelsRes, rulesData, activityRes, providersRes, statsData] = await Promise.all([
        fetch("/api/v1/models"),
        fetchRoutingRulesApi(),
        fetch("/api/v1/models/activity"),
        fetch("/api/v1/models/providers"),
        fetchRoutingStats().catch(() => null),
      ]);

      if (!modelsRes.ok) throw new Error("Failed to load models list");

      const modelsData = await modelsRes.json();
      setModels(modelsData);

      const initialFormRules: Record<string, any> = {};
      rulesData.forEach((rule) => {
        initialFormRules[rule.role] = {
          name: rule.name || `${rule.role} Route`,
          description: rule.description || "",
          primary: rule.primary_model_id || rule.primary || "",
          fallback: rule.fallback_model_id || rule.fallback || "",
          finalFallback: rule.final_fallback_model_id || rule.finalFallbackModel || "",
          status: rule.status || "Active",
          tags: rule.tags || [],
        };
      });
      setEditedRules(initialFormRules);

      if (activityRes.ok) setActivities(await activityRes.json());
      if (providersRes.ok) setProviders(await providersRes.json());
      if (statsData) {
        const statsRaw: any = statsData;
        const latencyMs = statsRaw.avg_latency_ms ?? (statsRaw.avgLatency?.value ? parseFloat(statsRaw.avgLatency.value) : null);
        setRoutingStats({ avgLatencyMs: latencyMs });
      }

      // Auto select first model if none selected
      if (modelsData.length > 0 && !selectedModelId) {
        setSelectedModelId(modelsData[0].id);
      }
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Cannot load model registry from backend sidecar.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();

    // Set polling interval for updates
    const timer = setInterval(() => {
      fetch("/api/v1/models")
        .then((res) => res.json())
        .then((data) => setModels(data))
        .catch(console.error);

      fetch("/api/v1/models/activity")
        .then((res) => res.json())
        .then((data) => setActivities(data))
        .catch(console.error);
    }, 15000);

    return () => clearInterval(timer);
  }, []);

  const handleStart = async (modelId: string) => {
    try {
      const res = await fetch(`/api/v1/models/${modelId}/start`, { method: "POST" });
      if (res.ok) await fetchAllData();
    } catch (err) {
      alert("Failed to start model: " + err);
    }
  };

  const handleStop = async (modelId: string) => {
    try {
      const res = await fetch(`/api/v1/models/${modelId}/stop`, { method: "POST" });
      if (res.ok) await fetchAllData();
    } catch (err) {
      alert("Failed to stop model: " + err);
    }
  };

  const handleRestart = async (modelId: string) => {
    try {
      const res = await fetch(`/api/v1/models/${modelId}/restart`, { method: "POST" });
      if (res.ok) await fetchAllData();
    } catch (err) {
      alert("Failed to restart model: " + err);
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedModelIds.length === 0) return;
    if (!window.confirm(`Xóa ${selectedModelIds.length} model đã chọn?`)) return;
    for (const id of selectedModelIds) {
      await fetch(`/api/v1/models/${encodeURIComponent(id)}`, { method: 'DELETE' });
    }
    setSelectedModelIds([]);
    await fetchAllData();
  };

  const handleDeleteAll = async () => {
    if (!window.confirm(`Xóa toàn bộ ${filteredModels.length} model hiện tại? Hành động không thể hoàn tác!`)) return;
    for (const m of filteredModels) {
      await fetch(`/api/v1/models/${encodeURIComponent(m.id)}`, { method: 'DELETE' });
    }
    setSelectedModelIds([]);
    await fetchAllData();
  };

  const handleDeleteByProvider = async (providerId: string) => {
    const toDelete = filteredModels.filter(m => m.providerId === providerId);
    if (toDelete.length === 0) return;
    if (!window.confirm(`Xóa ${toDelete.length} model của provider "${providerId}"?`)) return;
    for (const m of toDelete) {
      await fetch(`/api/v1/models/${encodeURIComponent(m.id)}`, { method: 'DELETE' });
    }
    setSelectedModelIds([]);
    setShowProviderDrop(false);
    await fetchAllData();
  };

  const toggleRowSelect = (id: string) => {
    setSelectedModelIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const toggleSelectAll = () => {
    if (selectedModelIds.length === filteredModels.length) {
      setSelectedModelIds([]);
    } else {
      setSelectedModelIds(filteredModels.map(m => m.id));
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    if (!window.confirm(`Xóa model "${modelId}" khỏi registry? Hành động này không thể hoàn tác.`)) return;
    try {
      const res = await fetch(`/api/v1/models/${encodeURIComponent(modelId)}`, { method: "DELETE" });
      if (res.ok) {
        await fetchAllData();
        setSelectedModelId("");
      } else {
        const body = await res.json();
        alert("Xóa thất bại: " + (body.detail || body.message));
      }
    } catch (err) {
      alert("Lỗi: " + err);
    }
  };

  const handleClearApiKey = async (providerId: string) => {
    if (!window.confirm(`Xóa API Key của provider "${providerId}"? Sau đó các model thuộc provider này sẽ không hoạt động.`)) return;
    try {
      const res = await fetch(`/api/v1/models/providers/${encodeURIComponent(providerId)}/api-key`, { method: "DELETE" });
      if (res.ok) {
        await fetchAllData();
      } else {
        const body = await res.json();
        alert("Xóa API Key thất bại: " + (body.detail || body.message));
      }
    } catch (err) {
      alert("Lỗi: " + err);
    }
  };

  const handleSetDefault = async (modelId: string) => {
    try {
      const res = await fetch(`/api/v1/models/${modelId}/set-default`, { method: "POST" });
      if (res.ok) {
        alert("Set default model fallback successfully!");
        await fetchAllData();
      }
    } catch (err) {
      alert("Failed to set default: " + err);
    }
  };

  const handleToggleModel = (modelId: string) => {
    if (checkedModelIds.includes(modelId)) {
      setCheckedModelIds(checkedModelIds.filter(id => id !== modelId));
    } else {
      setCheckedModelIds([...checkedModelIds, modelId]);
    }
  };

  const handleSelectAllModels = () => {
    if (checkedModelIds.length === fetchedModels.length) {
      setCheckedModelIds([]);
    } else {
      setCheckedModelIds(fetchedModels.map(m => m.model_id));
    }
  };

  const handleSelectFreeModels = () => {
    const freeIds = fetchedModels
      .filter(m => {
        const id = m.model_id.toLowerCase();
        const name = (m.display_name || "").toLowerCase();
        return id.includes(':free') || id.includes('-free') || id.includes('/free') ||
               name.includes('free') || id.endsWith('free');
      })
      .map(m => m.model_id);
    setCheckedModelIds(freeIds);
  };

  const handleFetchModels = async (isEdit: boolean = false) => {
    const targetForm = isEdit ? editProviderForm : providerForm;
    if (isEdit) {
      setIsFetchingModels(true);
      setEditConnectionStatus({ text: "", type: "success" });
    } else {
      setIsFetchingModels(true);
      setConnectionStatus({ text: "", type: "success" });
    }
    
    try {
      const res = await fetch("/api/v1/models/providers/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_source: targetForm.api_source,
          base_url: targetForm.base_url,
          api_key: targetForm.api_key || null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setFetchedModels(data.models || []);
        setCheckedModelIds((data.models || []).map((m: any) => m.model_id));
        const successMsg = data.message || `Endpoint OK - Đã lấy ${data.models?.length} models từ endpoint`;
        if (isEdit) {
          setEditConnectionStatus({ text: successMsg, type: "success" });
        } else {
          setConnectionStatus({ text: successMsg, type: "success" });
        }
      } else {
        const errorMsg = data.detail || "Không thể lấy danh sách models";
        if (isEdit) {
          setEditConnectionStatus({ text: errorMsg, type: "error" });
        } else {
          setConnectionStatus({ text: errorMsg, type: "error" });
        }
      }
    } catch (err) {
      if (isEdit) {
        setEditConnectionStatus({ text: String(err), type: "error" });
      } else {
        setConnectionStatus({ text: String(err), type: "error" });
      }
    } finally {
      setIsFetchingModels(false);
    }
  };

  const handleTestConnection = async (isEdit: boolean = false) => {
    const targetForm = isEdit ? editProviderForm : providerForm;
    if (isEdit) {
      setIsTesting(true);
      setEditConnectionStatus({ text: "", type: "success" });
    } else {
      setIsTesting(true);
      setConnectionStatus({ text: "", type: "success" });
    }
    
    try {
      const res = await fetch("/api/v1/models/providers/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_source: targetForm.api_source,
          base_url: targetForm.base_url,
          api_key: targetForm.api_key || null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        const successMsg = "Kết nối thành công! Endpoint hoạt động bình thường.";
        if (isEdit) {
          setEditConnectionStatus({ text: successMsg, type: "success" });
        } else {
          setConnectionStatus({ text: successMsg, type: "success" });
        }
        if (fetchedModels.length === 0 && data.models) {
          setFetchedModels(data.models);
          setCheckedModelIds(data.models.map((m: any) => m.model_id));
        }
      } else {
        const errorMsg = data.detail || "Kết nối thất bại.";
        if (isEdit) {
          setEditConnectionStatus({ text: errorMsg, type: "error" });
        } else {
          setConnectionStatus({ text: errorMsg, type: "error" });
        }
      }
    } catch (err) {
      if (isEdit) {
        setEditConnectionStatus({ text: String(err), type: "error" });
      } else {
        setConnectionStatus({ text: String(err), type: "error" });
      }
    } finally {
      setIsTesting(false);
    }
  };

  const handleAddProvider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!providerForm.name) {
      alert("Vui lòng nhập Key Name");
      return;
    }

    const providerId = providerForm.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');

    try {
      // 1. Create provider
      const provRes = await fetch("/api/v1/models/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: providerId,
          name: providerForm.name,
          api_source: providerForm.api_source,
          base_url: providerForm.base_url,
          api_key: providerForm.api_key || null,
        }),
      });

      if (!provRes.ok) {
        const body = await provRes.json();
        alert("Lỗi khi thêm provider: " + (body.detail || "Unknown error"));
        return;
      }

      // 2. Register checked models
      const selectedModels = fetchedModels.filter(m => checkedModelIds.includes(m.model_id));
      if (selectedModels.length > 0) {
        const promises = selectedModels.map(m => {
          return fetch("/api/v1/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: m.model_id,
              provider_id: providerId,
              model_id: m.model_id,
              type: "API",
              capabilities: m.capabilities || ["chat"],
              tags: ["Cloud"],
              roles: ["General Chat"],
            }),
          });
        });
        await Promise.all(promises);
      }

      setIsAddModalOpen(false);
      // Reset form
      setProviderForm({
        id: "",
        name: "",
        api_source: "openai",
        base_url: "https://api.openai.com/v1",
        api_key: "",
      });
      setFetchedModels([]);
      setCheckedModelIds([]);
      setConnectionStatus({ text: "", type: "success" });
      await fetchAllData();
      alert("Thêm Provider và đăng ký Models thành công!");
    } catch (err) {
      alert("Lỗi khi thêm provider/models: " + err);
    }
  };

  const handleEditProvider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editProviderForm.provider_id) {
      alert("Vui lòng chọn provider để chỉnh sửa.");
      return;
    }

    try {
      const res = await fetch(`/api/v1/models/providers/${editProviderForm.provider_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editProviderForm.name,
          api_source: editProviderForm.api_source,
          base_url: editProviderForm.base_url,
          api_key: editProviderForm.api_key || null,
        }),
      });

      if (!res.ok) {
        const body = await res.json();
        alert("Lỗi khi cập nhật provider: " + (body.detail || "Unknown error"));
        return;
      }

      // Register checked models if any
      const selectedModels = fetchedModels.filter(m => checkedModelIds.includes(m.model_id));
      if (selectedModels.length > 0) {
        const promises = selectedModels.map(m => {
          return fetch("/api/v1/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: m.model_id,
              provider_id: editProviderForm.provider_id,
              model_id: m.model_id,
              type: "API",
              capabilities: m.capabilities || ["chat"],
              tags: ["Cloud"],
              roles: ["General Chat"],
            }),
          });
        });
        await Promise.all(promises);
      }

      setIsImportModalOpen(false);
      setFetchedModels([]);
      setCheckedModelIds([]);
      setEditConnectionStatus({ text: "", type: "success" });
      await fetchAllData();
      alert("Cập nhật Provider và API key thành công!");
    } catch (err) {
      alert("Lỗi khi cập nhật: " + err);
    }
  };

  const handleSelectEditProvider = (providerId: string) => {
    const p = providers.find((x) => x.id === providerId);
    setFetchedModels([]);
    setCheckedModelIds([]);
    setEditConnectionStatus({ text: "", type: "success" });
    if (p) {
      setEditProviderForm({
        provider_id: providerId,
        name: p.name || "",
        api_source: p.apiSource || "openai",
        base_url: p.baseUrl || "",
        api_key: "",
      });
    } else {
      setEditProviderForm({
        provider_id: "",
        name: "",
        api_source: "openai",
        base_url: "",
        api_key: "",
      });
    }
  };

  const handleSaveRoutingRules = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const promises = Object.keys(editedRules).map((role) => {
        const r = editedRules[role];
        return patchRoutingRule(role, {
          name: r.name,
          description: r.description,
          primary_model_id: r.primary || null,
          fallback_model_id: r.fallback || null,
          final_fallback_model_id: r.finalFallback || null,
          status: r.status,
          tags: r.tags,
        });
      });

      await Promise.all(promises);
      setIsEditRulesOpen(false);
      await fetchAllData();
      alert("Routing rules updated successfully.");
    } catch (err) {
      alert("Failed to update rules: " + err);
    }
  };

  const _handleSyncProvider = async (providerId: string) => {
    try {
      const res = await fetch(`/api/v1/models/providers/${providerId}/sync`, { method: "POST" });
      if (res.ok) {
        alert(`Synchronized provider ${providerId} successfully!`);
        await fetchAllData();
      } else {
        const body = await res.json();
        alert("Sync failed: " + body.detail);
      }
    } catch (err) {
      alert("Failed to sync provider: " + err);
    }
  };

  const handleRunAllBenchmarks = async () => {
    try {
      const modelIds = models.filter((m) => m.hasKey && m.status !== "Offline").map((m) => m.id);
      if (modelIds.length === 0) {
        alert("No online models configured with API Keys to benchmark.");
        return;
      }
      alert(`Running quick latency benchmark on ${modelIds.length} models in the background.`);
      const res = await fetch("/api/v1/models/benchmarks/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_ids: modelIds,
          test_name: "smoke",
          prompt: "Say OK in one sentence.",
          max_tokens: 16,
        }),
      });
      if (res.ok) {
        await fetchAllData();
      }
    } catch (err) {
      alert("Failed to run benchmarks: " + err);
    }
  };

  // Metrics calculations
  const totalModels = models.length;
  const activeModels = models.filter((m) => m.status === "Running" || m.status === "Ready").length;
  const localModels = models.filter((m) => m.type === "Local").length;
  const apiModels = models.filter((m) => m.type === "API").length;
  const avgLatency = routingStats.avgLatencyMs !== null 
    ? routingStats.avgLatencyMs 
    : models.filter((m) => m.latencyP50Ms).reduce((acc, curr) => acc + (curr.latencyP50Ms || 0), 0) / (models.filter((m) => m.latencyP50Ms).length || 1);
  const ollamaRunningModel = models.find((m) => m.providerId === "ollama" && (m.status === "Running" || m.status === "Ready"));
  const memoryFootprint = ollamaRunningModel ? `Active (${ollamaRunningModel.name})` : "Idle";

  // Filters logic
  const filteredModels = models.filter((model) => {
    // Hide API models without a key when toggle is on
    if (hideNoKey && model.type === "API" && !model.hasKey) return false;

    if (activeFilterTab === "running" && (model.status !== "Running" && model.status !== "Ready")) return false;
    if (activeFilterTab === "local" && model.type !== "Local") return false;
    if (activeFilterTab === "api" && model.type !== "API") return false;
    if (activeFilterTab === "quantized" && !model.name.includes("Q4") && !model.name.includes("Q5") && !model.name.includes("Q8") && !model.quantization) return false;
    if (activeFilterTab === "offline" && model.status !== "Offline") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        model.name.toLowerCase().includes(q) ||
        model.provider.toLowerCase().includes(q) ||
        model.roles.toLowerCase().includes(q) ||
        model.capabilities.some((c) => c.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const selectedModel = models.find((m) => m.id === selectedModelId) || models[0];

  if (loading) {
    return (
      <main className="models-view" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ color: 'var(--text-dim)', fontSize: '1.2rem' }}>Loading Model Registry Sidecar...</div>
      </main>
    );
  }

  return (
    <main className="models-view">
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Models</h1>
          <p className="dashboard-subtitle-text">Manage local and cloud models, routing, health, and performance.</p>
        </div>
        {error && (
          <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5', padding: '8px 16px', borderRadius: '6px', border: '1px solid rgba(239, 68, 68, 0.2)', fontSize: '0.86rem' }}>
            ⚠ {error}
          </div>
        )}
        <div className="models-header-right" style={{ position: 'relative' }}>
          <button 
            className="chat-send-btn" 
            style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px', border: isAddModalOpen ? '1px solid var(--color-primary)' : '' }} 
            onClick={() => { setIsAddModalOpen(!isAddModalOpen); setIsImportModalOpen(false); }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
            </svg>
            Thêm API Key
          </button>
          <button 
            className="role-btn" 
            style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px', border: isImportModalOpen ? '1px solid var(--color-primary)' : '' }} 
            onClick={() => { setIsImportModalOpen(!isImportModalOpen); setIsAddModalOpen(false); }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit API key
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={() => { setIsEditRulesOpen(true); setIsAddModalOpen(false); setIsImportModalOpen(false); }}>
            Edit Routing
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={handleRunAllBenchmarks}>
            ⚡ Run Benchmark
          </button>

          {/* Floating Dropdown/Popover for Thêm API Key */}
          {isAddModalOpen && (
            <div style={{
              position: 'absolute',
              top: '44px',
              right: '290px',
              width: '340px',
              background: '#0c101f',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '16px',
              zIndex: 1000,
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.6), 0 0 15px rgba(59, 130, 246, 0.25)',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              textAlign: 'left'
            }}>
              {/* Triangle Pointer */}
              <div style={{
                position: 'absolute',
                top: '-7px',
                right: '48px',
                width: '12px',
                height: '12px',
                background: '#0c101f',
                borderTop: '1px solid var(--border-color)',
                borderLeft: '1px solid var(--border-color)',
                transform: 'rotate(45deg)',
              }} />

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '8px' }}>
                <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '0.96rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
                  </svg>
                  Thêm API Key
                </h3>
                <button 
                  onClick={() => setIsAddModalOpen(false)} 
                  style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: '1rem', padding: '2px' }}
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleAddProvider} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>Provider</label>
                  <select 
                    value={providerForm.api_source} 
                    onChange={(e) => {
                      const source = e.target.value;
                      let defaultUrl = "https://api.openai.com/v1";
                      if (source === "anthropic") defaultUrl = "https://api.anthropic.com";
                      if (source === "google") defaultUrl = "https://generativelanguage.googleapis.com";
                      if (source === "ollama") defaultUrl = "http://localhost:11434";
                      setProviderForm({
                        ...providerForm,
                        api_source: source,
                        base_url: defaultUrl,
                      });
                    }}
                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem', width: '100%' }}
                  >
                    <option value="openai" style={{ background: 'var(--bg-darker)' }}>OpenAI</option>
                    <option value="anthropic" style={{ background: 'var(--bg-darker)' }}>Anthropic</option>
                    <option value="google" style={{ background: 'var(--bg-darker)' }}>Google Gemini</option>
                    <option value="ollama" style={{ background: 'var(--bg-darker)' }}>Ollama</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>Key Name</label>
                  <input 
                    type="text" 
                    placeholder="vd: OpenAI Primary" 
                    value={providerForm.name} 
                    onChange={(e) => setProviderForm({ ...providerForm, name: e.target.value })} 
                    required 
                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem' }} 
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>API Key</label>
                  <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                    <input 
                      type={showApiKey ? "text" : "password"} 
                      placeholder="••••••••••••••••••••••••••••"
                      value={providerForm.api_key} 
                      onChange={(e) => setProviderForm({ ...providerForm, api_key: e.target.value })} 
                      required 
                      style={{ flex: 1, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px 36px 6px 6px', color: 'var(--text-main)', fontSize: '0.82rem' }} 
                    />
                    <button 
                      type="button" 
                      onClick={() => setShowApiKey(!showApiKey)} 
                      style={{ position: 'absolute', right: '8px', background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                    >
                      {showApiKey ? (
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.815 7.815 3 3m-3-3-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
                        </svg>
                      ) : (
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>Base URL (Optional)</label>
                  <input 
                    type="text" 
                    placeholder="https://api.openai.com/v1" 
                    value={providerForm.base_url} 
                    onChange={(e) => setProviderForm({ ...providerForm, base_url: e.target.value })} 
                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem' }} 
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-main)', fontWeight: '600' }}>Models từ endpoint</span>
                    <span style={{ fontSize: '0.64rem', color: '#10b981', background: 'rgba(16, 185, 129, 0.1)', padding: '1px 4px', borderRadius: '3px' }}>Có thể chọn nhiều model</span>
                  </div>
                  {fetchedModels.length > 0 && (
                    <div style={{ display: 'flex', gap: '8px', marginTop: '2px', marginBottom: '2px', flexWrap: 'wrap' }}>
                      <button 
                        type="button" 
                        onClick={handleSelectAllModels} 
                        style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.3)', borderRadius: '4px', color: '#60a5fa', cursor: 'pointer', fontSize: '0.68rem', padding: '2px 8px', fontWeight: '600' }}
                      >
                        {checkedModelIds.length === fetchedModels.length ? "✕ Bỏ hết" : "✓ Chọn tất cả"}
                      </button>
                      <button 
                        type="button" 
                        onClick={handleSelectFreeModels} 
                        style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: '4px', color: '#34d399', cursor: 'pointer', fontSize: '0.68rem', padding: '2px 8px', fontWeight: '600' }}
                      >
                        🆓 Chọn Free
                      </button>
                    </div>
                  )}
                  <div style={{ 
                    maxHeight: '120px', 
                    overflowY: 'auto', 
                    border: '1px solid var(--border-color)', 
                    borderRadius: '4px', 
                    padding: '8px', 
                    display: 'flex', 
                    flexDirection: 'column', 
                    gap: '6px', 
                    background: 'rgba(0,0,0,0.3)',
                    marginTop: '4px'
                  }}>
                    {fetchedModels.length === 0 ? (
                      <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', textAlign: 'center', padding: '8px 0' }}>Chưa tải models. Bấm "Lấy models" bên dưới.</div>
                    ) : (
                      fetchedModels.map(m => (
                        <label key={m.model_id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.76rem', cursor: 'pointer', color: 'var(--text-main)', userSelect: 'none' }}>
                          <input 
                            type="checkbox" 
                            checked={checkedModelIds.includes(m.model_id)} 
                            onChange={() => handleToggleModel(m.model_id)} 
                            style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }} 
                          />
                          {m.model_id}
                        </label>
                      ))
                    )}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                  <button 
                    type="button" 
                    onClick={() => handleFetchModels(false)} 
                    disabled={isFetchingModels}
                    className="role-btn" 
                    style={{ flex: 1, padding: '4px 8px', fontSize: '0.76rem', height: '28px', justifyContent: 'center' }}
                  >
                    {isFetchingModels ? "Đang tải..." : "Lấy models"}
                  </button>
                  <button 
                    type="button" 
                    onClick={() => handleTestConnection(false)} 
                    disabled={isTesting}
                    className="role-btn" 
                    style={{ flex: 1, padding: '4px 8px', fontSize: '0.76rem', height: '28px', justifyContent: 'center' }}
                  >
                    {isTesting ? "Đang test..." : "Test kết nối"}
                  </button>
                </div>

                {connectionStatus.text && (
                  <div style={{ 
                    fontSize: '0.72rem', 
                    color: connectionStatus.type === 'success' ? '#10b981' : '#f87171', 
                    display: 'flex', 
                    alignItems: 'flex-start', 
                    gap: '4px',
                    lineHeight: '1.2'
                  }}>
                    <span>{connectionStatus.type === 'success' ? '✔' : '⚠'}</span>
                    <span>{connectionStatus.text}</span>
                  </div>
                )}

                <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '8px' }}>
                  <button 
                    type="button" 
                    className="role-btn" 
                    onClick={() => setIsAddModalOpen(false)} 
                    style={{ padding: '4px 12px', fontSize: '0.78rem', height: '28px' }}
                  >
                    Hủy
                  </button>
                  <button 
                    type="submit" 
                    className="chat-send-btn" 
                    disabled={!providerForm.name} 
                    style={{ padding: '4px 12px', fontSize: '0.78rem', height: '28px', opacity: providerForm.name ? 1 : 0.5 }}
                  >
                    Lưu
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Floating Dropdown/Popover for Edit API key */}
          {isImportModalOpen && (
            <div style={{
              position: 'absolute',
              top: '44px',
              right: '180px',
              width: '340px',
              background: '#0c101f',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '16px',
              zIndex: 1000,
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.6), 0 0 15px rgba(59, 130, 246, 0.25)',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              textAlign: 'left'
            }}>
              {/* Triangle Pointer */}
              <div style={{
                position: 'absolute',
                top: '-7px',
                right: '48px',
                width: '12px',
                height: '12px',
                background: '#0c101f',
                borderTop: '1px solid var(--border-color)',
                borderLeft: '1px solid var(--border-color)',
                transform: 'rotate(45deg)',
              }} />

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '8px' }}>
                <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '0.96rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                  Edit API key
                </h3>
                <button 
                  onClick={() => setIsImportModalOpen(false)} 
                  style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: '1rem', padding: '2px' }}
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleEditProvider} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>Chọn API Provider</label>
                  <select 
                    value={editProviderForm.provider_id} 
                    onChange={(e) => handleSelectEditProvider(e.target.value)}
                    required
                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem', width: '100%' }}
                  >
                    <option value="" style={{ background: 'var(--bg-darker)' }}>-- Chọn provider cần sửa --</option>
                    {providers.filter(p => p.id !== 'ollama').map((p) => (
                      <option key={p.id} value={p.id} style={{ background: 'var(--bg-darker)' }}>{p.name} ({p.id})</option>
                    ))}
                  </select>
                </div>

                {editProviderForm.provider_id && (
                  <>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>Provider Name</label>
                      <input 
                        type="text" 
                        value={editProviderForm.name} 
                        onChange={(e) => setEditProviderForm({ ...editProviderForm, name: e.target.value })} 
                        required 
                        style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem' }} 
                      />
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>API Format</label>
                      <select 
                        value={editProviderForm.api_source} 
                        onChange={(e) => setEditProviderForm({ ...editProviderForm, api_source: e.target.value })}
                        style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem', width: '100%' }}
                      >
                        <option value="openai" style={{ background: 'var(--bg-darker)' }}>OpenAI</option>
                        <option value="anthropic" style={{ background: 'var(--bg-darker)' }}>Anthropic</option>
                        <option value="google" style={{ background: 'var(--bg-darker)' }}>Google Gemini</option>
                      </select>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>Endpoint Base URL</label>
                      <input 
                        type="text" 
                        value={editProviderForm.base_url} 
                        onChange={(e) => setEditProviderForm({ ...editProviderForm, base_url: e.target.value })} 
                        required 
                        style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.82rem' }} 
                      />
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontWeight: '600' }}>API Key mới (để trống nếu giữ nguyên)</label>
                      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                        <input 
                          type={showEditApiKey ? "text" : "password"} 
                          placeholder="Nhập API key mới..."
                          value={editProviderForm.api_key} 
                          onChange={(e) => setEditProviderForm({ ...editProviderForm, api_key: e.target.value })} 
                          style={{ flex: 1, background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px 36px 6px 6px', color: 'var(--text-main)', fontSize: '0.82rem' }} 
                        />
                        <button 
                          type="button" 
                          onClick={() => setShowEditApiKey(!showEditApiKey)} 
                          style={{ position: 'absolute', right: '8px', background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                        >
                          {showEditApiKey ? (
                            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.815 7.815 3 3m-3-3-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
                            </svg>
                          ) : (
                            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.74rem', color: 'var(--text-main)', fontWeight: '600' }}>Đăng ký thêm Models từ endpoint</span>
                      </div>
                      {fetchedModels.length > 0 && (
                        <div style={{ display: 'flex', gap: '8px', marginTop: '2px', marginBottom: '2px', flexWrap: 'wrap' }}>
                          <button 
                            type="button" 
                            onClick={handleSelectAllModels} 
                            style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.3)', borderRadius: '4px', color: '#60a5fa', cursor: 'pointer', fontSize: '0.68rem', padding: '2px 8px', fontWeight: '600' }}
                          >
                            {checkedModelIds.length === fetchedModels.length ? "✕ Bỏ hết" : "✓ Chọn tất cả"}
                          </button>
                          <button 
                            type="button" 
                            onClick={handleSelectFreeModels} 
                            style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: '4px', color: '#34d399', cursor: 'pointer', fontSize: '0.68rem', padding: '2px 8px', fontWeight: '600' }}
                          >
                            🆓 Chọn Free
                          </button>
                        </div>
                      )}
                      <div style={{ 
                        maxHeight: '100px', 
                        overflowY: 'auto', 
                        border: '1px solid var(--border-color)', 
                        borderRadius: '4px', 
                        padding: '8px', 
                        display: 'flex', 
                        flexDirection: 'column', 
                        gap: '6px', 
                        background: 'rgba(0,0,0,0.3)',
                        marginTop: '4px'
                      }}>
                        {fetchedModels.length === 0 ? (
                          <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', textAlign: 'center', padding: '4px 0' }}>Chưa tải models. Bấm "Lấy models" bên dưới.</div>
                        ) : (
                          fetchedModels.map(m => (
                            <label key={m.model_id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.76rem', cursor: 'pointer', color: 'var(--text-main)', userSelect: 'none' }}>
                              <input 
                                type="checkbox" 
                                checked={checkedModelIds.includes(m.model_id)} 
                                onChange={() => handleToggleModel(m.model_id)} 
                                style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }} 
                              />
                              {m.model_id}
                            </label>
                          ))
                        )}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                      <button 
                        type="button" 
                        onClick={() => handleFetchModels(true)} 
                        disabled={isFetchingModels}
                        className="role-btn" 
                        style={{ flex: 1, padding: '4px 8px', fontSize: '0.76rem', height: '28px', justifyContent: 'center' }}
                      >
                        {isFetchingModels ? "Đang tải..." : "Lấy models"}
                      </button>
                      <button 
                        type="button" 
                        onClick={() => handleTestConnection(true)} 
                        disabled={isTesting}
                        className="role-btn" 
                        style={{ flex: 1, padding: '4px 8px', fontSize: '0.76rem', height: '28px', justifyContent: 'center' }}
                      >
                        {isTesting ? "Đang test..." : "Test kết nối"}
                      </button>
                    </div>

                    {editConnectionStatus.text && (
                      <div style={{ 
                        fontSize: '0.72rem', 
                        color: editConnectionStatus.type === 'success' ? '#10b981' : '#f87171', 
                        display: 'flex', 
                        alignItems: 'flex-start', 
                        gap: '4px',
                        lineHeight: '1.2'
                      }}>
                        <span>{editConnectionStatus.type === 'success' ? '✔' : '⚠'}</span>
                        <span>{editConnectionStatus.text}</span>
                      </div>
                    )}
                  </>
                )}

                <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '8px' }}>
                  <button 
                    type="button" 
                    className="role-btn" 
                    onClick={() => setIsImportModalOpen(false)} 
                    style={{ padding: '4px 12px', fontSize: '0.78rem', height: '28px' }}
                  >
                    Hủy
                  </button>
                  <button 
                    type="submit" 
                    className="chat-send-btn" 
                    disabled={!editProviderForm.provider_id} 
                    style={{ padding: '4px 12px', fontSize: '0.78rem', height: '28px', opacity: editProviderForm.provider_id ? 1 : 0.5 }}
                  >
                    Cập nhật
                  </button>
                </div>
              </form>
            </div>
          )}
      </div>
    </div>

      {/* Metric row grid */}
      <div className="metrics-row-grid">
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              <span>Total Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{totalModels}</div>
              <div className="m-card-subtext">All registered models</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Active Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{activeModels}</div>
              <div className="m-card-subtext">{totalModels ? ((activeModels / totalModels) * 100).toFixed(1) : 0}% of total</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <span>Local Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{localModels}</div>
              <div className="m-card-subtext">{totalModels ? ((localModels / totalModels) * 100).toFixed(1) : 0}% of total</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9" />
              </svg>
              <span>API Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{apiModels}</div>
              <div className="m-card-subtext">{totalModels ? ((apiModels / totalModels) * 100).toFixed(1) : 0}% of total</div>
            </div>
            <svg className="m-card-sparkline-svg orange" viewBox="0 0 68 24">
              <polyline points="0,18 15,10 30,12 45,8 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Avg Latency</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{avgLatency ? `${Math.round(avgLatency)}ms` : "—"}</div>
              <div className="m-card-subtext">p50 benchmark avg</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,22 15,14 30,18 45,8 60,12 68,6" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2M7 19h10" />
              </svg>
              <span>Local Resource</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{memoryFootprint}</div>
              <div className="m-card-subtext">Ollama load state</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Main layout splitted */}
      <div className="agents-main-layout">
        {/* Left Pane Model Library */}
        <div className="agents-directory-pane">
          <div className="dashboard-panel" style={{ flex: 1 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '12px 16px', flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
              {/* Title + Search + hide-no-key */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
                <span className="panel-title">Model Library</span>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <div className="search-box-container">
                    <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Tìm theo tên, provider, capabilities..."
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                    />
                  </div>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.74rem', color: 'var(--text-dim)', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}>
                    <input
                      type="checkbox"
                      checked={hideNoKey}
                      onChange={(e) => setHideNoKey(e.target.checked)}
                      style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }}
                    />
                    Ẩn model chưa có API key
                  </label>
                </div>
              </div>

              {/* Status filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '3px' }}>
                <button className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`} onClick={() => setActiveFilterTab("all")}>Tất cả</button>
                <button className={`tab-btn ${activeFilterTab === "running" ? "active" : ""}`} onClick={() => setActiveFilterTab("running")}>Running</button>
                <button className={`tab-btn ${activeFilterTab === "local" ? "active" : ""}`} onClick={() => setActiveFilterTab("local")}>Local</button>
                <button className={`tab-btn ${activeFilterTab === "api" ? "active" : ""}`} onClick={() => setActiveFilterTab("api")}>API</button>
                <button className={`tab-btn ${activeFilterTab === "quantized" ? "active" : ""}`} onClick={() => setActiveFilterTab("quantized")}>Quantized</button>
                <button className={`tab-btn ${activeFilterTab === "offline" ? "active" : ""}`} onClick={() => setActiveFilterTab("offline")}>Offline</button>
              </div>

              {/* Bulk action toolbar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'var(--text-dim)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={selectedModelIds.length === filteredModels.length && filteredModels.length > 0}
                    onChange={toggleSelectAll}
                    style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }}
                  />
                  Đã chọn {selectedModelIds.length} model
                </label>
                <button
                  className="role-btn"
                  style={{ height: '30px', padding: '0 12px', fontSize: '0.76rem', display: 'flex', alignItems: 'center', gap: '5px', borderColor: 'rgba(239,68,68,0.4)', color: '#fca5a5' }}
                  onClick={handleDeleteSelected}
                  disabled={selectedModelIds.length === 0}
                >
                  <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  Xóa đã chọn
                </button>
                {/* Delete by provider dropdown */}
                <div style={{ position: 'relative' }}>
                  <button
                    className="role-btn"
                    style={{ height: '30px', padding: '0 12px', fontSize: '0.76rem', display: 'flex', alignItems: 'center', gap: '5px' }}
                    onClick={() => setShowProviderDrop(p => !p)}
                  >
                    <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
                    Xóa theo API / Provider
                    <svg width="10" height="10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7"/></svg>
                  </button>
                  {showProviderDrop && (
                    <div style={{ position: 'absolute', top: '34px', left: 0, background: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '4px', zIndex: 999, minWidth: '180px', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
                      {Array.from(new Set(filteredModels.map(m => m.providerId))).map(pid => (
                        <button
                          key={pid}
                          onClick={() => handleDeleteByProvider(pid)}
                          style={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', color: 'var(--text-main)', padding: '6px 10px', fontSize: '0.78rem', cursor: 'pointer', borderRadius: '4px' }}
                          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(239,68,68,0.1)')}
                          onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                        >
                          {pid}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {/* Delete all - far right */}
                <div style={{ flex: 1 }} />
                <button
                  className="role-btn"
                  style={{ height: '30px', padding: '0 14px', fontSize: '0.76rem', display: 'flex', alignItems: 'center', gap: '5px', borderColor: 'rgba(239,68,68,0.5)', color: '#fca5a5', background: 'rgba(239,68,68,0.08)' }}
                  onClick={handleDeleteAll}
                >
                  <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  Xóa tất cả model
                </button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0px' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th style={{ width: '36px', textAlign: 'center', padding: '8px 4px' }}>
                      <input
                        type="checkbox"
                        checked={selectedModelIds.length === filteredModels.length && filteredModels.length > 0}
                        onChange={toggleSelectAll}
                        style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }}
                      />
                    </th>
                    <th>MODEL ↕</th>
                    <th>PROVIDER ↕</th>
                    <th>TYPE ↕</th>
                    <th>CONTEXT ↕</th>
                    <th>STATUS ↕</th>
                    <th>API KEY ↕</th>
                    <th>CAPABILITIES ↕</th>
                    <th>LATENCY (P50) ↕</th>
                    <th style={{ textAlign: 'center' }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredModels.map((model) => (
                    <tr
                      key={model.id}
                      className={selectedModelId === model.id ? "selected-row" : ""}
                      style={{ cursor: 'pointer' }}
                    >
                      <td style={{ textAlign: 'center', padding: '8px 4px' }} onClick={(e) => { e.stopPropagation(); toggleRowSelect(model.id); }}>
                        <input
                          type="checkbox"
                          checked={selectedModelIds.includes(model.id)}
                          onChange={() => toggleRowSelect(model.id)}
                          style={{ accentColor: 'var(--color-primary)', cursor: 'pointer' }}
                        />
                      </td>
                      <td onClick={() => setSelectedModelId(model.id)}>
                        <div className="agent-name-cell">
                          <span className="agent-color-dot" style={{ backgroundColor: model.type === "Local" ? "#3b82f6" : "#10b981" }} />
                          <div style={{ fontWeight: '700' }}>
                            {model.name}
                            {model.quantization && (
                              <span className="model-quant-tag" style={{ marginLeft: '4px', fontSize: '0.64rem', padding: '1px 4px', backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: '3px' }}>
                                {model.quantization}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td style={{ fontWeight: '500' }} onClick={() => setSelectedModelId(model.id)}>{model.provider}</td>
                      <td onClick={() => setSelectedModelId(model.id)}>
                        <span style={{ color: model.type === "Local" ? "var(--color-primary)" : "var(--color-warning)", fontWeight: '600', fontSize: '0.74rem' }}>
                          {model.type}
                        </span>
                      </td>
                      <td onClick={() => setSelectedModelId(model.id)}>{model.context}</td>
                      <td onClick={() => setSelectedModelId(model.id)}>
                        <span className={`agent-status-badge ${model.status.toLowerCase()}`}>
                          {model.status}
                        </span>
                      </td>
                      <td onClick={() => setSelectedModelId(model.id)}>
                        {model.type === "API" ? (
                          model.hasKey ? (
                            <span style={{ color: 'var(--color-success)', fontSize: '0.72rem' }}>✔ Configured</span>
                          ) : (
                            <span style={{ color: '#eab308', fontSize: '0.72rem', fontWeight: 'bold' }}>⚠ Needs key</span>
                          )
                        ) : (
                          <span style={{ color: 'var(--text-dim)', fontSize: '0.72rem' }}>— Local</span>
                        )}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.76rem' }} onClick={() => setSelectedModelId(model.id)}>
                        {model.capabilities.join(", ")}
                      </td>
                      <td onClick={() => setSelectedModelId(model.id)}>{model.rt}</td>
                      <td style={{ textAlign: 'center', padding: '6px 8px' }}>
                        <button
                          title="Xóa model này"
                          onClick={(e) => { e.stopPropagation(); handleDeleteModel(model.id); }}
                          style={{
                            background: 'rgba(239,68,68,0.1)',
                            border: '1px solid rgba(239,68,68,0.35)',
                            borderRadius: '5px',
                            color: '#f87171',
                            cursor: 'pointer',
                            width: '28px',
                            height: '28px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                <span>Hiển thị {filteredModels.length} / {models.length} models</span>
                {selectedModelIds.length > 0 && <span style={{ color: 'var(--color-primary)' }}>Đã chọn: {selectedModelIds.length}</span>}
              </div>
            </div>
          </div>

        </div>

        {/* Right column Model details card */}
        {selectedModel && (
          <aside className="agent-details-pane">
            <div className="agent-details-card">
              <header className="agent-details-header">
                <div className="details-header-top">
                  <div className="details-title-box">
                    <div className="details-title-icon-box" style={{ backgroundColor: selectedModel.type === "Local" ? "rgba(59, 130, 246, 0.1)" : "rgba(16, 185, 129, 0.1)" }}>
                      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                      </svg>
                    </div>
                    <div>
                      <h2 className="details-title-name">{selectedModel.name}</h2>
                    </div>
                  </div>

                  <span className={`details-status-badge ${selectedModel.status.toLowerCase()}`}>
                    ● {selectedModel.status}
                  </span>
                </div>

                <div className="details-id-row" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'stretch', width: '100%' }}>
                  {/* Model ID row */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {editingModelId === selectedModel.id ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>Model ID:</span>
                          <input
                            type="text"
                            value={tempModelId}
                            onChange={(e) => setTempModelId(e.target.value)}
                            onKeyDown={async (e) => {
                              if (e.key === "Enter") {
                                await handleSaveModelId(selectedModel.id, tempModelId);
                              } else if (e.key === "Escape") {
                                setEditingModelId(null);
                              }
                            }}
                            onBlur={() => setEditingModelId(null)}
                            autoFocus
                            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--color-primary)', color: 'var(--text-main)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.78rem', width: '220px' }}
                          />
                        </div>
                      ) : (
                        <span
                          onClick={() => {
                            setEditingModelId(selectedModel.id);
                            setTempModelId(selectedModel.modelId);
                          }}
                          style={{ cursor: 'pointer', borderBottom: '1px dashed var(--text-dim)', fontSize: '0.78rem' }}
                          title="Click to edit Model ID"
                        >
                          Model ID: <strong style={{ color: 'var(--text-main)' }}>{selectedModel.modelId}</strong> ✎
                        </span>
                      )}
                    </div>
                    {!selectedModel.hasKey && selectedModel.type === "API" && (
                      <span style={{ color: '#f59e0b', fontWeight: 'bold', fontSize: '0.74rem' }}>Needs API Key</span>
                    )}
                  </div>

                  {/* API Key row (only for API models) */}
                  {selectedModel.type === "API" && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem' }}>
                        <span style={{ color: 'var(--text-dim)' }}>API Key:</span>
                        {editingApiKey === selectedModel.providerId ? (
                          <input
                            type="password"
                            value={tempApiKey}
                            onChange={(e) => setTempApiKey(e.target.value)}
                            onKeyDown={async (e) => {
                              if (e.key === "Enter") {
                                await handleSaveApiKey(selectedModel.providerId, tempApiKey);
                              } else if (e.key === "Escape") {
                                setEditingApiKey(null);
                              }
                            }}
                            onBlur={() => setEditingApiKey(null)}
                            placeholder="Type new API key & press Enter"
                            autoFocus
                            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--color-primary)', color: 'var(--text-main)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.78rem', width: '220px' }}
                          />
                        ) : (
                          <span
                            onClick={() => {
                              setEditingApiKey(selectedModel.providerId);
                              setTempApiKey("");
                            }}
                            style={{ cursor: 'pointer', borderBottom: '1px dashed var(--text-dim)', color: selectedModel.hasKey ? 'var(--color-success)' : '#f59e0b', fontWeight: '600' }}
                            title="Click to set/change API Key"
                          >
                            {selectedModel.hasKey ? "•••••••• (Click to edit)" : "Needs key (Click to edit)"} ✎
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </header>

              <div className="agent-details-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '0.8rem' }}>
                  <div>
                    <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Provider</span>
                    <span style={{ fontWeight: '600', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {selectedModel.provider}
                      {selectedModel.type === "API" && (
                        <button
                          onClick={() => _handleSyncProvider(selectedModel.providerId)}
                          style={{ background: 'none', border: 'none', color: 'var(--color-primary)', cursor: 'pointer', padding: '0 2px', fontSize: '0.7rem', textDecoration: 'underline' }}
                          title="Sync provider models catalog"
                        >
                          Sync
                        </button>
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Deployment</span>
                    <span style={{ fontWeight: '600' }}>{selectedModel.deployment}</span>
                  </div>
                  <div>
                    <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Billing Mode</span>
                    <span style={{ fontWeight: '600', fontFamily: 'var(--font-mono)' }}>{selectedModel.billingMode}</span>
                  </div>
                </div>

                <div className="details-section-box">
                  <p className="details-section-desc">{selectedModel.description}</p>
                </div>

                <div className="details-section-box">
                  <div className="details-tools-badges-grid">
                    {selectedModel.tags.map((tag, idx) => (
                      <span key={idx} className="details-tool-badge" style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', color: '#93c5fd', borderColor: 'rgba(59, 130, 246, 0.15)' }}>{tag}</span>
                    ))}
                  </div>
                </div>

                <div className="details-section-box">
                  <span className="details-section-title">Quota Details</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.78rem' }}>
                    {selectedModel.quota && (
                      <>
                        {selectedModel.quota.rpmLimit && <div>RPM Limit: <strong>{selectedModel.quota.rpmLimit}</strong></div>}
                        {selectedModel.quota.rpdLimit && <div>RPD Limit: <strong>{selectedModel.quota.rpdLimit}</strong></div>}
                        {selectedModel.quota.remainingRequestsToday !== null && (
                          <div>Requests Remaining Today: <strong>{selectedModel.quota.remainingRequestsToday}</strong></div>
                        )}
                        {selectedModel.quota.remainingTokensToday !== null && (
                          <div>Tokens Remaining Today: <strong>{selectedModel.quota.remainingTokensToday}</strong></div>
                        )}
                        {selectedModel.quota.resetAt && <div>Reset Time: <strong>{new Date(selectedModel.quota.resetAt).toLocaleTimeString()}</strong></div>}
                      </>
                    )}
                  </div>
                </div>

                <div className="details-section-box">
                  <span className="details-section-title">Performance Metrics</span>
                  <div className="details-health-stats-grid">
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Latency (p50)</span>
                      <span className="details-health-stat-val">{selectedModel.rt}</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Tokens / Sec</span>
                      <span className="details-health-stat-val">{selectedModel.tokensPerSec}</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Success Rate</span>
                      <span className="details-health-stat-val">{selectedModel.sr}</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Uptime</span>
                      <span className="details-health-stat-val">{selectedModel.uptime}</span>
                    </div>
                  </div>
                </div>
              </div>

              <footer className="agent-details-footer">
                <button
                  className="details-footer-btn start"
                  onClick={() => handleStart(selectedModel.id)}
                  disabled={!selectedModel.hasKey && selectedModel.type === "API"}
                  style={{ opacity: (!selectedModel.hasKey && selectedModel.type === "API") ? 0.5 : 1 }}
                >
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  </svg>
                  <span>Start</span>
                </button>
                <button
                  className="details-footer-btn"
                  style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }}
                  onClick={() => handleStop(selectedModel.id)}
                >
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-danger)' }}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H10a1 1 0 01-1-1v-4z" />
                  </svg>
                  <span style={{ color: '#fca5a5' }}>Stop</span>
                </button>
                <button
                  className="details-footer-btn restart"
                  onClick={() => handleRestart(selectedModel.id)}
                  disabled={!selectedModel.hasKey && selectedModel.type === "API"}
                  style={{ opacity: (!selectedModel.hasKey && selectedModel.type === "API") ? 0.5 : 1 }}
                >
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                  </svg>
                  <span>Restart</span>
                </button>
              </footer>
              <div style={{ display: 'flex', gap: '8px', margin: '0 16px 16px 16px' }}>
                <button
                  className="role-btn"
                  style={{ flex: 1, height: '32px', fontSize: '0.8rem', justifyContent: 'center' }}
                  onClick={() => handleSetDefault(selectedModel.id)}
                >
                  ★ Set as Default
                </button>
                {selectedModel.type === "API" && (
                  <button
                    className="role-btn"
                    style={{ flex: 1, height: '32px', fontSize: '0.8rem', justifyContent: 'center', borderColor: 'rgba(234,179,8,0.4)', color: '#fbbf24' }}
                    onClick={() => handleClearApiKey(selectedModel.providerId)}
                    title={`Xóa API Key của provider ${selectedModel.providerId}`}
                  >
                    🗝 Xóa API Key
                  </button>
                )}
                <button
                  className="role-btn"
                  style={{ flex: 1, height: '32px', fontSize: '0.8rem', justifyContent: 'center', borderColor: 'rgba(239,68,68,0.4)', color: '#fca5a5' }}
                  onClick={() => handleDeleteModel(selectedModel.id)}
                  title="Xóa model này khỏi registry"
                >
                  🗑 Xóa Model
                </button>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* Model Activity logs panel at the bottom */}
      <div className="dashboard-panel" style={{ marginTop: '16px' }}>
        <header className="panel-header">
          <span className="panel-title">Recent Model Registry Activity Logs</span>
        </header>
        <div className="panel-body" style={{ maxHeight: '180px', overflowY: 'auto' }}>
          <div className="timeline-logs-container">
            {activities.slice(0, 8).map((act, idx) => (
              <div key={idx} className="timeline-event-row" style={{ fontSize: '0.78rem' }}>
                <span className="t-event-time">{act.time}</span>
                <span className="t-event-node completed" style={{ backgroundColor: act.level === "error" ? "var(--color-danger)" : (act.level === "warning" ? "#eab308" : "var(--color-success)") }} />
                <div className="t-event-details">
                  <span className="t-event-actor" style={{ fontWeight: 'bold' }}>{act.modelId || act.providerId}</span>
                  <span className="t-event-desc" style={{ color: 'var(--text-main)', marginLeft: '6px' }}>{act.message}</span>
                </div>
              </div>
            ))}
            {activities.length === 0 && <div style={{ color: 'var(--text-dim)', textAlign: 'center', padding: '12px' }}>No activity records.</div>}
          </div>
        </div>
      </div>

      {/* Modals/Form dialog structures */}
      {isEditRulesOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(3px)' }}>
          <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '24px', width: '600px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '1.2rem' }}>Edit Routing Rules</h3>
            <form onSubmit={handleSaveRoutingRules} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ maxHeight: '450px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px', paddingRight: '6px' }}>
                {Object.keys(editedRules).map((role) => (
                  <div key={role} style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '4px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontWeight: 'bold', fontSize: '0.86rem', color: '#93c5fd' }}>{role}</span>
                      <select 
                        value={editedRules[role].status} 
                        onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], status: e.target.value } })}
                        style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '2px 6px', color: 'var(--text-main)', fontSize: '0.76rem' }}
                      >
                        <option value="Active">Active</option>
                        <option value="Weighted">Weighted</option>
                        <option value="Fallback">Fallback</option>
                        <option value="Disabled">Disabled</option>
                      </select>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Route Name</span>
                          <input 
                            type="text" 
                            value={editedRules[role].name} 
                            onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], name: e.target.value } })}
                            style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px 8px', color: 'var(--text-main)', fontSize: '0.8rem' }}
                          />
                        </div>
                        <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Description</span>
                          <input 
                            type="text" 
                            value={editedRules[role].description} 
                            onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], description: e.target.value } })}
                            style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px 8px', color: 'var(--text-main)', fontSize: '0.8rem' }}
                          />
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Primary Model</span>
                          <select value={editedRules[role].primary} onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], primary: e.target.value } })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px', color: 'var(--text-main)', fontSize: '0.8rem', width: '100%' }}>
                            <option value="" style={{ background: 'var(--bg-darker)' }}>None</option>
                            {models.map((m) => (
                              <option key={m.id} value={m.id} style={{ background: 'var(--bg-darker)' }}>{m.name}</option>
                            ))}
                          </select>
                        </div>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Fallback Model</span>
                          <select value={editedRules[role].fallback} onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], fallback: e.target.value } })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px', color: 'var(--text-main)', fontSize: '0.8rem', width: '100%' }}>
                            <option value="" style={{ background: 'var(--bg-darker)' }}>None</option>
                            {models.map((m) => (
                              <option key={m.id} value={m.id} style={{ background: 'var(--bg-darker)' }}>{m.name}</option>
                            ))}
                          </select>
                        </div>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Final Fallback Model</span>
                          <select value={editedRules[role].finalFallback} onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], finalFallback: e.target.value } })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px', color: 'var(--text-main)', fontSize: '0.8rem', width: '100%' }}>
                            <option value="" style={{ background: 'var(--bg-darker)' }}>None</option>
                            {models.map((m) => (
                              <option key={m.id} value={m.id} style={{ background: 'var(--bg-darker)' }}>{m.name}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Tags (comma separated)</span>
                        <input 
                          type="text" 
                          value={Array.isArray(editedRules[role].tags) ? editedRules[role].tags.join(", ") : editedRules[role].tags || ""} 
                          onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], tags: e.target.value.split(",").map((t: string) => t.trim()) } })}
                          style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px 8px', color: 'var(--text-main)', fontSize: '0.8rem' }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" className="role-btn" onClick={() => setIsEditRulesOpen(false)} style={{ padding: '6px 16px' }}>Cancel</button>
                <button type="submit" className="chat-send-btn" style={{ padding: '6px 16px' }}>Save Rules</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
