/**
 * Registro global de buscadores de ticker por ventana flotante.
 * =============================================================
 *
 * Permite el "type-ahead": cuando una ventana tiene el foco y el usuario
 * teclea una letra, enrutamos esa pulsación al buscador de ticker de esa
 * ventana (lo enfocamos y arrancamos la búsqueda con la letra escrita).
 *
 * Cada buscador (el componente compartido `TickerSearch` y algunos inputs
 * nativos) se auto-registra usando su `windowId`. El listener global de
 * teclado consulta `floatingFocusManager.getCurrent()` y delega aquí.
 */

export interface TickerSearchEntry {
  /** Devuelve el <input> si está montado/visible (para desempatar por orden en el DOM). */
  getInput: () => HTMLInputElement | null;
  /** Enfoca el buscador y arranca una búsqueda con el carácter tecleado. */
  type: (char: string) => void;
}

const registry = new Map<string, Set<TickerSearchEntry>>();

/** Registra un buscador para una ventana. Devuelve la función para desregistrar. */
export function registerTickerSearch(windowId: string, entry: TickerSearchEntry): () => void {
  let set = registry.get(windowId);
  if (!set) {
    set = new Set();
    registry.set(windowId, set);
  }
  set.add(entry);

  return () => {
    const current = registry.get(windowId);
    if (!current) return;
    current.delete(entry);
    if (current.size === 0) {
      registry.delete(windowId);
    }
  };
}

/** Indica si la ventana tiene al menos un buscador de ticker registrado. */
export function hasTickerSearch(windowId: string | null): boolean {
  if (!windowId) return false;
  const set = registry.get(windowId);
  return !!set && set.size > 0;
}

/**
 * Enruta un carácter al buscador de la ventana indicada.
 * Si hay varios (p. ej. Ratio Analysis), elige el visible que aparece antes
 * en el DOM; si ninguno está montado, usa el primero registrado (p. ej. un
 * buscador que se despliega bajo demanda).
 * @returns true si se entregó a algún buscador.
 */
export function typeIntoTickerSearch(windowId: string, char: string): boolean {
  const set = registry.get(windowId);
  if (!set || set.size === 0) return false;

  const entries = [...set];
  const visible = entries.filter((e) => {
    const el = e.getInput();
    return !!el && el.isConnected;
  });

  let chosen: TickerSearchEntry | undefined;
  if (visible.length > 0) {
    visible.sort((a, b) => {
      const ea = a.getInput()!;
      const eb = b.getInput()!;
      return ea.compareDocumentPosition(eb) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
    chosen = visible[0];
  } else {
    chosen = entries[0];
  }

  if (!chosen) return false;
  chosen.type(char);
  return true;
}
