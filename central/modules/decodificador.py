"""
Decodificador de mensajes UNE 135401-4
Parsea respuestas del regulador
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger('Central.Decodificador')


@dataclass
class MensajeDecodificado:
    """Estructura para un mensaje decodificado"""
    codigo: int
    codigo_nombre: str
    subregulador: int
    datos_raw: bytes
    datos: Dict[str, Any]
    valido: bool
    error: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class DecodificadorUNE:
    """Decodifica mensajes del protocolo UNE 135401-4"""
    
    # Nombres de códigos
    NOMBRES_CODIGOS = {
        0x91: 'SINCRONIZACION',
        0xB3: 'CAMBIO_MODO',
        0xB4: 'ESTADO_ALARMAS',
        0xB5: 'CONFIG',
        0xB6: 'GRUPOS_AVERIADOS',
        0xB7: 'INCOMPATIBILIDADES',
        0xB9: 'ESTADO_GRUPOS',
        0x94: 'DATOS_TRAFICO',
        0xD1: 'ACK_PLAN',
        0xD2: 'ACK_HORA',
        0xD4: 'ACK_ESTADOS',
        0xD5: 'ACK_FASE',
        0xDD: 'ACK_ALARMAS',
        0x06: 'ACK',
        0x15: 'NACK',
    }
    
    # Estados de grupos
    ESTADOS_GRUPO = {
        0: 'Apagado',
        1: 'Verde',
        2: 'Ámbar', 
        3: 'Rojo',
        4: 'Rojo Int.',
        5: 'Verde Int.',
        6: 'Ámbar Int.'
    }
    
    # Estados de representación
    ESTADOS_REPR = {
        0: 'APAGADO',
        1: 'INTERMITENTE',
        2: 'COLORES'
    }
    
    def __init__(self):
        pass
    
    @staticmethod
    def decodificar_byte(byte):
        """Decodifica un byte UNE (quita bit 7)"""
        return byte & 0x7F
    
    def decodificar(self, mensaje: bytes) -> MensajeDecodificado:
        """
        Decodifica un mensaje UNE completo
        
        Args:
            mensaje: Bytes del mensaje (incluyendo STX y ETX)
        
        Returns:
            MensajeDecodificado con los datos parseados
        """
        try:
            # Manejar ACK/NACK de un solo byte
            if len(mensaje) == 1:
                if mensaje[0] == 0x06:  # ACK
                    return MensajeDecodificado(
                        codigo=0x06, codigo_nombre='ACK',
                        subregulador=0, datos_raw=mensaje,
                        datos={'ack': True}, valido=True
                    )
                elif mensaje[0] == 0x15:  # NACK
                    return MensajeDecodificado(
                        codigo=0x15, codigo_nombre='NACK',
                        subregulador=0, datos_raw=mensaje,
                        datos={'nack': True}, valido=True
                    )
            
            # Validar longitud mínima para mensajes UNE completos
            if len(mensaje) < 4:
                return MensajeDecodificado(
                    codigo=0, codigo_nombre='INVALIDO',
                    subregulador=0, datos_raw=mensaje,
                    datos={}, valido=False, error='Mensaje muy corto'
                )
            
            # Verificar STX y ETX
            if mensaje[0] != 0x02:
                return MensajeDecodificado(
                    codigo=0, codigo_nombre='INVALIDO',
                    subregulador=0, datos_raw=mensaje,
                    datos={}, valido=False, error='Falta STX'
                )
            
            if mensaje[-1] != 0x03 and mensaje[-1] != 0x04:
                return MensajeDecodificado(
                    codigo=0, codigo_nombre='INVALIDO',
                    subregulador=0, datos_raw=mensaje,
                    datos={}, valido=False, error='Falta ETX/EOT'
                )
            
            # Extraer campos
            subregulador = mensaje[1]
            codigo = mensaje[2]
            codigo_decodificado = self.decodificar_byte(codigo)
            
            # Datos son todo entre código y checksum
            datos_raw = mensaje[3:-2] if len(mensaje) > 4 else b''
            
            # Obtener nombre del código
            codigo_nombre = self.NOMBRES_CODIGOS.get(codigo, f'0x{codigo:02X}')
            
            # Decodificar según tipo de mensaje
            datos = self._decodificar_datos(codigo, datos_raw, subregulador)
            
            return MensajeDecodificado(
                codigo=codigo,
                codigo_nombre=codigo_nombre,
                subregulador=subregulador,
                datos_raw=datos_raw,
                datos=datos,
                valido=True
            )
            
        except Exception as e:
            logger.error(f"Error decodificando mensaje: {e}")
            return MensajeDecodificado(
                codigo=0, codigo_nombre='ERROR',
                subregulador=0, datos_raw=mensaje,
                datos={}, valido=False, error=str(e)
            )
    
    def _decodificar_datos(self, codigo, datos_raw, subregulador) -> Dict[str, Any]:
        """Decodifica los datos según el código de mensaje"""
        
        if codigo == 0x91:  # Sincronización
            return self._decodificar_sincronizacion(datos_raw)
        
        elif codigo == 0xB3:  # Cambio de modo
            return self._decodificar_cambio_modo(datos_raw)
        
        elif codigo == 0xB4:  # Estado/Alarmas
            return self._decodificar_estado_alarmas(datos_raw)
        
        elif codigo == 0xB6:  # Grupos averiados
            return self._decodificar_grupos_averiados(datos_raw)
        
        elif codigo == 0xB9:  # Estado de grupos
            return self._decodificar_estado_grupos(datos_raw)
        
        elif codigo == 0x94:  # Datos de tráfico
            return self._decodificar_datos_trafico(datos_raw)
        
        elif codigo in [0xD1, 0xD2, 0xD4, 0xD5, 0xDD]:  # ACKs
            return {'ack': True}
        
        elif codigo == 0x06:  # ACK simple
            return {'ack': True}
        
        elif codigo == 0x15:  # NACK
            return {'nack': True}
        
        else:
            # Datos sin procesar
            return {'raw': [self.decodificar_byte(b) for b in datos_raw]}
    
    def _decodificar_sincronizacion(self, datos) -> Dict[str, Any]:
        """
        Decodifica respuesta de sincronización (0x91)
        Formato del regulador real:
        - Byte 0: Nº de plan
        - Byte 1: Hora
        - Byte 2: Minuto
        - Byte 3: Segundo
        - Byte 4: Fase actual
        - Byte 5: Tiempo ciclo MSB (bits 13-7)
        - Byte 6: Tiempo ciclo LSB (bits 6-0)
        - Byte 7: Tiempo restante de fase
        """
        resultado = {}
        
        if len(datos) >= 1:
            resultado['plan'] = self.decodificar_byte(datos[0])
        
        if len(datos) >= 4:
            resultado['hora'] = self.decodificar_byte(datos[1])
            resultado['minuto'] = self.decodificar_byte(datos[2])
            resultado['segundo'] = self.decodificar_byte(datos[3])
        
        if len(datos) >= 5:
            resultado['fase_actual'] = self.decodificar_byte(datos[4])
        
        if len(datos) >= 7:
            # Tiempo de ciclo en 2 bytes (MSB, LSB)
            ciclo_msb = self.decodificar_byte(datos[5])
            ciclo_lsb = self.decodificar_byte(datos[6])
            resultado['segundos_ciclo'] = (ciclo_msb << 7) | ciclo_lsb
            resultado['ciclo_total'] = resultado['segundos_ciclo']  # Para compatibilidad
        
        if len(datos) >= 8:
            resultado['tiempo_resta_fase'] = self.decodificar_byte(datos[7])
        
        return resultado
    
    def _decodificar_cambio_modo(self, datos) -> Dict[str, Any]:
        """
        Decodifica mensaje de cambio de modo (0xB3)
        
        Formato esperado según protocolo UNE:
        - 1 byte: bits 3-2 = modo_control, bits 1-0 = estado_repr
        
        Si el mensaje tiene muchos bytes, puede ser un mensaje de error
        del regulador (algunos envían texto ASCII como respuesta de error).
        """
        resultado = {
            'modo_control': -1,  # -1 = desconocido
            'estado_repr': 0
        }
        
        if len(datos) >= 1:
            # Si hay demasiados bytes (>5), probablemente es un mensaje de error en texto
            if len(datos) > 5:
                # Intentar decodificar como texto para ver si es un error
                try:
                    texto = bytes([self.decodificar_byte(b) for b in datos]).decode('ascii', errors='ignore')
                    logger.warning(f"0xB3 respuesta con formato inesperado (posible error): {texto[:50]}")
                except:
                    pass
                # Marcar como desconocido
                resultado['modo_control'] = -1
                resultado['estado_repr'] = 0
                resultado['estado_repr_nombre'] = 'DESCONOCIDO'
                resultado['error_formato'] = True
            else:
                # Formato normal: 1 byte con bits de modo
                modo_byte = self.decodificar_byte(datos[0])
                resultado['modo_control'] = (modo_byte >> 2) & 0x03  # Bits 3-2
                resultado['estado_repr'] = modo_byte & 0x03  # Bits 1-0
                resultado['estado_repr_nombre'] = self.ESTADOS_REPR.get(resultado['estado_repr'], 'DESCONOCIDO')
        
        return resultado
    
    def _decodificar_estado_alarmas(self, datos) -> Dict[str, Any]:
        """
        Decodifica respuesta de estado/alarmas (0xB4)
        
        El mensaje puede incluir información adicional sobre qué grupos
        tienen fallos, pero el detalle completo se obtiene con 0xB6.
        """
        resultado = {
            'alarmas': {
                'lampara_fundida': False,
                'conflicto': False,
                'puerta_abierta': False,
                'fallo_24v': False,
                'fallo_rojo': False
            },
            'grupos_con_fallo': []  # Lista de grupos que tienen fallo
        }
        
        if len(datos) >= 1:
            byte_alarmas = self.decodificar_byte(datos[0])
            resultado['alarmas']['lampara_fundida'] = bool(byte_alarmas & 0x01)
            resultado['alarmas']['conflicto'] = bool(byte_alarmas & 0x02)
            resultado['alarmas']['puerta_abierta'] = bool(byte_alarmas & 0x04)
            resultado['alarmas']['fallo_24v'] = bool(byte_alarmas & 0x08)
            resultado['alarmas']['fallo_rojo'] = bool(byte_alarmas & 0x10)
        
        # El byte 2 puede contener un bitmap de grupos con fallo
        if len(datos) >= 2:
            byte_grupos = self.decodificar_byte(datos[1])
            resultado['grupos_bitmap'] = byte_grupos
            # Extraer grupos del bitmap (cada bit = un grupo)
            for i in range(8):
                if byte_grupos & (1 << i):
                    resultado['grupos_con_fallo'].append(i + 1)
        
        if len(datos) >= 3:
            resultado['ciclo'] = self.decodificar_byte(datos[2])
        
        return resultado
    
    def _decodificar_grupos_averiados(self, datos) -> Dict[str, Any]:
        """
        Decodifica respuesta de grupos averiados (0xB6)
        
        Formato según norma UNE 135401-4:
        - Pares de bytes: Nº de grupo + Salida
        - Salida: 1=rojo, 2=ámbar, 4=verde (se suman)
        """
        resultado = {
            'grupos_averiados': []
        }
        
        # Los datos vienen en pares: grupo + tipo_fallo
        i = 0
        while i + 1 < len(datos):
            num_grupo = self.decodificar_byte(datos[i])
            tipo_fallo = self.decodificar_byte(datos[i + 1])
            
            # Decodificar tipo de fallo
            fallos = []
            if tipo_fallo & 0x01:
                fallos.append('rojo')
            if tipo_fallo & 0x02:
                fallos.append('ámbar')
            if tipo_fallo & 0x04:
                fallos.append('verde')
            
            resultado['grupos_averiados'].append({
                'grupo': num_grupo,
                'fallo_tipo': tipo_fallo,
                'fallos': fallos,
                'descripcion': f"G{num_grupo}: {', '.join(fallos)}" if fallos else f"G{num_grupo}: desconocido"
            })
            
            i += 2
        
        return resultado
    
    def _decodificar_estado_grupos(self, datos) -> Dict[str, Any]:
        """
        Decodifica estado de grupos (0xB9)
        Formato del regulador real: 1 BYTE POR GRUPO
        Valores del protocolo B9:
        - 0 = Apagado
        - 1 = Rojo
        - 4 = Ámbar
        - 9 = Rojo intermitente (1 + 8)
        - 12 = Ámbar intermitente (4 + 8)
        - 16 = Verde
        - 24 = Verde intermitente (16 + 8)
        """
        resultado = {'grupos': []}
        
        # Mapeo de valores protocolo B9 a estados internos
        # Interno: 0=Apagado, 1=Verde, 2=Ámbar, 3=Rojo, 4=Rojo Int, 5=Verde Int, 6=Ámbar Int
        def mapear_protocolo_a_interno(valor):
            if valor == 0:
                return 0  # Apagado
            elif valor == 16:
                return 1  # Verde
            elif valor == 24:
                return 5  # Verde intermitente
            elif valor == 4:
                return 2  # Ámbar
            elif valor == 12:
                return 6  # Ámbar intermitente
            elif valor == 1:
                return 3  # Rojo
            elif valor == 9:
                return 4  # Rojo intermitente
            else:
                # Intentar deducir por bits
                base = valor & 0x17  # Quitar bit de intermitente
                intermitente = bool(valor & 0x08)
                if base == 16:
                    return 5 if intermitente else 1  # Verde
                elif base == 4:
                    return 6 if intermitente else 2  # Ámbar
                elif base == 1:
                    return 4 if intermitente else 3  # Rojo
                return 0  # Default apagado
        
        for i, byte in enumerate(datos):
            byte_dec = self.decodificar_byte(byte)
            estado_interno = mapear_protocolo_a_interno(byte_dec)
            grupo_num = i + 1
            resultado['grupos'].append({
                'numero': grupo_num,
                'estado': estado_interno,
                'estado_nombre': self.ESTADOS_GRUPO.get(estado_interno, f'{estado_interno}'),
                'valor_protocolo': byte_dec
            })
        
        return resultado
    
    def _decodificar_datos_trafico(self, datos) -> Dict[str, Any]:
        """
        Decodifica datos de tráfico (0x94)
        Formato del regulador real (4 bytes):
        - Byte 0: Estado representación (0=apagado, 1=intermitente, 2=colores)
        - Byte 1: Control de planes (0=LOCAL, 1/2=ORDENADOR)
        - Byte 2: Coordinación (1=LOCAL, 3=ORDENADOR)
        - Byte 3: Método (0=tiempos fijos)
        
        NOTA: El regulador NO envía grupos en este mensaje.
        Los grupos se envían espontáneamente en mensaje 0xB9.
        """
        resultado = {}
        
        if len(datos) >= 1:
            byte0 = self.decodificar_byte(datos[0])
            resultado['estado_repr'] = byte0 & 0x07  # 3 bits inferiores
            resultado['estado_repr_nombre'] = self.ESTADOS_REPR.get(resultado['estado_repr'], 'DESCONOCIDO')
        
        if len(datos) >= 2:
            resultado['control_planes'] = self.decodificar_byte(datos[1])
            # 0 = LOCAL, 1 o 2 = ORDENADOR
            resultado['modo_ordenador'] = resultado['control_planes'] > 0
        
        if len(datos) >= 3:
            resultado['coordinacion'] = self.decodificar_byte(datos[2])
        
        if len(datos) >= 4:
            resultado['metodo'] = self.decodificar_byte(datos[3])
        
        return resultado
    
    def formatear_grupos(self, grupos: List[Dict]) -> str:
        """Formatea lista de grupos para mostrar"""
        colores = {0: '⚫', 1: '🟢', 2: '🟡', 3: '🔴', 4: '🔴', 5: '🟢', 6: '🟡'}
        return ' '.join(colores.get(g['estado'], '?') for g in grupos[:8])
    
    def formatear_mensaje(self, msg: MensajeDecodificado) -> str:
        """Formatea un mensaje decodificado para log detallado"""
        if not msg.valido:
            return f"[ERROR] {msg.error} | Raw: {msg.datos_raw.hex() if msg.datos_raw else 'N/A'}"
        
        # ACK/NACK simple
        if msg.codigo == 0x06:
            return "✓ ACK"
        if msg.codigo == 0x15:
            return "✗ NACK"
        
        texto = f"[{msg.codigo_nombre}] Sub:{msg.subregulador}"
        
        # Datos de sincronización (0x91)
        if 'plan' in msg.datos:
            texto += f" Plan:{msg.datos['plan']}"
        if 'hora' in msg.datos:
            h = msg.datos.get('hora', 0)
            m = msg.datos.get('minuto', 0)
            s = msg.datos.get('segundo', 0)
            texto += f" Hora:{h:02d}:{m:02d}:{s:02d}"
        if 'fase_actual' in msg.datos:
            texto += f" Fase:{msg.datos['fase_actual']}"
        if 'segundos_ciclo' in msg.datos:
            texto += f" Ciclo:{msg.datos['segundos_ciclo']}s"
        
        # Estado de grupos (0xB9)
        if 'grupos' in msg.datos:
            texto += f" Grupos:{self.formatear_grupos(msg.datos['grupos'])}"
        
        # Estado representación
        if 'estado_repr_nombre' in msg.datos:
            texto += f" Modo:{msg.datos['estado_repr_nombre']}"
        elif 'estado_repr' in msg.datos:
            texto += f" Repr:{msg.datos['estado_repr']}"
        
        # Alarmas
        if 'alarmas' in msg.datos:
            alarmas_activas = [k for k, v in msg.datos['alarmas'].items() if v]
            if alarmas_activas:
                texto += f" ⚠️Alarmas:{','.join(alarmas_activas)}"
        
        return texto
