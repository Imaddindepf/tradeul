'use client';

import { useState, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';

// ============================================================================
// Types
// ============================================================================

export interface IndicatorParams {
    period?: number;
    multiplier?: number;
    std_dev?: number;
    fast?: number;
    slow?: number;
    signal?: number;
}

export interface FilterCondition {
    field: string;
    params?: IndicatorParams | null;
    operator: string;
    value?: number | number[] | boolean | null;
    compare_field?: string | null;
    compare_params?: IndicatorParams | null;
}

export interface ScreenerTemplate {
    id: number;
    userId: string;
    name: string;
    description?: string | null;
    filters: FilterCondition[];
    sortBy: string;
    sortOrder: string;
    limitResults: number;
    isFavorite: boolean;
    color?: string | null;
    icon?: string | null;
    useCount: number;
    lastUsedAt?: string | null;
    isShared: boolean;
    isPublic: boolean;
    createdAt: string;
    updatedAt: string;
}

export interface CreateTemplateData {
    name: string;
    description?: string;
    filters: FilterCondition[];
    sort_by: string;
    sort_order: string;
    limit_results: number;
    is_favorite?: boolean;
    color?: string;
    icon?: string;
}

export interface UpdateTemplateData {
    name?: string;
    description?: string;
    filters?: FilterCondition[];
    sort_by?: string;
    sort_order?: string;
    limit_results?: number;
    is_favorite?: boolean;
    color?: string;
    icon?: string;
}

// ============================================================================
// Hook
// ============================================================================

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export function useScreenerTemplates() {
    const { getToken } = useAuth();
    const [templates, setTemplates] = useState<ScreenerTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchWithAuth = useCallback(async (
        endpoint: string,
        options: RequestInit = {}
    ) => {
        const token = await getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }

        const response = await fetch(`${API_BASE}/api/v1/screener/templates${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...options.headers,
            },
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || `HTTP ${response.status}`);
        }

        // DELETE returns 204 No Content
        if (response.status === 204) {
            return null;
        }

        return response.json();
    }, [getToken]);

    // List all templates
    const listTemplates = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchWithAuth('');
            setTemplates(data.templates || []);
            return data.templates;
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to load templates';
            setError(message);
            return [];
        } finally {
            setLoading(false);
        }
    }, [fetchWithAuth]);

    // Get single template
    const getTemplate = useCallback(async (id: number) => {
        setLoading(true);
        setError(null);
        try {
            return await fetchWithAuth(`/${id}`);
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to load template';
            setError(message);
            return null;
        } finally {
            setLoading(false);
        }
    }, [fetchWithAuth]);

    // Create template
    const createTemplate = useCallback(async (data: CreateTemplateData) => {
        setLoading(true);
        setError(null);
        try {
            const template = await fetchWithAuth('', {
                method: 'POST',
                body: JSON.stringify(data),
            });
            setTemplates(prev => [template, ...prev]);
            return template;
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to create template';
            setError(message);
            return null;
        } finally {
            setLoading(false);
        }
    }, [fetchWithAuth]);

    // Update template
    const updateTemplate = useCallback(async (id: number, data: UpdateTemplateData) => {
        setLoading(true);
        setError(null);
        try {
            const template = await fetchWithAuth(`/${id}`, {
                method: 'PUT',
                body: JSON.stringify(data),
            });
            setTemplates(prev => prev.map(t => t.id === id ? template : t));
            return template;
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to update template';
            setError(message);
            return null;
        } finally {
            setLoading(false);
        }
    }, [fetchWithAuth]);

    // Delete template
    const deleteTemplate = useCallback(async (id: number) => {
        setLoading(true);
        setError(null);
        try {
            await fetchWithAuth(`/${id}`, { method: 'DELETE' });
            setTemplates(prev => prev.filter(t => t.id !== id));
            return true;
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to delete template';
            setError(message);
            return false;
        } finally {
            setLoading(false);
        }
    }, [fetchWithAuth]);

    // Mark template as used (tracking)
    const useTemplate = useCallback(async (id: number) => {
        try {
            const template = await fetchWithAuth(`/${id}/use`, { method: 'POST' });
            setTemplates(prev => prev.map(t => t.id === id ? template : t));
            return template;
        } catch (err) {
            // Silent fail for tracking
            console.warn('Failed to track template usage:', err);
            return null;
        }
    }, [fetchWithAuth]);

    // Duplicate template
    const duplicateTemplate = useCallback(async (id: number) => {
        setLoading(true);
        setError(null);
        try {
            const template = await fetchWithAuth(`/${id}/duplicate`, { method: 'POST' });
            setTemplates(prev => [...prev, template]);
            return template;
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to duplicate template';
            setError(message);
            return null;
        } finally {
            setLoading(false);
        }
    }, [fetchWithAuth]);

    // Toggle favorite
    const toggleFavorite = useCallback(async (id: number) => {
        const template = templates.find(t => t.id === id);
        if (!template) return null;
        
        return updateTemplate(id, { is_favorite: !template.isFavorite });
    }, [templates, updateTemplate]);

    return {
        templates,
        loading,
        error,
        listTemplates,
        getTemplate,
        createTemplate,
        updateTemplate,
        deleteTemplate,
        useTemplate,
        duplicateTemplate,
        toggleFavorite,
    };
}

