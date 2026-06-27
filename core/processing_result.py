"""
Modelo de resultado de procesamiento con soporte para Graceful Degradation.
Un resultado puede ser válido aunque incompleto, con un nivel de confianza
que guía las fases siguientes del pipeline.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class ConfidenceLevel(str, Enum):
    HIGH = "high"        # Todos los datos presentes y validados
    MEDIUM = "medium"    # Datos clave presentes, demografía parcial
    LOW = "low"          # Diagnóstico inferido, SNOMED no validado
    MINIMAL = "minimal"  # Solo texto diagnóstico, sin código formal


@dataclass
class ProcessingResult:
    """
    Encapsula el resultado de una fase de extracción con metadatos de calidad.
    Permite que el pipeline continúe en modo degradado en lugar de abortar.
    """
    # Datos del paciente (todos opcionales para soportar informes anónimos)
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    genero: str = "unknown"
    fecha_nacimiento: Optional[str] = None

    # Datos diagnósticos
    diagnostico_texto: Optional[str] = None
    snomed_id: Optional[str] = None
    snomed_validado: bool = False

    # Metadatos de calidad
    confidence_level: ConfidenceLevel = ConfidenceLevel.MINIMAL
    warnings: List[str] = field(default_factory=list)
    can_proceed_phase2: bool = False  # ¿Hay suficiente info para inferir CIE-10?

    @classmethod
    def from_llm_output(cls, datos: dict) -> "ProcessingResult":
        """
        Construye un ProcessingResult desde el JSON del LLM (nuevo schema multi-diagnóstico).
        Soporta también el schema legacy con clave 'diagnostico' (singular).
        """
        paciente = datos.get("paciente", {})
        diagnosticos = datos.get("diagnosticos", [])

        # Compatibilidad con schema legacy (clave 'diagnostico' singular)
        if not diagnosticos and "diagnostico" in datos:
            d = datos["diagnostico"]
            diagnosticos = [{"tipo": "PRINCIPAL", "orden": 1,
                             "texto": d.get("texto"), "snomed_id": d.get("snomed_id")}]

        # Diagnóstico principal = primer PRINCIPAL encontrado
        principal = next((d for d in diagnosticos if d.get("tipo") == "PRINCIPAL"), None)

        result = cls(
            nombre=paciente.get("nombre") if paciente.get("nombre") not in (None, "Desconocido", "") else None,
            apellidos=paciente.get("apellidos") if paciente.get("apellidos") not in (None, "Desconocido", "") else None,
            genero=paciente.get("genero", "unknown"),
            fecha_nacimiento=paciente.get("fecha_nacimiento") if paciente.get("fecha_nacimiento") not in (None, "Desconocido", "") else None,
            diagnostico_texto=principal.get("texto") if principal else None,
            snomed_id=str(principal.get("snomed_id")) if principal and principal.get("snomed_id") else None,
        )
        result._diagnosticos_completos = diagnosticos  # lista completa para FHIR y DB
        result._datos_paciente_completos = paciente     # incluye identificadores
        result._calcular_confianza()
        return result

    def _calcular_confianza(self):
        """Determina el nivel de confianza y si puede continuar a Fase 2."""
        tiene_demografía_completa = all([self.nombre, self.apellidos, self.fecha_nacimiento])
        tiene_diagnostico = bool(self.diagnostico_texto)
        tiene_snomed = bool(self.snomed_id)

        if not tiene_diagnostico:
            self.confidence_level = ConfidenceLevel.MINIMAL
            self.warnings.append("No se extrajo diagnóstico del documento.")
            self.can_proceed_phase2 = False
            return

        if tiene_snomed and tiene_demografía_completa:
            self.confidence_level = ConfidenceLevel.HIGH
        elif tiene_snomed:
            self.confidence_level = ConfidenceLevel.MEDIUM
            self.warnings.append("Datos demográficos incompletos. El FHIR usará valores por defecto.")
        elif tiene_diagnostico:
            self.confidence_level = ConfidenceLevel.LOW
            self.warnings.append("SNOMED CT no resuelto. La Fase 2 operará sin mapeo validado.")
        else:
            self.confidence_level = ConfidenceLevel.MINIMAL

        # Fase 2 puede continuar si hay diagnóstico, aunque no haya SNOMED formal
        self.can_proceed_phase2 = tiene_diagnostico

    def to_fhir_dict(self) -> dict:
        """Convierte al dict esperado por crear_fhir_base() (schema con 'diagnosticos')."""
        diagnosticos = getattr(self, '_diagnosticos_completos', [])
        paciente_completo = getattr(self, '_datos_paciente_completos', {})
        if not diagnosticos:
            diagnosticos = [{
                "tipo": "PRINCIPAL", "orden": 1,
                "texto": self.diagnostico_texto or "Diagnóstico no especificado",
                "snomed_id": self.snomed_id,
            }]
        return {
            "paciente": {
                "nombre": self.nombre or "Anónimo",
                "apellidos": self.apellidos or "Desconocido",
                "genero": self.genero,
                "fecha_nacimiento": self.fecha_nacimiento,
                "identificadores": paciente_completo.get("identificadores", {}),
            },
            "diagnosticos": diagnosticos,
        }

    def log_warnings(self):
        for w in self.warnings:
            print(f"  [⚠️  DEGRADED] {w}")
