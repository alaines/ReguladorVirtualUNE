"""
Módulo Generador de Respuestas UNE
Genera respuestas a los diferentes códigos del protocolo
"""

import logging
from datetime import datetime
from .protocolo_une import (
    ProtocoloUNE, 
    codificar_byte_une, 
    construir_mensaje
)

logger = logging.getLogger(__name__)


class GeneradorRespuestas:
    """Genera respuestas según el protocolo UNE 135401-4"""
    
    @staticmethod
    def respuesta_sincronizacion(estado, subregulador_id):
        """
        Respuesta al código 0x91 - Sincronización (Plan en curso)
        Formato según UNE 135401-4:
        - Byte 0: Nº de plan (1-based index para compatibilidad con centrales)
        - Byte 1: Hora inicio del plan
        - Byte 2: Minuto inicio del plan
        - Byte 3: Segundo inicio del plan
        - Byte 4: Fase normal (número de fase actual)
        - Byte 5-6: Tiempo transcurrido de ciclo (MSB, LSB) - 2 bytes
        - Byte 7: Tiempo que resta de la fase (modo A, opcional en modo B)
        """
        ahora = datetime.now()
        
        # Obtener offset de plan ID desde configuración
        plan_offset = estado.config.get('comunicacion', {}).get('plan_id_offset', 0)
        
        # CONVERSIÓN DE ID DE PLAN PARA REPORTE:
        # Internamente usamos IDs 129, 131, 132, 133...
        # Pero al reportar a la central, enviamos 1, 3, 4, 5... (restando 128)
        # Esto es porque el protocolo UNE codifica con bit 7, y 0x83 = plan 3 codificado
        plan_para_enviar = estado.plan_actual - 128 + plan_offset
        if plan_para_enviar < 0:
            plan_para_enviar = estado.plan_actual  # Fallback si el plan es menor a 128
        
        logger.debug(f"Respuesta 0x91: plan_interno={estado.plan_actual}, plan_para_central={plan_para_enviar}")
        
        # Tiempo de ciclo en 2 bytes (MSB, LSB) con bit 7 activo
        ciclo_msb = (estado.ciclo_actual >> 7) & 0x7F
        ciclo_lsb = estado.ciclo_actual & 0x7F
        
        # Calcular tiempo restante de fase (aproximado)
        tiempo_resta = 0  # Por defecto 0 en modo B
        
        datos = bytes([
            codificar_byte_une(plan_para_enviar),  # Plan ID con offset aplicado
            codificar_byte_une(ahora.hour),      # Hora inicio
            codificar_byte_une(ahora.minute),    # Minuto inicio  
            codificar_byte_une(ahora.second),    # Segundo inicio
            codificar_byte_une(estado.fase_actual),  # Fase normal
            codificar_byte_une(ciclo_msb),       # Tiempo ciclo MSB
            codificar_byte_une(ciclo_lsb),       # Tiempo ciclo LSB
            codificar_byte_une(tiempo_resta)     # Tiempo resta fase
        ])
        
        logger.debug(f"Respuesta 0x91: plan={estado.plan_actual} (enviando como {plan_para_enviar}), hora={ahora.hour}:{ahora.minute}:{ahora.second}, "
                     f"fase={estado.fase_actual}, ciclo={estado.ciclo_actual}")
        return construir_mensaje(subregulador_id, ProtocoloUNE.SINCRONIZACION, datos)
    
    @staticmethod
    def respuesta_alarmas(estado, subregulador_id):
        """
        Respuesta al código 0xB4 - Alarmas (Estado del regulador)
        Formato según UNE 135401-4 - 4 bytes de alarmas:
        
        Byte 1: Incompatibilidad(1), Sincronización(2), Transmisión(4),
                Grupo averiado(8), Lámpara fundida(16), Detector averiado(32), Puerta abierta(64)
        
        Byte 2: Control manual(1), Autodiagnóstico(2), Reset(4),
                Reloj sin inicializar(8), Temperatura(16), Check datos(32), Tensión(64)
        
        Byte 3: Grabación local(1), Grabación ordenador(2), Acceso incorrecto(4), (reservados)
        
        Byte 4: Alarmas programadas (8 bits)
        """
        logger.info("Generando respuesta 0xB4 (Alarmas)")
        
        # Byte 1: Alarmas principales con bit 7 activo
        byte1 = 0x80
        if estado.alarma_roja:
            byte1 |= 0x01  # Incompatibilidad
        if estado.alarma_lampara:
            byte1 |= 0x10  # Lámpara fundida
        if estado.alarma_conflicto:
            byte1 |= 0x01  # También incompatibilidad
        
        # Byte 2: Más alarmas (todos en 0 = sin alarmas) + bit 7
        byte2 = 0x80
        
        # Byte 3: Más alarmas + bit 7
        byte3 = 0x80
        # Indicar que hay comunicación con ordenador si modo es centralizado
        if estado.modo_control == 2:
            byte3 |= 0x10  # Bit 4 indica algo relacionado con ordenador
        
        # Byte 4: Alarmas programadas (0 = ninguna) + bit 7
        byte4 = 0x80
        
        datos = bytes([byte1, byte2, byte3, byte4])
        
        return construir_mensaje(subregulador_id, ProtocoloUNE.ALARMAS, datos)
    
    @staticmethod
    def respuesta_configuracion(estado, subregulador_id):
        """
        Respuesta al código 0xB5 - Parámetros de configuración
        IMPORTANTE: El regulador real responde con ACK simple (sin datos).
        """
        logger.info("Generando respuesta 0xB5 (Parámetros configuración) - ACK simple")
        # Respuesta vacía como el regulador real
        return construir_mensaje(subregulador_id, ProtocoloUNE.CONFIGURACION, b'')
    
    @staticmethod
    def respuesta_tablas_programacion(estado, subregulador_id):
        """
        Respuesta al código 0xB6 - Tablas de programación
        IMPORTANTE: El regulador real responde con ACK simple (sin datos).
        Enviar datos completos hace que la central mapee mal los planes.
        """
        logger.info("Generando respuesta 0xB6 (Tablas de programación) - ACK simple")
        # Respuesta vacía como el regulador real
        return construir_mensaje(subregulador_id, ProtocoloUNE.TABLAS_PROGRAMACION, b'')
    
    @staticmethod
    def respuesta_incompatibilidades(estado, subregulador_id):
        """
        Respuesta al código 0xB7 - Incompatibilidades
        Respuesta vacía (sin datos adicionales)
        """
        return construir_mensaje(subregulador_id, ProtocoloUNE.INCOMPATIBILIDADES, b'')
    
    @staticmethod
    def mensaje_cambio_fase(fase_entrante, subregulador_id):
        """
        Mensaje 0xD5 - Impulso de cambio de fase (envío espontáneo)
        """
        datos = bytes([codificar_byte_une(fase_entrante)])
        logger.info(f"Generando mensaje espontáneo 0xD5: fase={fase_entrante}")
        return construir_mensaje(subregulador_id, ProtocoloUNE.CAMBIO_FASE, datos)
    
    @staticmethod
    def mensaje_estado_grupos(estado, subregulador_id):
        """
        Mensaje 0xB9 - Estado de todos los grupos (envío espontáneo)
        Formato: 1 byte por grupo con valores protocolo UNE
        Confirmado según captura real del regulador:
        - 0=Apagado
        - 1=Rojo
        - 4=Ámbar
        - 12=Ámbar intermitente (bit 3 = intermitente)
        - 16=Verde
        """
        estados_raw = estado.get_estado_grupos()
        
        # Mapear códigos UNE internos a valores protocolo B9
        # UNE interno: 0=Apagado, 1=Verde, 2=Ámbar, 3=Rojo, 4=Rojo Int, 5=Verde Int, 6=Ámbar Int
        # Protocolo B9: 0=Apagado, 1=Rojo, 4=Ámbar, 12=Ámbar Int, 16=Verde
        # Según captura real: en intermitente el regulador envía 0x8C = 12 decimal
        def mapear_estado(e):
            if e == 0:  # Apagado
                return 0
            elif e == 1:  # Verde
                return 16
            elif e == 5:  # Verde intermitente
                return 24  # 16 + 8 (bit 3 intermitente)
            elif e == 2:  # Ámbar
                return 4
            elif e == 6:  # Ámbar intermitente (CONFIRMADO: 0x8C = 12 en captura real)
                return 12  # 4 + 8 (bit 3 intermitente)
            elif e == 3:  # Rojo
                return 1
            elif e == 4:  # Rojo intermitente
                return 9   # 1 + 8 (bit 3 intermitente)
            else:
                return 1  # Por defecto rojo
        
        estados = [mapear_estado(e) for e in estados_raw]
        
        # Formato: 1 byte por grupo (codificado con bit 7)
        datos_bytes = [codificar_byte_une(e) for e in estados]
        
        datos = bytes(datos_bytes)
        logger.debug(f"Generando mensaje 0xB9: estados_raw={estados_raw}, mapeados={estados}, bytes={[hex(b) for b in datos_bytes]}")
        return construir_mensaje(subregulador_id, ProtocoloUNE.ESTADO_GRUPOS, datos)
    
    @staticmethod
    def mensaje_estados(estado, subregulador_id):
        """
        Mensaje 0xD4 - Estados del regulador (envío espontáneo)
        
        Según norma UNE 135401-4, directiva Estados (0x54/0xD4) tiene 4 bytes:
        
        BYTE 1 - Estado de representación:
          0 = Apagado, 1 = Intermitente, 2 = Colores
        
        BYTE 2 - Selección de planes:
          0 = Control LOCAL de planes (horario)
          2 = Control externo/ORDENADOR
          
        BYTE 3 - Coordinación/Control:
          0 = Coordinado señal externa
          1 = Coordinado reloj interno (LOCAL)
          3 = Control externo (ORDENADOR)
        
        BYTE 4 - Método de control:
          0 = Tiempos fijos
          1 = Semiactuado
          2 = Actuado total
        """
        # Byte 1: Estado de representación
        byte1_repr = estado.estado_representacion & 0x07
        
        # Byte 2: Selección de planes
        # Según análisis del log real del regulador:
        # - 0x82 (→ 0x02) = Control externo (ORDENADOR)
        # - 0x80 (→ 0x00) = Control local (LOCAL)
        if estado.modo_control == 2:  # Ordenador/Centralizado
            byte2_planes = 2  # Control externo (según log real)
        else:  # Local o Manual
            byte2_planes = 0  # Control local de planes
        
        # Byte 3: Coordinación/Control
        # Según análisis del log real:
        # - 0x83 (→ 0x03) = Control externo cuando ORDENADOR
        # - 0x81 (→ 0x01) = Coordinado reloj interno cuando LOCAL
        if estado.modo_control == 2:  # Ordenador/Centralizado
            byte3_coord = 3  # Control externo (según log real)
        elif estado.modo_control == 3:  # Manual
            byte3_coord = 8  # Control manual
        else:  # Local
            byte3_coord = 1  # Coordinado con reloj interno
        
        # Byte 4: Método de control (tiempos fijos por defecto)
        byte4_metodo = 0
        
        print(f"[DEBUG] Generando mensaje 0xD4: modo_control={estado.modo_control} (1=LOCAL, 2=ORDENADOR, 3=MANUAL), "
            f"repr={byte1_repr}, planes={byte2_planes}, coord={byte3_coord}, metodo={byte4_metodo}")

        datos = bytes([
            codificar_byte_une(byte1_repr),
            codificar_byte_une(byte2_planes),
            codificar_byte_une(byte3_coord),
            codificar_byte_une(byte4_metodo)
        ])
        
        logger.info(f"Generando mensaje 0xD4 Estados: modo={estado.modo_control}, repr={estado.estado_representacion}, "
                    f"bytes=[{byte1_repr}, {byte2_planes}, {byte3_coord}, {byte4_metodo}]")
        return construir_mensaje(subregulador_id, ProtocoloUNE.ESTADOS, datos)
    
    @staticmethod
    def mensaje_cambio_modo(estado, subregulador_id):
        """
        Mensaje 0xB3 - Respuesta de detectores (datos externos)
        
        NOTA: Según UNE 135401-4, 0xB3 es para detectores físicos, no para estados.
        Este método ahora llama a mensaje_estados para mantener compatibilidad.
        """
        # Redirigir a mensaje_estados (0xD4) que es el correcto para estados
        return GeneradorRespuestas.mensaje_estados(estado, subregulador_id)
    
    @staticmethod
    def respuesta_mando_directo(estado, subregulador_id):
        """
        Respuesta al código 0xDB - Estado de mando directo
        """
        datos = bytes([codificar_byte_une(e) for e in estado.estado_grupos])
        return construir_mensaje(subregulador_id, ProtocoloUNE.CONSULTA_MANDO_DIRECTO, datos)
    
    @staticmethod
    def respuesta_trcam(estado):
        """
        Mensaje TRCAM - Cambio en detectores (tiempo real)
        """
        datos = bytes([codificar_byte_une(c) for c in estado.contador_detectores])
        return construir_mensaje(0, ProtocoloUNE.DETECTORES_PRESENCIA, datos)
