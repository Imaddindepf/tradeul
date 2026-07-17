/**
 * Workflow Canvas — modelo genérico de nodos para TODOS los canvases de
 * Tradeul (ejecución del agente, alertas armadas, y futuros pipelines).
 *
 * Un canvas concreto es solo un adaptador: convierte su fuente de datos
 * (steps del grafo LangGraph, specs de alertas, un pipeline programado…)
 * en capas de WorkflowNodeSpec. El renderizado, layout, aristas y las
 * animaciones internas de procesamiento viven una única vez aquí.
 */

export type WorkflowNodeStatus =
  | 'pending'    // en cola (ejecución) / sin datos
  | 'running'    // procesando ahora — glow primario + scanline
  | 'complete'   // terminó bien
  | 'error'      // falló
  | 'live'       // workflow permanente vigilando (alerta armada, stream…)
  | 'paused'     // workflow permanente en pausa
  | 'fired';     // acaba de disparar — glow ámbar

/** Bloques de contenido tipados que un nodo puede renderizar, en orden. */
export type NodeBlock =
  | { kind: 'progress'; text: string }
  | { kind: 'metrics'; items: Array<{ label: string; value: string | number }> }
  | { kind: 'chips'; style: 'primary' | 'neutral' | 'mono'; items: string[] }
  | { kind: 'text'; text: string }
  | { kind: 'error'; text: string }
  | {
      kind: 'table';
      title?: string;
      columns: string[];
      rows: string[][];
      total?: number;
      /** Las filas entran una a una en cascada la primera vez que se ven. */
      cascade?: boolean;
    }
  | {
      kind: 'code';
      language?: string;
      content: string;
      /** El código se "escribe" en vivo la primera vez que aparece. */
      typewriter?: boolean;
    }
  | {
      kind: 'feed';
      /** Filas en vivo (disparos, ticks): entran deslizándose, keyed por id. */
      rows: Array<{ id: string; cells: string[]; highlight?: boolean }>;
    };

export interface WorkflowNodeSpec {
  id: string;
  title: string;
  subtitle?: string;
  status: WorkflowNodeStatus;
  /** Chip numerado en el header (pasos de ejecución). */
  stepNumber?: number;
  /** Duración en segundos (se muestra junto al subtítulo). */
  duration?: number;
  /** Texto del footer derecho; si falta se deriva del status. */
  badge?: string;
  /** Texto del footer izquierdo (p. ej. "computation step" / "live workflow"). */
  footerLabel?: string;
  blocks: NodeBlock[];
}

export type WorkflowEdgeState = 'idle' | 'active' | 'live' | 'done' | 'fired';

export interface WorkflowEdgeSpec {
  source: string;
  target: string;
  state: WorkflowEdgeState;
}
