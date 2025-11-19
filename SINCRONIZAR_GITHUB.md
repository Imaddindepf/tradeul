# 🔄 Guía para Sincronizar con GitHub sin Perder Cambios Locales

## 📋 Estado Actual

✅ **Archivos restaurados**: Se restauraron ~35 archivos vacíos con stubs mínimos válidos  
✅ **Nuevas tablas V2**: Implementación completa con:
   - `CategoryTableV2.tsx` - Nueva arquitectura con TanStack Table + Virtual + Zustand + RxJS
   - `useRxWebSocket.ts` - WebSocket Singleton
   - `useTickersStore.ts` - Zustand store global
   - `VirtualizedDataTable.tsx` - Componente de tabla virtualizada

## 🚀 Pasos para Sincronizar

### Opción 1: Si NO tienes Git inicializado

```bash
# 1. Inicializar repositorio
cd /Users/imaddinamsif/Desktop/Tradeul-Amsif
git init

# 2. Agregar remote de GitHub
git remote add origin <TU-REPO-URL-AQUI>

# 3. Agregar todos los archivos
git add .

# 4. Primer commit
git commit -m "feat: Restore empty files and add V2 tables architecture

- Restored 35+ empty files with minimal valid stubs
- Added CategoryTableV2 with TanStack Table + Virtual + Zustand + RxJS
- Implemented WebSocket Singleton pattern
- Added Zustand global state management
- Added VirtualizedDataTable component"

# 5. Push inicial
git branch -M main
git push -u origin main
```

### Opción 2: Si YA tienes Git inicializado pero quieres traer cambios de GitHub

```bash
cd /Users/imaddinamsif/Desktop/Tradeul-Amsif

# 1. Ver estado actual
git status

# 2. Agregar cambios locales (incluyendo archivos restaurados)
git add .

# 3. Commit de cambios locales
git commit -m "feat: Restore empty files and add V2 tables architecture"

# 4. Traer cambios de GitHub
git fetch origin

# 5. Ver diferencias antes de mergear
git log HEAD..origin/main --oneline

# 6. Mergear cambios de GitHub (permitir historias no relacionadas)
git merge origin/main --allow-unrelated-histories

# 7. Si hay conflictos, resolverlos manualmente
# Git te mostrará los archivos en conflicto
# Edita los archivos marcados con <<<<<<< HEAD

# 8. Después de resolver conflictos:
git add .
git commit -m "merge: Merge GitHub changes with local V2 tables"

# 9. Push a GitHub
git push origin main
```

### Opción 3: Usar Stash (Recomendado si hay muchos cambios)

```bash
cd /Users/imaddinamsif/Desktop/Tradeul-Amsif

# 1. Guardar cambios locales temporalmente
git stash push -m "V2 tables and restored files"

# 2. Traer cambios de GitHub
git fetch origin
git pull origin main

# 3. Recuperar cambios locales
git stash pop

# 4. Resolver conflictos si los hay
# Edita archivos con conflictos

# 5. Agregar y commitear
git add .
git commit -m "feat: Merge V2 tables with GitHub changes"

# 6. Push
git push origin main
```

## 🛡️ Archivos Importantes a Proteger

Estos archivos contienen la nueva arquitectura V2 y NO deben sobrescribirse:

```
✅ frontend/components/scanner/CategoryTableV2.tsx
✅ frontend/hooks/useRxWebSocket.ts
✅ frontend/stores/useTickersStore.ts
✅ frontend/components/table/VirtualizedDataTable.tsx
✅ frontend/app/(dashboard)/scanner/page.tsx (usa CategoryTableV2)
```

## 🔍 Verificar Cambios Antes de Mergear

```bash
# Ver qué archivos cambiaron localmente
git diff --name-only

# Ver diferencias específicas
git diff frontend/components/scanner/CategoryTableV2.tsx

# Ver qué archivos están en GitHub pero no localmente
git diff --name-only origin/main

# Ver commits que están en GitHub pero no localmente
git log HEAD..origin/main --oneline
```

## ⚠️ Si Hay Conflictos

### Archivos en Conflicto Común:

1. **`package.json`**: 
   - Mantén ambas dependencias
   - Asegúrate de tener `@tanstack/react-virtual` y `rxjs`

2. **`tsconfig.json`**:
   - Usa la versión más completa
   - Asegúrate de tener `"paths": { "@/*": ["./*"] }`

3. **Archivos de layout**:
   - Si GitHub tiene una versión más completa, úsala
   - Si local tiene cambios importantes, mantén los locales

### Resolver Conflictos:

```bash
# Ver archivos en conflicto
git status

# Abrir archivo en conflicto
# Busca marcadores:
# <<<<<<< HEAD (tus cambios)
# ======= (separador)
# >>>>>>> origin/main (cambios de GitHub)

# Edita manualmente y elimina los marcadores
# Guarda el archivo

# Marcar como resuelto
git add <archivo-resuelto>

# Continuar merge
git commit
```

## 📦 Después de Sincronizar

```bash
# 1. Verificar que todo compile
cd frontend
npm run build

# 2. Si hay errores, corregirlos
npm run lint

# 3. Probar localmente
npm run dev

# 4. Verificar que las tablas V2 funcionen
# Abre http://localhost:3000/scanner
```

## 🎯 Checklist Final

- [ ] Archivos vacíos restaurados
- [ ] Cambios locales commiteados
- [ ] Cambios de GitHub traídos
- [ ] Conflictos resueltos
- [ ] Build exitoso (`npm run build`)
- [ ] Tablas V2 funcionando
- [ ] Push a GitHub completado

## 🆘 Si Algo Sale Mal

### Deshacer último commit:
```bash
git reset --soft HEAD~1
```

### Deshacer merge:
```bash
git merge --abort
```

### Volver a estado anterior:
```bash
git reset --hard HEAD
# ⚠️ CUIDADO: Esto elimina cambios no commiteados
```

### Ver historial:
```bash
git log --oneline --graph --all
```

## 📞 Comandos Útiles

```bash
# Ver estado
git status

# Ver diferencias
git diff

# Ver ramas
git branch -a

# Ver remotes
git remote -v

# Ver último commit
git log -1

# Ver archivos modificados
git ls-files -m
```

---

**💡 Tip**: Si tienes dudas sobre qué versión mantener de un archivo en conflicto, compara ambas versiones y elige la más completa o combina ambas si es necesario.

