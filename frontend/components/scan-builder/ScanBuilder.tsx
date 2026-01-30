'use client';

import { useState, useCallback } from 'react';
import { useUserFilters } from '@/hooks/useUserFilters';
import { useFiltersStore } from '@/stores/useFiltersStore';
import { Save, Trash2, Play, Plus, Edit2, Check, X } from 'lucide-react';
import type { UserFilterCreate } from '@/lib/types/scannerFilters';

interface ScanBuilderProps {
  onScanSelect?: (scanId: number) => void;
}

export function ScanBuilder({ onScanSelect }: ScanBuilderProps) {
  const { filters, loading, createFilter, updateFilter, deleteFilter } = useUserFilters();
  const { activeFilters } = useFiltersStore();

  const [newScanName, setNewScanName] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [saving, setSaving] = useState(false);

  // Save current filters as a new scan
  const handleSaveScan = useCallback(async () => {
    if (!newScanName.trim()) return;

    setSaving(true);
    try {
      const newFilter: UserFilterCreate = {
        name: newScanName.trim(),
        description: `Custom scan: ${newScanName}`,
        enabled: true,
        filter_type: 'custom',
        parameters: activeFilters,
        priority: 0,
      };

      const result = await createFilter(newFilter);
      if (result) {
        setNewScanName('');
      }
    } finally {
      setSaving(false);
    }
  }, [newScanName, activeFilters, createFilter]);

  // Toggle scan enabled/disabled
  const handleToggle = useCallback(async (id: number, currentEnabled: boolean) => {
    await updateFilter(id, { enabled: !currentEnabled });
  }, [updateFilter]);

  // Delete a scan
  const handleDelete = useCallback(async (id: number) => {
    if (confirm('Delete this scan?')) {
      await deleteFilter(id);
    }
  }, [deleteFilter]);

  // Start editing name
  const startEdit = (id: number, name: string) => {
    setEditingId(id);
    setEditName(name);
  };

  // Save edited name
  const saveEdit = async () => {
    if (editingId && editName.trim()) {
      await updateFilter(editingId, { name: editName.trim() });
    }
    setEditingId(null);
    setEditName('');
  };

  // Cancel edit
  const cancelEdit = () => {
    setEditingId(null);
    setEditName('');
  };

  // Count active filters
  const activeFilterCount = Object.values(activeFilters).filter(v => v !== undefined && v !== null).length;

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header - Save New Scan */}
      <div className="flex-shrink-0 p-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newScanName}
            onChange={(e) => setNewScanName(e.target.value)}
            placeholder="Name your scan..."
            className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-blue-400"
            onKeyDown={(e) => e.key === 'Enter' && handleSaveScan()}
          />
          <button
            onClick={handleSaveScan}
            disabled={!newScanName.trim() || activeFilterCount === 0 || saving}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Save className="w-4 h-4" />
            <span className="text-sm font-medium">Save</span>
          </button>
        </div>
        {activeFilterCount > 0 && (
          <p className="mt-1.5 text-xs text-slate-500">
            {activeFilterCount} filter{activeFilterCount !== 1 ? 's' : ''} configured
          </p>
        )}
      </div>

      {/* Saved Scans List */}
      <div className="flex-1 overflow-y-auto p-3">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
          My Scans ({filters.length})
        </h3>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
          </div>
        ) : filters.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <Plus className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No scans saved yet</p>
            <p className="text-xs mt-1">Configure filters above and save</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filters.map((filter) => (
              <div
                key={filter.id}
                className={`
                  p-3 rounded-lg border transition-all
                  ${filter.enabled
                    ? 'border-blue-200 bg-blue-50/50'
                    : 'border-slate-200 bg-slate-50/50 opacity-60'}
                `}
              >
                <div className="flex items-center justify-between">
                  {editingId === filter.id ? (
                    <div className="flex items-center gap-2 flex-1">
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="flex-1 px-2 py-1 text-sm border border-blue-300 rounded focus:outline-none"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit();
                          if (e.key === 'Escape') cancelEdit();
                        }}
                      />
                      <button onClick={saveEdit} className="p-1 text-green-500 hover:bg-green-100 rounded">
                        <Check className="w-4 h-4" />
                      </button>
                      <button onClick={cancelEdit} className="p-1 text-red-500 hover:bg-red-100 rounded">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleToggle(filter.id, filter.enabled)}
                          className={`w-8 h-4 rounded-full transition-colors ${filter.enabled ? 'bg-blue-500' : 'bg-slate-300'
                            }`}
                        >
                          <div className={`w-3 h-3 rounded-full bg-white transform transition-transform ${filter.enabled ? 'translate-x-4' : 'translate-x-0.5'
                            }`} />
                        </button>
                        <span className="font-medium text-sm text-slate-700">{filter.name}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => onScanSelect?.(filter.id)}
                          className="p-1.5 text-blue-500 hover:bg-blue-100 rounded"
                          title="Run scan"
                        >
                          <Play className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => startEdit(filter.id, filter.name)}
                          className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded"
                          title="Edit name"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(filter.id)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </>
                  )}
                </div>

                {/* Filter summary */}
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(filter.parameters || {}).map(([key, value]) => {
                    if (value === undefined || value === null) return null;
                    return (
                      <span
                        key={key}
                        className="inline-flex items-center px-2 py-0.5 bg-white rounded text-xs text-slate-600 border border-slate-200"
                      >
                        {key.replace(/_/g, ' ')}: {typeof value === 'number' ? value.toLocaleString() : String(value)}
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
