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
        Tu objetivo es leer un documento médico desestructurado (ya sea en texto o PDF) y extraer información clave.
        
        INSTRUCCIONES:
        1. Identifica los datos demográficos del paciente (nombre, apellidos, género biológico, fecha de nacimiento). Si un dato no aparece, usa "Desconocido".
        2. Detecta el diagnóstico cardiológico principal.
        3. Busca en tu conocimiento interno el identificador numérico exacto de SNOMED CT (conceptId / SCTID) que le corresponde a ese diagnóstico.

        Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin markdown adicional:
        {
          "paciente": {
             "nombre": "<texto>", 
             "apellidos": "<texto>", 
             "genero": "<male | female | unknown>", 
             "fecha_nacimiento": "<YYYY-MM-DD o Desconocido>"
          },
          "diagnostico": {
             "texto": "<texto del diagnostico encontrado>", 
             "snomed_id": "<número de SNOMED CT>"
          }
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
            
            # 4. Validamos y corregimos el código SNOMED CT
            snomed_id = datos.get('diagnostico', {}).get('snomed_id')
            texto_diagnostico = datos.get('diagnostico', {}).get('texto', '')
            
            if snomed_id:
                # Validar que el código existe en la base de datos
                if not self._validar_snomed(snomed_id):
                    print(f"  [⚠️] Código SNOMED {snomed_id} no válido. Iniciando búsqueda inteligente...")
                    
                    # Buscar conceptos candidatos usando palabras clave
                    conceptos_candidatos = self._buscar_snomed(texto_diagnostico, limite=10)
                    
                    if conceptos_candidatos:
                        print(f"  [🔍] Evaluando {len(conceptos_candidatos)} conceptos candidatos...")
                        
                        # Usar el agente selector para elegir el mejor concepto
                        concepto_seleccionado = self.seleccionar_concepto_snomed(
                            texto_diagnostico, 
                            conceptos_candidatos
                        )
                        
                        if concepto_seleccionado:
                            datos['diagnostico']['snomed_id'] = concepto_seleccionado['concept_id']
                            datos['diagnostico']['snomed_description'] = concepto_seleccionado['description']
                            print(f"  [✅] Código corregido: {concepto_seleccionado['concept_id']}")
                        else:
                            print(f"  [❌] No se pudo seleccionar un concepto válido")
                            datos['diagnostico']['snomed_id'] = None
                    else:
                        print(f"  [❌] No se encontraron conceptos SNOMED para: {texto_diagnostico}")
                        datos['diagnostico']['snomed_id'] = None
                else:
                    print(f"  [✅] Código SNOMED {snomed_id} validado correctamente")
            
            return datos
            
        except json.JSONDecodeError:
            print("[!] Error: El Agente Extractor no pudo generar un JSON válido.")
            return None
        except Exception as e:
            print(f"[!] Error de conexión o procesamiento en Fase 1: {e}")
            import traceback
            traceback.print_exc()
            return None