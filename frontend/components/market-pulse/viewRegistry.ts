import type { PulseViewType } from './types';

export interface ViewDefinition {
  key: PulseViewType;
  label: string;
  shortLabel: string;
}

export const VIEW_DEFINITIONS: ViewDefinition[] = [
  { key: 'overview', label: 'Market Overview',  shortLabel: 'Overview' },
  { key: 'table',    label: 'Table',            shortLabel: 'Table' },
  { key: 'treemap',  label: 'Treemap',          shortLabel: 'Map' },
  { key: 'bubble',   label: 'Bubble Scatter',   shortLabel: 'Scatter' },
  { key: 'rotation', label: 'Rotation',         shortLabel: 'Bars' },
  { key: 'breadth',  label: 'Breadth Monitor',  shortLabel: 'Breadth' },
];
