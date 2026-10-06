import { parseSseChunk } from "./sse";
import type {
  AppConfig,
  Overview,
  QualityReport,
  Relationship,
  SessionState,
  StreamEvent,
  TableResult,
  UploadResponse,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the DataPilot server. Is the backend running?", 0, "network");
  }
  if (!response.ok) {
    let message = "The server returned an unexpected error.";
    let code = "error";
    try {
      const body = await response.json();
      message = body.error?.message ?? message;
      code = body.error?.code ?? code;
    } catch {
      message = `The server returned status ${response.status}.`;
    }
    throw new ApiError(message, response.status, code);
  }
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const setLlm = (id: string, body: { provider: string; api_key: string; model: string }) =>
  request<SessionState>(`/api/sessions/${id}/llm`, { ...json(body), method: "PUT" });
export const clearLlm = (id: string) => request<SessionState>(`/api/sessions/${id}/llm`, { method: "DELETE" });
export const getConfig = () => request<AppConfig>("/api/config");
export const createSession = () => request<{ session_id: string }>("/api/sessions", { method: "POST" });
export const getSession = (id: string) => request<SessionState>(`/api/sessions/${id}`);
export const resetConversation = (id: string) => request<SessionState>(`/api/sessions/${id}/reset`, { method: "POST" });
export const clearFilters = (id: string) => request<SessionState>(`/api/sessions/${id}/filters`, { method: "DELETE" });
export const loadSamples = (id: string) => request<UploadResponse>(`/api/sessions/${id}/samples`, { method: "POST" });
export const deleteDataset = (id: string, name: string) =>
  request<SessionState>(`/api/sessions/${id}/datasets/${encodeURIComponent(name)}`, { method: "DELETE" });
export const getPreview = (id: string, name: string) =>
  request<TableResult>(`/api/sessions/${id}/datasets/${encodeURIComponent(name)}/preview?limit=50`);
export const getQuality = (id: string, name: string) =>
  request<QualityReport>(`/api/sessions/${id}/datasets/${encodeURIComponent(name)}/quality`);
export const getOverview = (id: string, name: string) =>
  request<Overview>(`/api/sessions/${id}/datasets/${encodeURIComponent(name)}/summary`);
export const addRelationship = (
  id: string,
  body: { left_table: string; left_column: string; right_table: string; right_column: string },
) => request<Relationship>(`/api/sessions/${id}/relationships`, json(body));

export function uploadFiles(id: string, files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<UploadResponse>(`/api/sessions/${id}/datasets`, { method: "POST", body: form });
}

export async function streamChat(
  id: string,
  message: string,
  dataset: string | null,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/sessions/${id}/chat`, { ...json({ message, dataset }), signal });
  } catch {
    if (signal.aborted) return;
    throw new ApiError("Cannot reach the DataPilot server. Is the backend running?", 0, "network");
  }
  if (!response.ok || !response.body) {
    let text = "The server could not start the analysis.";
    try {
      text = (await response.json()).error?.message ?? text;
    } catch {
      text = `The server returned status ${response.status}.`;
    }
    throw new ApiError(text, response.status, "chat");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
}
