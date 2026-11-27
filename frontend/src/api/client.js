// Thin fetch wrapper + one function per backend endpoint. Every page talks to the API through here.

const BASE = "/api/v1";
const TOKEN_KEY = "reai_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

/** Error carrying the HTTP status and the API's `detail` message. */
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

/** Turn FastAPI error bodies (string or validation list) into one readable message. */
export function errorMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => `${(d.loc || []).slice(1).join(".") || "field"}: ${d.msg}`).join("; ");
  }
  return fallback;
}

async function request(path, { method = "GET", body, params, form, auth = true } = {}) {
  const url = new URL(BASE + path, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });

  const headers = {};
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    payload = new URLSearchParams(form);
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && auth && token) onUnauthorized();
    throw new ApiError(response.status, errorMessage(data, `Request failed (${response.status})`));
  }
  return data;
}

export const api = {
  // auth
  login: (email, password) => request("/auth/login", { method: "POST", form: { username: email, password }, auth: false }),
  me: () => request("/auth/me"),
  users: () => request("/users"),

  // leads
  leads: (params) => request("/leads", { params }),
  lead: (id) => request(`/leads/${id}`),
  createLead: (body) => request("/leads", { method: "POST", body }),
  updateLead: (id, body) => request(`/leads/${id}`, { method: "PATCH", body }),
  deleteLead: (id) => request(`/leads/${id}`, { method: "DELETE" }),
  interactions: (id) => request(`/leads/${id}/interactions`),
  addInteraction: (id, body) => request(`/leads/${id}/interactions`, { method: "POST", body }),
  requirements: (id) => request(`/leads/${id}/requirements`),
  scoreLead: (id) => request(`/leads/${id}/score`, { method: "POST" }),
  leadRecommendations: (id) => request(`/leads/${id}/recommendations`),
  leadFollowUps: (id) => request(`/leads/${id}/follow-ups`),
  suggestFollowUp: (id) => request(`/leads/${id}/follow-ups/suggest`, { method: "POST" }),
  createFollowUp: (id, body) => request(`/leads/${id}/follow-ups`, { method: "POST", body }),

  // follow-ups
  followUps: (params) => request("/follow-ups", { params }),
  editFollowUp: (id, body) => request(`/follow-ups/${id}`, { method: "PATCH", body }),
  approveFollowUp: (id) => request(`/follow-ups/${id}/approve`, { method: "POST" }),
  rejectFollowUp: (id) => request(`/follow-ups/${id}/reject`, { method: "POST" }),
  completeFollowUp: (id) => request(`/follow-ups/${id}/complete`, { method: "POST" }),

  // properties
  properties: (params) => request("/properties", { params }),
  searchProperties: (params) => request("/properties/search", { params }),

  // AI
  modelInfo: () => request("/model"),
  analyzeText: (text) => request("/nlp/analyze", { method: "POST", body: { text } }),
  runAgents: (leadId, message) => request(`/agents/leads/${leadId}/run`, { method: "POST", body: { message: message || null } }),
  chat: (body) => request("/chatbot/message", { method: "POST", body, auth: false }),
  agentLogs: (params) => request("/agents/logs", { params }),

  // analytics
  overview: () => request("/analytics/overview"),
  monthly: (months = 12) => request("/analytics/monthly", { params: { months } }),
  channels: () => request("/analytics/channels"),
  forecast: () => request("/analytics/forecast"),
  insights: () => request("/analytics/insights"),
};
