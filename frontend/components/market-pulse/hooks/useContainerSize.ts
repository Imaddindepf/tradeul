import { useRef, useState, useEffect } from 'react';

interface ContainerSize {
  width: number;
  height: number;
}

export function useContainerSize(debounceMs = 400, threshold = 5) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<ContainerSize>({ width: 0, height: 0 });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastRef = useRef<ContainerSize>({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => {
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      if (
        Math.abs(w - lastRef.current.width) > threshold ||
        Math.abs(h - lastRef.current.height) > threshold
      ) {
        lastRef.current = { width: w, height: h };
        setSize({ width: w, height: h });
      }
    };

    update();

    const ro = new ResizeObserver(() => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(update, debounceMs);
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [debounceMs, threshold]);

  return { ref, size };
}
