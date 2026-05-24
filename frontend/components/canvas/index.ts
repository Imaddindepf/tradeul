/**
 * Canvas — sistema genérico de widgets editables para ventanas flotantes.
 *
 * Uso típico:
 *
 *   const config: CanvasConfig = { manifest, defaultLayout, templates };
 *   const canvas = useCanvas(config);
 *
 *   <>
 *     <CanvasToolbar
 *       editMode={canvas.editMode}
 *       onToggleEdit={canvas.toggleEditMode}
 *       onOpenPalette={() => setPaletteOpen(true)}
 *       onReset={canvas.resetLayout}
 *       templates={config.templates}
 *       activeTemplateId={null}
 *       onSelectTemplate={(id) => canvas.setLayout(config.templates!.find(t => t.id === id)!.layout)}
 *     />
 *     <div className="relative flex-1 overflow-hidden">
 *       <CanvasGrid config={config} canvas={canvas} />
 *       <WidgetPalette
 *         open={paletteOpen}
 *         onClose={() => setPaletteOpen(false)}
 *         config={config}
 *         onAdd={(type) => { canvas.addWidget(type); setPaletteOpen(false); }}
 *       />
 *     </div>
 *   </>
 */

export { CanvasGrid } from './CanvasGrid';
export type { CanvasGridProps } from './CanvasGrid';

export { CanvasToolbar } from './CanvasToolbar';
export type { CanvasToolbarProps } from './CanvasToolbar';

export { WidgetPalette } from './WidgetPalette';
export type { WidgetPaletteProps } from './WidgetPalette';

export { WidgetShell } from './WidgetShell';
export type { WidgetShellProps } from './WidgetShell';

export { useCanvas } from './useCanvas';
export type { UseCanvasReturn } from './useCanvas';

export type {
    CanvasConfig,
    CanvasItem,
    CanvasLayout,
    CanvasTemplate,
    WidgetCategory,
    WidgetContext,
    WidgetDefinition,
    WidgetInstanceId,
    WidgetManifest,
    WidgetTypeId,
} from './types';

export { CANVAS_LAYOUT_VERSION, newInstanceId } from './types';
