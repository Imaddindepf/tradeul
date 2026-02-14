# Academy: Títulos de clases y asignación a módulos

## 1. Estructura de contenido

```
Curso (ej. "Anatomía de un Trader")  ← vinculado a chat_group
  └── Módulo 1 (ej. "Psicología del trading")
  │     ├── Clase 1.1 - Introducción
  │     ├── Clase 1.2 - Miedo y codicia
  │     └── ...
  └── Módulo 2 (ej. "Análisis técnico")
        ├── Clase 2.1 - Soportes y resistencias
        └── ...
```

---

## 2. Título de cada clase

### De dónde sale el título por defecto

Cuando Zoom envía el webhook `recording.completed`, el payload incluye:

```json
{
  "payload": {
    "object": {
      "id": 123456789,
      "uuid": "...",
      "topic": "Clase 3 - Soportes y resistencias",
      "start_time": "2025-02-10T18:00:00Z",
      "recording_files": [ ... ]
    }
  }
}
```

- **Campo a usar:** `payload.object.topic` → es el **título de la reunión de Zoom** (el que pones al crear/editar la reunión).
- **Flujo:** Al crear la lección en tu DB, guardas `title = topic` (o un fallback si viene vacío, ej. `"Clase sin título - 10/02/2025"`).

### Cómo tener títulos útiles desde Zoom

- Si usas **una reunión recurrente** con el mismo título genérico (ej. "Master Trading"), el título será siempre el mismo. Opciones:
  1. **Editar en tu app:** en el panel de administración del curso, cada lección tiene un campo "Título" editable.
  2. **Cambiar el título en Zoom** antes de cada clase (en la reunión programada, editas "título/topic").
  3. **Convención en el topic:** ej. `Módulo 2 - Clase 5 - Soportes` y luego puedes parsear o simplemente usar ese string como título.

Recomendación: usar **topic de Zoom como título por defecto** y permitir **edición en la app** siempre.

---

## 3. Módulos: poner cada clase en el módulo correcto

### Opción A – Asignación manual (recomendada al inicio)

1. Creas en tu app los **módulos** del curso (ej. Módulo 1, 2, 3... con nombre y orden).
2. Cuando llega una grabación nueva, la lección se crea **sin módulo** (`module_id = NULL`) o en un módulo tipo **"Sin asignar"**.
3. En un **panel de administración** (solo owner/admin del grupo):
   - Ves la lista de lecciones (con título, fecha, duración).
   - Cada lección tiene un selector "Módulo" (dropdown).
   - Asignas "Clase 3 - Soportes..." → Módulo 2, y opcionalmente editas el título.

Ventaja: control total. Desventaja: un paso manual por cada clase.

### Opción B – Asignación automática por reunión de Zoom

Si usas **varias reuniones de Zoom** (una por módulo o por bloque de clases):

- Reunión A (meeting_id 111) → solo clases del Módulo 1  
- Reunión B (meeting_id 222) → solo clases del Módulo 2  

En el **curso** guardas un mapa:

```json
{
  "zoom_meeting_id_to_module_id": {
    "111": "uuid-módulo-1",
    "222": "uuid-módulo-2"
  }
}
```

Cuando llega el webhook:

1. Lees `payload.object.id` (Zoom meeting id).
2. Buscas en ese mapa → obtienes `module_id`.
3. Creas la lección ya con `module_id` asignado.

Así **cada clase queda en el módulo correcto** sin tocar nada en la app.

### Opción C – Convención en el título (topic)

Si en Zoom siempre pones en el topic algo como `Módulo 2 - Clase 5 - Soportes`:

- Puedes parsear con una regex (ej. `Módulo (\d+)`) y tener un mapping numérico a tus módulos (orden), o
- Simplemente usar el topic como título y seguir asignando módulo a mano (Opción A).

Recomendación: combinar **B** (si tienes un meeting_id por módulo) con **A** (editar título/módulo cuando haga falta).

---

## 4. Schema de base de datos propuesto

```sql
-- Cursos (vinculados a un grupo de chat)
CREATE TABLE academy_courses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    group_id UUID NOT NULL REFERENCES chat_groups(id),
    name TEXT NOT NULL,
    description TEXT,
    thumbnail_url TEXT,
    -- Opcional: mapping meeting_id Zoom → module_id para asignación automática
    zoom_meeting_mapping JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Módulos (bloques del curso)
CREATE TABLE academy_modules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    course_id UUID NOT NULL REFERENCES academy_courses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Lecciones (cada clase = una grabación)
CREATE TABLE academy_lessons (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    course_id UUID NOT NULL REFERENCES academy_courses(id) ON DELETE CASCADE,
    module_id UUID REFERENCES academy_modules(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    mux_asset_id TEXT,
    mux_playback_id TEXT,
    duration_seconds INTEGER,
    thumbnail_url TEXT,
    zoom_meeting_id TEXT,
    zoom_recording_id TEXT,
    zoom_recording_start TIMESTAMPTZ,
    sort_order INTEGER DEFAULT 0,
    status TEXT DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Progreso por alumno (opcional)
CREATE TABLE academy_progress (
    user_id TEXT NOT NULL,
    lesson_id UUID NOT NULL REFERENCES academy_lessons(id) ON DELETE CASCADE,
    watched_seconds INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE,
    last_position_seconds INTEGER DEFAULT 0,
    last_watched_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, lesson_id)
);

CREATE INDEX idx_academy_lessons_course ON academy_lessons(course_id);
CREATE INDEX idx_academy_lessons_module ON academy_lessons(module_id);
CREATE INDEX idx_academy_modules_course ON academy_modules(course_id);
```

- **Título:** se guarda en `academy_lessons.title` (por defecto = Zoom `topic`, editable luego).
- **Módulo:** `academy_lessons.module_id`; si no asignas, queda `NULL` o apuntando a un módulo "Sin asignar".

---

## 5. Flujo resumido

| Paso | Título | Módulo |
|------|--------|--------|
| 1. Llega webhook Zoom | `title = payload.object.topic` (o fallback por fecha) | `module_id = zoom_meeting_mapping[meeting_id]` si existe, si no `NULL` |
| 2. Subes a Mux, creas lección | Se guarda en `academy_lessons.title` | Se guarda en `academy_lessons.module_id` |
| 3. Admin en la app | Puede editar título en "Editar lección" | Puede cambiar módulo en dropdown "Módulo" |
| 4. Alumno ve el curso | Ve módulos → dentro de cada módulo, lista de lecciones con título | Cada clase aparece bajo su módulo |

---

## 6. API sugerida (resumen)

- **Cursos**
  - `GET /api/academy/courses` – listar cursos del usuario (por grupos donde es miembro).
  - `POST /api/academy/courses` – crear curso (vincular a `group_id`).
  - `PUT /api/academy/courses/:id` – editar (nombre, descripción, `zoom_meeting_mapping`).
- **Módulos**
  - `GET /api/academy/courses/:id/modules` – listar módulos del curso (ordenados por `sort_order`).
  - `POST /api/academy/courses/:id/modules` – crear módulo (nombre, `sort_order`).
  - `PUT /api/academy/modules/:id` – editar módulo.
- **Lecciones**
  - `GET /api/academy/courses/:id/lessons` – listar lecciones (filtro opcional por `module_id`); cada una con título, módulo, duración, estado.
  - `GET /api/academy/lessons/:id` – detalle + signed URL para ver (solo si miembro del grupo).
  - `PUT /api/academy/lessons/:id` – **editar título, descripción, module_id, sort_order** (solo owner/admin del grupo).
- **Webhook Zoom** (interno): crea lección con `title = topic`, `module_id` por mapping o `NULL`.

Con esto tienes claro: **de dónde sale el título** (Zoom topic + editable en app) y **cómo poner cada clase en el módulo correcto** (manual, automático por meeting_id, o híbrido).
