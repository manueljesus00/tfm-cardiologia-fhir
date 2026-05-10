from fhir.resources.bundle import Bundle, BundleEntry
from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName
from fhir.resources.condition import Condition
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.reference import Reference
import datetime

# Mapeo de tipo_diagnostico → FHIR clinicalStatus / category
_CATEGORIA_FHIR = {
    "PRINCIPAL":   "encounter-diagnosis",
    "SECUNDARIO":  "problem-list-item",
    "ANTECEDENTE": "problem-list-item",
}

_CLINICAL_STATUS = {
    "PRINCIPAL":   "active",
    "SECUNDARIO":  "active",
    "ANTECEDENTE": "inactive",   # Los antecedentes ya no están activos
}


def crear_fhir_base(datos_clinicos: dict) -> Bundle:
    """
    Construye un Bundle FHIR R4 con:
      - 1 recurso Patient
      - N recursos Condition (uno por diagnóstico: PRINCIPAL, SECUNDARIO, ANTECEDENTE)

    Args:
        datos_clinicos: Dict con claves 'paciente' y 'diagnosticos' (lista).
                        Compatible con el nuevo JSON Schema del LLM.
    """
    paciente_data = datos_clinicos['paciente']
    diagnosticos  = datos_clinicos.get('diagnosticos', [])

    # 1. Recurso Patient
    paciente_id = "paciente-001"
    paciente = Patient.model_construct(id=paciente_id)
    paciente.name = [HumanName(
        family=paciente_data.get('apellidos') or 'Desconocido',
        given=[paciente_data.get('nombre') or 'Desconocido'],
    )]
    paciente.gender = paciente_data.get('genero', 'unknown')
    fecha = paciente_data.get('fecha_nacimiento')
    if fecha and str(fecha).lower() not in ('null', 'desconocido', ''):
        paciente.birthDate = str(fecha)

    entries = [BundleEntry.model_construct(
        resource=paciente,
        fullUrl=f"Patient/{paciente_id}",
    )]

    # 2. Un Condition por cada diagnóstico
    ahora = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for i, diag in enumerate(diagnosticos):
        tipo = diag.get('tipo', 'SECUNDARIO')
        condicion_id = f"diag-{tipo.lower()}-{diag.get('orden', i+1):02d}"

        condicion = Condition.model_construct(id=condicion_id)
        condicion.subject = Reference(reference=f"Patient/{paciente_id}")

        snomed_id = diag.get('snomed_id')
        codificaciones = []
        if snomed_id and str(snomed_id) not in ('None', 'null', '0', ''):
            codificaciones.append(Coding(
                system="http://snomed.info/sct",
                code=str(snomed_id),
                display=diag.get('snomed_descripcion') or diag.get('texto', ''),
            ))

        condicion.code = CodeableConcept(
            coding=codificaciones if codificaciones else None,
            text=diag.get('texto', ''),
        )

        # Categoría FHIR según el tipo de diagnóstico
        condicion.category = [CodeableConcept(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/condition-category",
            code=_CATEGORIA_FHIR.get(tipo, "problem-list-item"),
            display=tipo,
        )])]

        # Estado clínico: activo para PRINCIPAL/SECUNDARIO, inactivo para ANTECEDENTE
        condicion.clinicalStatus = CodeableConcept(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/condition-clinical",
            code=_CLINICAL_STATUS.get(tipo, "active"),
        )])

        condicion.recordedDate = ahora

        entries.append(BundleEntry.model_construct(
            resource=condicion,
            fullUrl=f"Condition/{condicion_id}",
        ))

    # 3. Bundle Document
    bundle = Bundle.model_construct(type="document", id="bundle-tfm-001")
    bundle.entry = entries
    return bundle
