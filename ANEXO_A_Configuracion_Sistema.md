# ANEXO A — Configuración del Sistema y Guía de Despliegue

---

## A.1 Entorno de Pruebas

Todo el desarrollo, las pruebas de integración y la ejecución del benchmark multi-modelo
se realizaron sobre el equipo que se detalla a continuación. No se empleó infraestructura
en la nube ni GPU dedicada; todos los modelos locales ejecutaron sobre CPU / GPU integrada.

### A.1.1 Hardware

| Componente | Especificación |
|---|---|
| **Equipo** | ASUS Zenbook UX3402VA |
| **Procesador** | Intel® Core™ i7-1360P (13.ª generación) |
| — Núcleos / hilos | 12 núcleos / 16 hilos lógicos |
| — Frecuencia base | 2,2 GHz (boost hasta 5,0 GHz) |
| **Memoria RAM** | 16 GB LPDDR5x-6400 (SK Hynix, 8 módulos DIMM × 2 GB soldados) |
| **Gráficos** | Intel® Iris® Xe Graphics (GPU integrada, sin VRAM dedicada) |
| **Almacenamiento** | 512 GB NVMe SSD (Micron 3400 — PCIe 4.0) |

> **Nota sobre los LLM locales:** La ausencia de GPU dedicada implica que todos los modelos
> Ollama se ejecutan sobre CPU. En este equipo, un modelo de 7 B parámetros (p. ej.
> `phi4-mini`, `llama3.2:3b`) tarda entre 15 y 45 segundos en generar una respuesta
> completa para un informe clínico típico.

### A.1.2 Sistema Operativo y Runtime

| Componente | Versión |
|---|---|
| **Sistema operativo** | Microsoft Windows 11 Home (Build 26200, 64 bits) |
| **Python** | 3.13.4 |
| **Docker Desktop** | 28.1.1 |
| **Docker Compose** | v2.35.1-desktop.1 |
| **Node.js** | 22.19.0 (LTS) |
| **npm** | 10.9.3 |
| **Ollama** | 0.30.3 (servicio nativo Windows) |

---

## A.2 Requisitos Previos

Antes de levantar el proyecto es necesario tener instaladas y configuradas las
siguientes herramientas:

1. **Python 3.11+** — se recomienda 3.13.  
   Descarga: https://www.python.org/downloads/

2. **Docker Desktop para Windows** (incluye Docker Compose v2).  
   Descarga: https://www.docker.com/products/docker-desktop/  
   Debe estar en ejecución con el motor Linux habilitado.

3. **Node.js 18+ (LTS)** y npm.  
   Descarga: https://nodejs.org/

4. **Ollama** (solo si se desea ejecutar modelos LLM locales).  
   Descarga: https://ollama.com/download/windows  
   El instalador registra Ollama como servicio de Windows en `http://localhost:11434`.

5. **Claves de API** (opcionales, según los modelos que se quieran usar):
   - Google Gemini: https://aistudio.google.com/app/apikey
   - Groq (nivel gratuito disponible): https://console.groq.com/keys
   - OpenAI / Anthropic: respectivos portales de desarrolladores

---

## A.3 Estructura de Archivos y Variables de Entorno

### A.3.1 Archivo `.env`

Crear un archivo `.env` en la raíz del proyecto con el siguiente contenido
(sustituir los valores entre `<>` por las claves reales):

```env
# ── Obligatoria ───────────────────────────────────────────────────────────────
GOOGLE_API_KEY=<tu_clave_google_gemini>

# ── Opcionales (benchmark multi-modelo) ──────────────────────────────────────
OPENAI_API_KEY=<tu_clave_openai>
ANTHROPIC_API_KEY=<tu_clave_anthropic>
GROQ_API_KEY=<tu_clave_groq>

# ── Base de datos PostgreSQL ──────────────────────────────────────────────────
DB_USER=postgres
DB_PASSWORD=snomed_password
DB_NAME=snomed_irbd
DB_HOST=localhost
DB_PORT=5432

# ── Ollama (por defecto ya apunta a localhost) ────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
```

---

## A.4 Guía de Despliegue Paso a Paso

### Paso 1 — Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd tfm-cardiologia-fhir
```

### Paso 2 — Crear y activar el entorno virtual Python

```powershell
# Windows (PowerShell)
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### Paso 3 — Instalar dependencias Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Las dependencias principales son:

| Paquete | Versión mínima | Propósito |
|---|---|---|
| `google-generativeai` | 0.8.0 | SDK Google Gemini |
| `markitdown[all]` | 0.1.0 | Conversión local PDF → Markdown |
| `fhir.resources` | 8.2.0 | Modelos Pydantic v2 para HL7 FHIR R4 |
| `fastapi` | 0.111.0 | API REST |
| `uvicorn[standard]` | 0.29.0 | Servidor ASGI |
| `mcp` | 1.2.0 | Model Context Protocol (cliente y servidor) |
| `openai` | 1.30.0 | SDK OpenAI + adaptador Ollama |
| `anthropic` | 0.25.0 | SDK Anthropic Claude |
| `pandas` | 2.0.0 | Procesamiento CSV del benchmark |
| `psycopg2-binary` | 2.9.0 | Conector PostgreSQL |
| `python-dotenv` | 1.0.0 | Carga de variables `.env` |

### Paso 4 — Levantar la base de datos SNOMED CT (Docker)

```bash
docker compose up -d snomed-db
```

Este comando:
- Crea un contenedor PostgreSQL 15 (`snomed_irbd_postgres`) expuesto en el puerto `5432`.
- Ejecuta automáticamente el script `data/init_db/01-restore-dump.sh`, que restaura
  el volcado `IRBD_Multibase_PostgreSQL_snapshot_20251201.sql` con la base de datos
  SNOMED CT española.
- La primera vez tarda **10-15 minutos** dependiendo del disco (el dump es de ~2 GB).

Verificar que la base de datos está lista:

```bash
docker logs snomed_irbd_postgres --tail 20
# Buscar: "database system is ready to accept connections"
```

Crear el esquema clínico (tablas `pacientes`, `informes`, `diagnosticos`):

```bash
docker exec -i snomed_irbd_postgres psql -U postgres -d snomed_irbd \
  < database/migrations/002_clinical_schema.sql
docker exec -i snomed_irbd_postgres psql -U postgres -d snomed_irbd \
  < database/migrations/003_benchmark_multimodel.sql
```

### Paso 5 — Instalar modelos Ollama (opcional)

Si se quieren ejecutar modelos LLM locales, primero verificar que el servicio Ollama
está activo:

```powershell
# Comprobar servicio
ollama list

# Si no responde, iniciarlo manualmente
ollama serve
```

Descargar los modelos usados en el benchmark:

```bash
# Modelos de propósito general (recomendados para equipos sin GPU)
ollama pull phi4-mini        # ~2,5 GB — muy eficiente en CPU
ollama pull llama3.2:3b      # ~2,0 GB — buena relación calidad/velocidad

# Modelos médicos especializados
ollama pull meditron         # ~4,1 GB — preentrenado en literatura PubMed
ollama pull cniongolo/biomistral  # ~4,1 GB — BioMistral fine-tuned en textos EHR
```

> En el equipo de pruebas (sin GPU dedicada), `phi4-mini` tardó en media
> **22 segundos por informe** frente a los **3,1 s** de Gemini 2.5 Flash.

### Paso 6 — Levantar el servidor MCP SNOMED CT

El servidor MCP actúa como intermediario entre el agente LLM y la base de datos SNOMED.
Se inicia automáticamente con la API (véase Paso 7), pero puede probarse de forma
independiente:

```bash
python mcp_servers/snomed_server.py
```

### Paso 7 — Levantar la API REST (backend)

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

La API queda disponible en:

| Recurso | URL |
|---|---|
| API base | http://localhost:8000 |
| Documentación interactiva (Swagger UI) | http://localhost:8000/docs |
| Esquema OpenAPI JSON | http://localhost:8000/openapi.json |
| Healthcheck | http://localhost:8000/health |

Al arrancar, el lifespan de FastAPI lanza automáticamente el proceso hijo
`mcp_servers/snomed_server.py` mediante transporte stdio y espera a que esté listo
antes de aceptar peticiones.

### Paso 8 — Levantar el portal web (frontend)

```bash
cd portal-tfm
npm install          # solo la primera vez
npm run dev
```

El portal queda disponible en **http://localhost:3000**.

Secciones disponibles:

| Ruta | Descripción |
|---|---|
| `/` | Página principal |
| `/demo` | Interfaz interactiva de procesamiento de informes |
| `/benchmarks` | Dashboard de métricas multi-modelo |
| `/modelos` | Catálogo de modelos LLM disponibles |
| `/arquitectura` | Diagrama de la arquitectura del sistema |
| `/autor` | Información del proyecto |

---

## A.5 Ejecución del Benchmark Multi-Modelo

El benchmark compara todos los modelos configurados sobre el mismo conjunto de
informes clínicos de entrada:

```bash
# Benchmark completo (todos los modelos activos en benchmark_multi.py)
python benchmark_multi.py

# Benchmark con un único informe para prueba rápida
python benchmark_multi.py --max-informes 1
```

Los resultados se guardan en `data/benchmark_multi_report.csv` y son leídos
automáticamente por el endpoint `GET /benchmarks` y el dashboard web.

---

## A.6 Comandos de Mantenimiento Habituales

```powershell
# Detener y eliminar los contenedores Docker (conserva los datos)
docker compose down

# Eliminar también los volúmenes (borra la base de datos — requiere nueva restauración)
docker compose down -v

# Ver logs de la base de datos en tiempo real
docker logs -f snomed_irbd_postgres

# Reiniciar Ollama si hay conflicto de puerto (Only one usage of each socket address)
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
ollama serve

# Activar entorno virtual y arrancar todo de una vez (script útil para desarrollo)
.\venv\Scripts\Activate.ps1
Start-Job { ollama serve }
Start-Job { docker compose up -d snomed-db }
uvicorn api.app:app --reload
```

---

## A.7 Verificación Rápida del Sistema

Ejecutar la siguiente secuencia para comprobar que todos los componentes están
operativos antes de procesar informes:

```powershell
# 1. Base de datos
docker ps --filter "name=snomed_irbd_postgres" --format "{{.Status}}"
# Esperado: Up X minutes

# 2. API REST
Invoke-RestMethod http://localhost:8000/health
# Esperado: { status: "ok", version: "1.0.0" }

# 3. Modelos disponibles
Invoke-RestMethod http://localhost:8000/modelos
# Esperado: lista con gemini-2.5-flash, groq/*, ollama/*

# 4. Ollama
Invoke-RestMethod http://localhost:11434/api/tags
# Esperado: lista de modelos descargados

# 5. Frontend
Start-Process "http://localhost:3000/health" # o abrir manualmente en el navegador
```

---

*Anexo elaborado para el Trabajo de Fin de Máster: "Homogeneización semántica de
registros clínicos mediante IA". Universidad Pablo de Olavide. Junio 2026.*
