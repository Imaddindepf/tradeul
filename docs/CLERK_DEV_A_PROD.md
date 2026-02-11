# Migración de Clerk: Desarrollo → Producción

Has pasado de la instancia de **desarrollo** de Clerk a **producción** (de pago). Las instancias son independientes: los usuarios y los `user_id` de dev **no existen** en producción. Esta guía explica cómo migrar usuarios y conservar los datos en tu base de datos.

---

## 1. Cambiar las variables de entorno a producción

En tu `.env` (o donde definas las variables) usa las claves **live** de la instancia de producción:

- `CLERK_PUBLISHABLE_KEY`: debe empezar por `pk_live_...` (no `pk_test_...`)
- `CLERK_SECRET_KEY`: debe empezar por `sk_live_...` (no `sk_test_...`)

Servicios que usan Clerk en este proyecto:

- **Frontend**: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (y opcionalmente publishable/secret vía env)
- **api_gateway**: `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` (desde `shared/config` o env)
- **websocket_server**: `CLERK_PUBLISHABLE_KEY`
- **websocket_chat**: `CLERK_PUBLISHABLE_KEY`
- **chat** (routers): `CLERK_SECRET_KEY`

Asegúrate de que en producción todos apunten a las claves **live**.

---

## 2. Migrar usuarios de Dev → Prod (y conservar datos en tu BD)

Tu backend guarda datos por `user_id` de Clerk en:

- `user_notes`, `user_preferences`, `user_filters` (scanner), `user_alert_strategies`, `user_screener_templates`, chat, etc.

Si creas usuarios nuevos en prod con el script de Clerk, recibirán **nuevos** `user_id` y los datos actuales en PostgreSQL quedarían “huérfanos”. Para evitarlo hay que usar **external_id** y **custom session claims**.

### 2.1 Exportar usuarios desde la instancia de desarrollo

1. Entra en el [Clerk Dashboard](https://dashboard.clerk.com).
2. Selecciona la instancia de **desarrollo** (no la de producción).
3. **Settings** (de la instancia) → **User Exports** → **Export all users**.
4. Descarga el CSV cuando esté listo.

Ese CSV contiene los usuarios con sus identificadores (email, etc.) y el `user_id` de dev que usas hoy en tu BD.

### 2.2 Script de migración oficial de Clerk

Clerk ofrece un script que lee un JSON/CSV y crea usuarios en la instancia que indiques (en tu caso, producción) usando la Backend API:

```bash
git clone https://github.com/clerk/migration-script.git
cd migration-script
bun install
```

Crea un `.env` en esa carpeta con la clave **de producción**:

```bash
CLERK_SECRET_KEY=sk_live_xxxxxxxx
```

- **Importante**: usa `sk_live_...` para que los usuarios se creen en la instancia de **producción**.

El script acepta el CSV exportado desde el Dashboard. Para migrar **desde otra instancia de Clerk** usa el transformer `clerk`:

```bash
bun migrate -y -t clerk -f /ruta/al/export-desarrollo.csv
```

(Adapta `-f` a la ruta real del CSV descargado.)

Requisitos del CSV/JSON: debe tener al menos `userId` y un identificador (por ejemplo `email`, o `phone`/`username` según tu caso). El formato del export del Dashboard suele ser compatible; si no, revisa [Schema Fields Reference](https://github.com/clerk/migration-script/blob/main/docs/schema-fields.md) y el validador en el repo.

### 2.3 Mantener el mismo `user_id` en tu app (external_id + JWT custom)

Para que la **misma** base de datos siga funcionando sin cambiar `user_id` en tus tablas:

1. **Al importar en producción**: cada usuario creado en prod debe tener en Clerk un **external_id** igual al `user_id` que tenía en **desarrollo** (el que está en tu PostgreSQL).  
   El script de migración, cuando el origen es Clerk (transformer `clerk`), puede mapear el `userId` del CSV al `external_id` del usuario en la instancia destino; revisa la doc del script y los [transformers](https://github.com/clerk/migration-script/blob/main/docs/creating-transformers.md) por si necesitas un mapeo explícito `userId` → `external_id`.

2. **En la instancia de producción** (Dashboard de Clerk):  
   - Ve a **Sessions** → **Customize session token** (o **Edit** en la sesión).  
   - En los **Claims** añade algo como:

   ```json
   {
     "userId": "{{user.external_id || user.id}}"
   }
   ```

   Así, los usuarios migrados (con `external_id` = antiguo user_id de dev) seguirán teniendo en el JWT el mismo `userId` que usas en tu BD, y los usuarios nuevos en prod tendrán `user.id` de Clerk.

Con eso, no hace falta cambiar `user_id` en PostgreSQL: el backend y los WebSockets seguirán recibiendo el mismo `userId` que ya tienes guardado.

### 2.4 Contraseñas y OAuth

- Las **contraseñas** hasheadas del export de Clerk se pueden migrar; el script y la API de Clerk lo soportan (incluyendo mejora a bcrypt si aplica).
- **OAuth** (Google, etc.) no se puede migrar tal cual; el usuario tendrá que volver a enlazar la cuenta en producción (Clerk usa [Account Linking](https://clerk.com/docs/guides/configure/auth-strategies/social-connections/account-linking)).

---

## 3. Resumen rápido

| Paso | Acción |
|------|--------|
| 1 | Poner en prod `pk_live_...` y `sk_live_...` en todos los servicios que usan Clerk. |
| 2 | Exportar usuarios desde el Dashboard de la instancia **desarrollo** (CSV). |
| 3 | Clonar y usar el [migration-script](https://github.com/clerk/migration-script) con `CLERK_SECRET_KEY=sk_live_...` y transformer `clerk` para crear esos usuarios en la instancia **producción**, configurando `external_id` = user_id de dev cuando sea posible. |
| 4 | En el Dashboard de **producción**, personalizar el session token con `"userId": "{{user.external_id || user.id}}"`. |
| 5 | Desplegar backend y frontend con las variables de producción; los usuarios migrados seguirán viendo sus datos (notas, preferencias, filtros, etc.) porque el JWT seguirá enviando el mismo `userId` que ya tienes en la BD. |

Si en lugar de migrar prefieres que los usuarios se registren de nuevo en producción, basta con cambiar a las claves `pk_live_`/`sk_live_` y desplegar; los datos antiguos en la BD quedarían asociados a user_ids de dev y no serían accesibles en prod (solo útiles para una migración manual o limpieza).
