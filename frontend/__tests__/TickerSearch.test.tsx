/**
 * Tests para TickerSearch Component
 * Verifica funcionalidad de autocomplete/typeahead
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TickerSearch } from '@/components/common/TickerSearch';

// Mock fetch
global.fetch = jest.fn();

describe('TickerSearch', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        (global.fetch as jest.Mock).mockClear();
    });

    it('debe renderizar el input correctamente', () => {
        const onChange = jest.fn();
        render(<TickerSearch value="" onChange={onChange} />);
        
        const input = screen.getByPlaceholderText('Ticker');
        expect(input).toBeInTheDocument();
    });

    it('debe llamar a onChange cuando el usuario escribe', () => {
        const onChange = jest.fn();
        render(<TickerSearch value="" onChange={onChange} />);
        
        const input = screen.getByPlaceholderText('Ticker');
        fireEvent.change(input, { target: { value: 'AAPL' } });
        
        expect(onChange).toHaveBeenCalledWith('AAPL');
    });

    it('debe hacer debounce de las búsquedas (150ms)', async () => {
        const onChange = jest.fn();
        const { rerender } = render(<TickerSearch value="" onChange={onChange} />);
        
        // Mock de respuesta exitosa
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                results: [
                    { symbol: 'AAPL', name: 'Apple Inc', exchange: 'NASDAQ' }
                ]
            })
        });
        
        // Simular escritura rápida
        rerender(<TickerSearch value="A" onChange={onChange} />);
        rerender(<TickerSearch value="AA" onChange={onChange} />);
        rerender(<TickerSearch value="AAP" onChange={onChange} />);
        rerender(<TickerSearch value="AAPL" onChange={onChange} />);
        
        // Debe hacer solo 1 request después del debounce
        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledTimes(1);
        }, { timeout: 200 });
    });

    it('debe mostrar resultados cuando la API responde', async () => {
        const onChange = jest.fn();
        const { rerender } = render(<TickerSearch value="" onChange={onChange} />);
        
        // Mock de respuesta exitosa
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                results: [
                    { symbol: 'AAPL', name: 'Apple Inc', exchange: 'NASDAQ' },
                    { symbol: 'AABA', name: 'Altaba Inc', exchange: 'NASDAQ' }
                ]
            })
        });
        
        rerender(<TickerSearch value="AA" onChange={onChange} />);
        
        await waitFor(() => {
            expect(screen.getByText('AAPL')).toBeInTheDocument();
            expect(screen.getByText('Apple Inc')).toBeInTheDocument();
            expect(screen.getByText('AABA')).toBeInTheDocument();
        });
    });

    it('debe mostrar indicador de carga mientras busca', async () => {
        const onChange = jest.fn();
        const { rerender } = render(<TickerSearch value="" onChange={onChange} />);
        
        // Mock que tarda en responder
        (global.fetch as jest.Mock).mockImplementationOnce(() => 
            new Promise(resolve => setTimeout(() => resolve({
                ok: true,
                json: async () => ({ results: [] })
            }), 100))
        );
        
        rerender(<TickerSearch value="AAPL" onChange={onChange} />);
        
        // Debe mostrar loading spinner
        await waitFor(() => {
            const loader = screen.queryByTitle(/loading/i);
            expect(loader).toBeInTheDocument();
        });
    });

    it('debe mostrar error cuando la API falla', async () => {
        const onChange = jest.fn();
        const { rerender } = render(<TickerSearch value="" onChange={onChange} />);
        
        // Mock de error
        (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));
        
        rerender(<TickerSearch value="AAPL" onChange={onChange} />);
        
        await waitFor(() => {
            const errorIcon = screen.queryByTitle(/error/i);
            expect(errorIcon).toBeInTheDocument();
        });
    });

    it('debe limpiar el input cuando se hace clic en X', () => {
        const onChange = jest.fn();
        const { rerender } = render(<TickerSearch value="" onChange={onChange} />);
        
        rerender(<TickerSearch value="AAPL" onChange={onChange} />);
        
        const clearButton = screen.getByRole('button');
        fireEvent.click(clearButton);
        
        expect(onChange).toHaveBeenCalledWith('');
    });

    it('debe llamar a onSelect cuando se selecciona un ticker', async () => {
        const onChange = jest.fn();
        const onSelect = jest.fn();
        const { rerender } = render(
            <TickerSearch value="" onChange={onChange} onSelect={onSelect} />
        );
        
        // Mock de respuesta
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                results: [
                    { symbol: 'AAPL', name: 'Apple Inc', exchange: 'NASDAQ' }
                ]
            })
        });
        
        rerender(<TickerSearch value="AA" onChange={onChange} onSelect={onSelect} />);
        
        await waitFor(() => {
            expect(screen.getByText('AAPL')).toBeInTheDocument();
        });
        
        // Click en el resultado
        const result = screen.getByText('AAPL');
        fireEvent.click(result);
        
        expect(onSelect).toHaveBeenCalledWith(
            expect.objectContaining({ symbol: 'AAPL' })
        );
    });

    it('debe soportar navegación con teclado (ArrowDown/Up/Enter)', async () => {
        const onChange = jest.fn();
        const onSelect = jest.fn();
        const { rerender } = render(
            <TickerSearch value="" onChange={onChange} onSelect={onSelect} />
        );
        
        // Mock de respuesta con múltiples resultados
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                results: [
                    { symbol: 'AAPL', name: 'Apple Inc', exchange: 'NASDAQ' },
                    { symbol: 'AABA', name: 'Altaba Inc', exchange: 'NASDAQ' }
                ]
            })
        });
        
        rerender(<TickerSearch value="AA" onChange={onChange} onSelect={onSelect} />);
        
        await waitFor(() => {
            expect(screen.getByText('AAPL')).toBeInTheDocument();
        });
        
        const input = screen.getByPlaceholderText('Ticker');
        
        // ArrowDown para seleccionar primer resultado
        fireEvent.keyDown(input, { key: 'ArrowDown' });
        
        // Enter para confirmar
        fireEvent.keyDown(input, { key: 'Enter' });
        
        expect(onSelect).toHaveBeenCalled();
    });

    it('debe cancelar requests anteriores cuando el usuario sigue escribiendo', async () => {
        const onChange = jest.fn();
        const { rerender } = render(<TickerSearch value="" onChange={onChange} />);
        
        // Mock múltiples requests
        const abortMock = jest.fn();
        const originalAbortController = global.AbortController;
        
        global.AbortController = jest.fn().mockImplementation(() => ({
            abort: abortMock,
            signal: {}
        })) as any;
        
        rerender(<TickerSearch value="A" onChange={onChange} />);
        await new Promise(resolve => setTimeout(resolve, 50));
        
        rerender(<TickerSearch value="AA" onChange={onChange} />);
        await new Promise(resolve => setTimeout(resolve, 50));
        
        rerender(<TickerSearch value="AAP" onChange={onChange} />);
        
        // Debe haber cancelado las requests anteriores
        expect(abortMock).toHaveBeenCalled();
        
        global.AbortController = originalAbortController;
    });
});

