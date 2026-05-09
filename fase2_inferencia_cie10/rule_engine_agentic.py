"""
fase2_inferencia_cie10/rule_engine_agentic.py — Motor de reglas agéntico.

Diferencia con rule_engine.py original:
- ANTES: Python hace un bucle for y llama al LLM UNA VEZ POR REGLA.
- AHORA: El LLM recibe TODAS las reglas y llama a la tool `evaluar_regla_mapeo`
          por sí mismo, decidiendo el orden y cuándo detenerse.

Esto convierte al LLM de "transformador de texto" a "agente con herramientas",
usando Gemini Function Calling nativo (estructura compatible con MCP tools).
"""
import json
import re
import logging
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

logger = logging.getLogger(__name__)


class AgenteCodificadorAgentico:
    """
    Motor de inferencia CIE-10 agéntico usando Gemini Function Calling.

    El LLM recibe el contexto clínico y TODAS las reglas de una sola vez,
    luego invoca `evaluar_regla_mapeo` como herramienta para estructurar
    su razonamiento — sin que Python decida el orden de evaluación.
    """

    # Declaración de la herramienta en formato compatible con MCP
    _EVALUAR_REGLA_TOOL = FunctionDeclaration(
        name="evaluar_regla_mapeo",
        description=(
            "Evalúa si una regla condicional SNOMED→CIE-10 se cumple dado el contexto "
            "clínico del paciente. Llama a esta función por cada regla que analices. "
            "Detente en el primer True de cada mapGroup."
        ),
        parameters={
            "type": "object",
            "properties": {
                "map_group": {
                    "type": "integer",
                    "description": "Número de grupo de mapeo SNOMED",
                },
                "map_priority": {
                    "type": "integer",
                    "description": "Prioridad dentro del grupo (menor = mayor prioridad)",
                },
                "map_rule": {
                    "type": "string",
                    "description": "Texto de la regla condicional",
                },
                "map_target": {
                    "type": "string",
                    "description": "Código CIE-10-ES candidato para esta regla",
                },
                "cumple_regla": {
                    "type": "boolean",
                    "description": "True si el contexto clínico satisface la condición",
                },
                "razonamiento": {
                    "type": "string",
                    "description": "Justificación clínica de la evaluación",
                },
                "informacion_faltante": {
                    "type": "string",
                    "description": "Dato clínico ausente que impide confirmar la regla, o null",
                },
            },
            "required": [
                "map_group", "map_priority", "map_rule",
                "map_target", "cumple_regla", "razonamiento",
            ],
        },
    )

    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=[Tool(function_declarations=[self._EVALUAR_REGLA_TOOL])],
        )

    def procesar_historial(self, clinical_context: str, refset_rules: list) -> dict:
        """
        El LLM recibe TODO el contexto y las reglas de una vez y decide
        autónomamente cómo evaluarlas usando Function Calling.

        Args:
            clinical_context: Resumen clínico del paciente (desde FHIRParser).
            refset_rules: Lista de reglas SNOMED→CIE-10 desde la IRBD.

        Returns:
            Dict con los resultados por mapGroup: {grupo_id: {resultado}}.
        """
        if not refset_rules:
            print("[⚠️  AGENTIC] Sin reglas SNOMED — modo inferencia directa.")
            return self._inferencia_sin_reglas(clinical_context)

        reglas_texto = json.dumps(refset_rules, ensure_ascii=False, indent=2)

        prompt = f"""
Eres un experto en codificación clínica CIE-10-ES especializado en Cardiología.

TAREA:
Analiza el contexto clínico del paciente y las reglas de mapeo SNOMED→CIE-10 disponibles.
Para cada mapGroup, evalúa las reglas en orden de prioridad (menor número = mayor prioridad)
usando la herramienta `evaluar_regla_mapeo`. Detente en el primer resultado True de cada grupo.

REGLAS DE EVALUACIÓN:
- Si la regla es "TRUE" u "OTHERWISE TRUE": siempre se cumple (es el código por defecto del grupo).
- Si la regla contiene "IFA [concepto]": busca evidencia de ese concepto en el contexto clínico.
- Si falta información para confirmar una regla IFA: márcala como False e indica qué falta.

CONTEXTO CLÍNICO DEL PACIENTE:
{clinical_context}

REGLAS DE MAPEO SNOMED→CIE-10 (ordenadas por grupo y prioridad):
{reglas_texto}

Procede a evaluar cada grupo de mapeo usando la herramienta disponible.
"""

        print("\n[🤖 AGENTIC] Iniciando razonamiento agéntico con Function Calling...")

        try:
            response = self.model.generate_content(prompt)
            resultados = self._procesar_function_calls(response)

            if not resultados:
                logger.warning("El agente no produjo ninguna evaluación de regla.")

            return resultados

        except Exception as e:
            logger.error(f"Error en razonamiento agéntico: {e}")
            # Fallback al motor original si el agéntico falla
            print(f"[⚠️] Fallback a motor secuencial por error: {e}")
            return self._fallback_secuencial(clinical_context, refset_rules)

    def _procesar_function_calls(self, response) -> dict:
        """
        Extrae y procesa las llamadas a `evaluar_regla_mapeo` de la respuesta del LLM.
        Solo registra el primer True por mapGroup (respeta la lógica SNOMED).
        """
        resultados = {}
        total_evaluadas = 0

        for candidate in response.candidates:
            for part in candidate.content.parts:
                if not hasattr(part, 'function_call') or not part.function_call:
                    continue

                fc = part.function_call
                if fc.name != "evaluar_regla_mapeo":
                    continue

                args = dict(fc.args)
                total_evaluadas += 1
                grupo = args.get("map_group", 0)
                cumple = args.get("cumple_regla", False)

                status = "✅ TRUE" if cumple else "❌ FALSE"
                print(
                    f"  [Grupo {grupo} | P{args.get('map_priority')}] "
                    f"{status} → {args.get('map_target', '?')} "
                    f"| {args.get('razonamiento', '')[:80]}"
                )

                # Solo registramos el primer True por grupo (estándar SNOMED)
                if cumple and grupo not in resultados:
                    resultados[grupo] = {
                        "rule_evaluation": True,
                        "selected_code": args.get("map_target"),
                        "confidence_score": 1.0,
                        "clinical_reasoning": args.get("razonamiento"),
                        "missing_information": args.get("informacion_faltante"),
                    }

        print(f"\n[🤖 AGENTIC] Reglas evaluadas: {total_evaluadas} | Grupos resueltos: {len(resultados)}")
        return resultados

    def _inferencia_sin_reglas(self, clinical_context: str) -> dict:
        """
        Modo degradado: cuando no hay reglas SNOMED, el LLM infiere
        el CIE-10 directamente desde el texto clínico.
        """
        # Para inferencia libre no necesitamos Function Calling
        model_libre = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""
Eres un experto en CIE-10-ES. No hay reglas de mapeo disponibles para este diagnóstico.
Infiere el código CIE-10-ES más apropiado para el siguiente contexto clínico cardiológico:

{clinical_context}

Devuelve ÚNICAMENTE un JSON válido, sin markdown:
{{"codigo": "<CIE-10>", "descripcion": "<descripcion del codigo>", "confianza": <0.0-1.0>}}
"""
        try:
            response = model_libre.generate_content(prompt)
            texto = re.sub(r'```json|```', '', response.text).strip()
            data = json.loads(texto)
            print(f"  [🤖 AGENTIC] CIE-10 inferido directamente: {data.get('codigo')} (confianza: {data.get('confianza')})")
            return {
                0: {
                    "rule_evaluation": True,
                    "selected_code": data.get("codigo"),
                    "confidence_score": data.get("confianza", 0.5),
                    "clinical_reasoning": data.get("descripcion", ""),
                    "missing_information": None,
                }
            }
        except Exception as e:
            logger.error(f"Error en inferencia sin reglas: {e}")
            return {}

    def _fallback_secuencial(self, clinical_context: str, refset_rules: list) -> dict:
        """
        Fallback al motor secuencial original si el agéntico falla.
        Importamos el motor original aquí para evitar dependencia circular.
        """
        from fase2_inferencia_cie10.rule_engine import AgenteCodificadorCardiologia
        motor_original = AgenteCodificadorCardiologia()
        return motor_original.procesar_historial(clinical_context, refset_rules)
