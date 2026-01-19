#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
REGULADOR VIRTUAL TIPO M - MODO B
Basado en norma UNE 135401-4:2003

Este regulador ESCUCHA en puerto 19000 esperando conexión de la central
Modo B: Comunicación asíncrona con envío espontáneo de datos al detectar cambios
"""

import socket
import threading
import time
import random
import logging
from datetime import datetime

# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

def configurar_logging():
    """Configura el sistema de logging para el regulador"""
    logger = logging.getLogger('ReguladorUNE')
    logger.setLevel(logging.DEBUG)
    
    formato = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    fh = logging.FileHandler(f'regulador_log_{timestamp}.txt', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formato)
    
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(formato)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

logger = configurar_logging()

# ============================================================================
# CONFIGURACIÓN DEL REGULADOR
# ============================================================================

class ConfigRegulador:
    """Configuración del regulador virtual"""
    
    # Conexión (SERVIDOR - Escucha conexiones de la central)
    ESCUCHAR_IP = "0.0.0.0"         # Escucha en todas las interfaces
    ESCUCHAR_PORT = 19000           # Puerto donde escucha el regulador
    
    # Identificación
    SUBREGULADOR_ID = 1             # ID de este subregulador (1-4)
    
    # Características
    NUM_GRUPOS = 8                  # Grupos semafóricos
    NUM_DETECTORES = 4              # Detectores físicos
    NUM_PLANES = 4                  # Planes almacenados
    
    # Parámetros de operación
    MODO_OPERACION = "A"            # Modo A: síncrono (con mensajes espontáneos de cambio)
    TIEMPO_CICLO = 70               # Segundos
    ENVIAR_KEEP_ALIVE = False       # No enviar keep-alive periódico (comportamiento modo A)
    
    # Timings
    TIMEOUT_CONEXION = 5            # Timeout para conexión
    INTERVALO_ESTADO = 10           # Envío de estado cada 10s si no hay ACK
    TIMEOUT_ACK = 10                # Espera ACK antes de reenviar
    MAX_REINTENTOS = 3              # Reintentos antes de cerrar sesión


# ============================================================================
# CONSTANTES DEL PROTOCOLO
# ============================================================================

class ProtocoloUNE:
    """Constantes del protocolo UNE 135401-4"""
    
    # Caracteres de control
    STX = b'\x02'   # Inicio de transmisión
    ETX = b'\x03'   # Fin de transmisión
    EOT = b'\x04'   # Fin de transmisión parcial
    ACK = b'\x06'   # Acuse de recibo positivo
    NACK = b'\x15'  # Acuse de recibo negativo
    DC1 = b'\x11'   # Comunicaciones ON
    DC3 = b'\x13'   # Comunicaciones OFF
    
    # Mensajes especiales
    DET = 0x20      # Petición de detectores
    
    # Códigos de función (más comunes)
    PLAN_EN_CURSO = 0xC9            # Pregunta por plan en curso
    DETECTORES_PRESENCIA = 0xB0     # Detectores de presencia
    DETECTORES_TIEMPO_REAL = 0xD3   # Activar/desactivar tiempo real
    ALARMAS = 0xB4                  # Estado de alarmas
    SELECCION_PLAN = 0x51           # Orden de cambio de plan
    MANDO_DIRECTO = 0xDC            # Mando directo de grupos
    CONSULTA_MANDO_DIRECTO = 0xDB   # Consulta de mando directo


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def codificar_byte_une(valor):
    """Codifica un byte con bit 7 activo (como regulador real)"""
    return (valor & 0x7F) | 0x80

def decodificar_byte_une(byte):
    """Decodifica un byte quitando el bit 7"""
    return byte & 0x7F

def calcular_checksum(datos):
    """
    Calcula checksum XOR con bit 7 activo (como regulador real)
    """
    checksum = 0
    for byte in datos:
        checksum ^= byte
    return bytes([checksum | 0x80])  # Activar bit 7


def calcular_checksum_8bits(datos):
    """
    Calcula checksum usando 8 bits completos (sin máscara)
    Para compatibilidad con centrales que no aplican la máscara de 7 bits
    """
    checksum = 0
    for byte in datos:
        checksum ^= byte
    return bytes([checksum & 0xFF])


def verificar_checksum(datos, checksum_recibido):
    """
    Verifica el checksum intentando ambos métodos:
    1. UNE estándar (7 bits LSB)
    2. Método alternativo (8 bits completos)
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


def construir_mensaje(subregulador, codigo, datos=b''):
    """Construye un mensaje según el protocolo UNE"""
    cuerpo = bytes([subregulador, codigo]) + datos
    checksum = calcular_checksum(cuerpo)
    mensaje = ProtocoloUNE.STX + cuerpo + checksum + ProtocoloUNE.ETX
    return mensaje


# ============================================================================
# ESTADO DEL REGULADOR
# ============================================================================

class EstadoRegulador:
    """Mantiene el estado actual del regulador"""
    
    def __init__(self, config):
        self.config = config
        
        # Planes (numeración como regulador real: 130, 131, 132)
        self.planes = {130, 131, 132, 133}  # Planes almacenados
        self.plan_actual = 130  # Plan 130 por defecto (como el real)
        self.hora_inicio_plan = datetime.now()
        self.modo_control = 1  # 1=Local, 2=Ordenador/Central, 3=Manual
        
        # Estado de representación: 0=Apagado, 1=Intermitente, 2=Colores
        self.estado_representacion = 2  # Por defecto: Colores
        
        # Ciclo y fases
        self.ciclo_actual = 0
        self.fase_actual = 1  # Fase 1 o 2
        self.tiempo_en_fase = 0
        self.tiempo_inicio_fase = datetime.now()
        self.en_transitorio = False
        
        # Detectores
        self.detectores = [False] * config.NUM_DETECTORES
        self.contador_detectores = [0] * config.NUM_DETECTORES
        self.tiempo_real_detectores = False
        
        # Alarmas
        self.alarma_roja = False
        self.alarma_lampara = False
        self.alarma_conflicto = False
        
        # Grupos (6 grupos: 1,2,3 vehiculares, 4,5,6 peatonales)
        # Fase 1: Grupos 1,5,6 en verde
        # Fase 2: Grupos 2,3,4 en verde
        self.estado_grupos = [0] * 6  # Estados de los 6 grupos
    
    def get_parametros_plan(self):
        """Obtiene los parámetros del plan actual (ajustado a regulador real)"""
        if self.plan_actual == 131:
            return {"ciclo": 144, "fase1": 72, "fase2": 67, "estructura": 1, "transitorio": 5}
        elif self.plan_actual == 132:
            return {"ciclo": 120, "fase1": 60, "fase2": 55, "estructura": 1, "transitorio": 5}
        else:  # Plan 130 (principal, como el real)
            return {"ciclo": 130, "fase1": 65, "fase2": 60, "estructura": 1, "transitorio": 5}
    
    def get_estado_grupos(self):
        """Obtiene el estado de los 6 grupos según la fase actual, transitorio y estado de representación"""
        # Estados: 0=Apagado, 1=Verde, 2=Ámbar, 3=Rojo
        # IMPORTANTE: G1 y G5 SIEMPRE en ÁMBAR (como regulador real)
        
        # Si está en apagado, todos los grupos apagados
        if self.estado_representacion == 0:
            return [0, 0, 0, 0, 0, 0]
        
        # Si está en intermitente, todos en ámbar intermitente (representamos como 2)
        if self.estado_representacion == 1:
            return [2, 2, 2, 2, 2, 2]  # Todos en ámbar/intermitente
        
        # Estado normal (colores = 2)
        # G1 y G5 SIEMPRE en ámbar (comportamiento del regulador real)
        if self.en_transitorio:
            # Durante transitorio: grupos en ámbar o rojo, pero G1 y G5 siempre ámbar
            if self.fase_actual == 1:
                # Saliendo de fase 2, grupos 2,3,4 en ámbar, resto en rojo
                return [2, 2, 2, 2, 2, 3]  # [G1, G2, G3, G4, G5, G6] - G1,G5 ámbar
            else:
                # Saliendo de fase 1, grupos 1,5,6 en ámbar, resto en rojo  
                return [2, 3, 3, 3, 2, 2]  # G1,G5 ámbar
        else:
            # Fase estable - G1 y G5 SIEMPRE ÁMBAR
            if self.fase_actual == 1:
                # Fase 1: G2 en verde, G3/G4 en rojo, G6 variable
                return [2, 1, 3, 3, 2, 3]  # G1,G5 siempre ámbar
            else:
                # Fase 2: G3 o G4 en verde, resto ajustado
                return [2, 3, 1, 3, 2, 3]  # G1,G5 siempre ámbar
        
    def actualizar_ciclo(self):
        """Actualiza el contador de ciclo según el plan actual"""
        params = self.get_parametros_plan()
        tiempo_transcurrido = (datetime.now() - self.tiempo_inicio_fase).total_seconds()
        
        # Determinar si estamos en transitorio o fase estable
        if self.fase_actual == 1:
            duracion_fase = params["fase1"]
        else:
            duracion_fase = params["fase2"]
        
        # Verificar si debemos cambiar de fase
        if tiempo_transcurrido >= duracion_fase:
            # Cambiar a la siguiente fase
            self.fase_actual = 2 if self.fase_actual == 1 else 1
            self.tiempo_inicio_fase = datetime.now()
            
            # Incrementar ciclo al completar fase 2
            if self.fase_actual == 1:
                self.ciclo_actual = (self.ciclo_actual + 1) % 256
            
            return True  # Hubo cambio de fase
        
        return False  # No hubo cambio
                
    def simular_cambio_detectores(self):
        """Simula cambios aleatorios en detectores"""
        if random.random() < 0.3:  # 30% de cambio
            idx = random.randint(0, self.config.NUM_DETECTORES - 1)
            nuevo_estado = random.choice([True, False])
            if self.detectores[idx] != nuevo_estado:
                self.detectores[idx] = nuevo_estado
                if nuevo_estado:
                    self.contador_detectores[idx] = (self.contador_detectores[idx] + 1) % 256
                return True
        return False


# ============================================================================
# GENERADOR DE RESPUESTAS
# ============================================================================

class GeneradorRespuestas:
    """Genera respuestas según el protocolo UNE"""
    
    @staticmethod
    def respuesta_plan_en_curso(estado, subregulador_id):
        """Respuesta al código 0xC9 - Plan en curso"""
        now = datetime.now()
        datos = bytes([
            estado.plan_actual,
            now.hour,
            now.minute,
            now.second,
            estado.ciclo_actual,
            estado.fase_actual
        ])
        return construir_mensaje(subregulador_id, ProtocoloUNE.PLAN_EN_CURSO, datos)
    
    @staticmethod
    def respuesta_detectores_presencia(estado, subregulador_id):
        """Respuesta al código 0xB0 - Detectores de presencia"""
        datos = bytes(estado.contador_detectores)
        return construir_mensaje(subregulador_id, ProtocoloUNE.DETECTORES_PRESENCIA, datos)
    
    @staticmethod
    def respuesta_alarmas(estado, subregulador_id):
        """Respuesta al código 0xB4 - Alarmas (Estado del regulador)"""
        logger.info("   >>> Generando respuesta 0xB4 (Alarmas)")
        
        # Byte de alarmas con bit 7 activo (0x80 = sin alarmas)
        alarmas = 0x80
        
        # Datos del plan actual (codificados con bit 7)
        plan = codificar_byte_une(estado.plan_actual)
        grupos = codificar_byte_une(6)  # 6 grupos: 1,2,3 vehiculares + 4,5,6 peatonales
        
        # Parámetros del plan actual
        params = estado.get_parametros_plan()
        ciclo = codificar_byte_une(params['ciclo'])
        fase1 = codificar_byte_une(params['fase1'])
        fase2 = codificar_byte_une(params['fase2'])
        estructura = codificar_byte_une(params['estructura'])
        desfase = codificar_byte_une(0)  # Sin desfase
        transitorio = codificar_byte_une(5)  # Ámbar 3 + Rojo-rojo 2
        
        datos = bytes([
            alarmas, plan, grupos, ciclo, fase1, fase2, estructura, transitorio, desfase
        ])
        return construir_mensaje(subregulador_id, ProtocoloUNE.ALARMAS, datos)
    
    @staticmethod
    def respuesta_configuracion(estado, subregulador_id):
        """Respuesta al código 0xB5 - Parámetros de configuración"""
        modo_control_interno = estado.modo_control if hasattr(estado, 'modo_control') else 1
        logger.info(f"   >>> Generando respuesta 0xB5 con modo_control={modo_control_interno}")
        
        # Byte 1: Selección de planes (según UNE - bits) - con bit 7
        if modo_control_interno == 2:  # Ordenador
            byte_seleccion_planes = 0x84  # 0x80 | 0x04 = Bit 2: Plan por ordenador
        else:  # Local
            byte_seleccion_planes = 0x80  # Solo bit 7
        
        # Byte 2: Coordinación y control (según UNE - bits) - con bit 7
        if modo_control_interno == 2:  # Ordenador/Central
            byte_coordinacion = 0x86  # 0x80 | 0x06 = Coordinado por ordenador + Control centralizado
        elif modo_control_interno == 3:  # Manual
            byte_coordinacion = 0x88  # 0x80 | 0x08 = Control manual
        else:  # Local
            byte_coordinacion = 0x80  # Solo bit 7
        
        estado_representacion = codificar_byte_une(2)  # 2 = Colores
        funcionamiento = codificar_byte_une(0)  # 0 = Tiempos fijos
        plan_actual = codificar_byte_une(estado.plan_actual)
        
        # Parámetros del plan actual
        params = estado.get_parametros_plan()
        ciclo = codificar_byte_une(params['ciclo'])
        duracion_fases = codificar_byte_une(params['fase1'])  # Fase más larga
        duracion_minima = codificar_byte_une(10)
        
        estructura = codificar_byte_une(params['estructura'])
        tabla_minimos = codificar_byte_une(1)
        tabla_transitorios = codificar_byte_une(1)
        desfases = codificar_byte_une(0)  # Sin desfase
        
        datos = bytes([
            byte_seleccion_planes,  # Byte 1: Modo selección de planes
            byte_coordinacion,       # Byte 2: Modo coordinación y control
            funcionamiento,          # Byte 3: Método de control (tiempos fijos=0)
            plan_actual, ciclo, estructura, tabla_minimos, tabla_transitorios,
            desfases, duracion_fases, duracion_minima
        ])
        return construir_mensaje(subregulador_id, 0xB5, datos)
    
    @staticmethod
    def respuesta_sincronizacion(estado, subregulador_id):
        """Respuesta al código 0x91 - Sincronización (con codificación bit 7 como real)"""
        params = estado.get_parametros_plan()
        ahora = datetime.now()
        
        # Codificar con bit 7 activo (como regulador real)
        datos = bytes([
            codificar_byte_une(estado.plan_actual & 0xFF),  # Plan con bit 7
            codificar_byte_une(ahora.hour),
            codificar_byte_une(ahora.minute),
            codificar_byte_une(ahora.second),
            codificar_byte_une(estado.ciclo_actual)
        ])
        return construir_mensaje(subregulador_id, 0x91, datos)
    
    @staticmethod
    def respuesta_tablas_programacion(estado, subregulador_id):
        """Respuesta al código 0xB6 - Tablas de programación (con codificación bit 7)"""
        # Definir tres planes con parámetros correctos (usando numeración 130, 131, 132)
        planes = [
            {"id": 130, "ciclo": 130, "grupos": 6, "fases": [65, 60], "estructura": 1, "transitorio": 5, "desfase": 0, "minimo": 20, "maximo": 50},
            {"id": 131, "ciclo": 80, "grupos": 6, "fases": [40, 30], "estructura": 1, "transitorio": 5, "desfase": 0, "minimo": 30, "maximo": 70},
            {"id": 132, "ciclo": 70, "grupos": 6, "fases": [35, 25], "estructura": 1, "transitorio": 5, "desfase": 0, "minimo": 40, "maximo": 90}
        ]
        
        datos = b''
        for plan in planes:
            datos += bytes([
                codificar_byte_une(plan["id"]),
                codificar_byte_une(plan["grupos"]),
                codificar_byte_une(plan["ciclo"]),
                codificar_byte_une(plan["fases"][0]),
                codificar_byte_une(plan["fases"][1]),
                codificar_byte_une(plan["estructura"]),
                codificar_byte_une(plan["transitorio"]),
                codificar_byte_une(plan["desfase"]),
                codificar_byte_une(plan["minimo"]),
                codificar_byte_une(plan["maximo"])
            ])
        
        return construir_mensaje(subregulador_id, 0xB6, datos)
    
    @staticmethod
    def respuesta_trcam(estado):
        """Mensaje TRCAM - Cambio en detectores (tiempo real)"""
        # TRCAM es un mensaje espontáneo (sin subregulador ID específico)
        datos = bytes(estado.contador_detectores)
        return construir_mensaje(0, ProtocoloUNE.DETECTORES_PRESENCIA, datos)
    
    @staticmethod
    def respuesta_mando_directo(estado, subregulador_id):
        """Respuesta al código 0xDB - Estado de mando directo"""
        datos = bytes(estado.estado_grupos)
        return construir_mensaje(subregulador_id, ProtocoloUNE.CONSULTA_MANDO_DIRECTO, datos)
    
    @staticmethod
    def mensaje_cambio_fase(fase_entrante, subregulador_id):
        """Mensaje 0xD5 - Impulso de cambio de fase (envío espontáneo)"""
        datos = bytes([fase_entrante])
        return construir_mensaje(subregulador_id, 0xD5, datos)
    
    @staticmethod
    def mensaje_estado_grupos(estado, subregulador_id):
        """Mensaje 0xB9 - Estado de todos los grupos (envío espontáneo)"""
        # Codificar estado de grupos según UNE: 2 bits por grupo
        # 00=Apagado, 01=Verde, 10=Ámbar, 11=Rojo
        estados = estado.get_estado_grupos()
        
        # Empaquetar 4 grupos por byte (2 bits cada uno)
        # Para 6 grupos necesitamos 2 bytes (4+2)
        byte1 = (estados[0] << 6) | (estados[1] << 4) | (estados[2] << 2) | estados[3]
        byte2 = (estados[4] << 6) | (estados[5] << 4)
        
        datos = bytes([byte1, byte2])
        return construir_mensaje(subregulador_id, 0xB9, datos)


# ============================================================================
# REGULADOR VIRTUAL
# ============================================================================

class ReguladorVirtual:
    """Regulador virtual que escucha en puerto 19000"""
    
    def __init__(self):
        self.config = ConfigRegulador()
        self.estado = EstadoRegulador(self.config)
        
        # Sockets
        self.server_socket = None
        self.client_socket = None
        self.conectado = False
        
        # Control
        self.lock = threading.Lock()
        self.ultimo_ack = time.time()
        self.mensajes_sin_ack = 0
    
    def enviar_mensaje(self, mensaje):
        """Envía un mensaje a la central"""
        if not self.conectado:
            return False
        
        try:
            with self.lock:
                self.client_socket.sendall(mensaje)
            
            msg_hex = mensaje.hex().upper()
            print(f"📤 Enviado: {msg_hex}")
            logger.info(f"TX → {msg_hex}")
            logger.debug(f"TX → Bytes: {' '.join(f'{b:02X}' for b in mensaje)}")
            return True
        except socket.error as e:
            print(f"❌ Error al enviar: {e}")
            logger.error(f"Error al enviar: {e}")
            self.conectado = False
            return False
    
    def procesar_mensaje_recibido(self, data):
        """Procesa un mensaje recibido de la central"""
        msg_hex = data.hex().upper()
        print(f"📥 Recibido: {msg_hex}")
        logger.info(f"RX ← {msg_hex}")
        logger.debug(f"RX ← Longitud: {len(data)} bytes")
        
        # Detectar mensajes concatenados buscando STX después del primer mensaje
        # Los mensajes terminan en ETX (0x03), entonces buscar STX después de un ETX
        mensajes = []
        inicio = 0
        
        for i in range(len(data)):
            if data[i] == 0x03:  # ETX
                # Mensaje completo desde inicio hasta ETX (inclusive)
                if inicio < len(data):
                    mensajes.append(data[inicio:i+1])
                    # Buscar el siguiente STX
                    if i+1 < len(data) and data[i+1] == 0x02:
                        inicio = i+1
                    else:
                        inicio = i+1
        
        if len(mensajes) > 1:
            print(f"   ⚠️ Mensajes concatenados detectados ({len(mensajes)} mensajes)")
            logger.info(f"Mensajes concatenados: {len(mensajes)} mensajes en buffer")
            
            # Procesar cada mensaje por separado
            for i, mensaje_individual in enumerate(mensajes):
                print(f"   → Procesando mensaje {i+1}/{len(mensajes)}: {mensaje_individual.hex().upper()}")
                logger.debug(f"Mensaje {i+1}: {mensaje_individual.hex().upper()}")
                self._procesar_mensaje_individual(mensaje_individual)
            return
        
        # Mensaje individual
        self._procesar_mensaje_individual(data)
    
    def _procesar_mensaje_individual(self, data):
        """Procesa un mensaje individual (no concatenado)"""
        if len(data) < 3:
            print("⚠️ Mensaje muy corto, ignorado")
            logger.warning(f"Mensaje muy corto: {len(data)} bytes")
            return
        
        # Mensajes especiales de 1 byte
        if len(data) == 1:
            if data == ProtocoloUNE.ACK:
                print("✅ ACK recibido")
                logger.info("← ACK (0x06)")
                self.ultimo_ack = time.time()
                self.mensajes_sin_ack = 0
                return
            elif data == ProtocoloUNE.NACK:
                print("⚠️ NACK recibido")
                logger.warning("← NACK (0x15)")
                return
            elif data == ProtocoloUNE.DC1:
                print("🟢 DC1 - Comunicaciones ON")
                logger.info("← DC1 (0x11)")
                self.enviar_mensaje(ProtocoloUNE.ACK)
                return
            elif data == ProtocoloUNE.DC3:
                print("🔴 DC3 - Comunicaciones OFF")
                logger.info("← DC3 (0x13)")
                self.enviar_mensaje(ProtocoloUNE.ACK)
                return
            elif data[0] == ProtocoloUNE.DET:
                print("📊 DET - Petición de detectores")
                logger.info("← DET (0x20)")
                self.estado.contador_detectores = [0, 0, 0, 0]
                respuesta = GeneradorRespuestas.respuesta_detectores_presencia(
                    self.estado, self.config.SUBREGULADOR_ID
                )
                self.enviar_mensaje(respuesta)
                return
        
        # Mensajes con estructura completa
        if not data.startswith(ProtocoloUNE.STX):
            print("⚠️ Mensaje sin STX, ignorado")
            logger.warning(f"Mensaje sin STX - Primer byte: 0x{data[0]:02X}")
            return
        
        if not (data.endswith(ProtocoloUNE.ETX) or data.endswith(ProtocoloUNE.EOT)):
            print("⚠️ Mensaje sin ETX/EOT, ignorado")
            logger.warning(f"Mensaje sin ETX/EOT - Último byte: 0x{data[-1]:02X}")
            return
        
        # Detectar formato de mensaje
        # Formato corto sin checksum: [STX][SUBREG][CÓDIGO][ETX] = 4 bytes
        # Formato estándar con checksum: [STX][SUBREG][CÓDIGO][DATOS...][CHECKSUM][ETX] >= 5 bytes
        sin_checksum = (len(data) == 4)
        
        if sin_checksum:
            print("   ⚠️ Formato sin checksum (4 bytes)")
            logger.info(f"Mensaje sin checksum: {data.hex().upper()}")
            
            # Extraer campos directamente
            subregulador = data[1]
            codigo = data[2]
            datos = b''
        else:
            # Verificar checksum
            checksum_recibido = data[-2]
            valido, checksum_calculado, metodo = verificar_checksum(data[1:-2], checksum_recibido)
            
            if not valido:
                print(f"⚠️ Checksum incorrecto: recibido={checksum_recibido:02X}, calculado={checksum_calculado:02X}")
                
                # Log detallado del error
                logger.error("=" * 70)
                logger.error("ERROR DE CHECKSUM")
                logger.error("=" * 70)
                logger.error(f"Mensaje completo: {data.hex().upper()}")
                logger.error(f"Longitud: {len(data)} bytes")
                logger.error(f"Cuerpo (para checksum): {data[1:-2].hex().upper()}")
                logger.error(f"Checksum recibido: 0x{checksum_recibido:02X} ({checksum_recibido})")
                logger.error(f"Checksum 7 bits (UNE): 0x{checksum_calculado:02X}")
                logger.error(f"Checksum 8 bits: 0x{calcular_checksum_8bits(data[1:-2])[0]:02X}")
                logger.error(f"No coincide con ningún método")
                logger.error("=" * 70)
                
                # CASO ESPECIAL: Mensaje 0xB3 (cambio de modo) viene con checksum inválido
                # pero necesitamos procesarlo de todas formas
                if len(data) >= 4:
                    codigo_especial = data[2]
                    if codigo_especial == 0xB3:
                        logger.warning("⚠️ Procesando 0xB3 a pesar del checksum inválido")
                        print("   ⚠️ Procesando código 0xB3 (cambio de modo) con checksum inválido")
                        # Procesar como mensaje válido
                        subregulador = data[1]
                        datos = data[3:-2] if len(data) > 5 else b''
                        self.procesar_codigo(subregulador, codigo_especial, datos)
                        return
                
                self.enviar_mensaje(ProtocoloUNE.NACK)
                return
            else:
                # Checksum válido, registrar método usado
                if metodo != "7 bits (UNE estándar)":
                    logger.warning(f"⚠️ Checksum válido usando método alternativo: {metodo}")
                    print(f"   ⚠️ Checksum con método: {metodo}")
            
            # Extraer campos
            subregulador = data[1]
            codigo = data[2]
            datos = data[3:-2] if len(data) > 5 else b''
        
        print(f"   Subregulador: {subregulador}, Código: 0x{codigo:02X}, Datos: {datos.hex().upper()}")
        logger.info(f"Mensaje válido → Subreg:{subregulador} Cód:0x{codigo:02X} Datos:{datos.hex().upper()}")
        
        # Procesar según el código
        self.procesar_codigo(subregulador, codigo, datos)
    
    def procesar_codigo(self, subregulador, codigo, datos):
        """Procesa un código de función específico"""
        # En Modo B, responder a todos los subreguladores
        # La central puede preguntar por cualquier subregulador
        print(f"   → Procesando para subregulador {subregulador}")
        logger.debug(f"Procesando subreg:{subregulador} código:0x{codigo:02X}")
        
        if codigo == 0x91:  # Sincronización
            print("   → Pregunta: Sincronización")
            logger.info("Código 0x91 - Sincronización")
            respuesta = GeneradorRespuestas.respuesta_sincronizacion(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.PLAN_EN_CURSO:  # 0xC9
            print("   → Pregunta: Plan en curso")
            logger.info(f"Código 0x{codigo:02X} - Plan en curso: {self.estado.plan_actual}")
            respuesta = GeneradorRespuestas.respuesta_plan_en_curso(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.DETECTORES_PRESENCIA:  # 0xB0
            print("   → Pregunta: Estado de detectores")
            logger.info("Código 0xB0 - Detectores de presencia")
            respuesta = GeneradorRespuestas.respuesta_detectores_presencia(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.ALARMAS:  # 0xB4
            print("   → Pregunta: Alarmas")
            logger.info("Código 0xB4 - Alarmas")
            respuesta = GeneradorRespuestas.respuesta_alarmas(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        elif codigo == 0xB5:  # Parámetros de configuración
            print("   → Pregunta: Parámetros de configuración")
            logger.info("Código 0xB5 - Configuración")
            respuesta = GeneradorRespuestas.respuesta_configuracion(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        elif codigo == 0xB6:  # Tablas de programación
            print("   → Pregunta: Tablas de programación")
            logger.info("Código 0xB6 - Tablas programación")
            respuesta = GeneradorRespuestas.respuesta_tablas_programacion(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        elif codigo == 0xB3:  # Cambio de modo de control / estado de representación
            print(f"\n🔧 CAMBIO DE MODO/ESTADO RECIBIDO")
            if len(datos) >= 1:
                modo_byte_recibido = datos[0]
                # Decodificar byte (quitar bit 7)
                modo_byte = decodificar_byte_une(modo_byte_recibido)
                
                print(f"   Byte recibido: 0x{modo_byte_recibido:02X} → decodificado: 0x{modo_byte:02X} ({modo_byte:08b})")
                logger.info(f"Código 0xB3 - Byte recibido={modo_byte_recibido:02X}, decodificado={modo_byte:02X} ({modo_byte:08b})")
                
                # Bits del byte de modo (según UNE 135401-4):
                # Bits 0-1: Estado de representación (00=Apagado, 01=Intermitente, 10=Colores)
                # Bit 2 (0x04): Plan seleccionado por ordenador
                # Bit 3 (0x08): Control manual
                # Bit 4 (0x10): Control ordenador grupos mando directo
                # Bit 5-6: Reservados
                
                ESTADOS_REPR = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES"}
                MODOS_CONTROL = {1: "LOCAL", 2: "ORDENADOR/CENTRAL", 3: "MANUAL"}
                
                # Guardar estado anterior
                modo_anterior = self.estado.modo_control
                estado_repr_anterior = self.estado.estado_representacion
                
                # Detectar estado de representación (bits 0-1)
                estado_repr_nuevo = modo_byte & 0x03
                cambio_estado_repr = (estado_repr_nuevo != self.estado.estado_representacion)
                self.estado.estado_representacion = estado_repr_nuevo
                
                # Detectar modo de control basado en bits activos
                modo_nuevo = None
                if modo_byte & 0x04 or modo_byte & 0x10:  # Bit 2 o bit 4: Plan por ordenador o grupos mando directo
                    modo_nuevo = 2  # Ordenador/Central
                elif modo_byte & 0x08:  # Bit 3: Control manual
                    modo_nuevo = 3  # Manual
                else:  # Sin bits de control = Local
                    modo_nuevo = 1  # Local
                
                cambio_modo = (modo_nuevo != self.estado.modo_control)
                self.estado.modo_control = modo_nuevo
                
                # Mostrar cambios
                if cambio_estado_repr:
                    print(f"   ✅ Estado representación: {ESTADOS_REPR.get(estado_repr_anterior, '?')} → {ESTADOS_REPR.get(estado_repr_nuevo, '?')}")
                    logger.info(f"✅ Estado representación: {estado_repr_anterior} → {estado_repr_nuevo}")
                
                if cambio_modo:
                    print(f"   ✅ Modo de control: {MODOS_CONTROL.get(modo_anterior, '?')} → {MODOS_CONTROL.get(modo_nuevo, '?')}")
                    logger.info(f"✅ Modo de control: {modo_anterior} → {modo_nuevo}")
                else:
                    print(f"   ℹ️  Modo de control mantiene: {MODOS_CONTROL.get(modo_nuevo, '?')}")
                    logger.info(f"Modo de control mantiene: {modo_nuevo}")
                
            else:
                logger.warning("Código 0xB3 recibido sin datos")
                cambio_estado_repr = False
                cambio_modo = False
            
            # Responder con ACK
            self.enviar_mensaje(ProtocoloUNE.ACK)
            
            # Enviar mensaje espontáneo 0xB3 confirmando el nuevo estado (como regulador real)
            if 'modo_byte' in dir():
                # Construir byte de estado actual (con bit 7)
                byte_estado_actual = codificar_byte_une(
                    (self.estado.modo_control - 1) << 2 |  # Bits 2-3 según modo
                    self.estado.estado_representacion      # Bits 0-1 estado representación
                )
                respuesta_b3 = construir_mensaje(0x80, 0xB3, bytes([byte_estado_actual]))
                print(f"   📤 Confirmación 0xB3: modo={MODOS_CONTROL.get(self.estado.modo_control, '?')}, estado={ESTADOS_REPR.get(self.estado.estado_representacion, '?')}")
                logger.info(f"Enviando confirmación 0xB3: byte={byte_estado_actual:02X}")
                self.enviar_mensaje(respuesta_b3)
            
            # Si hubo cambio de estado de representación, enviar mensaje de grupos actualizado
            if 'cambio_estado_repr' in dir() and cambio_estado_repr:
                # Enviar mensaje 0xD4 confirmando el nuevo estado
                ESTADOS_REPR = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES"}
                respuesta_d4 = bytes([
                    ProtocoloUNE.STX[0],
                    0x80,  # Subregulador 128
                    0xD4,  # Código Estados
                    self.estado.estado_representacion
                ])
                checksum_d4 = calcular_checksum(respuesta_d4[1:])
                respuesta_d4 += checksum_d4 + bytes([ProtocoloUNE.ETX[0]])
                print(f"   📤 Enviando confirmación estado: {ESTADOS_REPR.get(self.estado.estado_representacion, '?')}")
                self.enviar_mensaje(respuesta_d4)
                
                # Enviar mensaje 0xB9 con estado de grupos actualizado
                msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, 0x81)
                estados = self.estado.get_estado_grupos()
                print(f"   📤 Enviando estado grupos: {estados}")
                self.enviar_mensaje(msg_grupos)
        
        elif codigo == 0xB7:  # Grupos con incompatibilidad
            print("   → Pregunta: Incompatibilidades")
            logger.info("Código 0xB7 - Incompatibilidades")
            # Respuesta vacía: no hay incompatibilidades
            respuesta = bytes([
                ProtocoloUNE.STX[0],
                subregulador,
                0xB7
            ])
            checksum = calcular_checksum(respuesta[1:])
            respuesta += checksum + bytes([ProtocoloUNE.ETX[0]])
            self.enviar_mensaje(respuesta)
        
        elif codigo == 0xD4 or codigo == 0x54:  # Estados (cambio de representación)
            # Código 0xD4 (11010100) o 0x54 (01010100) - Estados
            # 0=Apagado, 1=Intermitente, 2=Colores
            ESTADOS_NOMBRES = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES"}
            
            if len(datos) >= 1:
                nuevo_estado = datos[0] & 0x03  # Solo los 2 bits inferiores
                estado_anterior = self.estado.estado_representacion
                self.estado.estado_representacion = nuevo_estado
                
                nombre_estado = ESTADOS_NOMBRES.get(nuevo_estado, f"DESCONOCIDO({nuevo_estado})")
                print(f"   ✅ Estado cambiado: {ESTADOS_NOMBRES.get(estado_anterior, '?')} → {nombre_estado}")
                logger.info(f"Código 0x{codigo:02X} - Cambio de estado: {estado_anterior} → {nuevo_estado} ({nombre_estado})")
                
                # Responder con ACK
                self.enviar_mensaje(ProtocoloUNE.ACK)
                
                # Enviar mensaje de confirmación con el nuevo estado
                respuesta = bytes([
                    ProtocoloUNE.STX[0],
                    subregulador,
                    0xD4 if codigo == 0xD4 else 0x54,
                    nuevo_estado
                ])
                checksum = calcular_checksum(respuesta[1:])
                respuesta += checksum + bytes([ProtocoloUNE.ETX[0]])
                self.enviar_mensaje(respuesta)
                logger.info(f"   Respuesta estado: {nombre_estado}")
            else:
                # Sin datos: consulta del estado actual
                logger.info(f"Código 0x{codigo:02X} - Consulta de estado actual: {self.estado.estado_representacion}")
                print(f"   → Consulta: Estado actual es {ESTADOS_NOMBRES.get(self.estado.estado_representacion, '?')}")
                
                respuesta = bytes([
                    ProtocoloUNE.STX[0],
                    subregulador,
                    0xD4 if codigo == 0xD4 else 0x54,
                    self.estado.estado_representacion
                ])
                checksum = calcular_checksum(respuesta[1:])
                respuesta += checksum + bytes([ProtocoloUNE.ETX[0]])
                self.enviar_mensaje(respuesta)
        
        elif codigo == 0x92:  # Cambio de plan (orden o consulta)
            if len(datos) >= 1:
                nuevo_plan = datos[0]
                print(f"   → Orden: Cambiar a PLAN {nuevo_plan}")
                logger.info(f"Código 0x92 - Cambio a plan {nuevo_plan}")
                
                # Cambiar el plan actual
                plan_anterior = self.estado.plan_actual
                self.estado.plan_actual = nuevo_plan
                self.estado.hora_inicio_plan = datetime.now()
                print(f"   ✅ Plan cambiado: {plan_anterior} → {nuevo_plan}")
                logger.info(f"✅ Plan cambiado: {plan_anterior} → {nuevo_plan}")
            else:
                # Sin datos: la central consulta el plan actual sin cambiarlo
                logger.info(f"Código 0x92 - Consulta de plan actual: {self.estado.plan_actual}")
                print(f"   → Consulta: Plan actual es {self.estado.plan_actual}")
            
            # Responder confirmando el plan actual
            respuesta = bytes([
                ProtocoloUNE.STX[0],
                subregulador,
                0x92,
                self.estado.plan_actual
            ])
            checksum = calcular_checksum(respuesta[1:])
            respuesta += checksum + bytes([ProtocoloUNE.ETX[0]])
            self.enviar_mensaje(respuesta)
            logger.info(f"   Respuesta 0x92: Plan {self.estado.plan_actual}")
        
        elif codigo == 0x94:  # Datos de tráfico / Tabla transitorios
            print("   → Pregunta: Datos de tráfico")
            logger.info("Código 0x94 - Datos tráfico")
            # Enviar ACK como reconocimiento
            self.enviar_mensaje(ProtocoloUNE.ACK)
        
        elif codigo == ProtocoloUNE.DETECTORES_TIEMPO_REAL:  # 0xD3
            if len(datos) >= 1:
                activar = datos[0] == 1
                self.estado.tiempo_real_detectores = activar
                print(f"   → Orden: Tiempo real {'ACTIVADO' if activar else 'DESACTIVADO'}")
                logger.info(f"Código 0xD3 - Tiempo real {'ON' if activar else 'OFF'}")
        
        elif codigo == ProtocoloUNE.SELECCION_PLAN:  # 0x51
            if len(datos) >= 4:
                nuevo_plan = datos[0]
                hora = datos[1]
                minuto = datos[2]
                segundo = datos[3]
                print(f"   → Orden: Cambiar a plan {nuevo_plan} a las {hora:02d}:{minuto:02d}:{segundo:02d}")
                logger.info(f"Código 0x51 - Cambio a plan {nuevo_plan}")
                
                if nuevo_plan in self.estado.planes:
                    plan_anterior = self.estado.plan_actual
                    self.estado.plan_actual = nuevo_plan
                    self.estado.hora_inicio_plan = datetime.now()
                    print(f"   ✅ Plan cambiado a {nuevo_plan}")
                    logger.info(f"Plan cambiado: {plan_anterior} → {nuevo_plan}")
                    
                    respuesta = GeneradorRespuestas.respuesta_plan_en_curso(
                        self.estado, subregulador
                    )
                    self.enviar_mensaje(respuesta)
                else:
                    logger.warning(f"Plan {nuevo_plan} no existe")
        
        elif codigo == ProtocoloUNE.MANDO_DIRECTO:  # 0xDC
            print("   → Orden: Mando directo de grupos")
            logger.info(f"Código 0xDC - Mando directo: {datos.hex().upper()}")
            if len(datos) == self.config.NUM_GRUPOS:
                self.estado.estado_grupos = list(datos)
        
        elif codigo == ProtocoloUNE.CONSULTA_MANDO_DIRECTO:  # 0xDB
            print("   → Pregunta: Estado de mando directo")
            logger.info("Código 0xDB - Consulta mando directo")
            respuesta = GeneradorRespuestas.respuesta_mando_directo(
                self.estado, subregulador
            )
            self.enviar_mensaje(respuesta)
        
        else:
            print(f"   ⚠️ Código 0x{codigo:02X} no implementado")
            logger.warning(f"Código 0x{codigo:02X} no implementado")
    
    def hilo_recepcion(self):
        """Hilo para recibir mensajes de la central"""
        logger.debug("Hilo de recepción iniciado")
        
        while self.conectado:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    print("\n⚠️ Conexión cerrada por la central")
                    logger.info("Conexión cerrada por la central")
                    self.conectado = False
                    break
                
                self.procesar_mensaje_recibido(data)
            
            except socket.timeout:
                continue
            except socket.error as e:
                print(f"\n❌ Error en recepción: {e}")
                logger.error(f"Error en recepción: {e}")
                self.conectado = False
                break
        
        logger.debug("Hilo de recepción finalizado")
    
    def hilo_simulacion(self):
        """Hilo para simular cambios en el regulador"""
        logger.debug("Hilo de simulación iniciado")
        
        while self.conectado:
            time.sleep(1)  # Verificar cada segundo
            
            # Actualizar ciclo y detectar cambios de fase
            cambio_fase = self.estado.actualizar_ciclo()
            
            if cambio_fase:
                # Hubo cambio de fase - enviar notificación
                fase_entrante = self.estado.fase_actual
                
                # Enviar mensaje 0xD5 (Cambio de fase) a subregulador 129
                msg_cambio = GeneradorRespuestas.mensaje_cambio_fase(fase_entrante, 129)
                print(f"\n🚦 CAMBIO DE FASE → Fase {fase_entrante}")
                logger.info(f"Cambio de fase detectado: Fase {fase_entrante}")
                self.enviar_mensaje(msg_cambio)
                
                # Enviar mensaje 0xB9 (Estado de grupos) a subregulador 129
                time.sleep(0.1)
                msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, 129)
                estados = self.estado.get_estado_grupos()
                logger.info(f"Estado grupos: {estados}")
                self.enviar_mensaje(msg_grupos)
            
            # Simular cambios en detectores si tiempo real está activo
            if self.estado.tiempo_real_detectores:
                cambio = self.estado.simular_cambio_detectores()
                if cambio:
                    trcam = GeneradorRespuestas.respuesta_trcam(self.estado)
                    print("\n🔔 Cambio en detectores - Enviando TRCAM")
                    logger.info("Cambio en detectores detectado - Enviando TRCAM")
                    self.enviar_mensaje(trcam)
        
        logger.debug("Hilo de simulación finalizado")
    
    def hilo_keep_alive(self):
        """Hilo para enviar mensajes periódicos de estado (keep-alive)"""
        logger.debug("Hilo de keep-alive iniciado")
        
        # Si está en modo A, no enviar keep-alive periódico
        if not self.config.ENVIAR_KEEP_ALIVE:
            logger.info("Keep-alive desactivado (modo A)")
            while self.conectado:
                time.sleep(10)
            logger.debug("Hilo de keep-alive finalizado")
            return
        
        contador = 0
        
        while self.conectado:
            time.sleep(5)  # Enviar cada 5 segundos
            
            if self.conectado and self.client_socket:
                contador += 1
                # Enviar mensaje de estado para subregulador 128 (0x80)
                # La central espera recibir actualizaciones periódicas
                respuesta = GeneradorRespuestas.respuesta_alarmas(
                    self.estado, 0x80
                )
                
                print(f"💓 Keep-alive #{contador} - Enviando estado...")
                logger.info(f"Keep-alive #{contador} - Enviando mensaje de estado")
                self.enviar_mensaje(respuesta)
        
        logger.debug("Hilo de keep-alive finalizado")
    
    def iniciar_servidor(self):
        """Inicia el servidor y espera conexión de la central"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.config.ESCUCHAR_IP, self.config.ESCUCHAR_PORT))
            self.server_socket.listen(1)
            
            print(f"📡 Servidor iniciado en puerto {self.config.ESCUCHAR_PORT}")
            print("⏳ Esperando conexión de la central...\n")
            logger.info(f"Servidor escuchando en {self.config.ESCUCHAR_IP}:{self.config.ESCUCHAR_PORT}")
            
            self.client_socket, addr = self.server_socket.accept()
            self.client_socket.settimeout(1.0)
            self.conectado = True
            
            print(f"✅ Central conectada desde {addr[0]}:{addr[1]}\n")
            logger.info(f"Central conectada desde {addr[0]}:{addr[1]}")
            
            # Enviar mensaje de estado inicial (palabra de estado) para subregulador 128 (0x80)
            # La central suele preguntar por subregulador 128
            print("📤 Enviando estado inicial...")
            logger.info("Enviando estado inicial del regulador")
            
            # Enviar alarmas (palabra de estado) para subregulador 128 (0x80)
            respuesta = GeneradorRespuestas.respuesta_alarmas(
                self.estado, 0x80
            )
            self.enviar_mensaje(respuesta)
            
            return True
        
        except socket.error as e:
            print(f"❌ Error al iniciar servidor: {e}")
            logger.error(f"Error al iniciar servidor: {e}")
            return False
    
    def ejecutar(self):
        """Ejecuta el regulador virtual"""
        print("\n" + "="*60)
        print(f"🚦 REGULADOR VIRTUAL TIPO M - MODO {self.config.MODO_OPERACION}")
        print("="*60)
        print(f"📍 Subregulador ID: {self.config.SUBREGULADOR_ID}")
        print(f"🌐 Escuchando en: {self.config.ESCUCHAR_IP}:{self.config.ESCUCHAR_PORT}")
        print(f"⚙️  Modo: {self.config.MODO_OPERACION} (Asíncrono - Envío espontáneo)")
        print("="*60 + "\n")
        
        if not self.iniciar_servidor():
            return
        
        # Iniciar hilos
        hilo_rx = threading.Thread(target=self.hilo_recepcion, daemon=True)
        hilo_sim = threading.Thread(target=self.hilo_simulacion, daemon=True)
        hilo_keepalive = threading.Thread(target=self.hilo_keep_alive, daemon=True)
        
        hilo_rx.start()
        hilo_sim.start()
        hilo_keepalive.start()
        
        print("✅ Regulador virtual ejecutándose en Modo B")
        print("   (Envía mensajes espontáneamente cada 5 segundos)")
        print("   Presiona Ctrl+C para detener\n")
        print("="*60)
        
        try:
            while self.conectado:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Deteniendo regulador...")
            logger.info("Deteniendo regulador (Ctrl+C)")
        finally:
            if self.client_socket:
                self.client_socket.close()
            if self.server_socket:
                self.server_socket.close()
            print("👋 Regulador detenido")
            logger.info("Regulador detenido")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("INICIANDO REGULADOR VIRTUAL - MODO B")
    logger.info("=" * 70)
    regulador = ReguladorVirtual()
    regulador.ejecutar()
    logger.info("=" * 70)
    logger.info("REGULADOR FINALIZADO")
    logger.info("=" * 70)
