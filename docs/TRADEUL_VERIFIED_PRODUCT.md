# Tradeul Verified — Verificación de traders sin confianza ciega

> **Documento de producto y arquitectura** · v1.0 · Julio 2026
> Audiencia: clientes, inversores e ingeniería.

---

## 1. Resumen ejecutivo

**Tradeul Verified** es un sistema de verificación pública de traders en el que **nadie tiene que confiar en Tradeul** — ni en el trader, ni en ningún tercero. Cada afirmación de rendimiento ("gané más de 100.000 € en 2025", "mi drawdown máximo fue inferior al 10%") está respaldada por pruebas criptográficas derivadas directamente de los datos del broker, registradas en un ledger público auditable e imposibles de falsificar o reescribir.

El trader elige cuánto revela: desde su PnL exacto hasta solo ratios o umbrales ("más de X"), todo verificable con la misma solidez matemática. La privacidad y la transparencia dejan de ser opuestos.

**La frase que define el producto:** *"No confíes en nosotros. No puedes — y ese es el punto."*

---

## 2. El problema

Las plataformas actuales de verificación de traders (Kinfo y similares) tienen tres fallos estructurales:

1. **Trusted party.** La plataforma es juez y parte: ella verifica, ella publica, ella puede equivocarse o mentir. El usuario no tiene forma de auditar nada.
2. **Verificación superficial.** Screenshots, imports manuales o conexiones API que el propio trader controla y puede manipular (cherry-picking de cuentas, edición retrospectiva, cuentas demo).
3. **Privacidad binaria.** O muestras todo o no muestras nada. Muchos traders excelentes no quieren exponer su capital, así que quedan fuera del sistema — y el ecosistema pierde su señal.

El resultado: los "verificados" de hoy no son verificables, y los mejores traders a menudo no participan.

---

## 3. El producto (qué ve el usuario)

### 3.1 Perfil verificado

Cada trader verificado tiene un perfil público en Tradeul con:

- **Insignias de verificación** con umbrales estandarizados: `Beneficio verificado: +10k / +50k / +100k / +500k / +1M` (por año natural y acumulado).
- **Métricas verificadas sin cifras absolutas**: retorno %, win rate, profit factor, drawdown máximo, Sharpe, percentil en la plataforma.
- **Sello temporal**: "verificando en tiempo real desde marzo 2026" — la fecha desde la que las operaciones se registran comprometidas *antes* de conocerse el resultado.
- **Botón "Verificar prueba"**: cualquier visitante (o auditor externo) puede comprobar la validez criptográfica de cada afirmación sin cuenta en Tradeul.

### 3.2 Niveles de revelación (elegidos por el trader)

| Nivel | Qué se muestra | Ejemplo |
|---|---|---|
| **Exacto** | PnL en dinero, verificado | "87.340 € en 2025 ✓" |
| **Umbral** | Insignia de bucket estándar | "+50k en 2025 ✓" |
| **Rango** | Intervalo | "Entre 50k y 250k ✓" |
| **Ratios** | Solo porcentajes y métricas de riesgo | "+42% anual, DD < 8% ✓" |
| **Percentil** | Posición relativa | "Top 3% de Tradeul ✓" |

Todos los niveles derivan del **mismo compromiso criptográfico**: el trader puede empezar en "ratios" y subir a "exacto" cuando quiera, al instante y sin re-verificación. Es matemáticamente imposible que los niveles se contradigan entre sí.

### 3.3 Revelación monetizable

El trader puede reservar los niveles más detallados (curva de equity real, PnL exacto, historial completo) para sus suscriptores o clientes de copy-trading. Tradeul gestiona el paywall y cobra comisión. La transparencia se convierte en el activo del trader, no en su coste.

---

## 4. Principios de diseño

1. **Criptografía antes que consenso.** El consenso humano es caro, lento y atacable (sybils, cuentas compradas). Solo se usa donde la matemática no llega.
2. **Tradeul opera, no decide.** Tradeul provee infraestructura; no puede alterar el historial, inflar métricas ni censurar sin que sea públicamente detectable.
3. **Nada retroactivo.** Las métricas verificadas solo cuentan desde el momento del compromiso. El pasado no se verifica; se verifica el presente hacia adelante.
4. **Privacidad por defecto, transparencia por elección.** El sistema nunca fuerza a revelar más de lo que el trader decide.
5. **Verificable por terceros.** Toda prueba es comprobable fuera de Tradeul, con herramientas open source.

---

## 5. Arquitectura: la pirámide de verificación

El sistema se organiza en tres capas, de la más fuerte (base) a la más débil (vértice). Cada capa solo maneja lo que la inferior no puede resolver.

```
        ┌─────────────────────┐
        │   CAPA 3: SOCIAL    │  Disputas residuales (whitelist de
        │   (panel con stake) │  brokers, casos ambiguos)
        ├─────────────────────┤
        │  CAPA 2: ECONÓMICA  │  Vigilancia con incentivos
        │  (optimista +       │  (desafíos, fraud proofs, slashing)
        │   fraud proofs)     │
        ├─────────────────────┤
        │ CAPA 1: CRIPTOGRÁFICA │  Veracidad de los datos
        │ (zkTLS + ZK proofs  │  (el broker es la fuente,
        │  + commit-reveal)   │   nadie es trusted party)
        └─────────────────────┘
```

### 5.1 Capa 1 — Criptográfica (veracidad de datos)

**El problema del oráculo.** La pregunta fundamental es: ¿cómo probar que los trades declarados son los que realmente se ejecutaron en el broker? Respuesta: **zkTLS**.

**zkTLS (TLSNotary / Reclaim Protocol / zkPass / Opacity).** Permite al trader generar una prueba criptográfica del contenido de su sesión HTTPS con el broker — "el servidor de Interactive Brokers respondió este historial de trades a este usuario autenticado" — sin revelar sus credenciales y sin que Tradeul vea ni intermedie los datos. Cualquiera puede verificar la prueba.

**Compromisos de Pedersen.** El PnL real (y cada métrica base) queda registrado en el ledger como un compromiso criptográfico: una "caja fuerte sellada" con el número verdadero dentro, que ni Tradeul puede abrir. Propiedades:

- *Ocultación (hiding):* el compromiso no revela nada del valor.
- *Vinculación (binding):* el trader no puede cambiar el valor después.
- *Homomorfismo aditivo:* se pueden agregar compromisos (PnL mensual → anual) sin abrirlos.

**Pruebas ZK sobre el compromiso.** Sobre esa caja sellada, el trader genera:

- **Range proofs (Bulletproofs):** "el valor comprometido es > X" o "está en [A, B]" sin abrirlo. Baratas de generar (~ms) y de verificar. Es el mecanismo detrás de las insignias "+50k".
- **zk-SNARKs de predicados compuestos:** "retorno anual > 40% Y drawdown < 15%", "win rate en percentil 90", calculados dentro de un circuito que toma como entrada privada los datos atestados por zkTLS.
- **Apertura selectiva:** para el nivel "exacto", el trader simplemente abre el compromiso y cualquiera comprueba que coincide.

**Commit-reveal en tiempo real.** El trader (vía la integración con su broker) publica el hash de cada operación *antes* de conocerse su resultado, o snapshots periódicos firmados de la cartera. Esto elimina el fraude número uno del sector: seleccionar retrospectivamente qué enseñar. Sin commit previo, la operación no computa en las métricas verificadas.

### 5.2 Capa 2 — Económica (vigilancia con incentivos)

Modelo de **verificación optimista**, análogo al de los optimistic rollups:

1. Las afirmaciones con prueba válida se aceptan por defecto.
2. El trader deposita un **stake** al verificarse.
3. Durante una **ventana de disputa** (p. ej. 7 días por afirmación), *cualquiera* puede presentar un **desafío** aportando una fraud proof (p. ej. evidencia de que la prueba zkTLS apunta a un endpoint suplantado, o de cuentas ocultas del mismo titular).
4. Si el desafío prospera, el trader pierde el stake (**slashing**) y la insignia; el desafiante cobra una parte como recompensa.

Esto convierte a la comunidad en policía **con incentivos correctos y sin votaciones masivas**: no importa cuántas cuentas compradas tengas, porque no se vota — se aportan pruebas, y aportar pruebas falsas también cuesta stake.

### 5.3 Capa 3 — Social (lo residual)

Queda un conjunto pequeño de decisiones que la criptografía no puede resolver:

- **Whitelist de brokers:** zkTLS prueba lo que dijo el servidor, no que el servidor diga la verdad. Un "broker" fantasma controlado por el tramposo pasaría la capa 1. La lista de brokers admitidos (regulados, con entidad verificable) la mantiene un **panel con stake y reputación en juego**, no Tradeul unilateralmente.
- **Disputas ambiguas** que las fraud proofs no zanjan mecánicamente.

Al ser pocos casos y con coste económico real por voto, el spam y las cuentas compradas son económicamente irracionales aquí.

---

## 6. El ledger público

**No hace falta una blockchain propia.** El diseño es un **transparency log** al estilo Certificate Transparency:

- **Árbol de Merkle append-only** operado por Tradeul: cada compromiso, prueba, insignia y disputa es una hoja.
- **Anclaje periódico** (p. ej. cada hora) de la raíz del árbol en una L2 pública barata (coste: céntimos). Una vez anclada, reescribir el historial es públicamente detectable.
- **Pruebas de inclusión y consistencia:** cualquier cliente puede verificar que una entrada está en el log y que el log nunca se ha reescrito.
- **Auditores externos (monitors):** cualquiera puede correr un monitor open source que replica y vigila el log — igual que los monitors de CT vigilan a las CAs.
- **Formato de atestaciones:** compatible con EAS (Ethereum Attestation Service) para que las insignias sean portables y componibles fuera de Tradeul.

Este diseño da la garantía clave del producto — **Tradeul no puede mentir sin ser cazado** — sin los costes, la latencia ni la fricción regulatoria de una cadena propia.

---

## 7. Flujos principales

### 7.1 Onboarding del trader

1. El trader declara **todas** sus cuentas de brokers admitidos (compromiso de cuentas). Añadir cuentas después es posible; las métricas de cada cuenta computan solo desde su fecha de alta. *Esta regla mata el cherry-picking de cuentas.*
2. Ejecuta el cliente zkTLS (extensión / app) y prueba la titularidad y el estado inicial de cada cuenta.
3. Deposita el stake y acepta el protocolo de disputas.
4. Se publica en el ledger: compromiso de cuentas + snapshot inicial + fecha de inicio.

### 7.2 Operativa continua

1. Snapshots periódicos (p. ej. diarios) de cada cuenta vía zkTLS → compromisos al ledger.
2. Opcional (nivel "tiempo real"): hash de cada orden al ejecutarse.
3. El agregador local del trader (open source, auditable) calcula métricas y genera las pruebas ZK que el trader decida publicar.

### 7.3 Emisión de una insignia

1. El trader elige la afirmación (p. ej. "+100k en 2025") desde los buckets estándar.
2. Su cliente genera la range proof sobre los compromisos del período.
3. La prueba se publica en el ledger, se abre la ventana de disputa y, al cerrarse sin desafíos válidos, la insignia queda activa en el perfil.

### 7.4 Disputa

1. Desafiante deposita bond + presenta evidencia.
2. Resolución mecánica si la fraud proof es verificable por circuito; si no, escalado al panel de la capa 3.
3. Resultado y razonamiento quedan en el ledger. Slashing al que pierda (trader tramposo o desafiante spammer).

---

## 8. Modelo de amenazas

| Ataque | Descripción | Mitigación |
|---|---|---|
| **Cherry-picking de cuentas** | Abrir 10 cuentas, operar al azar, verificar solo la ganadora | Compromiso de cuentas en onboarding; nada retroactivo; métricas solo desde fecha de commit |
| **Cherry-picking temporal** | Verificar solo los períodos buenos | Snapshots periódicos obligatorios; huecos en la serie invalidan las insignias del período |
| **Broker falso/cómplice** | Servidor controlado por el tramposo que "atesta" datos inventados | Whitelist de brokers regulados (capa 3) |
| **Cuentas demo/paper** | Verificar una cuenta de práctica | El circuito zkTLS extrae y prueba el tipo de cuenta del endpoint del broker |
| **Búsqueda binaria del PnL** | Consultar "¿> X?" con X libre hasta extraer el valor exacto | No hay oráculo interactivo: el trader publica, nadie consulta; umbrales solo en buckets estándar |
| **Sybils en verificación** | Cuentas compradas para "aprobar" a un tramposo | No se vota la veracidad: capa 1 es matemática, capa 2 exige pruebas con stake |
| **Spam de disputas** | Desafíos masivos para acosar a un trader | Bond del desafiante con slashing si el desafío es frívolo |
| **Rollback del ledger** | Tradeul reescribe el historial | Raíz de Merkle anclada en L2 pública; monitors externos detectan inconsistencia |
| **Contradicción entre niveles** | Decir "+100k" y luego revelar 50k | Imposible: todos los niveles derivan del mismo compromiso vinculante |

**Coste operativo real a presupuestar:** los conectores zkTLS dependen de los endpoints/HTML de cada broker y requieren mantenimiento continuo. Es el principal coste recurrente de ingeniería del producto.

---

## 9. Modelo de negocio

1. **Suscripción del trader verificado** — cuota por mantener el perfil verificado activo (cubre infraestructura de pruebas y snapshots).
2. **Comisión sobre revelación monetizada** — el trader cobra a sus suscriptores por el detalle (equity curve real, PnL exacto); Tradeul se lleva un %.
3. **Señal para el resto de la plataforma** — los perfiles verificados alimentan rankings, copy-trading y descubrimiento dentro de Tradeul, aumentando retención y conversión del producto principal.
4. **API de verificación B2B** — fondos, prop firms y medios pueden verificar insignias programáticamente ("proof-of-track-record as a service").

---

## 10. Comparativa

| | Kinfo y similares | Tradeul Verified |
|---|---|---|
| Quién verifica | La plataforma (trusted party) | Criptografía + incentivos económicos |
| Fuente de datos | Import controlado por el trader | Sesión atestada con el broker (zkTLS) |
| Cherry-picking | Posible | Bloqueado por commit-reveal y compromiso de cuentas |
| Privacidad | Binaria (todo o nada) | Espectro: exacto / umbral / rango / ratios / percentil |
| Auditable por terceros | No | Sí, con herramientas open source |
| La plataforma puede mentir | Sí (nada lo impediría) | No sin ser detectada (transparency log anclado) |

---

## 11. Stack propuesto y decisiones abiertas

**Propuesta base:**

- **zkTLS:** evaluar Reclaim Protocol (mejor DX, conectores mantenidos) vs TLSNotary (más maduro criptográficamente, self-host) vs zkPass/Opacity. Criterios: cobertura de brokers objetivo, modelo de atestadores, coste por prueba, licencia.
- **Compromisos y range proofs:** Pedersen + Bulletproofs (librerías maduras: `dalek`/`bulletproofs` en Rust).
- **Circuitos de predicados:** Circom/Groth16 o Halo2 según necesidad de trusted setup y tamaño de circuito.
- **Ledger:** transparency log propio (estilo Trillian/CT) + anclaje en una L2 (Base u Optimism) + atestaciones formato EAS.
- **Cliente del trader:** extensión de navegador o app de escritorio open source que genera las pruebas en local (los datos crudos nunca salen del dispositivo del trader).

**Decisiones abiertas para la fase de diseño técnico:**

1. Proveedor zkTLS y su modelo de atestadores (¿red descentralizada o atestador dedicado auditable?).
2. Granularidad del commit-reveal en el MVP (¿snapshot diario o por operación?).
3. Denominación del stake y las recompensas (fiat custodiado vs token — implicaciones regulatorias muy distintas).
4. Lista inicial de brokers (priorizar los 3–5 con mejor superficie de datos: IBKR, etc.).
5. Jurisdicción y encaje regulatorio de las insignias de rendimiento (marketing financiero).

---

## 12. Roadmap por fases

**Fase 1 — MVP "verificación fuerte, disputa manual" (3–4 meses)**
- 2 brokers soportados vía zkTLS; snapshots diarios.
- Compromisos + range proofs; insignias de umbral estándar y nivel "ratios".
- Transparency log con anclaje en L2; verificador público web.
- Disputas resueltas por panel interno con proceso publicado (la capa 2 completa llega en Fase 2).

**Fase 2 — Verificación optimista (2–3 meses)**
- Stake, desafíos, fraud proofs mecánicas y slashing.
- Nivel "exacto" (apertura de compromiso) y revelación monetizable con paywall.
- Monitors externos open source del ledger.

**Fase 3 — Escala y ecosistema**
- Más brokers; commit por operación en tiempo real.
- Panel social descentralizado para la whitelist de brokers.
- API B2B de verificación; atestaciones EAS portables.

---

## 13. KPIs

- Traders verificados activos y ratio de retención de la verificación.
- % de insignias que superan la ventana de disputa sin desafíos.
- Fraudes detectados por el sistema económico (salud del mecanismo, no vanity metric).
- Verificaciones de pruebas realizadas por terceros (adopción de la auditabilidad).
- Ingresos por revelación monetizada y conversión a copy-trading.

---

## 14. Glosario (para el pitch a no técnicos)

- **zkTLS:** técnica que permite probar lo que un sitio web te mostró (tu historial en el broker) sin revelar tu contraseña y sin que nadie intermedie tus datos.
- **Compromiso criptográfico:** una caja fuerte sellada con un número dentro. No se puede ver el número (privacidad) ni cambiarlo después (compromiso).
- **Prueba de rango:** demostrar que el número de la caja es "mayor que X" sin abrir la caja.
- **Commit-reveal:** apuntar el resultado en un sobre cerrado *antes* de que ocurra, para que nadie pueda elegir después qué enseñar.
- **Transparency log:** un registro público al que solo se puede añadir, nunca borrar ni editar, y que cualquiera puede vigilar.
- **Verificación optimista:** se acepta lo que tiene prueba válida, pero cualquiera puede desafiarlo con evidencia y hay dinero en juego por mentir — en ambas direcciones.
- **Slashing:** perder el depósito por hacer trampa (o por acusar en falso).

---

*Preparado para el pitch de Tradeul Verified. Este documento es la referencia de producto; el diseño técnico detallado (esquemas de circuitos, formato del log, protocolo de disputa) se derivará de las decisiones abiertas de la sección 11.*
