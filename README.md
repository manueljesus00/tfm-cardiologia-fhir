# 🫀 TFM: Codificación Clínica Automatizada (Cardiología) con LLMs y FHIR

Este repositorio contiene el código fuente desarrollado para el Trabajo de Fin de Máster (TFM) en Ingeniería Informática. El proyecto propone un sistema avanzado para automatizar la codificación clínica en el dominio de la cardiología, utilizando **Google Gemini** como motor de razonamiento lógico, una base de datos **PostgreSQL** local con los recursos oficiales de SNOMED CT, y estandarizando las salidas bajo el marco **HL7 FHIR (R4)**.

## 🚀 Características Principales

* **Procesamiento de Lenguaje Natural (PLN):** Extracción de diagnósticos y códigos SNOMED CT a partir de historiales clínicos desestructurados.
* **Arquitectura de Datos Profesional:** Uso de la **IRBD Multibase (Snapshot)** oficial del Ministerio de Sanidad montada sobre un contenedor **Docker** (PostgreSQL) para consultas ultrarrápidas de reglas de mapeo.
* **Motor de Razonamiento Clínico (LLM):** Evaluación automatizada de reglas complejas condicionales (Extended Map RefSet RF2) para transcodificar de SNOMED CT a CIE-10-ES.
* **Interoperabilidad Semántica:** Generación automática de recursos `Condition` y `Bundle` bajo el estándar internacional HL7 FHIR R4, listos para integrarse en una Historia Clínica Electrónica (HCE).

## 🚀 Arquitectura en Dos Fases

El proyecto está diseñado para reflejar un flujo de trabajo realista en interoperabilidad hospitalaria:

### Fase 1: Homogeneización Semántica (NLP -> FHIR R4)
Los informes médicos desestructurados (texto de alta) son procesados mediante Modelos de Lenguaje Grande (LLMs) para extraer entidades clínicas (demografía, diagnósticos) normalizadas bajo la ontología **SNOMED CT**. Esta información se empaqueta en un recurso estructurado estándar `Bundle` de **HL7 FHIR R4**, creando un registro clínico interoperable.

### Fase 2: Inferencia de Código (FHIR R4 -> CIE-10-ES)
Un motor de reglas (Rule Engine) consume el documento JSON generado en la Fase 1. Extrae el código SNOMED y consulta una base de datos **PostgreSQL local** (que contiene el Map RefSet oficial del Ministerio de Sanidad). Un agente inteligente evalúa las condiciones lógicas de mapeo (*MapRules* e *IFA rules*) utilizando el contexto clínico del propio documento FHIR para inferir y asignar el código final en **CIE-10-ES**.

## 📂 Estructura del Proyecto

```text
tfm-cardiologia-fhir/
├── docker-compose.yml        # Contenedor de Base de Datos PostgreSQL
├── .env                      # Credenciales de BBDD y APIs
├── database/                 # Capa de datos y consultas a la IRBD de SNOMED
├── fase1_homogeneizacion/    
│   ├── nlp_extractor.py      # Módulo NER (Extracción texto libre a entidades)
│   └── fhir_builder.py       # Generador de estructura JSON FHIR R4
├── fase2_inferencia_cie10/   
│   ├── fhir_parser.py        # Módulo que ingiere y lee registros FHIR JSON
│   └── rule_engine.py        # Evaluación de reglas de mapeo con LLM
└── main.py                   # Orquestador del pipeline completo
```

## 🛠️ Requisitos Previos

1. **Python 3.9+** instalado en tu sistema.
2. **Docker y Docker Compose** instalados y corriendo.
3. Una clave de API válida de **Google Gemini** (Google AI Studio).
4. El archivo oficial de la **IRBD Multibase PostgreSQL (Snapshot)** descargado desde el [Área de Descargas de SNOMED CT del Ministerio de Sanidad](https://snomed-ct.sanidad.gob.es/snomed-ct/).

## ⚙️ Instalación y Configuración

**1. Clonar el repositorio**
```bash
git clone https://github.com/manueljesus00/tfm-cardiologia-fhir.git
cd tfm-cardiologia-fhir
```

**2. Configurar Variables de Entorno**
Crea un archivo llamado `.env` en la raíz del proyecto y añade tus credenciales:
```env
GOOGLE_API_KEY="tu_clave_api_gemini_aqui"

# Credenciales BBDD Local
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="snomed_irbd"
DB_USER="postgres"
DB_PASSWORD="snomed_password"
```

**3. Levantar la Base de Datos Local (Docker)**
Coloca el archivo `.sql` o `.dump` descargado del Ministerio dentro de la carpeta `data/init_db/`. Al levantar el contenedor, Docker importará la base de datos automáticamente (esto puede tardar unos minutos la primera vez debido al volumen de datos).
```bash
docker-compose up -d
```
*(Puedes verificar que la base de datos está lista ejecutando `docker-compose logs -f snomed-db`)*.

**4. Crear Entorno Virtual e Instalar Dependencias**
```bash
# En Windows
python -m venv venv
venv\Scripts\activate

# En macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Instalar librerías
pip install -r requirements.txt
```

## 💻 Uso

Una vez que el contenedor de PostgreSQL esté corriendo y el entorno virtual activado, ejecuta el pipeline completo de demostración:

```bash
python main.py
```

**¿Qué hace este script?**
1. Busca en la base de datos local las reglas oficiales de la OMS para un diagnóstico (ej. Infarto agudo de miocardio).
2. Le pasa un historial clínico ficticio y las reglas al agente de Gemini.
3. El agente razona y selecciona el código CIE-10 exacto.
4. El sistema empaqueta el resultado en un documento JSON validado contra el esquema **FHIR R4**.

Al finalizar, se generará el archivo `bundle_diagnostico.json` en el directorio raíz.

## 🛑 Detener el entorno
Cuando termines de trabajar, puedes apagar la base de datos sin perder información:
```bash
docker-compose down
```

## ⚠️ Descargo de Responsabilidad

Este proyecto tiene un propósito **estrictamente académico e investigador** para la evaluación de un TFM. Los modelos de Inteligencia Artificial Generativa pueden producir alucinaciones, falsos positivos o errores de interpretación. El código generado por este sistema y los mapeos propuestos **no deben utilizarse en un entorno clínico real** sin la validación exhaustiva y supervisión de un profesional sanitario o un técnico en documentación clínica (codificador) certificado.
