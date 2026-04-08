import json
import re
import google.generativeai as genai

class AgenteCodificadorCardiologia:
    """
    Agente experto (MCP) que cruza el contexto clínico normalizado (desde FHIR)
    con las reglas condicionales de SNOMED CT (MapRules) para inferir el CIE-10.
    """
    
    def __init__(self):
        # Mantenemos gemini-2.5-flash por su excelente balance entre velocidad, coste y razonamiento
        self.model = genai.GenerativeModel('gemini-2.5-flash')

        self.system_prompt = """
        Eres un Agente Experto en Codificación Clínica, especializado en Cardiología.
        Evalúas reglas condicionales de mapeo (mapRules) desde SNOMED CT a CIE-10-ES.

        ENTRADAS:
        1. "clinical_context": Contexto clínico estructurado extraído de un registro FHIR R4.
        2. "mapRule": Regla condicional oficial de la OMS/SNOMED.
        3. "mapAdvice": Instrucciones clínicas adicionales.
        4. "target_code": Código CIE-10-ES candidato.

        INSTRUCCIONES:
        1. Lee el 'clinical_context' para entender la situación del paciente.
        2. Si la regla es "OTHERWISE TRUE" o "TRUE", evalúala como TRUE.
        3. Si la regla es "IFA [Concepto]", busca evidencia afirmativa en el contexto clínico.
        4. Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin markdown:
        {
          "rule_evaluation": true o false,
          "confidence_score": <número entre 0 y 1>,
          "selected_code": "<código o null>",
          "clinical_reasoning": "<Justificación de por qué se cumple o no la regla>",
          "missing_information": "<Qué dato falta según el mapAdvice, o null>"
        }
        """

    def construir_prompt_usuario(self, clinical_context, regla):
        # Ahora recibe clinical_context en lugar de un bloque de texto libre
        return f"""
        clinical_context: "{clinical_context}"
        mapRule: "{regla.get('mapRule', '')}"
        mapAdvice: "{regla.get('mapAdvice', '')}"
        target_code: "{regla.get('mapTarget', '')}"
        """

    def llamar_llm(self, prompt_completo):
        try:
            response = self.model.generate_content(prompt_completo)
            texto_limpio = re.sub(r'```json|```', '', response.text).strip()
            return texto_limpio
        except Exception as e:
            print(f"[!] Error de conexión con Gemini: {e}")
            return '{"rule_evaluation": false, "confidence_score": 0, "selected_code": null, "clinical_reasoning": "Error de API", "missing_information": null}'

    def procesar_historial(self, clinical_context, refset_rules):
        print("\n[🧠] Iniciando razonamiento del Agente sobre reglas de la IRBD...")

        # Agrupamos por mapGroup para procesar secuencias independientes (Estándar SNOMED)
        grupos = {}
        for r in refset_rules:
            grupos.setdefault(r['mapGroup'], []).append(r)

        resultados_finales = {}

        for grupo_id, reglas_grupo in grupos.items():
            print(f"\n--- Evaluando Grupo de Mapeo {grupo_id} ---")
            
            # Ordenamos por prioridad obligatoriamente
            reglas_ordenadas = sorted(reglas_grupo, key=lambda x: int(x['mapPriority']))
            codigo_seleccionado = None

            for regla in reglas_ordenadas:
                print(f"  -> Prioridad {regla['mapPriority']} | Regla: {regla['mapRule']}")
                
                prompt_usuario = self.construir_prompt_usuario(clinical_context, regla)
                prompt_completo = self.system_prompt + "\n\n" + prompt_usuario
                
                respuesta_llm = self.llamar_llm(prompt_completo)

                try:
                    analisis = json.loads(respuesta_llm)
                except json.JSONDecodeError:
                    print(f"     [Error] Gemini no devolvió un JSON válido.")
                    continue

                if analisis.get('rule_evaluation') == True:
                    print(f"     [✅ ÉXITO] Código CIE-10 asignado: {analisis.get('selected_code')}")
                    print(f"     [Razonamiento] {analisis.get('clinical_reasoning')}")
                    codigo_seleccionado = analisis.get('selected_code')
                    resultados_finales[grupo_id] = analisis
                    break # Al cumplirse la regla, terminamos con este mapGroup
                else:
                    print(f"     [❌ Falso] {analisis.get('clinical_reasoning')}")

            if not codigo_seleccionado:
                print(f"  [!] No se cumplió ninguna condición para el grupo {grupo_id}.")

        return resultados_finales