/**
 * Sistema Profesional de Z-Index
 * ================================
 * 
 * Arquitectura simple y lógica con 4 capas:
 * 
 * CAPA 1 (z-50): Navegación Global (Navbar + Sidebar) - Siempre visible
 * CAPA 2 (z-40): Controles del Scanner - Sobre navegación pero bajo contenido
 * CAPA 3 (z-10 a z-9999): Contenido Flotante - Todas las ventanas compiten por foco
 * CAPA 0 (z-0): Base - Dashboard background
 */

export const Z_INDEX = {
  // ============================================================================
  // CAPA 0: BASE (z-0)
  // ============================================================================
  BASE: 0,
  
  // ============================================================================
  // CAPA 3: CONTENIDO FLOTANTE (z-10 a z-9999)
  // ============================================================================
  /** 
   * Inicio para TODO el contenido flotante:
   * - Tablas del scanner
   * - Modal de metadata (como ventana flotante)
   * - Dilution Tracker
   * - Cualquier otra ventana
   * 
   * TODAS compiten por el foco y se apilan dinámicamente
   */
  FLOATING_CONTENT_BASE: 10,
  FLOATING_WINDOW_BASE: 10, // Alias para compatibilidad
  
  /** Límite máximo para contenido flotante */
  FLOATING_CONTENT_MAX: 9999,
  FLOATING_WINDOW_MANAGER: 899, // Alias para compatibilidad
  
  // ============================================================================
  // CAPA 2: CONTROLES DEL SCANNER (z-40)
  // ============================================================================
  /** Overlay que oscurece el fondo cuando el panel está abierto */
  SCANNER_PANEL_OVERLAY: 39,
  
  /** Panel deslizante de configuración de categorías */
  SCANNER_PANEL: 40,
  
  /** Botón azul para abrir el panel de configuración */
  SCANNER_BUTTON: 40,
  
  /** Popovers de configuración de tablas (columnas, filtros) */
  TABLE_SETTINGS_POPOVER: 40,
  
  // ============================================================================
  // CAPA 1: NAVEGACIÓN GLOBAL (z-50)
  // ============================================================================
  /** Overlay del mobile menu del sidebar */
  SIDEBAR_MOBILE_OVERLAY: 49,
  
  /** Sidebar principal de navegación */
  SIDEBAR: 50,
  
  /** Navbar principal (mismo nivel que sidebar) */
  NAVBAR: 50,
  
  /** Botón del mobile menu (debe estar sobre el sidebar) */
  SIDEBAR_MOBILE_BUTTON: 51,
  
  /** Popovers del navbar (Market Status, etc.) - sobre el navbar mismo */
  NAVBAR_POPOVER: 52,
  
  // ============================================================================
  // ELEMENTOS AUXILIARES
  // ============================================================================
  /** Headers sticky dentro de contenedores scrollables */
  TABLE_HEADER: 5,
  
  /** Tooltips y dropdowns básicos */
  TOOLTIP: 35,
  DROPDOWN: 35,
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
  private currentMaxZ: number = Z_INDEX.FLOATING_CONTENT_BASE;
  
  /**
   * Obtiene un nuevo z-index para contenido flotante
   */
  getNext(): number {
    this.currentMaxZ += 1;
    
    // Si llegamos al máximo, reiniciamos
    if (this.currentMaxZ >= Z_INDEX.FLOATING_CONTENT_MAX) {
      this.currentMaxZ = Z_INDEX.FLOATING_CONTENT_BASE + 1;
    }
    
    return this.currentMaxZ;
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
    this.currentMaxZ = Z_INDEX.FLOATING_CONTENT_BASE;
  }
}

// Instancia global del manager
export const floatingZIndexManager = new FloatingContentZIndexManager();
