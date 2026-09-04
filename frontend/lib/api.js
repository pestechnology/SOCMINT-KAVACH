"use client";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("vertex_token");
}
export function setToken(t) {
  localStorage.setItem("vertex_token", t);
}
export function clearToken() {
  localStorage.removeItem("vertex_token");
}

async function req(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const err = new Error(detail.detail || `${res.status} ${res.statusText}`);
    err.status = res.status; // let callers reliably detect 401 (expired token)
    throw err;
  }
  return res.json();
}

export const api = {
  register: (username, password) =>
    req("/auth/register", { method: "POST", body: { username, password }, auth: false }),
  login: (username, password) =>
    req("/auth/login", { method: "POST", body: { username, password }, auth: false }),
  listCases: () => req("/cases"),
  createCase: (title, seeds, minor_involved = false, country_filter = "ALL", case_context = "", capture_evidence = false) =>
    req("/cases", { method: "POST", body: { title, seeds, minor_involved, country_filter, case_context, capture_evidence } }),
  getCase: (id) => req(`/cases/${id}`),
  getResults: (id) => req(`/cases/${id}/results`),
  // Per-user bookmarks + severity flags on discovered accounts.
  getAnnotations: (id) => req(`/cases/${id}/annotations`),
  setAnnotation: (id, entityId, patch) =>
    req(`/cases/${id}/annotations/${entityId}`, { method: "PUT", body: patch }),
  // Case collections (named folders/watchlists to sort/save cases into).
  getCollections: () => req("/collections"),
  createCollection: (name, color = "") =>
    req("/collections", { method: "POST", body: { name, color } }),
  deleteCollection: (cid) => req(`/collections/${cid}`, { method: "DELETE" }),
  setCaseCollections: (caseId, collection_ids) =>
    req(`/cases/${caseId}/collections`, { method: "PUT", body: { collection_ids } }),
  // Grounded case chat — answers strictly from this case's data.
  caseChat: (id, question, history = []) =>
    req(`/cases/${id}/chat`, { method: "POST", body: { question, history } }),
  reportUrl: (id) => `${BASE}/cases/${id}/report`,
  // fetch the PDF WITH the auth header (a plain <a> navigation can't send headers)
  downloadReport: async (id) => {
    const res = await fetch(`${BASE}/cases/${id}/report`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      const err = new Error(d.detail || `${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
    return res.blob();
  },
  downloadSummary: async (id) => {
    const res = await fetch(`${BASE}/cases/${id}/summary`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      const err = new Error(d.detail || `${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
    return res.blob();
  },
  // Dedicated Evidence Exhibit Report (embedded screenshots + hashes + RFC-3161 timestamps).
  downloadEvidenceReport: async (id) => {
    const res = await fetch(`${BASE}/cases/${id}/evidence_report`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      const err = new Error(d.detail || `${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
    return res.blob();
  },
  // Agentic Web Browser
  getAgenticTools: () => req("/api/agentic-browser/tools"),
  startAgenticInvestigate: (body) => req("/api/agentic-browser/investigate", { method: "POST", body }),
  getAgenticStatus: (taskId) => req(`/api/agentic-browser/status/${taskId}`),
  runAgenticLookup: (body) => req("/api/agentic-browser/run", { method: "POST", body }),
  getCaseAgenticTasks: (caseId) => req(`/api/agentic-browser/case/${caseId}`),
  downloadSummaryReport: async (id) => {
    const res = await fetch(`${BASE}/cases/${id}/summary_report`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      const err = new Error(d.detail || `${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
    return res.blob();
  },
  // Quick Lookup (multi-source OSINT dossier)
  smartLookup: (body) => req("/api/agentic-browser/smart-lookup", { method: "POST", body }),
  smartLookupSend: (body) => req("/api/agentic-browser/smart-lookup/send", { method: "POST", body }),
  // Re-iteration / identifier cross-pivoting (multi-select: any mix of already-
  // discovered accounts, suggested candidates, and manually-typed identifiers, run as
  // ONE combined pivot; repeatable — select a new batch after each run completes).
  suggestPivot: (id, seeds) => req(`/cases/${id}/pivot/suggest`, { method: "POST", body: { seeds } }),
  runPivot: (id, seeds) => req(`/cases/${id}/pivot`, { method: "POST", body: { seeds } }),
};

export { BASE };
