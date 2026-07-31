#!/usr/bin/env python3
"""
Linter AST: prohíbe usar nombres decorados con @mcp.tool() como callables.

Desde fastmcp 2.7, @mcp.tool() (también .prompt/.resource) devuelve un objeto
FunctionTool en lugar de la función: cualquier llamada directa al nombre
decorado revienta en runtime con "TypeError: 'FunctionTool' object is not
callable". Ese patrón dejó events_get_events_by_ticker roto en producción
durante 5 meses sin que nada lo detectara (auditoría 2026-07-28).

Regla que impone este linter:
  - Un nombre decorado con *.tool()/*.prompt()/*.resource() NO puede
    referenciarse en modo Load en ningún sitio: ni llamarlo, ni pasarlo como
    callable, ni importarlo desde otro módulo, ni accederlo como atributo de
    módulo (`import servers.events as ev; ev.get_recent_events(...)`), ni
    resolverlo con getattr y un literal. La lógica compartida vive en helpers
    planos (p. ej. servers/events.py::_recent_events).
  - `from servers.X import *` está prohibido si X define tools (imposible de
    rastrear).
  - Supresión puntual (excepcional): comentario `# lint: allow-tool-ref`
    en la misma línea.

Limitación conocida: registros por alias (`t = mcp.tool; @t()...`) y getattr
con nombre variable no son detectables estáticamente.

Uso:  python scripts/lint_tool_calls.py [raíz]   (por defecto, el dir del repo)
Sale con código 1 si hay violaciones. Corre en el build del Dockerfile.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

DECORATOR_ATTRS = {"tool", "prompt", "resource"}
SUPPRESS_MARK = "# lint: allow-tool-ref"


def _decorator_matches(node: ast.expr) -> bool:
    """True si el decorador es *.tool / *.tool(...) (ídem prompt/resource)."""
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr in DECORATOR_ATTRS


def collect_decorated(tree: ast.Module) -> dict[str, int]:
    """Nombre -> línea de def, para toda función decorada como tool."""
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_decorator_matches(d) for d in node.decorator_list):
                found[node.name] = node.lineno
    return found


class _RefVisitor(ast.NodeVisitor):
    """Recoge toda referencia Load a un nombre decorado.

    Sin excepciones: también dentro del cuerpo de la propia tool (una llamada
    recursiva golpearía igualmente el FunctionTool ya rebindeado).
    """

    def __init__(self, decorated: dict[str, int]):
        self.decorated = decorated
        self.violations: list[tuple[int, str, str]] = []  # (línea, nombre, motivo)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in self.decorated:
            self.violations.append(
                (node.lineno, node.id,
                 "referencia a un nombre @mcp.tool() — es un FunctionTool, no una función")
            )


def check_file(path: Path, module_tools: dict[str, dict[str, int]]) -> list[str]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: error de sintaxis: {exc.msg}"]

    lines = src.splitlines()

    def suppressed(lineno: int) -> bool:
        return 0 < lineno <= len(lines) and SUPPRESS_MARK in lines[lineno - 1]

    problems: list[str] = []

    # 1) Referencias intra-módulo a tools del propio archivo
    decorated = collect_decorated(tree)
    if decorated:
        visitor = _RefVisitor(decorated)
        visitor.visit(tree)
        for lineno, name, why in visitor.violations:
            if not suppressed(lineno):
                problems.append(f"{path}:{lineno}: `{name}` — {why}")

    # 2) Imports de tools definidas en otros módulos del repo, star-imports
    #    y alias de módulo (para el paso 3)
    module_aliases: dict[str, str] = {}  # nombre local -> stem del módulo
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod_key = node.module.split(".")[-1]
            remote = module_tools.get(mod_key, {})
            for alias in node.names:
                if alias.name == "*" and remote and not suppressed(node.lineno):
                    problems.append(
                        f"{path}:{node.lineno}: `from {node.module} import *` — "
                        f"prohibido: {mod_key} define tools y el * no es rastreable"
                    )
                elif alias.name in remote and not suppressed(node.lineno):
                    problems.append(
                        f"{path}:{node.lineno}: import de la tool `{alias.name}` "
                        f"desde {node.module} — importa/extrae un helper plano, no la tool"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                stem = alias.name.split(".")[-1]
                if stem in module_tools:
                    # `import servers.events` → accesible como servers.events.X
                    # `import servers.events as ev` → accesible como ev.X
                    module_aliases[alias.asname or alias.name] = stem

    # 3) Acceso por atributo a tools de un módulo importado y getattr con literal
    all_tool_names = {t for tools in module_tools.values() for t in tools}

    def _dotted(node) -> str | None:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            base = _dotted(node.value)
            stem = module_aliases.get(base) if base else None
            if stem and node.attr in module_tools.get(stem, {}) and not suppressed(node.lineno):
                problems.append(
                    f"{path}:{node.lineno}: `{base}.{node.attr}` — acceso a una tool "
                    f"decorada de {stem} — usa/extrae un helper plano"
                )
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "getattr" and len(node.args) >= 2
              and isinstance(node.args[1], ast.Constant)
              and node.args[1].value in all_tool_names
              and not suppressed(node.lineno)):
            problems.append(
                f"{path}:{node.lineno}: getattr(..., \"{node.args[1].value}\") — "
                f"resuelve una tool decorada por nombre — usa un helper plano"
            )
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    targets = (sorted((root / "servers").glob("*.py"))
               + sorted((root / "clients").glob("*.py"))
               + [root / "main.py"])
    targets = [p for p in targets if p.exists()]

    # Mapa global módulo -> tools decoradas (para detectar imports cruzados)
    module_tools: dict[str, dict[str, int]] = {}
    for path in targets:
        try:
            module_tools[path.stem] = collect_decorated(
                ast.parse(path.read_text(encoding="utf-8"))
            )
        except SyntaxError:
            module_tools[path.stem] = {}

    problems: list[str] = []
    total_tools = sum(len(v) for v in module_tools.values())
    for path in targets:
        problems.extend(check_file(path, module_tools))

    print(f"lint_tool_calls: {len(targets)} archivos, {total_tools} tools decoradas")
    if problems:
        print(f"\n{len(problems)} VIOLACIONES (FunctionTool usado como callable):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("OK — ninguna tool decorada se usa como callable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
