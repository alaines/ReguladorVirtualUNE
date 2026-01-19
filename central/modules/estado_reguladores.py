"""
Gestión del estado de reguladores conectados
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger('Central.Estado')


class EstadoConexion(Enum):
    """Estados posibles de conexión"""
    DESCONECTADO = 0
    CONECTANDO = 1
    CONECTADO = 2
    ERROR = 3
    DESHABILITADO = 4


class EstadoRepresentacion(Enum):
    """Estados de representación del semáforo"""
    APAGADO = 0
    INTERMITENTE = 1
    COLORES = 2


@dataclass
class EstadoGrupo:
    """Estado de un grupo de semáforos"""
    numero: int
    estado: int = 0  # 0=Off, 1=Verde, 2=Ámbar, 3=Rojo
    nombre: str = ''
    
    @property
    def estado_nombre(self) -> str:
        nombres = {0: 'Apagado', 1: 'Verde', 2: 'Ámbar', 3: 'Rojo', 
                   4: 'Rojo Int.', 5: 'Verde Int.', 6: 'Ámbar Int.'}
        return nombres.get(self.estado, f'{self.estado}')
    
    @property
    def color_hex(self) -> str:
        colores = {0: '#333333', 1: '#00ff00', 2: '#ffaa00', 3: '#ff0000',
                   4: '#ff0000', 5: '#00ff00', 6: '#ffaa00'}
        return colores.get(self.estado, '#333333')


@dataclass
class Alarmas:
    """Estado de alarmas del regulador"""
    lampara_fundida: bool = False
    conflicto: bool = False
    puerta_abierta: bool = False
    fallo_24v: bool = False
    fallo_rojo: bool = False
    
    @property
    def tiene_alarmas(self) -> bool:
        return any([self.lampara_fundida, self.conflicto, 
                    self.puerta_abierta, self.fallo_24v, self.fallo_rojo])
    
    def to_dict(self) -> Dict[str, bool]:
        return {
            'lampara_fundida': self.lampara_fundida,
            'conflicto': self.conflicto,
            'puerta_abierta': self.puerta_abierta,
            'fallo_24v': self.fallo_24v,
            'fallo_rojo': self.fallo_rojo
        }


@dataclass
class EstadoRegulador:
    """Estado completo de un regulador"""
    
    # Identificación
    id: int
    nombre: str
    
    # Configuración de conexión
    tipo_conexion: str = 'tcp'  # 'tcp' o 'serial'
    ip: str = ''
    puerto: int = 5000
    puerto_com: str = ''
    baudrate: int = 9600
    modo: str = 'A'  # 'A' o 'B'
    subreguladores: List[int] = field(default_factory=lambda: [128, 129])
    polling_intervalo_ms: int = 5000
    habilitado: bool = True
    
    # Estado de conexión
    estado_conexion: EstadoConexion = EstadoConexion.DESCONECTADO
    ultimo_error: str = ''
    ultima_comunicacion: Optional[datetime] = None
    
    # Estado del regulador
    plan_actual: int = 0
    ciclo_total: int = 0
    segundos_ciclo: int = 0
    fase_actual: int = 0
    hora: int = 0
    minuto: int = 0
    segundo: int = 0
    estado_repr: EstadoRepresentacion = EstadoRepresentacion.COLORES
    
    # Grupos
    grupos: List[EstadoGrupo] = field(default_factory=list)
    num_grupos: int = 4
    
    # Alarmas
    alarmas: Alarmas = field(default_factory=Alarmas)
    
    # Detectores
    detectores: List[int] = field(default_factory=list)
    
    # Estadísticas
    mensajes_enviados: int = 0
    mensajes_recibidos: int = 0
    errores_comunicacion: int = 0
    
    def __post_init__(self):
        # Inicializar grupos si están vacíos
        if not self.grupos:
            self.grupos = [EstadoGrupo(i+1) for i in range(self.num_grupos)]
    
    @property
    def conectado(self) -> bool:
        return self.estado_conexion == EstadoConexion.CONECTADO
    
    @property
    def estado_conexion_texto(self) -> str:
        textos = {
            EstadoConexion.DESCONECTADO: 'Desconectado',
            EstadoConexion.CONECTANDO: 'Conectando...',
            EstadoConexion.CONECTADO: 'Conectado',
            EstadoConexion.ERROR: 'Error',
            EstadoConexion.DESHABILITADO: 'Deshabilitado'
        }
        return textos.get(self.estado_conexion, 'Desconocido')
    
    @property
    def estado_repr_texto(self) -> str:
        textos = {
            EstadoRepresentacion.APAGADO: 'APAGADO',
            EstadoRepresentacion.INTERMITENTE: 'INTERMITENTE',
            EstadoRepresentacion.COLORES: 'COLORES'
        }
        return textos.get(self.estado_repr, 'DESCONOCIDO')
    
    @property
    def hora_formateada(self) -> str:
        return f"{self.hora:02d}:{self.minuto:02d}:{self.segundo:02d}"
    
    @property
    def direccion(self) -> str:
        """Retorna la dirección de conexión como texto"""
        if self.tipo_conexion == 'tcp':
            return f"{self.ip}:{self.puerto}"
        else:
            return f"{self.puerto_com}@{self.baudrate}"
    
    def actualizar_desde_sincronizacion(self, datos: Dict[str, Any]):
        """Actualiza estado desde respuesta de sincronización"""
        if 'plan' in datos:
            self.plan_actual = datos['plan']
        if 'hora' in datos:
            self.hora = datos['hora']
        if 'minuto' in datos:
            self.minuto = datos['minuto']
        if 'segundo' in datos:
            self.segundo = datos['segundo']
        if 'segundos_ciclo' in datos:
            self.segundos_ciclo = datos['segundos_ciclo']
        if 'ciclo_total' in datos:
            self.ciclo_total = datos['ciclo_total']
        if 'fase_actual' in datos:
            self.fase_actual = datos['fase_actual']
        
        self.ultima_comunicacion = datetime.now()
    
    def actualizar_grupos(self, grupos_data: List[Dict]):
        """Actualiza estado de grupos"""
        for g_data in grupos_data:
            num = g_data.get('numero', 0)
            if 0 < num <= len(self.grupos):
                self.grupos[num-1].estado = g_data.get('estado', 0)
        
        self.ultima_comunicacion = datetime.now()
    
    def actualizar_alarmas(self, alarmas_data: Dict[str, bool]):
        """Actualiza estado de alarmas"""
        self.alarmas.lampara_fundida = alarmas_data.get('lampara_fundida', False)
        self.alarmas.conflicto = alarmas_data.get('conflicto', False)
        self.alarmas.puerta_abierta = alarmas_data.get('puerta_abierta', False)
        self.alarmas.fallo_24v = alarmas_data.get('fallo_24v', False)
        self.alarmas.fallo_rojo = alarmas_data.get('fallo_rojo', False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario para guardar configuración"""
        return {
            'id': self.id,
            'nombre': self.nombre,
            'tipo_conexion': self.tipo_conexion,
            'ip': self.ip,
            'puerto': self.puerto,
            'puerto_com': self.puerto_com,
            'baudrate': self.baudrate,
            'modo': self.modo,
            'subreguladores': self.subreguladores,
            'polling_intervalo_ms': self.polling_intervalo_ms,
            'habilitado': self.habilitado
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EstadoRegulador':
        """Crea instancia desde diccionario"""
        return cls(
            id=data.get('id', 0),
            nombre=data.get('nombre', ''),
            tipo_conexion=data.get('tipo_conexion', 'tcp'),
            ip=data.get('ip', ''),
            puerto=data.get('puerto', 5000),
            puerto_com=data.get('puerto_com', ''),
            baudrate=data.get('baudrate', 9600),
            modo=data.get('modo', 'A'),
            subreguladores=data.get('subreguladores', [128, 129]),
            polling_intervalo_ms=data.get('polling_intervalo_ms', 5000),
            habilitado=data.get('habilitado', True)
        )


class GestorReguladores:
    """Gestor de múltiples reguladores"""
    
    def __init__(self):
        self.reguladores: Dict[int, EstadoRegulador] = {}
        self._lock = threading.Lock()
        self._callbacks = []  # Callbacks para notificar cambios
    
    def agregar(self, regulador: EstadoRegulador):
        """Agrega un regulador"""
        with self._lock:
            self.reguladores[regulador.id] = regulador
        self._notificar_cambio('agregar', regulador.id)
    
    def obtener(self, regulador_id: int) -> Optional[EstadoRegulador]:
        """Obtiene un regulador por ID"""
        return self.reguladores.get(regulador_id)
    
    def eliminar(self, regulador_id: int):
        """Elimina un regulador"""
        with self._lock:
            if regulador_id in self.reguladores:
                del self.reguladores[regulador_id]
        self._notificar_cambio('eliminar', regulador_id)
    
    def listar(self) -> List[EstadoRegulador]:
        """Lista todos los reguladores"""
        return list(self.reguladores.values())
    
    def obtener_conectados(self) -> List[EstadoRegulador]:
        """Obtiene reguladores conectados"""
        return [r for r in self.reguladores.values() if r.conectado]
    
    def obtener_habilitados(self) -> List[EstadoRegulador]:
        """Obtiene reguladores habilitados"""
        return [r for r in self.reguladores.values() if r.habilitado]
    
    def siguiente_id(self) -> int:
        """Retorna el siguiente ID disponible"""
        if not self.reguladores:
            return 1
        return max(self.reguladores.keys()) + 1
    
    def registrar_callback(self, callback):
        """Registra callback para cambios"""
        self._callbacks.append(callback)
    
    def _notificar_cambio(self, tipo: str, regulador_id: int):
        """Notifica cambios a callbacks registrados"""
        for callback in self._callbacks:
            try:
                callback(tipo, regulador_id)
            except Exception as e:
                logger.error(f"Error en callback: {e}")
    
    def cargar_desde_config(self, config_reguladores: List[Dict]):
        """Carga reguladores desde configuración"""
        for reg_config in config_reguladores:
            regulador = EstadoRegulador.from_dict(reg_config)
            self.agregar(regulador)
        logger.info(f"Cargados {len(self.reguladores)} reguladores desde configuración")
    
    def guardar_a_config(self) -> List[Dict]:
        """Guarda reguladores a formato de configuración"""
        return [r.to_dict() for r in self.reguladores.values()]
