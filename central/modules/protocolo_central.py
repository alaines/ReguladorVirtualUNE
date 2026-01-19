"""
Protocolo UNE 135401-4 - Lado Central
Construcción y envío de comandos al regulador
"""

import logging

logger = logging.getLogger('Central.Protocolo')


class ProtocoloCentral:
    """Implementa el protocolo UNE desde el lado de la central"""
    
    # Constantes del protocolo
    STX = 0x02
    ETX = 0x03
    EOT = 0x04
    ACK = 0x06
    NACK = 0x15
    DC1 = 0x11  # XON - Activar comunicaciones
    DC3 = 0x13  # XOFF - Desactivar comunicaciones
    
    # Códigos de función principales
    CODIGOS = {
        # Consultas
        'SINCRONIZACION': 0x91,     # Sincronización (hora, plan, ciclo)
        'ESTADO_ALARMAS': 0xB4,     # Estado y alarmas
        'CONFIG': 0xB5,             # Parámetros de configuración
        'TABLAS': 0xB6,             # Tablas de programación
        'INCOMPATIBILIDADES': 0xB7, # Incompatibilidades
        'DATOS_TRAFICO': 0x94,      # Datos de tráfico
        
        # Control
        'SELECCION_PLAN': 0xD1,     # Selección de plan (0x51 pregunta, 0xD1 envío)
        'PUESTA_HORA': 0xD2,        # Puesta en hora (0x52 pregunta, 0xD2 envío)
        'ESTADOS': 0xD4,            # Estados del regulador (0x54 pregunta, 0xD4 envío)
        'CAMBIO_FASE': 0xD5,        # Cambio de fase
        'MANDO_SALIDAS': 0xD6,      # Mando directo salidas
        'DETECTORES_TR': 0xD3,      # Detectores tiempo real
        'CANCELAR_TR': 0xDC,        # Cancelar tiempo real
        'BORRAR_ALARMAS': 0xDD,     # Borrado de alarmas
        
        # Petición detectores
        'DET': 0x20,                # Petición detectores
    }
    
    # Valores para estado de representación (0xD4)
    ESTADO_REPR = {
        'APAGADO': 0x00,
        'INTERMITENTE': 0x01,
        'COLORES': 0x02
    }
    
    def __init__(self):
        pass
    
    @staticmethod
    def codificar_byte_une(valor):
        """Codifica un byte según UNE (bit 7 activo)"""
        return (valor | 0x80) & 0xFF
    
    @staticmethod
    def decodificar_byte_une(byte):
        """Decodifica un byte UNE (quita bit 7)"""
        return byte & 0x7F
    
    @staticmethod
    def calcular_checksum(datos):
        """
        Calcula checksum XOR de todos los bytes
        Solo afecta a los 7 bits de menor peso de cada byte
        """
        checksum = 0
        for byte in datos:
            checksum ^= (byte & 0x7F)
        return checksum & 0x7F
    
    def construir_mensaje(self, subregulador, codigo, datos=None):
        """
        Construye un mensaje según el protocolo UNE
        
        Args:
            subregulador: ID del subregulador destino (128 o 129)
            codigo: Código de función
            datos: Lista de bytes de datos (opcional)
        
        Returns:
            bytes: Mensaje completo con STX, checksum y ETX
        """
        mensaje = [self.STX, subregulador, codigo]
        
        if datos:
            mensaje.extend(datos)
        
        # Calcular checksum (sin STX)
        checksum = self.calcular_checksum(mensaje[1:])
        mensaje.append(checksum)
        mensaje.append(self.ETX)
        
        return bytes(mensaje)
    
    # =========================================================================
    # MENSAJES DE CONSULTA
    # =========================================================================
    
    def msg_sincronizacion(self, subregulador=129):
        """
        Consulta de sincronización (0x91)
        Obtiene: hora, plan actual, segundos en ciclo
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['SINCRONIZACION'])
    
    def msg_estado_alarmas(self, subregulador=128):
        """
        Consulta de estado y alarmas (0xB4)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['ESTADO_ALARMAS'])
    
    def msg_config(self, subregulador=128):
        """
        Consulta de parámetros de configuración (0xB5)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['CONFIG'])
    
    def msg_tablas(self, subregulador=128):
        """
        Consulta de tablas de programación (0xB6)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['TABLAS'])
    
    def msg_incompatibilidades(self, subregulador=128):
        """
        Consulta de incompatibilidades (0xB7)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['INCOMPATIBILIDADES'])
    
    def msg_datos_trafico(self, subregulador=129):
        """
        Consulta de datos de tráfico (0x94)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['DATOS_TRAFICO'])
    
    def msg_detectores(self, subregulador=128):
        """
        Petición de estado de detectores (0x20)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['DET'])
    
    # =========================================================================
    # MENSAJES DE CONTROL
    # =========================================================================
    
    def msg_seleccion_plan(self, plan_id, subregulador=129):
        """
        Selección de plan (0xD1)
        
        Args:
            plan_id: ID del plan (129-160 normalmente)
            subregulador: Subregulador destino
        """
        # El plan se envía codificado UNE
        datos = [self.codificar_byte_une(plan_id)]
        return self.construir_mensaje(subregulador, self.CODIGOS['SELECCION_PLAN'], datos)
    
    def msg_puesta_hora(self, hora, minuto, segundo, dia=1, mes=1, subregulador=128):
        """
        Puesta en hora (0xD2)
        
        Args:
            hora, minuto, segundo: Hora a establecer
            dia, mes: Fecha (opcional)
        """
        datos = [
            self.codificar_byte_une(hora),
            self.codificar_byte_une(minuto),
            self.codificar_byte_une(segundo),
            self.codificar_byte_une(dia),
            self.codificar_byte_une(mes)
        ]
        return self.construir_mensaje(subregulador, self.CODIGOS['PUESTA_HORA'], datos)
    
    def msg_estados(self, estado_repr, subregulador=128):
        """
        Comando de estados (0xD4)
        
        Args:
            estado_repr: 0=Apagado, 1=Intermitente, 2=Colores
        """
        datos = [self.codificar_byte_une(estado_repr)]
        return self.construir_mensaje(subregulador, self.CODIGOS['ESTADOS'], datos)
    
    def msg_intermitente(self, subregulador=128):
        """Poner regulador en modo intermitente"""
        return self.msg_estados(self.ESTADO_REPR['INTERMITENTE'], subregulador)
    
    def msg_apagar(self, subregulador=128):
        """Apagar regulador"""
        return self.msg_estados(self.ESTADO_REPR['APAGADO'], subregulador)
    
    def msg_colores(self, subregulador=128):
        """Poner regulador en modo colores (normal)"""
        return self.msg_estados(self.ESTADO_REPR['COLORES'], subregulador)
    
    def msg_cambio_fase(self, fase_id, subregulador=128):
        """
        Cambio de fase (0xD5)
        
        Args:
            fase_id: ID de la fase destino
        """
        datos = [self.codificar_byte_une(fase_id)]
        return self.construir_mensaje(subregulador, self.CODIGOS['CAMBIO_FASE'], datos)
    
    def msg_borrar_alarmas(self, subregulador=128):
        """
        Borrado de alarmas (0xDD)
        """
        return self.construir_mensaje(subregulador, self.CODIGOS['BORRAR_ALARMAS'])
    
    def msg_detectores_tiempo_real(self, activar=True, subregulador=128):
        """
        Activar/desactivar envío de detectores en tiempo real
        
        Args:
            activar: True para activar, False para cancelar
        """
        if activar:
            return self.construir_mensaje(subregulador, self.CODIGOS['DETECTORES_TR'])
        else:
            return self.construir_mensaje(subregulador, self.CODIGOS['CANCELAR_TR'])
    
    # =========================================================================
    # UTILIDADES
    # =========================================================================
    
    def obtener_nombre_codigo(self, codigo):
        """Obtiene el nombre de un código de función"""
        for nombre, valor in self.CODIGOS.items():
            if valor == codigo:
                return nombre
        return f"0x{codigo:02X}"
    
    def formatear_mensaje(self, mensaje):
        """Formatea un mensaje para mostrar en log"""
        if isinstance(mensaje, bytes):
            return ' '.join(f'{b:02X}' for b in mensaje)
        return str(mensaje)
