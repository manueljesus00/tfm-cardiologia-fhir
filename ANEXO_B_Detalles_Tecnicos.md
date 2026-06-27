# ANEXO B — Detalles Técnicos Adicionales

---

## B.1 Especificación de la API REST

La API REST se implementa con **FastAPI 0.111** sobre un servidor ASGI **Uvicorn**.
La documentación interactiva (Swagger UI) se genera automáticamente en `/docs`.

### B.1.1 Esquema de Endpoints

#### `GET /health`

Comprueba que el servidor y el servidor MCP SNOMED están operativos.

**Respuesta 200:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

#### `GET /modelos`

Devuelve el catálogo de modelos LLM disponibles para el procesamiento de informes.

**Respuesta 200:**
```json
[
  {
    "id":          "gemini-2.5-flash",
    "name":        "Gemini 2.5 Flash",
    "provider":    "google",
    "type":        "cloud",
    "description": "Modelo principal del TFM..."
  },
  {
    "id":          "groq/llama-3.1-8b-instant",
    "name":        "Llama 3.1 8B Instant",
    "provider":    "groq",
    "type":        "cloud",
    "description": "..."
  },
  {
    "id": "ollama/phi4-mini",
    "name": "Phi-4 Mini",
    "provider": "microsoft",
    "type": "local",
    "description": "..."
  }
]
```

Modelos disponibles y sus proveedores:

| ID de Modelo | Proveedor | Tipo | Requiere clave |
|---|---|---|---|
| `gemini-2.5-flash` | Google DeepMind | Cloud | `GOOGLE_API_KEY` |
| `groq/llama-3.1-8b-instant` | Meta / Groq | Cloud | `GROQ_API_KEY` |
| `groq/llama-3.3-70b-versatile` | Meta / Groq | Cloud | `GROQ_API_KEY` |
| `ollama/phi4-mini` | Microsoft | Local | — |
| `ollama/llama3.2:3b` | Meta | Local | — |

---

#### `POST /procesar`

Sube un informe clínico (`.txt` o `.pdf`) e inicia su procesamiento asíncrono.

**Request** — `multipart/form-data`:

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | `UploadFile` | Sí | Informe clínico en texto plano o PDF |
| `modelo` | `string` | No | ID del modelo (por defecto: `gemini-2.5-flash`) |

**Respuesta 202:**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "estado": "encolado",
  "mensaje": "Informe recibido. Consulta /resultado/{job_id} para el resultado."
}
```

El informe se almacena en un directorio temporal y se procesa en un hilo de
fondo (`BackgroundTasks`). El `job_id` es un UUID v4 generado en el momento
de la recepción.

---

#### `GET /resultado/{job_id}`

Consulta el estado y el resultado completo de un job de procesamiento.

**Estados posibles del campo `estado`:**

| Estado | Significado |
|---|---|
| `encolado` | El job fue aceptado pero aún no ha comenzado |
| `procesando` | La Fase 1 o la Fase 2 están en ejecución |
| `completado` | Pipeline completo; el campo `resultado` contiene el FHIR Bundle |
| `error` | Fallo irrecuperable; el campo `error` describe la causa |

**Respuesta 200 — job completado:**
```json
{
  "job_id": "3fa85f64-...",
  "estado": "completado",
  "archivo": "informe_cardio.pdf",
  "confidence_level": "high",
  "snomed_id": "53741008",
  "diagnostico": "Infarto agudo de miocardio",
  "cie10": {
    "1": {
      "map_group": 1,
      "map_priority": 1,
      "map_rule": "TRUE",
      "map_target": "I21.9",
      "cumple_regla": true,
      "razonamiento": "IAM sin especificar localización documentada",
      "informacion_faltante": null
    }
  },
  "fhir_bundle": { "...": "Bundle FHIR R4 completo" },
  "telemetria": {
    "modelo": "Gemini 2.5 Flash",
    "provider": "google",
    "tokens_fase1": 1842,
    "tokens_fase2": 634,
    "tokens_total": 2476,
    "tiempo_fase1_s": 2.8,
    "tiempo_fase2_s": 1.3,
    "tiempo_total_s": 4.1,
    "coste_eur": 0.000312
  }
}
```

---

#### `GET /benchmarks`

Devuelve las métricas históricas del benchmark multi-modelo. Lee el fichero
`data/benchmark_multi_report.csv` si existe; en caso contrario devuelve el
registro en memoria de la sesión actual.

**Respuesta 200:**
```json
[
  {
    "modelo":           "Gemini 2.5 Flash",
    "provider":         "google",
    "archivo":          "informe_01.txt",
    "latencia_total_s": 3.12,
    "tokens_totales":   2476,
    "coste_eur":        0.000312,
    "confidence":       "high",
    "exito":            true
  }
]
```

---

## B.2 Esquema de Base de Datos PostgreSQL

La base de datos `snomed_irbd` (PostgreSQL 15) aloja tanto la terminología
SNOMED CT española (esquema de solo lectura, restaurado del volcado oficial
de la IRBD) como el esquema clínico del TFM (escritura).

### B.2.1 Tablas del Esquema Clínico

#### `pacientes`

Almacena la identidad de cada paciente con soporte para resolución de entidad
mediante cinco tipos de identificador español.

```
pacientes
├── id               UUID  PK  (gen_random_uuid())
├── nombre           VARCHAR(100)
├── apellidos        VARCHAR(200)
├── fecha_nacimiento DATE
├── genero           VARCHAR(10)  CHECK IN ('male','female','unknown')
├── dni              VARCHAR(9)   ← UNIQUE PARTIAL (WHERE NOT NULL)
├── nie              VARCHAR(9)   ← UNIQUE PARTIAL (WHERE NOT NULL)
├── pasaporte        VARCHAR(20)  ← UNIQUE PARTIAL (WHERE NOT NULL)
├── nass             VARCHAR(12)  ← UNIQUE PARTIAL (WHERE NOT NULL)
├── nuss             VARCHAR(12)  ← UNIQUE PARTIAL (WHERE NOT NULL)
├── created_at       TIMESTAMPTZ
└── updated_at       TIMESTAMPTZ
```

Los índices únicos parciales permiten múltiples valores `NULL` (pacientes sin
ese identificador) garantizando la unicidad cuando el valor está presente.

#### `informes`

Relación 1:N con `pacientes`. Almacena el FHIR Bundle como columna `JSONB`.

```
informes
├── id                   UUID  PK
├── paciente_id          UUID  FK → pacientes(id)  ON DELETE CASCADE
├── nombre_archivo       VARCHAR(255)
├── fecha_procesamiento  TIMESTAMPTZ
├── confidence_level     VARCHAR(10)  CHECK IN ('high','medium','low','minimal')
├── fhir_bundle          JSONB        ← Bundle R4 serializado
└── created_at           TIMESTAMPTZ
```

#### `diagnosticos`

Relación 1:N con `informes`. Cada diagnóstico tiene un tipo jerárquico
(ENUM), un código SNOMED CT validado y un código CIE-10-ES inferido.

```
diagnosticos
├── id                  UUID  PK
├── informe_id          UUID  FK → informes(id)  ON DELETE CASCADE
├── tipo                tipo_diagnostico  ENUM  ('PRINCIPAL','SECUNDARIO','ANTECEDENTE')
├── orden               SMALLINT
├── texto               VARCHAR(1000)     ← texto libre extraído del informe
├── snomed_id           VARCHAR(20)       ← conceptId SNOMED CT
├── snomed_descripcion  VARCHAR(500)
├── snomed_validado     BOOLEAN
├── cie10_codigo        VARCHAR(10)       ← código CIE-10-ES asignado
├── cie10_descripcion   VARCHAR(500)
├── cie10_confidence    DECIMAL(4,3)      ← confianza 0.000–1.000
├── cie10_razonamiento  TEXT
└── created_at          TIMESTAMPTZ
```

#### `benchmark_multimodel`

Registra cada ejecución del benchmark. Una fila = un informe procesado por un modelo.

```
benchmark_multimodel
├── id                      SERIAL  PK
├── run_id                  UUID
├── timestamp               TIMESTAMPTZ
├── archivo                 TEXT
├── modelo                  TEXT     ← Nombre legible del modelo
├── provider                TEXT     ← "google"|"openai"|"anthropic"|"ollama"|"groq"
├── tiempo_fase1_s          FLOAT
├── tokens_fase1_prompt     INT
├── tokens_fase1_completion INT
├── tiempo_fase2_s          FLOAT
├── tokens_fase2_prompt     INT
├── tokens_fase2_completion INT
├── tiempo_total_s          FLOAT
├── tokens_totales          INT
├── coste_usd               FLOAT
├── coste_eur               FLOAT
├── confidence_level        TEXT
├── snomed_id               TEXT
├── cie10_codes             TEXT     ← códigos separados por coma
├── exito                   BOOLEAN
└── error                   TEXT
```

### B.2.2 Vista Agregada `benchmark_resumen_modelo`

```sql
SELECT modelo, provider,
       COUNT(*)                              AS total_docs,
       SUM(exito::int)                       AS docs_exitosos,
       ROUND(AVG(tiempo_total_s)::numeric,3) AS latencia_media_s,
       ROUND(AVG(tokens_totales)::numeric,0) AS tokens_medios,
       ROUND(SUM(coste_eur)::numeric,4)      AS coste_total_eur
FROM benchmark_multimodel
GROUP BY modelo, provider
ORDER BY latencia_media_s ASC;
```

### B.2.3 Función Almacenada `upsert_paciente()`

Implementa la resolución de entidad del paciente buscando coincidencia en
cualquiera de los cinco identificadores antes de insertar un nuevo registro.
Si el paciente ya existe, enriquece los campos vacíos con los nuevos datos
(patrón `COALESCE(existente, nuevo)`).

```
Firma:
  upsert_paciente(
    p_nombre           VARCHAR,
    p_apellidos        VARCHAR,
    p_fecha_nacimiento DATE,
    p_genero           VARCHAR,
    p_dni              VARCHAR,  p_nie VARCHAR,
    p_pasaporte        VARCHAR,  p_nass VARCHAR,  p_nuss VARCHAR
  ) RETURNS UUID
```

---

## B.3 Herramientas MCP del Servidor SNOMED CT

El servidor MCP (`mcp_servers/snomed_server.py`) expone tres herramientas
mediante el protocolo JSON-RPC 2.0 sobre transporte **stdio**. Cualquier
cliente MCP compatible (VS Code Copilot, Claude Desktop, agentes Python)
puede invocarlas.

> **Protección del canal stdio:** `builtins.print` se monkey-patchea a `stderr`
> antes de cualquier importación para garantizar que ningún `print()` accidental
> corrompa el canal JSON-RPC del protocolo MCP.

### B.3.1 `buscar_snomed`

Búsqueda de texto libre en la IRBD SNOMED CT española.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `texto` | string | Sí | Término clínico en español o inglés |
| `edition` | `"es"` / `"int"` | No (def: `"es"`) | Edición española o internacional |
| `limite` | integer | No (def: 5) | Máximo de conceptos candidatos |

**Respuesta de ejemplo:**
```json
[
  { "conceptId": "53741008", "term": "Infarto agudo de miocardio" },
  { "conceptId": "22298006", "term": "Infarto de miocardio" }
]
```

### B.3.2 `validar_snomed`

Verifica que un `conceptId` existe y está activo en la IRBD.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `conceptId` | string | Sí | Identificador numérico SNOMED CT |

**Respuesta de ejemplo:**
```json
{
  "valid": true,
  "conceptId": "53741008",
  "term": "Infarto agudo de miocardio",
  "active": true
}
```

### B.3.3 `obtener_reglas_cie10`

Recupera las reglas de mapeo CIE-10-ES para un concepto SNOMED CT dado,
según la tabla de mapeo oficial de la IRBD.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `snomed_id` | string | Sí | conceptId SNOMED CT de origen |

**Respuesta de ejemplo:**
```json
[
  {
    "mapGroup": 1,
    "mapPriority": 1,
    "mapRule": "TRUE",
    "mapTarget": "I21.9",
    "mapAdvice": "ALWAYS I21.9"
  }
]
```

---

## B.4 Arquitectura de Proveedores LLM

La clase abstracta `ModelProvider` (en `benchmark/providers.py`) define una
interfaz unificada que permite inyectar cualquier proveedor en los agentes
sin modificar su código interno.

```
ModelProvider (ABC)
│
├── generate(prompt) → GenerationResult        ← implementar en subclase
└── generate_content(prompt) → _AdaptedResponse  ← adaptador API Gemini
         │
         └── _AdaptedResponse
               ├── .text                       ← texto generado
               └── .usage_metadata
                     ├── .prompt_token_count
                     ├── .candidates_token_count
                     └── .total_token_count
```

El adaptador `_AdaptedResponse` imita la interfaz de `google.generativeai`
para que el código de los agentes (escrito inicialmente para Gemini) funcione
sin cambios con cualquier proveedor.

### B.4.1 Tabla de Proveedores Implementados

| Clase | Backend | Autenticación | Notas |
|---|---|---|---|
| `GeminiProvider` | `google-generativeai` SDK | `GOOGLE_API_KEY` | Modelo principal del TFM |
| `GroqProvider` | `openai` SDK (endpoint Groq) | `GROQ_API_KEY` | ~500 tokens/s, gratuito |
| `OllamaProvider` | `openai` SDK (`http://localhost:11434/v1`) | — | Requiere servicio Ollama activo |
| `OpenAIProvider` | `openai` SDK oficial | `OPENAI_API_KEY` | GPT-4o (de pago) |
| `AnthropicProvider` | `anthropic` SDK | `ANTHROPIC_API_KEY` | Claude 3.x (de pago) |

### B.4.2 `_TrackingProvider` — Instrumentación de Tokens

Decorador (patrón Wrapper) que envuelve cualquier `ModelProvider` y acumula
contadores de tokens entre llamadas:

```python
tracker = _TrackingProvider(provider)
# ... tras N llamadas a tracker.generate_content(prompt) ...
print(tracker.prompt_tokens)      # total tokens de entrada acumulados
print(tracker.completion_tokens)  # total tokens de salida acumulados
print(tracker.total_tokens)       # suma
```

---

## B.5 Flujo de Procesamiento del Pipeline

A continuación se detalla el flujo interno para la ruta `POST /procesar`:

```
POST /procesar (multipart: file + modelo)
│
├── 1. Guardar archivo en directorio temporal
├── 2. Generar job_id (UUID v4)
├── 3. Registrar job con estado "encolado"
├── 4. Lanzar BackgroundTask → _procesar_en_background()
└── 5. Devolver 202 Accepted con { job_id }

_procesar_en_background()
│
├── Marcar estado → "procesando"
│
├── FASE 1 — AgenteExtractorNER
│   ├── Si PDF: MarkItDown.convert() → Markdown local
│   ├── Llamada LLM (extracción NER clínica)
│   ├── Por cada diagnóstico: ciclo SNOMED CT (3 flujos)
│   │   ├── Sin ID → buscar_snomed() vía MCP
│   │   ├── ID inválido → buscar_snomed() + corregir
│   │   └── ID válido → validar_snomed() → marcar validado
│   └── Devuelve dict con entidades extraídas + SNOMED validados
│
├── Construir FHIR Bundle R4 (fhir.resources / Pydantic v2)
├── Persistir JSON → data/output_fhir/{job_id}_fhir.json
│
├── FASE 2 — AgenteCodificadorCardiologia
│   ├── extraer_contexto_desde_fhir() → contexto estructurado
│   ├── obtener_reglas_mapeo_cie10(snomed_id) → reglas IRBD
│   └── procesar_historial(resumen, reglas) → dict CIE-10 por mapGroup
│
├── Calcular telemetría (tokens, latencia, coste €)
├── Normalizar estructura CIE-10 → _normalizar_cie10()
└── Marcar estado → "completado" / "error"
```

---

## B.6 Estructura del FHIR Bundle de Salida

Cada informe genera un Bundle FHIR R4 (`resourceType: "Bundle"`) que contiene:

| Recurso FHIR | Descripción |
|---|---|
| `Patient` | Datos demográficos del paciente (nombre, fecha de nacimiento, sexo, identificadores) |
| `Condition` (principal) | Diagnóstico principal con código SNOMED CT validado |
| `Condition` (secundarios) | Comorbilidades activas con código SNOMED CT |
| `Condition` (antecedentes) | Historia clínica pasada |
| `Observation` | Hallazgos cuantitativos (FEVI, presión arterial, glucemia, etc.) |
| `MedicationStatement` | Medicación referenciada en el informe |
| `Procedure` | Procedimientos realizados (cateterismo, ecocardiografía, etc.) |

**Metadatos del Bundle:**
```json
{
  "resourceType": "Bundle",
  "type": "document",
  "timestamp": "2026-06-07T10:30:00Z",
  "meta": {
    "profile": ["http://hl7.org/fhir/StructureDefinition/Bundle"]
  }
}
```

Los códigos SNOMED CT se codifican con el sistema
`http://snomed.info/sct` y los CIE-10-ES con
`http://hl7.org/fhir/sid/icd-10`.

---

## B.7 Tabla de Precios de los Modelos LLM (Mayo–Junio 2026)

Precios en USD por millón de tokens (entrada / salida) empleados en el cálculo
del coste de cada run del benchmark. Tipo de cambio aplicado: **1 USD = 0,92 EUR**.

| Modelo | Provider | USD / M tokens entrada | USD / M tokens salida |
|---|---|---|---|
| `gemini-2.5-flash` | Google | 0,15 | 0,60 |
| `llama-3.1-8b-instant` | Groq | 0,05 | 0,08 |
| `llama-3.3-70b-versatile` | Groq | 0,59 | 0,79 |
| `gpt-4o` | OpenAI | 2,50 | 10,00 |
| `gpt-4o-mini` | OpenAI | 0,15 | 0,60 |
| `claude-3-5-sonnet` | Anthropic | 3,00 | 15,00 |
| `phi4-mini` | Ollama local | 0,00 | 0,00 |
| `llama3.2:3b` | Ollama local | 0,00 | 0,00 |
| `meditron` | Ollama local | 0,00 | 0,00 |
| `cniongolo/biomistral` | Ollama local | 0,00 | 0,00 |

> Los modelos locales (Ollama) tienen coste monetario cero pero consumen
> recursos de CPU/RAM del equipo anfitrión.

---

## B.8 Módulos del Proyecto y Responsabilidades

| Módulo | Responsabilidad principal |
|---|---|
| `api/app.py` | API REST FastAPI; gestión del ciclo de vida MCP; procesamiento asíncrono |
| `fase1_homogeneizacion/nlp_extractor.py` | Agente NER clínico con validación SNOMED CT en bucle |
| `fase1_homogeneizacion/fhir_builder.py` | Construcción del Bundle FHIR R4 desde entidades extraídas |
| `fase2_inferencia_cie10/rule_engine_agentic.py` | Motor CIE-10 con Function Calling (Gemini) |
| `fase2_inferencia_cie10/rule_engine.py` | Motor CIE-10 secuencial (sin function calling; compatible con todos los modelos) |
| `mcp_servers/snomed_server.py` | Servidor MCP que expone las 3 herramientas SNOMED CT |
| `mcp_client/snomed_client.py` | Cliente MCP síncrono con bridge asyncio/threading |
| `database/snomed_queries.py` | Consultas SQL directas a la IRBD SNOMED CT |
| `database/patient_repository.py` | Repositorio de pacientes (upsert, búsqueda) |
| `benchmark/providers.py` | Abstracción unificada de proveedores LLM (5 backends) |
| `benchmark/runner.py` | Ejecución del benchmark; `_TrackingProvider` para telemetría |
| `benchmark/pricing.py` | Tabla de precios USD/M tokens; conversión a EUR |
| `benchmark/db_writer.py` | Escritura de resultados en `benchmark_multimodel` |
| `core/processing_result.py` | `ProcessingResult` + `ConfidenceLevel` (lógica de confianza) |
| `config.py` | Carga de `.env`; configuración de SDK Google Gemini |
| `benchmark_multi.py` | Script CLI del benchmark multi-modelo |
| `portal-tfm/` | Portal web Next.js 14 (App Router) + Tailwind CSS + Recharts |

---

*Anexo elaborado para el Trabajo de Fin de Máster: "Homogeneización semántica de
registros clínicos mediante IA". Universidad Pablo de Olavide. Junio 2026.*
