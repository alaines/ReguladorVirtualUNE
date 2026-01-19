"""
Módulos de la Central Virtual UNE
"""

from .protocolo_central import ProtocoloCentral
from .conexion_manager import ConexionManager, ConexionTCP, ConexionSerial
from .estado_reguladores import EstadoRegulador, GestorReguladores, EstadoConexion, EstadoRepresentacion
from .decodificador import DecodificadorUNE

__all__ = [
    'ProtocoloCentral',
    'ConexionManager',
    'ConexionTCP', 
    'ConexionSerial',
    'EstadoRegulador',
    'GestorReguladores',
    'EstadoConexion',
    'EstadoRepresentacion',
    'DecodificadorUNE'
]

__version__ = '1.0.0'
