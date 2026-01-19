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
        0xB6: 'TABLAS',
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
            # Validar longitud mínima
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
        Formato esperado: Plan, Hora, Min, Seg, SegCiclo, ...
        """
        resultado = {}
        
        if len(datos) >= 1:
            resultado['plan'] = self.decodificar_byte(datos[0])
        
        if len(datos) >= 4:
            resultado['hora'] = self.decodificar_byte(datos[1])
            resultado['minuto'] = self.decodificar_byte(datos[2])
            resultado['segundo'] = self.decodificar_byte(datos[3])
        
        if len(datos) >= 5:
            resultado['segundos_ciclo'] = self.decodificar_byte(datos[4])
        
        if len(datos) >= 6:
            resultado['ciclo_total'] = self.decodificar_byte(datos[5])
        
        if len(datos) >= 7:
            resultado['fase_actual'] = self.decodificar_byte(datos[6])
        
        return resultado
    
    def _decodificar_cambio_modo(self, datos) -> Dict[str, Any]:
        """
        Decodifica mensaje de cambio de modo (0xB3)
        """
        resultado = {}
        
        if len(datos) >= 1:
            modo_byte = self.decodificar_byte(datos[0])
            resultado['modo_control'] = (modo_byte >> 2) & 0x03  # Bits 3-2
            resultado['estado_repr'] = modo_byte & 0x03  # Bits 1-0
            resultado['estado_repr_nombre'] = self.ESTADOS_REPR.get(resultado['estado_repr'], 'DESCONOCIDO')
        
        return resultado
    
    def _decodificar_estado_alarmas(self, datos) -> Dict[str, Any]:
        """
        Decodifica respuesta de estado/alarmas (0xB4)
        """
        resultado = {
            'alarmas': {
                'lampara_fundida': False,
                'conflicto': False,
                'puerta_abierta': False,
                'fallo_24v': False,
                'fallo_rojo': False
            }
        }
        
        if len(datos) >= 1:
            byte_alarmas = self.decodificar_byte(datos[0])
            resultado['alarmas']['lampara_fundida'] = bool(byte_alarmas & 0x01)
            resultado['alarmas']['conflicto'] = bool(byte_alarmas & 0x02)
            resultado['alarmas']['puerta_abierta'] = bool(byte_alarmas & 0x04)
            resultado['alarmas']['fallo_24v'] = bool(byte_alarmas & 0x08)
            resultado['alarmas']['fallo_rojo'] = bool(byte_alarmas & 0x10)
        
        if len(datos) >= 2:
            resultado['num_grupos'] = self.decodificar_byte(datos[1])
        
        if len(datos) >= 3:
            resultado['ciclo'] = self.decodificar_byte(datos[2])
        
        return resultado
    
    def _decodificar_estado_grupos(self, datos) -> Dict[str, Any]:
        """
        Decodifica estado de grupos (0xB9)
        Cada byte tiene 4 grupos (2 bits por grupo)
        """
        resultado = {'grupos': []}
        
        for i, byte in enumerate(datos):
            byte_dec = self.decodificar_byte(byte)
            
            # Extraer 4 grupos por byte (2 bits cada uno)
            for j in range(4):
                estado = (byte_dec >> (6 - j*2)) & 0x03
                grupo_num = i * 4 + j + 1
                resultado['grupos'].append({
                    'numero': grupo_num,
                    'estado': estado,
                    'estado_nombre': self.ESTADOS_GRUPO.get(estado, f'{estado}')
                })
        
        return resultado
    
    def _decodificar_datos_trafico(self, datos) -> Dict[str, Any]:
        """
        Decodifica datos de tráfico (0x94)
        """
        resultado = {}
        
        if len(datos) >= 1:
            byte0 = self.decodificar_byte(datos[0])
            resultado['estado_repr'] = byte0 & 0x03
            resultado['estado_repr_nombre'] = self.ESTADOS_REPR.get(resultado['estado_repr'], 'DESCONOCIDO')
        
        if len(datos) >= 2:
            resultado['plan'] = self.decodificar_byte(datos[1])
        
        # Detectores si hay más datos
        if len(datos) >= 3:
            resultado['detectores'] = []
            for i, byte in enumerate(datos[2:]):
                resultado['detectores'].append(self.decodificar_byte(byte))
        
        return resultado
    
    def formatear_grupos(self, grupos: List[Dict]) -> str:
        """Formatea lista de grupos para mostrar"""
        colores = {0: '⚫', 1: '🟢', 2: '🟡', 3: '🔴', 4: '🔴', 5: '🟢', 6: '🟡'}
        return ' '.join(colores.get(g['estado'], '?') for g in grupos[:8])
    
    def formatear_mensaje(self, msg: MensajeDecodificado) -> str:
        """Formatea un mensaje decodificado para log"""
        if not msg.valido:
            return f"[ERROR] {msg.error}"
        
        texto = f"[{msg.codigo_nombre}] Sub:{msg.subregulador}"
        
        if 'plan' in msg.datos:
            texto += f" Plan:{msg.datos['plan']}"
        
        if 'grupos' in msg.datos:
            texto += f" Grupos:{self.formatear_grupos(msg.datos['grupos'])}"
        
        if 'estado_repr_nombre' in msg.datos:
            texto += f" Estado:{msg.datos['estado_repr_nombre']}"
        
        return texto
