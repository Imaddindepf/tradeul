/**
 * Cliente REST de runs/artifacts del AI Agent V4.
 *
 * Cada query del chat es un run persistido; cada nodo guarda sus outputs
 * completos (tablas enteras, código, charts) como artifacts en el backend.
 * El inspector de nodo los pide aquí: GET /api/runs/{run}/nodes/{node}/artifacts.
 */
import { authFetchStandalone } from '@/hooks/useAuthFetch';
import type { Artifact } from '@/components/ai-agent/types';

const AGENT_BASE = process.env.NEXT_PUBLIC_AI_AGENT_V4_API_URL || 'https://agent.tradeul.com/v4';

export type GetTokenFn = (opts?: { skipCache?: boolean }) => Promise<string | null>;

async function request<T>(getToken: GetTokenFn, path: string): Promise<T> {
  const res = await authFetchStandalone(`${AGENT_BASE}${path}`, getToken);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface RunInfo {
  run_id: string;
  thread_id: string;
  query: string;
  status: string;
  started_at: number;
  finished_at: number | null;
  nodes: Record<string, Array<{ idx: number; kind: string; title: string }>>;
}

export function getRun(getToken: GetTokenFn, runId: string): Promise<RunInfo> {
  return request(getToken, `/api/runs/${encodeURIComponent(runId)}`);
}

export function getNodeArtifacts(
  getToken: GetTokenFn,
  runId: string,
  node: string,
): Promise<{ run_id: string; node: string; artifacts: Artifact[] }> {
  return request(
    getToken,
    `/api/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(node)}/artifacts`,
  );
}
