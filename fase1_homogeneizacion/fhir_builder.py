from fhir.resources.bundle import Bundle, BundleEntry
from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName
from fhir.resources.condition import Condition
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.reference import Reference
import datetime

def crear_fhir_base(datos_clinicos):
    paciente_data = datos_clinicos['paciente']
    diag_data = datos_clinicos['diagnostico']

    # 1. Crear Paciente
    paciente = Patient.model_construct(id="paciente-001")
    paciente.name = [HumanName(family=paciente_data.get('apellidos', 'Desconocido'), given=[paciente_data.get('nombre', 'Desconocido')])]
    paciente.gender = paciente_data.get('genero', 'unknown')
    paciente.birthDate = paciente_data.get('fecha_nacimiento')

    # 2. Crear Condición (Diagnóstico SNOMED)
    condicion = Condition.model_construct(id="diag-001")
    condicion.subject = Reference(reference=f"Patient/{paciente.id}")
    condicion.code = CodeableConcept(
        coding=[Coding(system="http://snomed.info/sct", code=str(diag_data['snomed_id']), display=diag_data['texto'])],
        text=diag_data['texto']
    )
    
    ahora = datetime.datetime.now(datetime.timezone.utc)
    condicion.recordedDate = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3. Ensamblar Bundle
    bundle = Bundle.model_construct(type="document", id="bundle-tfm-001")
    bundle.entry = [
        BundleEntry.model_construct(resource=paciente, fullUrl=f"Patient/{paciente.id}"),
        BundleEntry.model_construct(resource=condicion, fullUrl=f"Condition/{condicion.id}")
    ]
    return bundle