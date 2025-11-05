export interface TableSnapshot<T> {
  rows: T[];
  sequence?: number;
  count?: number;
}

export type TableDeltaAction<T> =
  | { action: 'add'; symbol: string; rank?: number; data: T }
  | { action: 'remove'; symbol: string }
  | { action: 'update'; symbol: string; rank?: number; data: T }
  | { action: 'rerank'; symbol: string; old_rank?: number; new_rank: number };

export interface TableDeltaBatch<T> {
  deltas: TableDeltaAction<T>[];
  sequence?: number;
}

export interface TableDataAdapter<T> {
  connect: (
    onSnapshot: (snapshot: TableSnapshot<T>) => void,
    onDelta: (batch: TableDeltaBatch<T>) => void
  ) => void;
  disconnect: () => void;
  requestResync?: () => void;
}


