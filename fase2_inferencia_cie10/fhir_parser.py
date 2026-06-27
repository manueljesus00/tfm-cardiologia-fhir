import json
import logging

# Configuración básica de logs para trazabilidad en tu TFM
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FHIRParser:
    """
    Clase encargada de parsear recursos HL7 FHIR R4 para extraer 
    contexto clínico destinado a la codificación CIE-10-ES.
    """
    
    def __init__(self, fhir_bundle_path):
        self.path = fhir_bundle_path
        self.data = self._load_json()
        
    def _load_json(self):
        """Carga el archivo JSON del Bundle FHIR."""
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error al cargar el archivo FHIR: {e}")
            return None

    def obtener_contexto_completo(self):
        """
        Extrae la información clave de todos los recursos del Bundle
        y la organiza para el motor de inferencia.
        """
        if not self.data or self.data.get('resourceType') != 'Bundle':
            logger.warning("El archivo no es un Bundle FHIR válido.")
            return None

        contexto = {
            "snomed_id": None,
            "diagnostico_texto": None,
            "paciente": {},
            "evidencias_clinicas": [],
            "resumen_razonamiento": ""
        }

        # Iterar por las entradas del Bundle
        for entry in self.data.get('entry', []):
            resource = entry.get('resource', {})
            resource_type = resource.get('resourceType')

            if resource_type == 'Patient':
                contexto['paciente'] = self._parse_patient(resource)
            
            elif resource_type == 'Condition':
                # Buscamos el código SNOMED en la condición
                snomed_info = self._parse_condition(resource)
                if snomed_info:
                    contexto['snomed_id'] = snomed_info['code']
                    contexto['diagnostico_texto'] = snomed_info['display']
                    contexto['evidencias_clinicas'].append(snomed_info['display'])

        # Construir el string de "historial_reconstruido" que leerá Gemini
        contexto['resumen_razonamiento'] = self._construir_resumen(contexto)
        
        return contexto

    def _parse_patient(self, resource):
        """Extrae datos demográficos relevantes para reglas de codificación."""
        return {
            "genero": resource.get('gender', 'unknown'),
            "nacimiento": resource.get('birthDate', 'unknown'),
            "id": resource.get('id')
        }

    def _parse_condition(self, resource):
        """Busca específicamente codificaciones del sistema SNOMED CT."""
        code_element = resource.get('code', {})
        for coding in code_element.get('coding', []):
            if "snomed.info/sct" in coding.get('system', '').lower():
                return {
                    "code": coding.get('code'),
                    "display": coding.get('display', code_element.get('text', ''))
                }
        return None

    def _construir_resumen(self, contexto):
        """Crea un párrafo de contexto clínico a partir de los datos FHIR."""
        p = contexto['paciente']
        resumen = f"Paciente de género {p.get('genero')} (nacido el {p.get('nacimiento')}). "
        resumen += f"Diagnóstico detectado en registro FHIR: {contexto['diagnostico_texto']}. "
        
        if contexto['evidencias_clinicas']:
            resumen += "Hallazgos clínicos adicionales: " + ", ".join(contexto['evidencias_clinicas']) + "."
            
        return resumen

# Función de utilidad para llamar desde main.py
def extraer_contexto_desde_fhir(ruta_archivo):
    parser = FHIRParser(ruta_archivo)
    return parser.obtener_contexto_completo()