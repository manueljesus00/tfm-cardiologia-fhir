# TFM: Homogeneización semántica automatizada de historiales clínicos

Trabajo de Fin de Máster en Ingeniería Informática. Sistema completo para automatizar la **codificación diagnóstica** de informes cardiológicos: extrae entidades clínicas mediante NER con LLMs, genera recursos **HL7 FHIR R4** y mapea automáticamente a **CIE-10-ES** consultando la IRBD Multibase del Ministerio de Sanidad.

**Portal web:** `https://manueljesus00.github.io/tfm-cardiologia-fhir/`

---

## Arquitectura del sistema

El pipeline se divide en dos fases independientes:

```
Informe médico (.txt / .pdf)
        │
        ▼
┌─────────────────────────────────┐
│  FASE 1 — Homogeneización NER   │  LLM (Gemini 3.1 Flash Lite / Groq / Ollama)
│  Extracción SNOMED CT → FHIR R4 │  + Servidor MCP SNOMED (PostgreSQL local)
└────────────────┬────────────────┘
                 │  Bundle FHIR JSON
                 ▼
┌─────────────────────────────────┐
│  FASE 2 — Inferencia CIE-10-ES  │  Agente LLM evalúa MapRules / IFA rules
│  FHIR R4 + IRBD → CIE-10       │  sobre la IRBD Multibase (Extended Map RefSet)
└─────────────────────────────────┘
```

### Componentes principales

| Directorio / fichero | Función |
|---|---|
| `fase1_homogeneizacion/` | Agente NER (`nlp_extractor.py`) + generador FHIR (`fhir_builder.py`) |
| `fase2_inferencia_cie10/` | Motor de reglas agéntico (`rule_engine_agentic.py`) + parser FHIR |
| `database/` | Conexión PostgreSQL, repositorio de pacientes, consultas SNOMED |
| `mcp_servers/snomed_server.py` | Servidor MCP que expone la IRBD como herramienta para los agentes |
| `mcp_client/snomed_client.py` | Cliente MCP usado por los agentes durante el procesamiento |
| `api/app.py` | Backend FastAPI — expone el pipeline como REST API |
| `portal-tfm/` | Frontend Next.js 14 — portal de demostración y benchmarks |
| `main.py` | Orquestador CLI del pipeline completo |
| `benchmark_fases.py` | Benchmark por fases con timeout configurable |
| `benchmark_multi.py` | Benchmark multi-modelo (11 LLMs simultáneos) |
| `generate_charts.py` | Generación de gráficas a partir de los CSV de benchmark |
| `data/benchmark_fase1.csv` | Resultados del benchmark Fase 1 (181 ejecuciones) |
| `data/benchmark_fase2.csv` | Resultados del benchmark Fase 2 (182 ejecuciones) |

---

## Modelos evaluados

Se evaluaron **11 LLMs** sobre un corpus de 27 informes cardiológicos sintéticos:

| Modelo | Provider | Tipo | Motor principal |
|---|---|---|---|
| **Gemini 3.1 Flash Lite** | Google | Cloud | ✅ Motor principal TFM |
| Groq / Llama 3.3 70B Versatile | Groq | Cloud | |
| Groq / Llama 3.1 8B Instant | Groq | Cloud | |
| Ollama / gemma3:4b | Local | Local | |
| Ollama / phi4-mini | Local | Local | |
| Ollama / llama3.2:3b | Local | Local | |
| Ollama / qwen2.5:7b | Local | Local | |
| Ollama / meditron:7b | Local | Local | |
| Ollama / medllama2:latest | Local | Local | |
| Ollama / biomistral:latest | Local | Local | |

---

## Requisitos previos

- **Python 3.10+**
- **Docker y Docker Compose** (para la base de datos SNOMED)
- **Node.js 20+** (solo para el portal web)
- Clave de API de **Google Gemini** (obligatoria) y opcionalmente Groq
- Dump de la **IRBD Multibase PostgreSQL** del [Ministerio de Sanidad](https://snomed-ct.sanidad.gob.es/)
  — fichero de ~716 MB en `data/init_db/`

---

## Instalación y configuración

### 1. Clonar el repositorio

```bash
git clone https://github.com/<usuario>/tfm-cardiologia-fhir.git
cd tfm-cardiologia-fhir
```

### 2. Variables de entorno

Crea el fichero `.env` en la raíz (ya está en `.gitignore`):

```env
# Google Gemini (obligatorio)
GOOGLE_API_KEY=tu_clave_aqui

# Groq (opcional)
GROQ_API_KEY=tu_clave_aqui

# PostgreSQL SNOMED
DB_HOST=localhost
DB_PORT=5432
DB_NAME=snomed_irbd
DB_USER=postgres
DB_PASSWORD=snomed_password

# Ollama (modelos locales)
OLLAMA_BASE_URL=http://localhost:11434
```

### 3. Base de datos SNOMED (Docker)

Coloca el `.sql` de la IRBD en `data/init_db/` y levanta el contenedor:

```bash
docker compose up -d snomed-db
# Verificar que la importación termina (~5-10 min la primera vez):
docker compose logs -f snomed-db
```

### 4. Entorno Python

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

---

## Uso

### Pipeline completo (CLI)

```bash
python main.py
```

Procesa los informes de `data/input_informes/`, genera los FHIR en `data/output_fhir/` y persiste los resultados en PostgreSQL.

### Backend REST API

```bash
uvicorn api.app:app --reload
```

Disponible en `http://localhost:8000`. Endpoints principales:

| Endpoint | Método | Descripción |
|---|---|---|
| `/procesar` | POST | Sube un informe y devuelve FHIR + CIE-10 |
| `/resultado/{id}` | GET | Recupera resultado por ID de job |
| `/benchmarks` | GET | Métricas agregadas del benchmark |
| `/modelos` | GET | Lista de modelos disponibles |
| `/health` | GET | Healthcheck |

### Portal web (desarrollo local)

```bash
cd portal-tfm
npm install
npm run dev   # http://localhost:3000
```

### Benchmarks

```bash
# Solo Fase 1, todos los modelos (timeout 120 s/documento)
python benchmark_fases.py --fase 1

# Solo Fase 2 usando FHIR ya existentes
python benchmark_fases.py --fase 2 --fhir-dir data/output_fhir

# Ambas fases encadenadas
python benchmark_fases.py --fase ambas

# Benchmark multi-modelo completo
python benchmark_multi.py

# Generar gráficas desde los CSV
python generate_charts.py
```

---

## Despliegue en producción

### Portal web — GitHub Pages

El portal se despliega automáticamente con GitHub Actions en cada `push` a `main`:

1. En GitHub → **Settings → Pages → Source**: selecciona **GitHub Actions**.
2. Haz push del código. El workflow `.github/workflows/deploy-pages.yml` construye
   el export estático y lo publica en `https://<usuario>.github.io/tfm-cardiologia-fhir/`.

Cuando el backend no está disponible, el portal usa datos mock del benchmark
(resultados reales del CSV) — no requiere claves de API para el despliegue.

### Backend — opciones recomendadas

El backend requiere acceso a PostgreSQL (con la IRBD de 716 MB) y a las APIs de LLM.
Opciones según el caso de uso:

| Opción | Coste | Notas |
|---|---|---|
| **VPS propio** (Hetzner, OVH) | ~5 €/mes | Docker Compose completo, máximo control |
| **Railway / Render** | Gratis/bajo | Soporta Docker; Railway tiene PostgreSQL integrado pero el dump excede el plan gratuito |
| **Google Cloud Run + Cloud SQL** | Pay-per-use | Escala a 0, ideal para demos puntuales |
| **Local + ngrok** | Gratis | Para demos en vivo; `ngrok http 8000` expone el localhost temporalmente |

Para el TFM la opción más práctica es **VPS + Docker Compose**:

```bash
# En el servidor (tras copiar el repositorio y el dump):
docker compose up -d snomed-db
uvicorn api.app:app --host 0.0.0.0 --port 8000 &
```

Configura `NEXT_PUBLIC_API_URL=https://tu-dominio.com` en GitHub como variable de entorno
del workflow para que el portal apunte al backend en producción.

---

## Estructura de ficheros

```text
tfm-cardiologia-fhir/
├── .env                          # Variables de entorno (NO subir a git)
├── .github/workflows/
│   └── deploy-pages.yml          # CI/CD → GitHub Pages
├── docker-compose.yml            # PostgreSQL SNOMED (contenedor)
├── requirements.txt
├── config.py                     # Carga de variables de entorno
├── main.py                       # Orquestador CLI
├── benchmark_fases.py            # Benchmark por fases
├── benchmark_multi.py            # Benchmark multi-modelo
├── generate_charts.py            # Gráficas de resultados
│
├── api/app.py                    # Backend FastAPI
├── core/processing_result.py     # Modelo de resultado con graceful degradation
├── database/                     # Conexión y consultas PostgreSQL
├── mcp_servers/snomed_server.py  # Servidor MCP SNOMED
├── mcp_client/snomed_client.py   # Cliente MCP para agentes
│
├── fase1_homogeneizacion/
│   ├── nlp_extractor.py          # Agente NER (LLM → SNOMED CT)
│   └── fhir_builder.py           # Generador de Bundle FHIR R4
│
├── fase2_inferencia_cie10/
│   ├── fhir_parser.py            # Ingestor de FHIR JSON
│   ├── rule_engine.py            # Motor de reglas básico
│   └── rule_engine_agentic.py    # Motor agéntico con LLM
│
├── data/
│   ├── benchmark_fase1.csv       # Resultados benchmark Fase 1 (181 filas)
│   ├── benchmark_fase2.csv       # Resultados benchmark Fase 2 (182 filas)
│   ├── graficas/                 # Gráficas generadas
│   ├── init_db/                  # Dump IRBD Multibase (no incluido en git)
│   ├── input_informes/           # Informes de entrada (no incluidos en git)
│   └── output_fhir/              # FHIR generados (no incluidos en git)
│
└── portal-tfm/                   # Frontend Next.js 14
    ├── app/                      # Rutas: /, /benchmarks, /demo, /modelos, /arquitectura, /autor
    ├── components/               # BenchmarkDashboard, Demo, Nav…
    └── lib/api.ts                # Cliente API con fallback a datos mock
```

---

## Descargo de responsabilidad

Este proyecto tiene un propósito **estrictamente académico e investigador**. Los modelos de lenguaje pueden producir alucinaciones o errores de interpretación. Los mapeos CIE-10 generados **no deben utilizarse en un entorno clínico real** sin la validación de un profesional sanitario o técnico en documentación clínica certificado.
