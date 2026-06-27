import json
import re
import os
import time
from typing import Optional
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from markitdown import MarkItDown
from database.snomed_queries import buscar_concepto_snomed, validar_concepto_snomed

# Instancia global de MarkItDown (conversión local PDF→Markdown, sin upload a LLM)
_markitdown = MarkItDown()


def _generate_with_retry(model, contenido, max_retries: int = 5, base_sleep: float = 20.0):
    """
    Llama a model.generate_content con reintentos exponenciales ante errores 429.
    El free tier de Gemini Flash permite 5 req/min; esperamos hasta que la API
    indique que podemos reintentar.
    """
    for intento in range(max_retries):
        try:
            return model.generate_content(contenido)
        except ResourceExhausted as e:
            if intento == max_retries - 1:
                raise
            # Intentar extraer el tiempo sugerido por la API del mensaje de error
            msg = str(e)
            sleep_s = base_sleep
            match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', msg)
            if match:
                sleep_s = int(match.group(1)) + 2  # +2 s de margen
            print(f"  [⏳] Rate limit (429). Esperando {sleep_s}s antes del reintento {intento+1}/{max_retries}...")
            time.sleep(sleep_s)
        except Exception:
            raise

class AgenteExtractorNER:
    """
    Agente experto en Procesamiento de Lenguaje Natural Clínico (PLN).
    Lee informes (TXT o PDF) y extrae las entidades para construir FHIR R4.

    Args:
        mcp_client: Instancia de MCPSnomedClient. Si se proporciona, todas las
                    búsquedas SNOMED se enrutan a través del protocolo MCP.
                    Si es None, llama directamente a la base de datos (modo legacy).
        pdf_mode: 'local_md' (default) convierte el PDF localmente con MarkItDown;
                  'cloud_upload' sube el PDF a la Files API de Gemini para análisis nativo.
    """

    def __init__(self, mcp_client=None, pdf_mode: str = "local_md"):
        self.mcp = mcp_client
        self.pdf_mode = pdf_mode  # Cambio 3: modo dual PDF
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite')
        
        self.system_prompt = """
        Actúa como un sistema experto de Procesamiento de Lenguaje Natural (PLN) clínico.
        Tu objetivo es leer un documento médico desestructurado y extraer información estructurada.

        INSTRUCCIONES:

        0. CLASIFICACIÓN DE DOMINIO:
           Determina si el documento es principalmente de cardiología (true) o de otra especialidad (false).
           Un documento es cardiológico si su tema central son enfermedades del corazón o sistema cardiovascular.

        1. DATOS DEL PACIENTE:
           - Extrae nombre, apellidos, género biológico (male/female/unknown) y fecha de nacimiento.
           - Busca IDENTIFICADORES ESPAÑOLES: DNI (8 dígitos + letra), NIE (X/Y/Z + 7 dígitos + letra),
             número de pasaporte, NASS/NUSS (número de seguridad social, 12 dígitos).
           - Si un dato no aparece, usa null (no "Desconocido").

        2. CLASIFICACIÓN JERÁRQUICA DE DIAGNÓSTICOS:
           Extrae TODOS los diagnósticos mencionados y clasifícalos en tres categorías:
           - "PRINCIPAL": El diagnóstico que motiva este episodio/informe (solo 1).
           - "SECUNDARIO": Comorbilidades activas que influyen en el tratamiento (puede haber varios).
           - "ANTECEDENTE": Enfermedades pasadas o historia previa relevante (puede haber varios).
           Para cada diagnóstico:
           - Incluye el texto original en español.
           - Incluye la traducción al inglés biomédico estándar (terminología SNOMED/ICD) en el campo "texto_en".
           - Busca su código SNOMED CT (conceptId numérico).

        Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin markdown:
        {
          "es_cardiologia": true,
          "paciente": {
            "nombre": "<texto o null>",
            "apellidos": "<texto o null>",
            "genero": "<male | female | unknown>",
            "fecha_nacimiento": "<YYYY-MM-DD o null>",
            "identificadores": {
              "dni": "<8 dígitos + letra o null>",
              "nie": "<X/Y/Z + 7 dígitos + letra o null>",
              "pasaporte": "<alfanumérico o null>",
              "nass": "<12 dígitos o null>",
              "nuss": "<12 dígitos o null>"
            }
          },
          "diagnosticos": [
            {
              "tipo": "PRINCIPAL",
              "orden": 1,
              "texto": "<diagnóstico principal en español>",
              "texto_en": "<English biomedical term>",
              "snomed_id": "<conceptId numérico o null>"
            },
            {
              "tipo": "SECUNDARIO",
              "orden": 1,
              "texto": "<diagnóstico secundario en español>",
              "texto_en": "<English biomedical term>",
              "snomed_id": "<conceptId numérico o null>"
            },
            {
              "tipo": "ANTECEDENTE",
              "orden": 1,
              "texto": "<antecedente en español>",
              "texto_en": "<English biomedical term>",
              "snomed_id": "<conceptId numérico o null>"
            }
          ]
        }
        """

    # ── Enrutamiento MCP / directo ─────────────────────────────────────────

    def _buscar_snomed(self, texto: str, edition: str = "es", limite: int = 5) -> list:
        """Busca SNOMED via MCP si hay cliente disponible, o directamente si no."""
        if self.mcp:
            return self.mcp.buscar_snomed(texto, edition=edition, limite=limite)
        return buscar_concepto_snomed(texto, limite=limite, edition=edition)

    def _validar_snomed(self, concept_id: str) -> bool:
        """Valida SNOMED via MCP si hay cliente disponible, o directamente si no."""
        if self.mcp:
            return self.mcp.validar_snomed(concept_id)
        return validar_concepto_snomed(concept_id)

    # ──────────────────────────────────────────────────────────────────────

    def seleccionar_concepto_snomed(self, texto_diagnostico, conceptos_candidatos):
        """
        Usa el LLM para evaluar múltiples conceptos SNOMED candidatos
        y seleccionar el más apropiado para el diagnóstico dado.
        """
        if not conceptos_candidatos:
            return None
        
        # Si solo hay un candidato, lo devolvemos directamente
        if len(conceptos_candidatos) == 1:
            return conceptos_candidatos[0]
        
        # Construir prompt para el agente selector
        candidatos_texto = "\n".join([
            f"{i+1}. ID: {c['concept_id']} - {c['description']}" 
            for i, c in enumerate(conceptos_candidatos)
        ])
        
        prompt_selector = f"""
Eres un experto en terminología médica SNOMED CT.

DIAGNÓSTICO ORIGINAL: "{texto_diagnostico}"

CONCEPTOS SNOMED CANDIDATOS:
{candidatos_texto}

TAREA:
Selecciona el concepto SNOMED que mejor represente el diagnóstico original.
Considera:
- Similitud semántica y clínica
- Especificidad apropiada
- Equivalencia de significado

Devuelve ÚNICAMENTE un JSON con esta estructura exacta, sin markdown:
{{
  "selected_id": "<ID del concepto seleccionado>",
  "confidence": <número entre 0 y 1>,
  "reasoning": "<breve explicación de por qué es el más apropiado>"
}}
"""
        
        try:
            response = _generate_with_retry(self.model, prompt_selector)
            texto_limpio = re.sub(r'```json|```', '', response.text).strip()
            seleccion = json.loads(texto_limpio)
            
            # Buscar el concepto seleccionado en la lista
            selected_id = seleccion.get('selected_id')
            for concepto in conceptos_candidatos:
                if concepto['concept_id'] == selected_id:
                    print(f"  [🎯] Concepto seleccionado: {concepto['description']}")
                    print(f"  [📊] Confianza: {seleccion.get('confidence', 0):.2f}")
                    print(f"  [💭] Razonamiento: {seleccion.get('reasoning', 'N/A')}")
                    return concepto
            
            # Si no se encontró, devolver el primero como fallback
            print(f"  [⚠️] ID seleccionado no encontrado, usando primer candidato")
            return conceptos_candidatos[0]
            
        except Exception as e:
            print(f"  [⚠️] Error en agente selector: {e}")
            # Fallback: devolver el primer candidato
            return conceptos_candidatos[0]

    def extraer_entidades(self, ruta_archivo):
        print(f"[🧠] Agente Extractor analizando el informe: {os.path.basename(ruta_archivo)}")

        # 1. Determinamos el tipo de archivo
        _, extension = os.path.splitext(ruta_archivo)
        extension = extension.lower()

        # 2. Preparamos el array de contenido que le pasaremos a Gemini
        contenido_a_enviar = [self.system_prompt]
        _texto_para_clasificar = ""

        if extension == '.txt':
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                texto = f.read()
            _texto_para_clasificar = texto
            contenido_a_enviar.append(f"\n\nTEXTO CLÍNICO:\n{texto}")

        elif extension == '.pdf':
            # Cambio 3: modo dual PDF
            if self.pdf_mode == "cloud_upload":
                print("  -> Subiendo PDF a Gemini Files API (cloud_upload)...")
                uploaded = genai.upload_file(ruta_archivo, mime_type="application/pdf")
                contenido_a_enviar = [self.system_prompt, uploaded]
                _texto_para_clasificar = f"PDF: {os.path.basename(ruta_archivo)}"
                print(f"  -> PDF subido como {uploaded.name}. Iniciando extracción NER.")
            else:
                print("  -> Convirtiendo PDF a Markdown con MarkItDown (local_md)...")
                resultado = _markitdown.convert(ruta_archivo)
                texto_md = resultado.text_content
                if not texto_md or not texto_md.strip():
                    print("  [⚠️] MarkItDown no extrajo texto (¿PDF escaneado?). Abortando.")
                    return None
                print(f"  -> PDF convertido ({len(texto_md)} caracteres). Iniciando extracción NER.")
                _texto_para_clasificar = texto_md
                contenido_a_enviar.append(f"\n\nDOCUMENTO CLÍNICO (convertido de PDF):\n{texto_md}")

        else:
            print(f"[!] Error: Extensión no soportada ({extension}). Usa .txt o .pdf.")
            return None

        # El filtro de dominio se evalúa dentro de la respuesta JSON del LLM principal (campo es_cardiologia)

        # 3. Invocamos al LLM con el contenido (Texto o PDF)
        try:
            response = _generate_with_retry(self.model, contenido_a_enviar)
            texto_limpio = re.sub(r'```json|```', '', response.text).strip()
            datos = json.loads(texto_limpio)

            # Cambio 1: filtro de dominio cardiológico integrado en la respuesta del LLM
            if not datos.get('es_cardiologia', True):
                print(f"  [🚫] Documento fuera del dominio cardiológico (según LLM). Omitiendo.")
                return {"fuera_de_dominio": True, "archivo": os.path.basename(ruta_archivo)}

            # 4. Validamos y corregimos SNOMED CT para CADA diagnóstico de la lista
            diagnosticos = datos.get('diagnosticos', [])
            for diag in diagnosticos:
                snomed_id = diag.get('snomed_id')
                texto_diag = diag.get('texto', '')

                # Cambio 5: usar el campo texto_en ya generado por el LLM principal
                texto_diag_en = diag.get('texto_en') or texto_diag
                print(f"  [🌐] EN term: '{texto_diag_en[:50]}'")

                if not snomed_id:
                    # Sin SNOMED sugerido → búsqueda directa en edición internacional
                    print(f"  [🔍] Sin SNOMED para '{texto_diag[:50]}'. Buscando (EN, int)...")
                    candidatos = self._buscar_snomed(texto_diag_en, edition="int", limite=10)
                    concepto = self.seleccionar_concepto_snomed(texto_diag, candidatos)
                    if concepto:
                        diag['snomed_id'] = concepto['concept_id']
                        diag['snomed_descripcion'] = concepto['description']
                        diag['snomed_validado'] = True
                        print(f"  [✅] SNOMED encontrado: {concepto['concept_id']}")
                    else:
                        diag['snomed_id'] = None
                        diag['snomed_validado'] = False
                elif not self._validar_snomed(snomed_id):
                    # SNOMED sugerido pero inválido → buscar y corregir con texto EN
                    print(f"  [⚠️] SNOMED {snomed_id} inválido para '{texto_diag[:50]}'. Corrigiendo (EN, int)...")
                    candidatos = self._buscar_snomed(texto_diag_en, edition="int", limite=10)
                    concepto = self.seleccionar_concepto_snomed(texto_diag, candidatos)
                    if concepto:
                        diag['snomed_id'] = concepto['concept_id']
                        diag['snomed_descripcion'] = concepto['description']
                        diag['snomed_validado'] = True
                        print(f"  [✅] Código corregido: {concepto['concept_id']}")
                    else:
                        diag['snomed_id'] = None
                        diag['snomed_validado'] = False
                else:
                    diag['snomed_validado'] = True
                    print(f"  [✅] SNOMED {snomed_id} validado ({diag.get('tipo')})")

            datos['diagnosticos'] = diagnosticos
            return datos

        except json.JSONDecodeError:
            print("[!] Error: El Agente Extractor no pudo generar un JSON válido.")
            return None
        except Exception as e:
            print(f"[!] Error de conexión o procesamiento en Fase 1: {e}")
            import traceback
            traceback.print_exc()
            return None