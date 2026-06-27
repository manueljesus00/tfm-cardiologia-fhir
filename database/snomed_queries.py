import pandas as pd
from sqlalchemy import text
from database.connection import get_engine
import re


def extraer_palabras_clave(texto):
    """
    Extrae palabras clave significativas de un texto clínico,
    eliminando palabras comunes y conectores.
    """
    # Palabras a ignorar (stop words clínicas en español)
    palabras_ignorar = {
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'de', 'del', 'al', 'a', 'en', 'con', 'sin', 'por', 'para',
        'no', 'ni', 'o', 'y', 'e', 'que', 'se', 'su', 'sus',
        'tratada', 'tratado', 'conocidos', 'conocidas', 'af', 'disorder'
    }
    
    # Convertir a minúsculas y dividir en palabras
    palabras = re.findall(r'\b\w+\b', texto.lower())
    
    # Filtrar palabras significativas (mínimo 3 caracteres y no en stop words)
    palabras_clave = [
        palabra for palabra in palabras 
        if len(palabra) >= 3 and palabra not in palabras_ignorar
    ]
    
    return palabras_clave


def traducir_terminos_medicos(texto):
    """
    Traduce términos médicos comunes del español al inglés
    para mejorar las búsquedas en SNOMED CT.
    """
    traducciones = {
        'hipertrigliceridemia': 'hypertriglyceridemia',
        'hipercolesterolemia': 'hypercholesterolemia',
        'diabetes': 'diabetes',
        'hipertension': 'hypertension',
        'hipertensiva': 'hypertensive',
        'crisis': 'crisis',
        'infarto': 'infarction',
        'insuficiencia': 'insufficiency',
        'cardiaca': 'cardiac',
        'coronaria': 'coronary',
        'arterial': 'arterial',
        'fibrilacion': 'fibrillation',
        'auricular': 'atrial',
        'ventricular': 'ventricular',
        'isquemica': 'ischemic',
        'aneurisma': 'aneurysm',
        'estenosis': 'stenosis',
        'arritmia': 'arrhythmia',
        'miocardio': 'myocardial',
        'endocardio': 'endocardial',
        'pericardio': 'pericardial',
        'valvular': 'valvular',
        'congenita': 'congenital',
        'aguda': 'acute',
        'cronica': 'chronic'
    }
    
    texto_lower = texto.lower()
    for esp, eng in traducciones.items():
        texto_lower = texto_lower.replace(esp, eng)
    
    return texto_lower

def buscar_concepto_snomed(texto_busqueda, limite=5, edition="es"):
    """
    Busca conceptos SNOMED CT por texto en las descripciones.
    
    Args:
        texto_busqueda: Texto clínico a buscar.
        limite: Número máximo de resultados.
        edition: 'es' para Edición Española (IRBD), 'int' para Edición Internacional.
                 La edición internacional amplía la búsqueda a descripciones en inglés
                 y puede encontrar conceptos no publicados aún en la edición española.
    
    Devuelve una lista de conceptos candidatos con su ID y descripción.
    """
    # Mapa de edición a schema y prefijo de tabla en la IRBD
    EDITION_CONFIG = {
        "es": {
            "concept_table": "snomedct_irbd_snapshot.iesc_concept",
            "description_table": "snomedct_irbd_snapshot.iesd_description",
            "language_filter": "",  # La IRBD ES ya filtra por idioma implícitamente
        },
        "int": {
            "concept_table": "snomedct_irbd_snapshot.iesc_concept",
            "description_table": "snomedct_irbd_snapshot.iesd_description",
            # Sin filtro de languageCode para incluir descripciones 'en' de la edición int.
            "language_filter": "AND d.\"languageCode\" IN ('en', 'es')",
        },
    }
    cfg = EDITION_CONFIG.get(edition, EDITION_CONFIG["es"])
    print(f"  [🌍] Edición SNOMED: {'Española (IRBD)' if edition == 'es' else 'Internacional'}")

    engine = get_engine()
    
    # Traducir términos médicos del español al inglés
    texto_traducido = traducir_terminos_medicos(texto_busqueda)
    print(f"  [🌐] Texto traducido: {texto_traducido}")
    
    # Extraer palabras clave del texto traducido
    palabras_clave = extraer_palabras_clave(texto_traducido)
    
    if not palabras_clave:
        print(f"[⚠️] No se pudieron extraer palabras clave de: '{texto_busqueda}'")
        return []
    
    print(f"  [🔍] Buscando por palabras clave: {', '.join(palabras_clave)}")
    
    # Construir condiciones LIKE para cada palabra clave
    condiciones_like = " AND ".join([
        f"LOWER(d.term) LIKE LOWER(:palabra_{i})" 
        for i in range(len(palabras_clave))
    ])
    
    query = text(f"""
        SELECT DISTINCT 
            c.id as concept_id,
            d.term as description,
            d."languageCode" as language,
            LENGTH(d.term) as term_length
        FROM 
            {cfg["concept_table"]} c
        JOIN 
            {cfg["description_table"]} d 
            ON c.id = d."conceptId"
        WHERE 
            c.active = 1 
            AND d.active = 1
            AND d."typeId" = 900000000000003001
            {cfg["language_filter"]}
            AND ({condiciones_like})
        ORDER BY 
            term_length ASC
        LIMIT :limite
    """)
    
    # Preparar parámetros
    parametros = {f'palabra_{i}': f'%{palabra}%' for i, palabra in enumerate(palabras_clave)}
    parametros['limite'] = limite * 3  # Buscar más candidatos para que el agente elija
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, parametros)
            
            resultados = []
            for row in result:
                resultados.append({
                    'concept_id': str(row.concept_id),
                    'description': str(row.description),
                    'language': str(row.language)
                })
            
            if not resultados:
                print(f"  [⚠️] No se encontraron conceptos SNOMED con todas las palabras clave")
                # Fallback 1: búsqueda permisiva en la misma edición
                resultados = buscar_concepto_snomed_permisivo(palabras_clave, limite * 2, engine, cfg)
                # Fallback 2: si la edición era ES y sigue sin resultados, probar internacional
                if not resultados and edition == "es":
                    print(f"  [🌍] Fallback a Edición Internacional SNOMED CT...")
                    return buscar_concepto_snomed(texto_busqueda, limite, edition="int")
            else:
                print(f"  [✓] Encontrados {len(resultados)} conceptos candidatos")
            
            return resultados
        
    except Exception as e:
        print(f"Error al buscar conceptos SNOMED: {e}")
        import traceback
        traceback.print_exc()
        return []


def buscar_concepto_snomed_permisivo(palabras_clave, limite, engine, cfg=None):
    """
    Búsqueda más permisiva que encuentra conceptos que contienen 
    al menos una de las palabras clave (en lugar de todas).
    """
    if not palabras_clave:
        return []

    if cfg is None:
        cfg = {
            "concept_table": "snomedct_irbd_snapshot.iesc_concept",
            "description_table": "snomedct_irbd_snapshot.iesd_description",
            "language_filter": "",
        }
    
    print(f"  [🔍] Búsqueda permisiva con cualquiera de las palabras clave...")
    
    # Construir condiciones LIKE con OR
    condiciones_like = " OR ".join([
        f"LOWER(d.term) LIKE LOWER(:palabra_{i})" 
        for i in range(len(palabras_clave))
    ])
    
    query = text(f"""
        SELECT DISTINCT 
            c.id as concept_id,
            d.term as description,
            d."languageCode" as language,
            LENGTH(d.term) as term_length
        FROM 
            {cfg["concept_table"]} c
        JOIN 
            {cfg["description_table"]} d 
            ON c.id = d."conceptId"
        WHERE 
            c.active = 1 
            AND d.active = 1
            AND d."typeId" = 900000000000003001
            {cfg["language_filter"]}
            AND ({condiciones_like})
        ORDER BY 
            term_length ASC
        LIMIT :limite
    """)
    
    parametros = {f'palabra_{i}': f'%{palabra}%' for i, palabra in enumerate(palabras_clave)}
    parametros['limite'] = limite
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, parametros)
            
            resultados = []
            for row in result:
                resultados.append({
                    'concept_id': str(row.concept_id),
                    'description': str(row.description),
                    'language': str(row.language)
                })
            
            print(f"  [✓] Encontrados {len(resultados)} conceptos en búsqueda permisiva")
            return resultados
        
    except Exception as e:
        print(f"Error en búsqueda permisiva: {e}")
        return []


def validar_concepto_snomed(concepto_id):
    """
    Verifica si un concepto SNOMED CT existe y está activo en la base de datos.
    Devuelve True si existe, False en caso contrario.
    """
    if not concepto_id:
        return False
        
    engine = get_engine()
    
    query = text("""
        SELECT COUNT(*) as existe
        FROM snomedct_irbd_snapshot.iesc_concept
        WHERE id = :concepto_id AND active = 1
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {'concepto_id': int(concepto_id)})
            row = result.fetchone()
            return row.existe > 0
        
    except Exception as e:
        print(f"Error al validar concepto SNOMED: {e}")
        return False


def obtener_reglas_mapeo_cie10(concepto_snomed_id):
    """
    Consulta la IRBD local para obtener las reglas de mapeo (Extended Map RefSet)
    de un concepto SNOMED CT hacia CIE-10 (ICD-10).
    """
    # Validaciones del input
    if not concepto_snomed_id or concepto_snomed_id == 'None':
        print("No se proporcionó un código SNOMED válido")
        return []
        
    try:
        concepto_id_int = int(concepto_snomed_id)
    except (ValueError, TypeError):
        print(f"El código SNOMED '{concepto_snomed_id}' no es un número válido")
        return []
        
    engine = get_engine()
    
    # En la IRBD del Ministerio, el Extended Map Refset está en el schema snomedct_irbd_snapshot
    # con el nombre iesr_extendedmap (International Edition Spanish Release)
    query = text("""
        SELECT 
            "referencedComponentId", 
            "mapGroup", 
            "mapPriority", 
            "mapRule", 
            "mapAdvice", 
            "mapTarget", 
            "mapCategoryId"
        FROM 
            snomedct_irbd_snapshot.iesr_extendedmap
        WHERE 
            active = 1 
            AND "referencedComponentId" = :concepto_id
        ORDER BY 
            "mapGroup" ASC, 
            "mapPriority" ASC
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {'concepto_id': int(concepto_snomed_id)})
            
            resultados = []
            for row in result:
                resultados.append({
                    'referencedComponentId': str(row.referencedComponentId),
                    'mapGroup': int(row.mapGroup),
                    'mapPriority': int(row.mapPriority),
                    'mapRule': str(row.mapRule) if row.mapRule else '',
                    'mapAdvice': str(row.mapAdvice) if row.mapAdvice else '',
                    'mapTarget': str(row.mapTarget) if row.mapTarget else '',
                    'mapCategoryId': str(row.mapCategoryId)
                })
            
            if not resultados:
                print(f"No se encontraron reglas de mapeo a CIE-10 para el ID {concepto_snomed_id}")
            
            return resultados
        
    except Exception as e:
        print(f"Error al consultar la IRBD local: {e}")
        import traceback
        traceback.print_exc()
        return []