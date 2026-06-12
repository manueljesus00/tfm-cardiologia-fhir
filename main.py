import os
import json
import config
from fase1_homogeneizacion import AgenteExtractorNER, crear_fhir_base
from fase2_inferencia_cie10 import extraer_contexto_desde_fhir, AgenteCodificadorCardiologia
from database.snomed_queries import obtener_reglas_mapeo_cie10
from database.patient_repository import persistir_resultado_clinico, ejecutar_migracion
from core.processing_result import ProcessingResult, ConfidenceLevel
from mcp_client import MCPSnomedClient

def procesar_archivo(ruta_entrada, ruta_fhir_intermedio, agente_ner, agente_codificador):
    """Ejecuta las dos fases del pipeline para un único archivo."""
    print("\n" + "="*60)
    print(f"🚀 PROCESANDO ARCHIVO: {os.path.basename(ruta_entrada)}")
    print("="*60)

    # ==========================================================
    # FASE 1: HOMOGENEIZACIÓN (TEXTO/PDF -> FHIR R4)
    # ==========================================================
    print("\n--- FASE 1: HOMOGENEIZACIÓN SEMÁNTICA ---")
    
    datos_extraidos = agente_ner.extraer_entidades(ruta_entrada)
    
    if not datos_extraidos:
        print(f"[!] Omitiendo {os.path.basename(ruta_entrada)} por fallo total en Fase 1 (LLM no respondió).")
        return

    # --- GRACEFUL DEGRADATION: evaluar calidad de la extracción ---
    result = ProcessingResult.from_llm_output(datos_extraidos)
    result.log_warnings()
    print(f"[*] Diagnóstico extraído: {result.diagnostico_texto}")
    print(f"[*] Código SNOMED CT: {result.snomed_id or 'No resuelto'}")
    print(f"[*] Nivel de confianza: {result.confidence_level.value.upper()}")

    if not result.can_proceed_phase2:
        print(f"[!] Confianza insuficiente (MINIMAL). No se puede generar un registro FHIR útil.")
        return

    # Guardamos y persistimos el FHIR con la lista completa de diagnósticos
    fhir_dict = result.to_fhir_dict()
    bundle_fhir = crear_fhir_base(fhir_dict)
    bundle_json = json.loads(bundle_fhir.json(indent=2))

    with open(ruta_fhir_intermedio, 'w', encoding='utf-8') as f:
        json.dump(bundle_json, f, indent=2, ensure_ascii=False)

    print(f"[✅] Registro FHIR R4 guardado en: {ruta_fhir_intermedio}")
    n_diags = len(fhir_dict.get('diagnosticos', []))
    print(f"[ℹ️] Diagnósticos extraídos: {n_diags} "
          f"({sum(1 for d in fhir_dict['diagnosticos'] if d['tipo']=='PRINCIPAL')} principal, "
          f"{sum(1 for d in fhir_dict['diagnosticos'] if d['tipo']=='SECUNDARIO')} secundarios, "
          f"{sum(1 for d in fhir_dict['diagnosticos'] if d['tipo']=='ANTECEDENTE')} antecedentes)")

    # ==========================================================
    # FASE 2: INFERENCIA CIE-10 (FHIR R4 -> CIE-10-ES)
    # ==========================================================
    print("\n--- FASE 2: INFERENCIA A CIE-10-ES ---")
    
    contexto_fhir = extraer_contexto_desde_fhir(ruta_fhir_intermedio)
    snomed_id = contexto_fhir.get('snomed_id')
    
    reglas_bbdd = obtener_reglas_mapeo_cie10(snomed_id) if snomed_id and snomed_id != '0' else []

    if not reglas_bbdd:
        if result.confidence_level == ConfidenceLevel.LOW:
            # Modo degradado: inferencia directa desde texto sin reglas SNOMED formales
            print(f"[⚠️  DEGRADED] Sin reglas SNOMED. Inferencia directa por texto diagnóstico.")
            resultado_cie10 = agente_codificador.procesar_historial(
                contexto_fhir['resumen_razonamiento'], reglas_bbdd=[]
            )
        else:
            print(f"[!] No se encontraron reglas de la OMS en BBDD para el concepto {snomed_id}.")
            return
    else:
        resultado_cie10 = agente_codificador.procesar_historial(contexto_fhir['resumen_razonamiento'], reglas_bbdd)

    print(f"\n[✅] DICTAMEN FINAL PARA {os.path.basename(ruta_entrada)}:")
    print(json.dumps(resultado_cie10, indent=2, ensure_ascii=False))

    # Enriquecer diagnósticos con los códigos CIE-10 inferidos antes de persistir
    diagnosticos_con_cie10 = fhir_dict.get('diagnosticos', [])
    principal_idx = next((i for i, d in enumerate(diagnosticos_con_cie10) if d.get('tipo') == 'PRINCIPAL'), None)
    if principal_idx is not None and resultado_cie10:
        primer_resultado = next(iter(resultado_cie10.values()), {})
        diagnosticos_con_cie10[principal_idx]['cie10_codigo'] = primer_resultado.get('selected_code')
        diagnosticos_con_cie10[principal_idx]['cie10_confidence'] = primer_resultado.get('confidence_score')
        diagnosticos_con_cie10[principal_idx]['cie10_razonamiento'] = primer_resultado.get('clinical_reasoning')

    # Persistir en la base de datos clínica normalizada
    ids = persistir_resultado_clinico(
        datos_paciente=fhir_dict['paciente'],
        nombre_archivo=os.path.basename(ruta_entrada),
        confidence_level=result.confidence_level.value,
        fhir_bundle=bundle_json,
        diagnosticos=diagnosticos_con_cie10,
    )
    print(f"[💾] Persistido → paciente_id: {ids['paciente_id']} | informe_id: {ids['informe_id']}")


def main():
    # 1. Aplicar migración DB clínica (idempotente — IF NOT EXISTS)
    print("Aplicando migración de esquema clínico...")
    ejecutar_migracion()

    # 2. Definimos y creamos los directorios si no existen
    input_dir = os.path.join("data", "input_informes")
    output_dir = os.path.join("data", "output_fhir")
    
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # 3. Obtenemos la lista de todos los archivos válidos en la carpeta
    archivos = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in ('.txt', '.pdf')
    ])

    if not archivos:
        print(f"[!] La carpeta '{input_dir}' está vacía.")
        print("Añade archivos .txt o .pdf con informes médicos para comenzar.")
        return

    print(f"[ℹ️] Se han detectado {len(archivos)} informe(s) médico(s) en la cola de procesamiento.\n")

    # 3. Levantamos el servidor MCP SNOMED UNA SOLA VEZ para toda la sesión.
    #    El servidor corre como subproceso Python y se comunica via stdio MCP.
    #    Al salir del bloque 'with', el subproceso se cierra limpiamente.
    print("Iniciando servidor MCP SNOMED IRBD...")
    with MCPSnomedClient() as mcp:

        # 4. Instanciamos los agentes inyectando el cliente MCP
        print("Inicializando Agentes de IA...")
        agente_ner = AgenteExtractorNER(mcp_client=mcp)
        agente_codificador = AgenteCodificadorCardiologia()

        # 5. Procesamos cada archivo en bucle
        for nombre_archivo in archivos:
            ruta_entrada = os.path.join(input_dir, nombre_archivo)
            nombre_base = os.path.splitext(nombre_archivo)[0]
            ruta_fhir_intermedio = os.path.join(output_dir, f"{nombre_base}_fhir.json")

            procesar_archivo(ruta_entrada, ruta_fhir_intermedio, agente_ner, agente_codificador)

    print("\n" + "="*60)
    print("[🎉] PROCESAMIENTO POR LOTES FINALIZADO CON ÉXITO")
    print("="*60)

if __name__ == "__main__":
    main()