"""
Gestor de conexiones para la Central UNE
Soporta TCP/IP y Serial RS-232
"""

import socket
import threading
import logging
import time
from abc import ABC, abstractmethod
from queue import Queue, Empty

try:
    import serial
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False
    
logger = logging.getLogger('Central.Conexion')


class ConexionBase(ABC):
    """Clase base abstracta para conexiones"""
    
    def __init__(self, regulador_id, nombre):
        self.regulador_id = regulador_id
        self.nombre = nombre
        self.conectado = False
        self.ultimo_error = None
        self.bytes_enviados = 0
        self.bytes_recibidos = 0
        self.mensajes_enviados = 0
        self.mensajes_recibidos = 0
        self._lock = threading.Lock()
        self._rx_queue = Queue()
        self._rx_thread = None
        self._running = False
    
    @abstractmethod
    def conectar(self) -> bool:
        """Establece la conexión"""
        pass
    
    @abstractmethod
    def desconectar(self):
        """Cierra la conexión"""
        pass
    
    @abstractmethod
    def enviar(self, datos: bytes) -> bool:
        """Envía datos"""
        pass
    
    @abstractmethod
    def recibir(self, timeout: float = 1.0) -> bytes:
        """Recibe datos"""
        pass
    
    def obtener_estado(self) -> dict:
        """Retorna el estado de la conexión"""
        return {
            'conectado': self.conectado,
            'ultimo_error': self.ultimo_error,
            'bytes_enviados': self.bytes_enviados,
            'bytes_recibidos': self.bytes_recibidos,
            'mensajes_enviados': self.mensajes_enviados,
            'mensajes_recibidos': self.mensajes_recibidos
        }


class ConexionTCP(ConexionBase):
    """Conexión TCP/IP al regulador"""
    
    def __init__(self, regulador_id, nombre, ip, puerto, timeout=5.0):
        super().__init__(regulador_id, nombre)
        self.ip = ip
        self.puerto = puerto
        self.timeout = timeout
        self._socket = None
    
    def conectar(self) -> bool:
        """Establece conexión TCP"""
        try:
            with self._lock:
                if self._socket:
                    self._socket.close()
                
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self.timeout)
                self._socket.connect((self.ip, self.puerto))
                self.conectado = True
                self.ultimo_error = None
                
                # Iniciar hilo de recepción
                self._running = True
                self._rx_thread = threading.Thread(target=self._receptor_loop, daemon=True)
                self._rx_thread.start()
                
                logger.info(f"[{self.nombre}] Conectado a {self.ip}:{self.puerto}")
                return True
                
        except socket.timeout:
            self.ultimo_error = f"Timeout conectando a {self.ip}:{self.puerto}"
            logger.error(f"[{self.nombre}] {self.ultimo_error}")
            self.conectado = False
            return False
            
        except socket.error as e:
            self.ultimo_error = f"Error de conexión: {e}"
            logger.error(f"[{self.nombre}] {self.ultimo_error}")
            self.conectado = False
            return False
    
    def desconectar(self):
        """Cierra la conexión TCP"""
        self._running = False
        with self._lock:
            if self._socket:
                try:
                    self._socket.close()
                except:
                    pass
                self._socket = None
            self.conectado = False
        logger.info(f"[{self.nombre}] Desconectado")
    
    def enviar(self, datos: bytes) -> bool:
        """Envía datos por TCP"""
        if not self.conectado or not self._socket:
            return False
        
        try:
            with self._lock:
                self._socket.sendall(datos)
                self.bytes_enviados += len(datos)
                self.mensajes_enviados += 1
            return True
            
        except socket.error as e:
            self.ultimo_error = f"Error enviando: {e}"
            logger.error(f"[{self.nombre}] {self.ultimo_error}")
            self.conectado = False
            return False
    
    def recibir(self, timeout: float = 1.0) -> bytes:
        """Recibe datos de la cola de recepción"""
        try:
            return self._rx_queue.get(timeout=timeout)
        except Empty:
            return b''
    
    def reconectar(self) -> bool:
        """Intenta reconectar"""
        logger.info(f"[{self.nombre}] Intentando reconectar...")
        self.desconectar()
        time.sleep(0.5)
        return self.conectar()
    
    def _receptor_loop(self):
        """Hilo receptor de datos"""
        buffer = b''
        sin_datos_count = 0
        max_sin_datos = 60  # ~30 segundos sin datos antes de considerar timeout
        
        while self._running and self.conectado:
            try:
                if self._socket:
                    self._socket.settimeout(0.5)
                    data = self._socket.recv(1024)
                    if data:
                        buffer += data
                        self.bytes_recibidos += len(data)
                        sin_datos_count = 0  # Reset contador
                        
                        # Procesar ACK/NACK de un solo byte al inicio del buffer
                        while buffer and buffer[0] in (0x06, 0x15):
                            ack_byte = bytes([buffer[0]])
                            self._rx_queue.put(ack_byte)
                            self.mensajes_recibidos += 1
                            buffer = buffer[1:]
                        
                        # Procesar mensajes completos (STX ... ETX)
                        while b'\x02' in buffer and b'\x03' in buffer:
                            start = buffer.find(b'\x02')
                            # Descartar bytes basura antes del STX
                            if start > 0:
                                buffer = buffer[start:]
                                start = 0
                            end = buffer.find(b'\x03', start)
                            if end > start:
                                mensaje = buffer[start:end+1]
                                self._rx_queue.put(mensaje)
                                self.mensajes_recibidos += 1
                                buffer = buffer[end+1:]
                            else:
                                break
                    else:
                        # Conexión cerrada por el otro lado
                        self.conectado = False
                        self.ultimo_error = "Conexión cerrada por el regulador"
                        logger.warning(f"[{self.nombre}] {self.ultimo_error}")
                        break
                        
            except socket.timeout:
                continue
            except socket.error as e:
                if self._running:
                    logger.error(f"[{self.nombre}] Error en recepción: {e}")
                break
        
        logger.debug(f"[{self.nombre}] Hilo receptor terminado")


class ConexionSerial(ConexionBase):
    """Conexión Serial RS-232 al regulador"""
    
    def __init__(self, regulador_id, nombre, puerto_com, baudrate=9600, timeout=5.0):
        super().__init__(regulador_id, nombre)
        self.puerto_com = puerto_com
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None
        
        if not SERIAL_DISPONIBLE:
            logger.warning("pyserial no disponible. Instale con: pip install pyserial")
    
    def conectar(self) -> bool:
        """Establece conexión serial"""
        if not SERIAL_DISPONIBLE:
            self.ultimo_error = "pyserial no instalado"
            return False
        
        try:
            with self._lock:
                if self._serial and self._serial.is_open:
                    self._serial.close()
                
                self._serial = serial.Serial(
                    port=self.puerto_com,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout
                )
                self.conectado = True
                self.ultimo_error = None
                
                # Iniciar hilo de recepción
                self._running = True
                self._rx_thread = threading.Thread(target=self._receptor_loop, daemon=True)
                self._rx_thread.start()
                
                logger.info(f"[{self.nombre}] Conectado a {self.puerto_com} @ {self.baudrate}")
                return True
                
        except serial.SerialException as e:
            self.ultimo_error = f"Error abriendo {self.puerto_com}: {e}"
            logger.error(f"[{self.nombre}] {self.ultimo_error}")
            self.conectado = False
            return False
    
    def desconectar(self):
        """Cierra la conexión serial"""
        self._running = False
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except:
                    pass
                self._serial = None
            self.conectado = False
        logger.info(f"[{self.nombre}] Desconectado")
    
    def enviar(self, datos: bytes) -> bool:
        """Envía datos por serial"""
        if not self.conectado or not self._serial:
            return False
        
        try:
            with self._lock:
                self._serial.write(datos)
                self.bytes_enviados += len(datos)
                self.mensajes_enviados += 1
            return True
            
        except serial.SerialException as e:
            self.ultimo_error = f"Error enviando: {e}"
            logger.error(f"[{self.nombre}] {self.ultimo_error}")
            self.conectado = False
            return False
    
    def recibir(self, timeout: float = 1.0) -> bytes:
        """Recibe datos de la cola de recepción"""
        try:
            return self._rx_queue.get(timeout=timeout)
        except Empty:
            return b''
    
    def _receptor_loop(self):
        """Hilo receptor de datos serial"""
        buffer = b''
        while self._running and self.conectado:
            try:
                if self._serial and self._serial.is_open:
                    if self._serial.in_waiting > 0:
                        data = self._serial.read(self._serial.in_waiting)
                        if data:
                            buffer += data
                            self.bytes_recibidos += len(data)
                            
                            # Procesar mensajes completos (STX ... ETX)
                            while b'\x02' in buffer and b'\x03' in buffer:
                                start = buffer.find(b'\x02')
                                end = buffer.find(b'\x03', start)
                                if end > start:
                                    mensaje = buffer[start:end+1]
                                    self._rx_queue.put(mensaje)
                                    self.mensajes_recibidos += 1
                                    buffer = buffer[end+1:]
                                else:
                                    break
                    else:
                        time.sleep(0.05)
                else:
                    break
                    
            except serial.SerialException as e:
                if self._running:
                    logger.error(f"[{self.nombre}] Error en recepción: {e}")
                break
        
        logger.debug(f"[{self.nombre}] Hilo receptor terminado")


class ConexionManager:
    """Gestor de múltiples conexiones a reguladores"""
    
    def __init__(self):
        self.conexiones = {}  # {regulador_id: ConexionBase}
        self._lock = threading.Lock()
    
    def agregar_tcp(self, regulador_id, nombre, ip, puerto, timeout=5.0) -> ConexionTCP:
        """Agrega una conexión TCP"""
        conexion = ConexionTCP(regulador_id, nombre, ip, puerto, timeout)
        with self._lock:
            self.conexiones[regulador_id] = conexion
        return conexion
    
    def agregar_serial(self, regulador_id, nombre, puerto_com, baudrate=9600, timeout=5.0) -> ConexionSerial:
        """Agrega una conexión serial"""
        conexion = ConexionSerial(regulador_id, nombre, puerto_com, baudrate, timeout)
        with self._lock:
            self.conexiones[regulador_id] = conexion
        return conexion
    
    def obtener(self, regulador_id) -> ConexionBase:
        """Obtiene una conexión por ID"""
        return self.conexiones.get(regulador_id)
    
    def conectar(self, regulador_id) -> bool:
        """Conecta un regulador específico"""
        conexion = self.conexiones.get(regulador_id)
        if conexion:
            return conexion.conectar()
        return False
    
    def desconectar(self, regulador_id):
        """Desconecta un regulador específico"""
        conexion = self.conexiones.get(regulador_id)
        if conexion:
            conexion.desconectar()
    
    def conectar_todos(self):
        """Conecta todos los reguladores"""
        resultados = {}
        for reg_id, conexion in self.conexiones.items():
            resultados[reg_id] = conexion.conectar()
        return resultados
    
    def desconectar_todos(self):
        """Desconecta todos los reguladores"""
        for conexion in self.conexiones.values():
            conexion.desconectar()
    
    def eliminar(self, regulador_id):
        """Elimina una conexión"""
        with self._lock:
            if regulador_id in self.conexiones:
                self.conexiones[regulador_id].desconectar()
                del self.conexiones[regulador_id]
    
    def listar(self) -> list:
        """Lista todas las conexiones"""
        return list(self.conexiones.values())
    
    def obtener_conectados(self) -> list:
        """Obtiene lista de reguladores conectados"""
        return [c for c in self.conexiones.values() if c.conectado]
