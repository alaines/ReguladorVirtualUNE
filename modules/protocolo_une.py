"""
Módulo de Protocolo UNE 135401-4
Constantes, códigos y funciones de bajo nivel del protocolo
"""

# ============================================================================
# CONSTANTES DEL PROTOCOLO
# ============================================================================

class ProtocoloUNE:
    """Constantes del protocolo UNE 135401-4"""
    
    # Caracteres de control
    STX = bytes([0x02])  # Start of Text
    ETX = bytes([0x03])  # End of Text
    EOT = bytes([0x04])  # End of Transmission
    ACK = bytes([0x06])  # Acknowledge
    NAK = bytes([0x15])  # Negative Acknowledge
    DLE = bytes([0x10])  # Data Link Escape
    
    # Códigos de mensaje - Consultas y Órdenes
    SINCRONIZACION = 0x91         # Sincronización (petición y respuesta)
    SELECCION_PLAN = 0x92         # Selección de plan
    INCOMPATIBILIDADES = 0xB7     # Tabla de incompatibilidades
    ALARMAS = 0xB4                # Estado de alarmas
    CONFIGURACION = 0xB5          # Parámetros de configuración
    TABLAS_PROGRAMACION = 0xB6    # Tablas de programación
    ESTADO_GRUPOS = 0xB9          # Estado de grupos semafóricos
    CAMBIO_MODO = 0xB3            # Cambio de modo de control
    DATOS_TRAFICO = 0x94          # Datos de tráfico
    
    # Códigos de mensaje - Órdenes de control
    PUESTA_EN_HORA = 0xD2         # Puesta en hora
    SELECCION_PLAN_D1 = 0xD1      # Selección de plan (orden)
    ESTADOS = 0xD4                # Estados (representación)
    CAMBIO_FASE = 0xD5            # Cambio de fase (espontáneo)
    
    # Códigos de mensaje - Mando directo
    MANDO_DIRECTO = 0xDC          # Mando directo de grupos
    CONSULTA_MANDO_DIRECTO = 0xDB # Consulta estado mando directo
    
    # Códigos de mensaje - Detectores
    DETECTORES_PRESENCIA = 0xA3   # TRCAM - Detectores de presencia

    # Diccionario de nombres de códigos (implementados)
    # Incluye tanto códigos codificados (0x9X, 0xBX, 0xDX) como decodificados (0x1X, 0x3X, 0x5X)
    NOMBRES_CODIGOS = {
        # Códigos codificados (con bit 7 activado)
        0x91: "SINCRONIZACION",
        0x92: "SELECCION_PLAN",
        0x94: "DATOS_TRAFICO",
        0xB3: "CAMBIO_MODO",
        0xB4: "ALARMAS",
        0xB5: "CONFIGURACION",
        0xB6: "TABLAS_PROGRAMACION",
        0xB7: "INCOMPATIBILIDADES",
        0xB9: "ESTADO_GRUPOS",
        0xD1: "SELECCION_PLAN_D1",
        0xD2: "PUESTA_EN_HORA",
        0xD4: "ESTADOS",
        0xD5: "CAMBIO_FASE",
        0xDB: "CONSULTA_MANDO_DIRECTO",
        0xDC: "MANDO_DIRECTO",
        0xA3: "DETECTORES_PRESENCIA",
        # Códigos decodificados (sin bit 7) - para usar con obtener_nombre_codigo()
        0x11: "SINCRONIZACION",        # 0x91 decodificado
        0x12: "SELECCION_PLAN",        # 0x92 decodificado
        0x14: "DATOS_TRAFICO",         # 0x94 decodificado
        0x33: "CAMBIO_MODO",           # 0xB3 decodificado
        0x34: "ALARMAS",               # 0xB4 decodificado
        0x35: "CONFIGURACION",         # 0xB5 decodificado
        0x36: "TABLAS_PROGRAMACION",   # 0xB6 decodificado
        0x37: "INCOMPATIBILIDADES",    # 0xB7 decodificado
        0x39: "ESTADO_GRUPOS",         # 0xB9 decodificado
        0x51: "SELECCION_PLAN_D1",     # 0xD1 decodificado
        0x52: "PUESTA_EN_HORA",        # 0xD2 decodificado
        0x54: "ESTADOS",               # 0xD4 decodificado
        0x55: "CAMBIO_FASE",           # 0xD5 decodificado
        0x5B: "CONSULTA_MANDO_DIRECTO",# 0xDB decodificado
        0x5C: "MANDO_DIRECTO",         # 0xDC decodificado
        0x23: "DETECTORES_PRESENCIA",  # 0xA3 decodificado
        0x20: "PETICION_ESTADO"        # 0x20 (DET)
    }
    
    # TABLA COMPLETA DE CÓDIGOS SEGÚN NORMA UNE 135401-4
    # Para comparar con códigos no identificados
    CODIGOS_NORMA_UNE = {
        # Mensajes especiales de 1 byte
        0x02: "STX - Inicio de transmisión",
        0x03: "ETX - Fin de transmisión",
        0x04: "EOT - Fin de transmisión parcial",
        0x06: "ACK - Acuse recibo positivo",
        0x13: "DC3/XOFF - Comunicaciones OFF",
        0x15: "NACK - Acuse recibo negativo",
        0x20: "DET - Petición detectores/estado",
        0x30: "TRCAM - Estado detectores tiempo real",
        0x33: "HTR - Hora tiempo real",
        # Comandos de control (0x10-0x1F)
        0x10: "CPL - Cambio de plan de funcionamiento",
        0x11: "CFI - Cambio funcionamiento intermitente",
        0x12: "CFF - Cambio tiempos fijos",
        0x13: "APA - Apagado del regulador",
        0x14: "ACT - Activación del regulador",
        # Directivas de control codificadas (0x50-0x5F)
        0x50: "PLR - Plan registrable",
        0x51: "SEP - Selección de plan",
        0x52: "PHF - Puesta en hora y fecha",
        0x54: "EST - Estados (control)",
        0x56: "MDS - Mando directo salidas",
        # Consultas/Información (0x90-0x9F, 0xB0-0xBF)
        0x91: "SNC - Sincronización",
        0x92: "SEP - Selección plan (consulta)",
        0x94: "DTR - Datos tráfico",
        0xA3: "DFP - Detectores físicos presencia",
        0xB0: "DFP - Detectores físicos presencia",
        0xB1: "DFC - Detector físico N (contaje)",
        0xB3: "CMC - Cambio modo control",
        0xB4: "ALR - Alarmas",
        0xB5: "CFG - Configuración",
        0xB6: "TPR - Tablas programación",
        0xB7: "INC - Incompatibilidades",
        0xB9: "EGR - Estado grupos",
        0xC9: "PLN - Plan en curso",
        # Directivas respuesta (0xD0-0xDF)
        0xD0: "PLR - Plan registrable (respuesta)",
        0xD1: "SEP - Selección plan (respuesta)",
        0xD2: "PHF - Puesta hora (respuesta)",
        0xD3: "DTR - Detectores tiempo real",
        0xD4: "EST - Estados (respuesta)",
        0xD5: "CFA - Cambio fase",
        0xD6: "MDS - Mando directo (respuesta)",
        0xDB: "CRT - Cruce tiempo real",
        0xDC: "CTR - Cancelación tiempo real",
        0xDD: "BAL - Borrado alarmas"
    }
    
    @staticmethod
    def obtener_nombre_codigo(codigo_decodificado):
        """Obtiene el nombre del código y si está en la norma UNE
        
        El código decodificado puede coincidir con códigos UNE diferentes:
        - 0x11 decodificado puede venir de 0x91 (Sincronización) codificado
        - 0x11 sin codificar es CFI (Cambio funcionamiento intermitente)
        
        Priorizamos NOMBRES_CODIGOS que indica lo que tenemos implementado.
        """
        nombre = ProtocoloUNE.NOMBRES_CODIGOS.get(codigo_decodificado)
        
        # Para la norma, buscamos primero el código codificado (añadiendo bit 7)
        codigo_codificado = codigo_decodificado | 0x80
        en_norma = ProtocoloUNE.CODIGOS_NORMA_UNE.get(codigo_codificado)
        
        # Si no está en la norma como codificado, buscar como decodificado
        if en_norma is None:
            en_norma = ProtocoloUNE.CODIGOS_NORMA_UNE.get(codigo_decodificado)
        
        return {
            'implementado': nombre is not None,
            'nombre': nombre if nombre else "NO IMPLEMENTADO",
            'en_norma': en_norma is not None,
            'nombre_norma': en_norma if en_norma else "NO ENCONTRADO EN NORMA UNE",
            'codigo': codigo_decodificado
        }


# ============================================================================
# FUNCIONES DE CODIFICACIÓN/DECODIFICACIÓN
# ============================================================================

def codificar_byte_une(valor):
    """
    Codifica un valor activando el bit 7 (como regulador real)
    Ejemplo: 130 (0x82) → 0x82 | 0x80 = 0x82 (ya tiene bit 7)
             2 → 0x02 | 0x80 = 0x82
    """
    return (valor & 0x7F) | 0x80


def decodificar_byte_une(byte):
    """
    Decodifica un byte quitando el bit 7
    Ejemplo: 0x82 → 0x02 (valor 2)
    """
    return byte & 0x7F


# ============================================================================
# FUNCIONES DE CHECKSUM
# ============================================================================

def calcular_checksum(datos):
    """
    Calcula checksum XOR con bit 7 activo (como regulador real)
    """
    checksum = 0
    for byte in datos:
        checksum ^= byte
    return bytes([checksum | 0x80])  # Activar bit 7


def verificar_checksum(datos, checksum_recibido):
    """
    Verifica el checksum intentando varios métodos
    Retorna: (es_valido, checksum_calculado, metodo_usado)
    """
    # Calcular checksum con bit 7 (como regulador real)
    checksum_calculado = calcular_checksum(datos)[0]
    if checksum_recibido == checksum_calculado:
        return True, checksum_calculado, "con bit 7 (regulador real)"
    
    # Método alternativo sin bit 7 (para compatibilidad)
    checksum_sin_bit7 = (checksum_calculado & 0x7F)
    if checksum_recibido == checksum_sin_bit7:
        return True, checksum_sin_bit7, "sin bit 7"
    
    return False, checksum_calculado, "ninguno"


# ============================================================================
# FUNCIONES DE CONSTRUCCIÓN DE MENSAJES
# ============================================================================

def construir_mensaje(subregulador, codigo, datos=b''):
    """
    Construye un mensaje según el protocolo UNE
    Formato: STX + Subregulador + Código + Datos + Checksum + ETX
    """
    cuerpo = bytes([subregulador, codigo]) + datos
    checksum = calcular_checksum(cuerpo)
    mensaje = ProtocoloUNE.STX + cuerpo + checksum + ProtocoloUNE.ETX
    return mensaje


def separar_mensajes(data):
    """
    Separa mensajes concatenados en una trama
    Retorna lista de mensajes individuales
    """
    mensajes = []
    buffer = data
    
    while len(buffer) >= 5:  # Mínimo: STX + SUB + COD + CHK + ETX
        # Buscar STX
        inicio = buffer.find(ProtocoloUNE.STX)
        if inicio == -1:
            break
        
        # Buscar ETX después del STX
        fin = buffer.find(ProtocoloUNE.ETX, inicio)
        if fin == -1:
            # Buscar EOT como alternativa
            fin = buffer.find(ProtocoloUNE.EOT, inicio)
            if fin == -1:
                break
        
        # Extraer mensaje
        mensaje = buffer[inicio:fin+1]
        mensajes.append(mensaje)
        
        # Avanzar buffer
        buffer = buffer[fin+1:]
    
    return mensajes


def decodificar_mensaje(mensaje):
    """
    Decodifica un mensaje UNE
    Retorna: (subregulador, codigo, datos, checksum_valido)
    """
    if len(mensaje) < 5:
        return None, None, None, False
    
    if mensaje[0] != ProtocoloUNE.STX[0]:
        return None, None, None, False
    
    if mensaje[-1] not in [ProtocoloUNE.ETX[0], ProtocoloUNE.EOT[0]]:
        return None, None, None, False
    
    subregulador = mensaje[1]
    codigo = mensaje[2]
    checksum_recibido = mensaje[-2]
    datos = mensaje[3:-2] if len(mensaje) > 5 else b''
    
    # Verificar checksum
    cuerpo = mensaje[1:-2]
    valido, _, _ = verificar_checksum(cuerpo, checksum_recibido)
    
    return subregulador, codigo, datos, valido
