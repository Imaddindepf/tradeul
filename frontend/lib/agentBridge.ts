/**
 * Puente ligero OpenUL/News -> ventana del Agente IA.
 *
 * Permite pedir un "Brief de Contexto" para una noticia que se abrirá en la
 * ventana del agente (reutilizada, miniaturizada) y persistirá en el hilo.
 *
 * Maneja la carrera de montaje: si la ventana del agente aún no está montada
 * cuando se dispara el evento, el contenido queda pendiente y el agente lo
 * consume al montar (`consumePendingBrief`). Si ya está montada, lo recibe por
 * el evento `agent:context-brief`.
 */

export interface ContextBriefNews {
  text: string;
  tickers?: string[];
  created_at?: string;
  received_at?: string;
  id?: string;
}

let pendingBrief: ContextBriefNews | null = null;

export const AGENT_CONTEXT_BRIEF_EVENT = 'agent:context-brief';

/** Solicita un brief de contexto para una noticia. */
export function requestContextBrief(news: ContextBriefNews): void {
  pendingBrief = news;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AGENT_CONTEXT_BRIEF_EVENT, { detail: { news } }));
  }
}

/** El agente lo llama al montar para recoger una petición pendiente. */
export function consumePendingBrief(): ContextBriefNews | null {
  const p = pendingBrief;
  pendingBrief = null;
  return p;
}

/** Limpia cualquier petición pendiente (al recibirla por evento). */
export function clearPendingBrief(): void {
  pendingBrief = null;
}
