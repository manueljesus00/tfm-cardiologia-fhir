from .fhir_parser import FHIRParser, extraer_contexto_desde_fhir
from .rule_engine import AgenteCodificadorCardiologia

# Definimos qué clases/funciones son públicas en la fase 2
__all__ = [
    'FHIRParser',
    'extraer_contexto_desde_fhir', 
    'AgenteCodificadorCardiologia'
]