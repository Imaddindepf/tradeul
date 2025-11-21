/**
 * Sistema Profesional de Z-Index
 * ================================
 * 
 * Arquitectura con 5 capas (de mayor a menor prioridad):
 * 
 * CAPA 5 (z-10000): Navegación Global (Navbar + Sidebar) - LÍMITE SUPERIOR, nada puede superarlo
 * CAPA 4 (z-9000): Popovers y controles del Navbar - Sobre el navbar
 * CAPA 3 (z-5000 a z-8999): Modales - Por debajo del navbar, sobre tablas
 * CAPA 2 (z-100 a z-4999): Tablas flotantes - Por debajo de modales
 * CAPA 1 (z-40): Controles del Scanner - Panel de configuración
 * CAPA 0 (z-0): Base - Dashboard background
 */

export const Z_INDEX = {
  // ============================================================================
  // CAPA 0: BASE (z-0)
  // ============================================================================
  BASE: 0,
  
  // ============================================================================
  // CAPA 1: CONTROLES DEL SCANNER (z-40)
  // ============================================================================
  /** Overlay que oscurece el fondo cuando el panel está abierto */
  SCANNER_PANEL_OVERLAY: 39,
  
  /** Panel deslizante de configuración de categorías */
  SCANNER_PANEL: 40,
  
  /** Botón azul para abrir el panel de configuración */
  SCANNER_BUTTON: 40,
  
  /** Popovers de configuración de tablas (columnas, filtros) */
  TABLE_SETTINGS_POPOVER: 40,
  
  /** Headers sticky dentro de contenedores scrollables */
  TABLE_HEADER: 5,
  
  /** Tooltips y dropdowns básicos */
  TOOLTIP: 35,
  DROPDOWN: 35,
  
  // ============================================================================
  // CAPA 2: TABLAS FLOTANTES (z-100 a z-4999)
  // ============================================================================
  /** 
   * Inicio para tablas flotantes del scanner
   * - Todas las tablas compiten por foco
   * - Se apilan dinámicamente
   */
  FLOATING_TABLES_BASE: 100,
  FLOATING_TABLES_MAX: 4999,
  
  // ============================================================================
  // CAPA 3: MODALES (z-5000 a z-8999)
  // ============================================================================
  /** 
   * Inicio para MODALES (ventanas de información):
   * - Modal de metadata del ticker
   * - Dilution Tracker
   * - Cualquier otra ventana modal
   * 
   * Los modales están SIEMPRE por encima de las tablas
   * pero por DEBAJO del navbar
   */
  MODAL_BASE: 5000,
  MODAL_MAX: 8999,
  
  // Aliases para compatibilidad con código existente
  FLOATING_CONTENT_BASE: 100, // Apunta a tablas por defecto
  FLOATING_WINDOW_BASE: 5000, // Ventanas flotantes = modales
  FLOATING_CONTENT_MAX: 4999,
  FLOATING_WINDOW_MANAGER: 899,
  
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
   * Obtiene un nuevo z-index para tablas flotantes
   */
  getNext(): number {
    this.currentMaxZ += 1;
    
    // Si llegamos al máximo de tablas, reiniciamos
    if (this.currentMaxZ >= Z_INDEX.FLOATING_TABLES_MAX) {
      this.currentMaxZ = Z_INDEX.FLOATING_TABLES_BASE + 1;
    }
    
    return this.currentMaxZ;
  }
  
  /**
   * Obtiene un nuevo z-index para modales (siempre por encima de tablas)
   */
  getNextModal(): number {
    // Los modales usan un rango separado y más alto
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
