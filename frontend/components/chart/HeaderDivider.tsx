/**
 * Vertical visual separator for the chart header. Centralised so we don't
 * scatter `<div className="w-px h-4 bg-muted"/>` literals across components.
 */
export function HeaderDivider({ height = 14 }: { height?: number }) {
    return (
        <span
            aria-hidden
            className="inline-block bg-[color:var(--color-border)]"
            style={{ width: 1, height }}
        />
    );
}
