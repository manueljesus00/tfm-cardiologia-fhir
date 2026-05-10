import json
import re
import os
import time
from typing import Optional
import google.generativeai as genai
from database.snomed_queries import buscar_concepto_snomed, validar_concepto_snomed

class AgenteExtractorNER:
    """
    Agente experto en Procesamiento de Lenguaje Natural Clínico (PLN).
    Lee informes (TXT o PDF) y extrae las entidades para construir FHIR R4.

    Args:
        mcp_client: Instancia de MCPSnomedClient. Si se proporciona, todas las
                    búsquedas SNOMED se enrutan a través del protocolo MCP.
                    Si es None, llama directamente a la base de datos (modo legacy).
    """
    
    def __init__(self, mcp_client=None):
        self.mcp = mcp_client
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.system_prompt = """
        Actúa como un sistema experto de Procesamiento de Lenguaje Natural (PLN) clínico.
        Tu objetivo es leer un documento médico desestructurado y extraer información estructurada.

        INSTRUCCIONES:

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
           Para cada diagnóstico, busca su código SNOMED CT (conceptId numérico).

        Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin markdown:
        {
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
              "texto": "<diagnóstico principal>",
              "snomed_id": "<conceptId numérico o null>"
            },
            {
              "tipo": "SECUNDARIO",
              "orden": 1,
              "texto": "<diagnóstico secundario>",
              "snomed_id": "<conceptId numérico o null>"
            },
            {
              "tipo": "ANTECEDENTE",
              "orden": 1,
              "texto": "<antecedente>",
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
            response = self.model.generate_content(prompt_selector)
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

        if extension == '.txt':
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                texto = f.read()
            contenido_a_enviar.append(f"\n\nTEXTO CLÍNICO:\n{texto}")

        elif extension == '.pdf':
            print("  -> Subiendo PDF a Gemini de forma segura...")
            archivo_pdf = genai.upload_file(ruta_archivo)
            
            # Los PDFs necesitan unos segundos para procesarse en los servidores de Google
            while archivo_pdf.state.name == 'PROCESSING':
                print('  . procesando documento...', end='\r')
                time.sleep(2)
                archivo_pdf = genai.get_file(archivo_pdf.name)
                
            print("  -> PDF procesado. Iniciando extracción NER.")
            contenido_a_enviar.append("\n\nDOCUMENTO CLÍNICO ADJUNTO:")
            contenido_a_enviar.append(archivo_pdf)
            
        else:
            print(f"[!] Error: Extensión no soportada ({extension}). Usa .txt o .pdf.")
            return None

        # 3. Invocamos al LLM con el contenido (Texto o PDF)
        try:
            response = self.model.generate_content(contenido_a_enviar)
            texto_limpio = re.sub(r'```json|```', '', response.text).strip()
            datos = json.loads(texto_limpio)

            # 4. Validamos y corregimos SNOMED CT para CADA diagnóstico de la lista
            diagnosticos = datos.get('diagnosticos', [])
            for diag in diagnosticos:
                snomed_id = diag.get('snomed_id')
                texto_diag = diag.get('texto', '')

                if not snomed_id:
                    # Sin SNOMED sugerido → búsqueda directa
                    print(f"  [🔍] Sin SNOMED para '{texto_diag[:50]}'. Buscando...")
                    candidatos = self._buscar_snomed(texto_diag, limite=10)
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
                    # SNOMED sugerido pero inválido → buscar y corregir
                    print(f"  [⚠️] SNOMED {snomed_id} inválido para '{texto_diag[:50]}'. Corrigiendo...")
                    candidatos = self._buscar_snomed(texto_diag, limite=10)
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