/**
 * Sistema Centralizado de Z-Index
 * ================================
 * 
 * Define una jerarquía clara de capas para evitar conflictos de z-index.
 * SIEMPRE usar estas constantes en lugar de valores hardcodeados.
 * 
 * Jerarquía (de menor a mayor):
 * 1. Base (0-9): Elementos base sin posicionamiento especial
 * 2. Sticky Elements (10-19): Headers, footers sticky
 * 3. Navigation (20-39): Sidebars, navbars
 * 4. Dropdowns & Tooltips (40-49): Elementos que flotan sobre contenido
 * 5. Overlays (50-59): Overlays de paneles secundarios
 * 6. Modals (60-79): Modales y diálogos
 * 7. Floating Windows (1000+): Ventanas flotantes con z-index dinámico
 * 8. Toasts & Notifications (9000-9999): Notificaciones y alertas
 */

export const Z_INDEX = {
  // ============================================================================
  // BASE LAYER (0-9)
  // ============================================================================
  BASE: 0,
  
  // ============================================================================
  // STICKY ELEMENTS (10-19)
  // ============================================================================
  /** Headers sticky de tablas y listas */
  TABLE_HEADER: 10,
  
  /** Sticky headers de páginas (debajo de navigation) */
  PAGE_HEADER: 15,
  
  // ============================================================================
  // NAVIGATION (20-39)
  // ============================================================================
  /** Overlay del mobile menu del sidebar principal */
  SIDEBAR_MOBILE_OVERLAY: 20,
  
  /** Sidebar principal de navegación */
  SIDEBAR: 30,
  
  /** Navbar principal (mismo nivel que sidebar - ambos son navegación global) */
  NAVBAR: 30,
  
  /** Botón del mobile menu (debe estar sobre el sidebar) */
  SIDEBAR_MOBILE_BUTTON: 35,
  
  // ============================================================================
  // DROPDOWNS & TOOLTIPS (40-49)
  // ============================================================================
  /** Dropdowns, select menus, tooltips */
  DROPDOWN: 40,
  TOOLTIP: 45,
  
  // ============================================================================
  // SECONDARY PANELS & OVERLAYS (50-59)
  // ============================================================================
  /** Overlay de paneles secundarios (como el mini sidebar del scanner) */
  PANEL_OVERLAY: 50,
  
  /** Paneles deslizantes secundarios (mini sidebar del scanner) */
  SLIDING_PANEL: 55,
  
  // ============================================================================
  // MODALS (60-79)
  // ============================================================================
  /** Overlay/backdrop de modales */
  MODAL_OVERLAY: 60,
  
  /** Contenido del modal (debe estar sobre el overlay) */
  MODAL_CONTENT: 65,
  
  /** Modales de confirmación/alertas (sobre otros modales) */
  ALERT_MODAL: 70,
  
  // ============================================================================
  // FLOATING WINDOWS (1000-8999)
  // ============================================================================
  /** Base para ventanas flotantes (se incrementa dinámicamente) */
  FLOATING_WINDOW_BASE: 1000,
  
  /** Manager de ventanas flotantes */
  FLOATING_WINDOW_MANAGER: 8999,
  
  // ============================================================================
  // NOTIFICATIONS (9000-9999)
  // ============================================================================
  /** Toasts y notificaciones */
  TOAST: 9000,
  
  /** Notificaciones de sistema críticas */
  NOTIFICATION: 9500,
  
  /** Máximo z-index reservado para elementos críticos */
  MAX: 9999,
} as const;

/**
 * Helper para debugging - muestra todos los z-indexes en consola
 */
export function debugZIndex() {
  console.table(Z_INDEX);
}

/**
 * Valida que un z-index esté dentro del rango apropiado
 */
export function isValidZIndex(value: number, layer: keyof typeof Z_INDEX): boolean {
  const layerValue = Z_INDEX[layer];
  return value >= layerValue && value < layerValue + 10;
}

