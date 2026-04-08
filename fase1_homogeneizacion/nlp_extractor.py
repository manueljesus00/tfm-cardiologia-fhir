import json
import re
import os
import time
import google.generativeai as genai

class AgenteExtractorNER:
    """
    Agente experto en Procesamiento de Lenguaje Natural Clínico (PLN).
    Lee informes (TXT o PDF) y extrae las entidades para construir FHIR R4.
    """
    
    def __init__(self):
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
            return datos
            
        except json.JSONDecodeError:
            print("[!] Error: El Agente Extractor no pudo generar un JSON válido.")
            return None
        except Exception as e:
            print(f"[!] Error de conexión o procesamiento en Fase 1: {e}")
            return None