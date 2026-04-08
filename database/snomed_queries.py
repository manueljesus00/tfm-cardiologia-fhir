import pandas as pd
from database.connection import get_engine

def obtener_reglas_mapeo_cie10(concepto_snomed_id):
    """
    Consulta la IRBD local para obtener las reglas de mapeo (Extended Map RefSet)
    de un concepto SNOMED CT hacia CIE-10 (ICD-10).
    """
    engine = get_engine()
    
    # En la IRBD del Ministerio, el Extended Map Refset suele estar en una tabla
    # llamada 'extendedmaprefset' o unificada en la tabla global de refsets.
    # Esta query asume el estándar RF2 adaptado a SQL:
    query = f"""
        SELECT 
            referencedComponentId, 
            mapGroup, 
            mapPriority, 
            mapRule, 
            mapAdvice, 
            mapTarget, 
            mapCategoryId
        FROM 
            extendedmaprefset  -- Ajustar al nombre de tabla exacto de la IRBD
        WHERE 
            active = '1' 
            AND referencedComponentId = '{concepto_snomed_id}'
            AND mapTarget LIKE 'I%' -- Filtro de cardiología (CIE-10 Capítulo IX)
        ORDER BY 
            mapGroup ASC, 
            CAST(mapPriority AS INTEGER) ASC;
    """
    
    try:
        # Usamos Pandas solo para extraer cómodamente los resultados de la BBDD
        df_reglas = pd.read_sql(query, engine)
        
        if df_reglas.empty:
            print(f"No se encontraron reglas de mapeo a CIE-10 para el ID {concepto_snomed_id}")
            return []
            
        # Convertimos a la lista de diccionarios que espera tu agente LLM
        return df_reglas.to_dict('records')
        
    except Exception as e:
        print(f"Error al consultar la IRBD local: {e}")
        return []