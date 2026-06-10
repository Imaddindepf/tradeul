"""
BoundedTTLCache - cache in-process con TTL por entrada y limite de tamano (LRU).

Motivo: los dicts module-level usados como cache ({} + timestamp) no tenian
evicción: cada combinacion de query params quedaba retenida en el heap para
siempre. Con payloads de varios MB (heatmap/performance/financials) el proceso
crecia hasta el limite del cgroup y el kernel lo mataba (OOM cada pocas horas).

Esta clase garantiza un techo de memoria: maxsize entradas como maximo, con
expiracion real por entrada y desalojo LRU.
"""

import time
from collections import OrderedDict
from typing import Any, Optional


class BoundedTTLCache:
    """Cache LRU con TTL por entrada. No thread-safe; apto para asyncio."""

    def __init__(self, maxsize: int, ttl_seconds: float):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._data: "OrderedDict[Any, tuple[float, Any]]" = OrderedDict()

    def get(self, key: Any) -> Optional[Any]:
        """Devuelve el valor si existe y no ha expirado; si expiro, lo elimina."""
        item = self._data.get(key)
        if item is None:
            return None
        ts, value = item
        if (time.time() - ts) >= self.ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: Any, value: Any) -> None:
        now = time.time()
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = (now, value)

        # Desalojo LRU si superamos el limite
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

        # Poda oportunista de expirados (barato: solo mira los mas viejos)
        for k in list(self._data.keys())[:8]:
            ts, _ = self._data[k]
            if (now - ts) >= self.ttl:
                del self._data[k]
            else:
                break

    def pop(self, key: Any, default: Any = None) -> Any:
        item = self._data.pop(key, None)
        return item[1] if item is not None else default

    def keys(self):
        return list(self._data.keys())

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        return self.get(key) is not None
