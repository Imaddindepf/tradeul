/**
 * Definiciones EXACTAS de los 55 layouts de TradingView, extraídas del
 * bundle library.257d05… de la Charting Library v31 licenciada.
 * Árbol de partición: hoja = índice de celda; ["h",…] = columnas lado a
 * lado; ["v",…] = filas apiladas. Generado automáticamente; no editar.
 */

export type LayoutNode = number | ['h' | 'v', ...LayoutNode[]];

export interface TVLayoutDef {
    id: string;
    /** Nº de charts (celdas) del layout. */
    count: number;
    /** Árbol de partición (la hoja 0 sola = layout de 1 celda). */
    tree: LayoutNode;
}

export const TV_LAYOUTS: Record<string, TVLayoutDef> = {
    's': { id: 's', count: 1, tree: 0 },
    '2h': { id: '2h', count: 2, tree: ["h",0,1] },
    '2v': { id: '2v', count: 2, tree: ["v",0,1] },
    '3h': { id: '3h', count: 3, tree: ["h",0,1,2] },
    '3v': { id: '3v', count: 3, tree: ["v",0,1,2] },
    '3s': { id: '3s', count: 3, tree: ["h",0,["v",1,2]] },
    '3r': { id: '3r', count: 3, tree: ["h",["v",0,1],2] },
    '2-1': { id: '2-1', count: 3, tree: ["v",["h",0,2],1] },
    '1-2': { id: '1-2', count: 3, tree: ["v",0,["h",1,2]] },
    '4': { id: '4', count: 4, tree: ["v",["h",0,2],["h",1,3]] },
    '4v': { id: '4v', count: 4, tree: ["v",0,1,2,3] },
    '4h': { id: '4h', count: 4, tree: ["h",0,1,2,3] },
    '4s': { id: '4s', count: 4, tree: ["h",0,["v",1,2,3]] },
    '4s-l': { id: '4s-l', count: 4, tree: ["h",["v",1,2,3],0] },
    '1-3': { id: '1-3', count: 4, tree: ["v",0,["h",1,2,3]] },
    '3-1': { id: '3-1', count: 4, tree: ["v",["h",0,1,2],3] },
    '2-2-l': { id: '2-2-l', count: 4, tree: ["h",0,1,["v",2,3]] },
    '2-2-r': { id: '2-2-r', count: 4, tree: ["h",["v",0,1],2,3] },
    '2-2': { id: '2-2', count: 4, tree: ["v",["h",0,1],["v",2,3]] },
    '1-4': { id: '1-4', count: 5, tree: ["v",0,["h",1,2,3,4]] },
    '5h': { id: '5h', count: 5, tree: ["h",0,1,2,3,4] },
    '5v': { id: '5v', count: 5, tree: ["v",0,1,2,3,4] },
    '5s': { id: '5s', count: 5, tree: ["h",0,["v",1,2,3,4]] },
    '5s-l': { id: '5s-l', count: 5, tree: ["h",["v",1,2,3,4],0] },
    '2-3': { id: '2-3', count: 5, tree: ["v",["h",0,1],["h",2,3,4]] },
    '3-2': { id: '3-2', count: 5, tree: ["v",["h",0,1,2],["h",3,4]] },
    '4-1': { id: '4-1', count: 5, tree: ["v",["h",0,1,2,3],4] },
    '2-3-l': { id: '2-3-l', count: 5, tree: ["h",0,1,["v",2,3,4]] },
    '2-3-r': { id: '2-3-r', count: 5, tree: ["h",["v",0,1,2],3,4] },
    '6': { id: '6', count: 6, tree: ["v",["h",0,2,4],["h",1,3,5]] },
    '6h': { id: '6h', count: 6, tree: ["h",0,1,2,3,4,5] },
    '6v': { id: '6v', count: 6, tree: ["v",0,1,2,3,4,5] },
    '6c': { id: '6c', count: 6, tree: ["v",["h",0,1],["h",2,3],["h",4,5]] },
    '2-4': { id: '2-4', count: 6, tree: ["v",["h",0,1],["h",2,3,4,5]] },
    '4-2': { id: '4-2', count: 6, tree: ["v",["h",0,1,2,3],["h",4,5]] },
    '4-3': { id: '4-3', count: 7, tree: ["v",["h",0,1,2,3],["h",4,5,6]] },
    '7h': { id: '7h', count: 7, tree: ["h",0,1,2,3,4,5,6] },
    '7s': { id: '7s', count: 7, tree: ["h",0,["v",1,2,3,4,5,6]] },
    '8': { id: '8', count: 8, tree: ["v",["h",0,2,4,6],["h",1,3,5,7]] },
    '8c': { id: '8c', count: 8, tree: ["v",["h",0,1],["h",2,3],["h",4,5],["h",6,7]] },
    '8h': { id: '8h', count: 8, tree: ["h",0,1,2,3,4,5,6,7] },
    '8v': { id: '8v', count: 8, tree: ["v",0,1,2,3,4,5,6,7] },
    '9s': { id: '9s', count: 9, tree: ["v",["h",0,1,2],["h",3,4,5],["h",6,7,8]] },
    '5-4': { id: '5-4', count: 9, tree: ["v",["h",0,1,2,3,4],["h",5,6,7,8]] },
    '9h': { id: '9h', count: 9, tree: ["h",0,1,2,3,4,5,6,7,8] },
    '9v': { id: '9v', count: 9, tree: ["v",0,1,2,3,4,5,6,7,8] },
    '10c5': { id: '10c5', count: 10, tree: ["v",["h",0,2,4,6,8],["h",1,3,5,7,9]] },
    '10h': { id: '10h', count: 10, tree: ["h",0,1,2,3,4,5,6,7,8,9] },
    '10v': { id: '10v', count: 10, tree: ["v",0,1,2,3,4,5,6,7,8,9] },
    '12c6': { id: '12c6', count: 12, tree: ["v",["h",0,2,4,6,8,10],["h",1,3,5,7,9,11]] },
    '12c4': { id: '12c4', count: 12, tree: ["v",["h",0,4,8],["h",1,5,9],["h",2,6,10],["h",3,7,11]] },
    '12h': { id: '12h', count: 12, tree: ["h",0,1,2,3,4,5,6,7,8,9,10,11] },
    '14c7': { id: '14c7', count: 14, tree: ["v",["h",0,2,4,6,8,10,12],["h",1,3,5,7,9,11,13]] },
    '16c8': { id: '16c8', count: 16, tree: ["v",["h",0,2,4,6,8,10,12,14],["h",1,3,5,7,9,11,13,15]] },
    '16c4': { id: '16c4', count: 16, tree: ["v",["h",0,4,8,12],["h",1,5,9,13],["h",2,6,10,14],["h",3,7,11,15]] },
};

/** Orden y agrupación del picker (por nº de charts), igual que TradingView. */
export const TV_LAYOUT_GROUPS: Array<{ count: number; ids: string[] }> = [
    { count: 1, ids: ['s'] },
    { count: 2, ids: ['2h','2v'] },
    { count: 3, ids: ['3h','3v','3s','3r','2-1','1-2'] },
    { count: 4, ids: ['4','4v','4h','4s','4s-l','1-3','3-1','2-2-l','2-2-r','2-2'] },
    { count: 5, ids: ['1-4','5h','5v','5s','5s-l','2-3','3-2','4-1','2-3-l','2-3-r'] },
    { count: 6, ids: ['6','6h','6v','6c','2-4','4-2'] },
    { count: 7, ids: ['4-3','7h','7s'] },
    { count: 8, ids: ['8','8c','8h','8v'] },
    { count: 9, ids: ['9s','5-4','9h','9v'] },
    { count: 10, ids: ['10c5','10h','10v'] },
    { count: 12, ids: ['12c6','12c4','12h'] },
    { count: 14, ids: ['14c7'] },
    { count: 16, ids: ['16c8','16c4'] },
];
