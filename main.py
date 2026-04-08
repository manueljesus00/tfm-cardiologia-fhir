import os
import json
import config
from fase1_homogeneizacion import AgenteExtractorNER, crear_fhir_base
from fase2_inferencia_cie10 import extraer_contexto_desde_fhir, AgenteCodificadorCardiologia
from database.snomed_queries import obtener_reglas_mapeo_cie10

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
        print(f"[!] Omitiendo {os.path.basename(ruta_entrada)} por fallo en Fase 1.")
        return

    print(f"[*] Diagnóstico extraído: {datos_extraidos.get('diagnostico', {}).get('texto')}")
    print(f"[*] Código SNOMED CT: {datos_extraidos.get('diagnostico', {}).get('snomed_id')}")
    
    # Construimos y guardamos el FHIR
    bundle_fhir = crear_fhir_base(datos_extraidos)
    with open(ruta_fhir_intermedio, 'w', encoding='utf-8') as f:
        f.write(bundle_fhir.json(indent=2))
        
    print(f"[✅] Registro FHIR R4 guardado en: {ruta_fhir_intermedio}")

    # ==========================================================
    # FASE 2: INFERENCIA CIE-10 (FHIR R4 -> CIE-10-ES)
    # ==========================================================
    print("\n--- FASE 2: INFERENCIA A CIE-10-ES ---")
    
    contexto_fhir = extraer_contexto_desde_fhir(ruta_fhir_intermedio)
    snomed_id = contexto_fhir.get('snomed_id')
    
    if not snomed_id:
        print(f"[!] No se encontró un SNOMED ID válido en el registro FHIR para este paciente.")
        return

    reglas_bbdd = obtener_reglas_mapeo_cie10(snomed_id)
    if not reglas_bbdd:
        print(f"[!] No se encontraron reglas de la OMS en BBDD para el concepto {snomed_id}.")
        return

    resultado_cie10 = agente_codificador.procesar_historial(contexto_fhir['resumen_razonamiento'], reglas_bbdd)
    
    print(f"\n[✅] DICTAMEN FINAL PARA {os.path.basename(ruta_entrada)}:")
    print(json.dumps(resultado_cie10, indent=2, ensure_ascii=False))


def main():
    # 1. Definimos y creamos los directorios si no existen
    input_dir = os.path.join("data", "input_informes")
    output_dir = os.path.join("data", "output_fhir")
    
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # 2. Obtenemos la lista de todos los archivos válidos en la carpeta
    archivos = [f for f in os.listdir(input_dir) if f.lower().endswith(('.txt', '.pdf'))]

    if not archivos:
        print(f"[!] La carpeta '{input_dir}' está vacía.")
        print("Añade archivos .txt o .pdf con informes médicos para comenzar.")
        return

    print(f"[ℹ️] Se han detectado {len(archivos)} informe(s) médico(s) en la cola de procesamiento.\n")

    # 3. Instanciamos los agentes UNA SOLA VEZ para optimizar recursos
    print("Inicializando Agentes de IA...")
    agente_ner = AgenteExtractorNER()
    agente_codificador = AgenteCodificadorCardiologia()

    # 4. Procesamos cada archivo en bucle
    for nombre_archivo in archivos:
        ruta_entrada = os.path.join(input_dir, nombre_archivo)
        
        # Generamos el nombre de salida dinámicamente (ej. juan_perez_fhir.json)
        nombre_base = os.path.splitext(nombre_archivo)[0]
        ruta_fhir_intermedio = os.path.join(output_dir, f"{nombre_base}_fhir.json")

        procesar_archivo(ruta_entrada, ruta_fhir_intermedio, agente_ner, agente_codificador)

    print("\n" + "="*60)
    print("[🎉] PROCESAMIENTO POR LOTES FINALIZADO CON ÉXITO")
    print("="*60)

if __name__ == "__main__":
    main()