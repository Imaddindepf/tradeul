/**
 * Sistema Profesional de Z-Index
 * ================================
 * 
 * Arquitectura con 6 capas (de mayor a menor prioridad):
 * 
 * CAPA 6 (z-10000): Navegación Global (Navbar + Sidebar) - LÍMITE SUPERIOR ABSOLUTO
 * CAPA 5 (z-9000): Popovers del Navbar (Market Status, etc)
 * CAPA 4 (z-8500): Panel de Configuración del Scanner - Por encima de todo excepto navbar/sidebar
 * CAPA 3 (z-5000 a z-8499): Modales (Ticker Metadata, Dilution Tracker)
 * CAPA 2 (z-100 a z-4999): Tablas Flotantes del Scanner
 * CAPA 1 (z-0 a z-99): Elementos auxiliares (tooltips, headers)
 * CAPA 0 (z-0): Base - Dashboard background
 */

export const Z_INDEX = {
  // ============================================================================
  // CAPA 0: BASE (z-0)
  // ============================================================================
  BASE: 0,
  
  // ============================================================================
  // CAPA 1: CONTROLES DEL SCANNER (z-8500)
  // ============================================================================
  /** Overlay que oscurece el fondo cuando el panel está abierto */
  SCANNER_PANEL_OVERLAY: 8499,
  
  /** Panel deslizante de configuración de categorías - Por encima de tablas, debajo de sidebar */
  SCANNER_PANEL: 8500,
  
  /** Botón azul para abrir el panel de configuración */
  SCANNER_BUTTON: 8500,
  
  /** Popovers de configuración de tablas (columnas, filtros) */
  TABLE_SETTINGS_POPOVER: 8500,
  
  /** Headers sticky dentro de contenedores scrollables */
  TABLE_HEADER: 5,
  
  /** Tooltips y dropdowns básicos */
  TOOLTIP: 35,
  DROPDOWN: 35,
  
  // ============================================================================
  // CAPA 2: TODAS LAS VENTANAS FLOTANTES (z-100 a z-8499)
  // ============================================================================
  /** 
   * Rango unificado para TODAS las ventanas flotantes:
   * - Tablas del scanner
   * - Settings, Dilution Tracker, SEC Filings
   * - Cualquier otra ventana
   * 
   * TODAS compiten en la misma jerarquía, sin privilegios.
   * Click = traer al frente.
   */
  FLOATING_TABLES_BASE: 100,
  FLOATING_TABLES_MAX: 8499,
  
  // Aliases para compatibilidad
  FLOATING_CONTENT_BASE: 100,
  FLOATING_WINDOW_BASE: 100,
  FLOATING_CONTENT_MAX: 8499,
  FLOATING_WINDOW_MANAGER: 899,
  
  // Modal solo para ticker metadata (popup sobre todo)
  MODAL_BASE: 8500,
  MODAL_MAX: 8999,
  
  /** Alias para modales genéricos (dropdowns de navbar, settings, etc) */
  MODAL: 9500,
  
  // ============================================================================
  // CAPA 4: POPOVERS DEL NAVBAR (z-9000)
  // ============================================================================
  /** Popovers del navbar (Market Status, etc.) - sobre el navbar mismo */
  NAVBAR_POPOVER: 9000,
  
  // ============================================================================
  // CAPA 5: NAVEGACIÓN GLOBAL (z-10000) - LÍMITE SUPERIOR DE LA APP
  // ============================================================================
  /** Overlay del mobile menu del sidebar */
  SIDEBAR_MOBILE_OVERLAY: 9999,
  
  /** Sidebar principal de navegación */
  SIDEBAR: 10000,
  
  /** Navbar principal - EL LÍMITE SUPERIOR, nada puede superarlo */
  NAVBAR: 10000,
  
  /** Botón del mobile menu (debe estar sobre el sidebar) */
  SIDEBAR_MOBILE_BUTTON: 10001,
  
  // ============================================================================
  // CAPA 6: WORKSPACE TABS (z-10002) - Barra inferior de workspaces
  // ============================================================================
  /** Barra de tabs de workspaces en la parte inferior */
  WORKSPACE_TABS: 10002,
} as const;

/**
 * Helper para debugging - muestra todos los z-indexes en consola
 */
export function debugZIndex() {
  console.table(Z_INDEX);
}

/**
 * Clase global para gestionar el z-index dinámico del contenido flotante
 */
class FloatingContentZIndexManager {
  private currentMaxZ: number = Z_INDEX.FLOATING_TABLES_BASE;
  
  /**
   * Obtiene un nuevo z-index para CUALQUIER ventana flotante
   * Todas las ventanas (scanner, settings, DT, SEC) compiten igual
   */
  getNext(): number {
    this.currentMaxZ += 1;
    
    // Si llegamos al máximo, reiniciamos
    if (this.currentMaxZ >= Z_INDEX.FLOATING_TABLES_MAX) {
      this.currentMaxZ = Z_INDEX.FLOATING_TABLES_BASE + 1;
    }
    
    return this.currentMaxZ;
  }
  
  /**
   * Obtiene un nuevo z-index para modales especiales (ticker metadata popup)
   * Estos SÍ van por encima de todo porque son popups informativos temporales
   */
  getNextModal(): number {
    const modalZ = Z_INDEX.MODAL_BASE + Math.floor(Math.random() * 100);
    return Math.min(modalZ, Z_INDEX.MODAL_MAX);
  }
  
  /**
   * Obtiene el z-index actual más alto
   */
  getCurrent(): number {
    return this.currentMaxZ;
  }
  
  /**
   * Resetea el contador (útil para testing)
   */
  reset(): void {
    this.currentMaxZ = Z_INDEX.FLOATING_TABLES_BASE;
  }
}

// Instancia global del manager
export const floatingZIndexManager = new FloatingContentZIndexManager();
