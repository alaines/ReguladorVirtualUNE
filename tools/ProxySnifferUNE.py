#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
PROXY SNIFFER UNE 135401-4
================================================================================
Programa que actúa como intermediario (man-in-the-middle) entre una central
de tráfico y un regulador real, capturando y decodificando todo el tráfico.

Arquitectura:
    Central → Proxy (puerto local) → Regulador Real (IP:puerto destino)

Uso:
    python ProxySnifferUNE.py --regulador-ip 192.168.1.100 --regulador-puerto 19000

Autor: Generado para análisis de protocolo UNE 135401-4
Fecha: 2026-01-14
================================================================================
"""

import socket
import threading
import time
import logging
import argparse
from datetime import datetime
from collections import defaultdict

# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

# Crear logger principal
logger = logging.getLogger('ProxySniffer')
logger.setLevel(logging.DEBUG)

# Formato de log
log_format = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', 
                                datefmt='%Y-%m-%d %H:%M:%S')

# Nombre de archivo con fecha (se rotará diariamente)
fecha_inicio = datetime.now().strftime("%Y%m%d")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f'sniffer_log_{timestamp}.txt'

# Handler para archivo
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_format)
logger.addHandler(file_handler)

# Handler para consola (solo INFO y superior)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)

# Variable global para rotación de log
current_log_date = fecha_inicio


# ============================================================================
# DICCIONARIO DE CÓDIGOS UNE 135401-4
# ============================================================================

CODIGOS_UNE = {
    # Sincronización y datos
    0x11: "Sincronización (0x11)",
    0x91: "Sincronización (0x91)",
    0x12: "Selección de plan (0x12)",
    0x92: "Selección de plan (0x92)",
    0x13: "Detectores tiempo real (0x13)",
    0x93: "Detectores tiempo real (0x93)",
    0x14: "Datos de tráfico (0x14)",
    0x94: "Datos de tráfico (0x94)",
    
    # Parámetros y configuración
    0x30: "Parámetros de tráfico (0x30)",
    0xB0: "Parámetros de tráfico (0xB0)",
    0x31: "Ciclo de regulación (0x31)",
    0xB1: "Ciclo de regulación (0xB1)",
    0x32: "Tabla de desfases (0x32)",
    0xB2: "Tabla de desfases (0xB2)",
    0x33: "Cambio modo control (0x33)",
    0xB3: "Cambio modo control (0xB3)",
    0x34: "Estado regulador/Alarmas (0x34)",
    0xB4: "Estado regulador/Alarmas (0xB4)",
    0x35: "Parámetros configuración (0x35)",
    0xB5: "Parámetros configuración (0xB5)",
    0x36: "Tablas programación (0x36)",
    0xB6: "Tablas programación (0xB6)",
    0x37: "Incompatibilidades (0x37)",
    0xB7: "Incompatibilidades (0xB7)",
    0x38: "Parámetros detectores (0x38)",
    0xB8: "Parámetros detectores (0xB8)",
    0x39: "Estado grupos (0x39)",
    0xB9: "Estado grupos (0xB9)",
    
    # Estados y control
    0x50: "Parámetros plan (0x50)",
    0xD0: "Parámetros plan (0xD0)",
    0x51: "Selección plan (0x51)",
    0xD1: "Selección plan (0xD1)",
    0x52: "Puesta en hora (0x52)",
    0xD2: "Puesta en hora (0xD2)",
    0x53: "Detectores (0x53)",
    0xD3: "Detectores (0xD3)",
    0x54: "Estados (0x54)",
    0xD4: "Estados (0xD4)",
    0x55: "Impulso cambio fase (0x55)",
    0xD5: "Impulso cambio fase (0xD5)",
    0x56: "Mando directo salidas (0x56)",
    0xD6: "Mando directo salidas (0xD6)",
    
    # Mando directo
    0x5B: "Consulta mando directo (0x5B)",
    0xDB: "Consulta mando directo (0xDB)",
}

ESTADOS_REPR = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES"}
ESTADOS_GRUPO = {0: "Apagado", 1: "Verde", 2: "Ámbar", 3: "Rojo"}
MODOS_CONTROL = {1: "Local", 2: "Ordenador", 3: "Manual"}


# ============================================================================
# DECODIFICADOR DE MENSAJES UNE
# ============================================================================

class DecodificadorUNE:
    """Decodifica mensajes del protocolo UNE 135401-4"""
    
    STX = 0x02
    ETX = 0x03
    ACK = 0x06
    NAK = 0x15
    
    @staticmethod
    def decodificar_byte_une(byte_codificado):
        """Decodifica un byte con codificación UNE (bit 7 invertido)"""
        return byte_codificado ^ 0x80
    
    @staticmethod
    def decodificar_mensaje(datos_hex, direccion="?"):
        """
        Decodifica un mensaje UNE y retorna descripción legible
        
        Args:
            datos_hex: bytes del mensaje
            direccion: "C→R" (Central a Regulador) o "R→C" (Regulador a Central)
        
        Returns:
            dict con información decodificada
        """
        if not datos_hex:
            return {"error": "Mensaje vacío"}
        
        resultado = {
            "hex": datos_hex.hex().upper(),
            "longitud": len(datos_hex),
            "direccion": direccion,
            "tipo": "desconocido",
            "descripcion": "",
            "detalles": []
        }
        
        # Verificar ACK/NAK
        if len(datos_hex) == 1:
            if datos_hex[0] == DecodificadorUNE.ACK:
                resultado["tipo"] = "ACK"
                resultado["descripcion"] = "✓ Confirmación (ACK)"
                return resultado
            elif datos_hex[0] == DecodificadorUNE.NAK:
                resultado["tipo"] = "NAK"
                resultado["descripcion"] = "✗ Error (NAK)"
                return resultado
        
        # Verificar formato mensaje UNE
        if len(datos_hex) >= 4 and datos_hex[0] == DecodificadorUNE.STX:
            return DecodificadorUNE._decodificar_mensaje_une(datos_hex, resultado)
        
        # Mensaje no reconocido
        resultado["descripcion"] = f"Datos sin formato UNE: {datos_hex.hex().upper()}"
        return resultado
    
    @staticmethod
    def _decodificar_mensaje_une(datos, resultado):
        """Decodifica un mensaje con formato UNE estándar"""
        
        # Estructura: STX + Subregulador + Código + [Datos...] + [Checksum] + ETX
        subregulador = datos[1]
        codigo = datos[2]
        
        # Determinar si tiene checksum (mensajes de 5+ bytes con ETX al final)
        if datos[-1] == DecodificadorUNE.ETX:
            if len(datos) == 4:  # Sin checksum: STX + SUB + COD + ETX
                datos_payload = bytes()
                checksum = None
            elif len(datos) >= 5:  # Con datos y/o checksum
                datos_payload = datos[3:-2]  # Todo menos STX, SUB, COD, CHK, ETX
                checksum = datos[-2]
            else:
                datos_payload = bytes()
                checksum = None
        else:
            datos_payload = datos[3:]
            checksum = None
        
        resultado["tipo"] = "mensaje_une"
        resultado["subregulador"] = subregulador
        resultado["codigo"] = codigo
        resultado["codigo_hex"] = f"0x{codigo:02X}"
        resultado["datos"] = datos_payload.hex().upper() if datos_payload else ""
        resultado["checksum"] = f"0x{checksum:02X}" if checksum else "N/A"
        
        # Obtener nombre del código
        nombre_codigo = CODIGOS_UNE.get(codigo, f"Código desconocido (0x{codigo:02X})")
        resultado["descripcion"] = f"Sub:{subregulador} → {nombre_codigo}"
        
        # Decodificar datos específicos según el código
        DecodificadorUNE._decodificar_datos_especificos(codigo, datos_payload, resultado)
        
        return resultado
    
    @staticmethod
    def _decodificar_datos_especificos(codigo, datos, resultado):
        """Decodifica los datos según el código específico"""
        
        detalles = resultado["detalles"]
        decodificar = DecodificadorUNE.decodificar_byte_une
        
        # Sincronización (0x91, 0x11)
        if codigo in [0x91, 0x11]:
            if len(datos) >= 8:
                plan = datos[0]  # El plan ya viene sin codificar en sincronización
                hora = decodificar(datos[1])
                minuto = decodificar(datos[2])
                segundo = decodificar(datos[3])
                fase = decodificar(datos[4])
                ciclo_msb = decodificar(datos[5])
                ciclo_lsb = decodificar(datos[6])
                resta = decodificar(datos[7])
                ciclo = (ciclo_msb << 7) | ciclo_lsb
                
                detalles.append(f"⏰ PLAN: {plan}")
                detalles.append(f"⏰ Hora: {hora:02d}:{minuto:02d}:{segundo:02d}")
                detalles.append(f"⏰ Fase actual: {fase}")
                detalles.append(f"⏰ Ciclo: {ciclo}s, Tiempo restante: {resta}s")
        
        # Selección de plan (0x92, 0x12, 0xD1, 0x51)
        elif codigo in [0x92, 0x12, 0xD1, 0x51]:
            if len(datos) >= 1:
                plan = decodificar(datos[0])
                detalles.append(f"🔔 CAMBIO A PLAN: {plan}")
                if len(datos) >= 4:
                    hora = decodificar(datos[1])
                    minuto = decodificar(datos[2])
                    segundo = decodificar(datos[3])
                    detalles.append(f"   Hora inicio: {hora:02d}:{minuto:02d}:{segundo:02d}")
        
        # Estado regulador / Alarmas (0xB4, 0x34)
        elif codigo in [0xB4, 0x34]:
            if len(datos) >= 1:
                byte_estado = decodificar(datos[0])
                detalles.append(f"Estado: 0x{byte_estado:02X} ({byte_estado:08b})")
                if byte_estado & 0x01: detalles.append("  ⚠️ Alarma roja activa")
                if byte_estado & 0x02: detalles.append("  ⚠️ Alarma lámpara")
                if byte_estado & 0x04: detalles.append("  ⚠️ Alarma conflicto")
                if not (byte_estado & 0x07): detalles.append("  ✅ Sin alarmas")
            if len(datos) >= 2:
                grupos = decodificar(datos[1])
                detalles.append(f"Grupos: {grupos}")
            if len(datos) >= 3:
                ciclo = decodificar(datos[2])
                detalles.append(f"Ciclo: {ciclo}s")
        
        # Cambio modo control (0xB3, 0x33)
        elif codigo in [0xB3, 0x33]:
            if len(datos) >= 1:
                modo_byte = decodificar(datos[0])
                detalles.append(f"Byte modo: 0x{modo_byte:02X} ({modo_byte:08b})")
                
                # Estado representación (bits 0-1)
                estado_repr = modo_byte & 0x03
                detalles.append(f"  📊 Estado repr: {ESTADOS_REPR.get(estado_repr, '?')}")
                
                # Determinar modo de control
                if modo_byte & 0x04 or modo_byte & 0x10:
                    detalles.append(f"  🖥️  MODO: ORDENADOR (Central)")
                elif modo_byte & 0x08:
                    detalles.append(f"  ✋ MODO: MANUAL")
                else:
                    detalles.append(f"  🏠 MODO: LOCAL")
        
        # Parámetros configuración (0xB5, 0x35)
        elif codigo in [0xB5, 0x35]:
            if len(datos) >= 4:
                fases = decodificar(datos[0])
                grupos = decodificar(datos[1])
                planes = decodificar(datos[2])
                ciclo = decodificar(datos[3])
                detalles.append(f"Configuración: {fases} fases, {grupos} grupos, {planes} planes")
                detalles.append(f"Ciclo base: {ciclo}s")
        
        # Estados (0xD4, 0x54)
        elif codigo in [0xD4, 0x54]:
            if len(datos) >= 4:
                repr_byte = decodificar(datos[0])
                planes_byte = decodificar(datos[1])
                coord_byte = decodificar(datos[2])
                metodo_byte = decodificar(datos[3])
                
                estado_repr = repr_byte & 0x03
                detalles.append(f"📊 Estado: {ESTADOS_REPR.get(estado_repr, '?')}")
                
                # Modo de selección de planes
                if planes_byte & 0x04:
                    detalles.append(f"🖥️  Plan por ORDENADOR")
                elif planes_byte & 0x01:
                    detalles.append(f"📡 Control externo")
                else:
                    detalles.append(f"🏠 Control LOCAL de planes")
                
                # Modo de coordinación
                if coord_byte & 0x04:
                    detalles.append(f"🖥️  Control CENTRALIZADO")
                elif coord_byte & 0x08:
                    detalles.append(f"✋ Control MANUAL")
                elif coord_byte & 0x01:
                    detalles.append(f"🏠 Coordinado LOCAL (reloj interno)")
                else:
                    detalles.append(f"📡 Coordinado señal externa")
                
                # Método
                metodos = ["Tiempos fijos", "Semiactuado", "Actuado total"]
                if metodo_byte < len(metodos):
                    detalles.append(f"⚙️  Método: {metodos[metodo_byte]}")
        
        # Impulso cambio fase (0xD5, 0x55)
        elif codigo in [0xD5, 0x55]:
            if len(datos) >= 1:
                fase = decodificar(datos[0])
                detalles.append(f"➡️  Fase entrante: {fase}")
        
        # Estado grupos (0xB9, 0x39)
        elif codigo in [0xB9, 0x39]:
            if len(datos) >= 1:
                detalles.append("🚦 Estados de grupos:")
                for i, byte_val in enumerate(datos):
                    val_decodificado = decodificar(byte_val)
                    # Mapeo de valores
                    if val_decodificado == 0:
                        estado_nombre = "⚫ APAGADO"
                    elif val_decodificado == 1:
                        estado_nombre = "🔴 ROJO"
                    elif val_decodificado == 4:
                        estado_nombre = "🟡 ÁMBAR"
                    elif val_decodificado == 16:
                        estado_nombre = "🟢 VERDE"
                    else:
                        estado_nombre = f"? ({val_decodificado})"
                    
                    detalles.append(f"   G{i+1}: {byte_val:02X} → {val_decodificado:02d} = {estado_nombre}")
        
        # Puesta en hora (0xD2, 0x52)
        elif codigo in [0xD2, 0x52]:
            if len(datos) >= 7:
                dia = decodificar(datos[0])
                hora = decodificar(datos[1])
                minuto = decodificar(datos[2])
                segundo = decodificar(datos[3])
                dia_mes = decodificar(datos[4])
                mes = decodificar(datos[5])
                anio = decodificar(datos[6])
                
                dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                nombre_dia = dias_semana[dia-1] if 1 <= dia <= 7 else f"Día {dia}"
                
                detalles.append(f"📅 {nombre_dia}")
                detalles.append(f"⏰ Hora: {hora:02d}:{minuto:02d}:{segundo:02d}")
                detalles.append(f"📅 Fecha: {dia_mes:02d}/{mes:02d}/20{anio:02d}")


# ============================================================================
# ROTACIÓN DE LOG DIARIA
# ============================================================================

def rotar_log_si_necesario():
    """Rota el archivo de log si cambió el día"""
    global current_log_date, file_handler, log_filename
    
    fecha_actual = datetime.now().strftime("%Y%m%d")
    
    if fecha_actual != current_log_date:
        # Cerrar handler actual
        logger.removeHandler(file_handler)
        file_handler.close()
        
        # Crear nuevo archivo
        timestamp_nuevo = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f'sniffer_log_{timestamp_nuevo}.txt'
        
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
        
        current_log_date = fecha_actual
        logger.info(f"="*60)
        logger.info(f"NUEVO DÍA - ROTACIÓN DE LOG")
        logger.info(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"="*60)
        
        print(f"\n📅 Nuevo día detectado - Log rotado a: {log_filename}")


# ============================================================================
# PROXY SNIFFER
# ============================================================================

class ProxySniffer:
    """
    Proxy que intercepta comunicación entre Central y Regulador
    Diseñado para captura prolongada con:
    - Rotación de logs diaria
    - Reconexión automática
    - Estadísticas acumuladas
    """
    
    def __init__(self, puerto_local, regulador_ip, regulador_puerto):
        self.puerto_local = puerto_local
        self.regulador_ip = regulador_ip
        self.regulador_puerto = regulador_puerto
        
        self.server_socket = None
        self.activo = True
        self.conexiones_totales = 0
        
        # Estadísticas
        self.stats = {
            "mensajes_central": 0,
            "mensajes_regulador": 0,
            "bytes_central": 0,
            "bytes_regulador": 0,
            "codigos_central": defaultdict(int),
            "codigos_regulador": defaultdict(int),
            "inicio": datetime.now()
        }
        
        # Seguimiento de eventos importantes
        self.eventos = []
        self.estado_actual = {
            "plan": None,
            "modo": None,
            "conexion_iniciada": False
        }
        
        self.decodificador = DecodificadorUNE()
    
    def iniciar(self):
        """Inicia el servidor proxy"""
        
        print("\n" + "="*70)
        print("🔍 PROXY SNIFFER UNE 135401-4")
        print("="*70)
        print(f"📡 Puerto local (para Central): {self.puerto_local}")
        print(f"🎯 Regulador destino: {self.regulador_ip}:{self.regulador_puerto}")
        print(f"📝 Log: sniffer_log_{timestamp}.txt")
        print("="*70 + "\n")
        
        logger.info("="*60)
        logger.info("PROXY SNIFFER INICIADO - MODO CAPTURA PROLONGADA")
        logger.info(f"Puerto local: {self.puerto_local}")
        logger.info(f"Regulador: {self.regulador_ip}:{self.regulador_puerto}")
        logger.info(f"Archivo log inicial: {log_filename}")
        logger.info("="*60)
        
        try:
            # Crear socket servidor
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.puerto_local))
            self.server_socket.listen(1)
            
            print(f"⏳ Esperando conexión de la central en puerto {self.puerto_local}...")
            print(f"📝 Logs se guardan en: {log_filename}")
            print(f"🔄 Los logs rotarán automáticamente cada día")
            print(f"\n💡 Presiona Ctrl+C para detener y ver estadísticas\n")
            
            while self.activo:
                try:
                    # Verificar rotación de log periódicamente
                    rotar_log_si_necesario()
                    
                    self.server_socket.settimeout(60)  # Timeout para verificar rotación
                    client_socket, client_addr = self.server_socket.accept()
                    
                    self.conexiones_totales += 1
                    print(f"\n✅ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Central conectada desde {client_addr[0]}:{client_addr[1]} (Conexión #{self.conexiones_totales})")
                    logger.info(f"="*60)
                    logger.info(f"NUEVA CONEXIÓN #{self.conexiones_totales}")
                    logger.info(f"Central conectada desde {client_addr}")
                    logger.info(f"="*60)
                    
                    # Manejar conexión en hilo
                    thread = threading.Thread(
                        target=self.manejar_conexion,
                        args=(client_socket, client_addr)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.activo:
                        logger.error(f"Error aceptando conexión: {e}")
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Deteniendo proxy...")
        finally:
            self.detener()
    
    def manejar_conexion(self, central_socket, central_addr):
        """Maneja una conexión de la central"""
        
        regulador_socket = None
        intentos_reconexion = 0
        max_intentos = 3
        
        while intentos_reconexion < max_intentos and self.activo:
            try:
                # Conectar al regulador real
                print(f"🔗 Conectando a regulador {self.regulador_ip}:{self.regulador_puerto}...")
                regulador_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                regulador_socket.settimeout(10)
                regulador_socket.connect((self.regulador_ip, self.regulador_puerto))
                break  # Conexión exitosa
            except Exception as e:
                intentos_reconexion += 1
                logger.warning(f"Intento {intentos_reconexion}/{max_intentos} fallido: {e}")
                if intentos_reconexion < max_intentos:
                    print(f"⚠️ Reintentando conexión al regulador en 5 segundos...")
                    time.sleep(5)
                else:
                    print(f"❌ No se pudo conectar al regulador después de {max_intentos} intentos")
                    logger.error(f"Conexión al regulador fallida después de {max_intentos} intentos")
                    central_socket.close()
                    return
        
        try:
            print(f"✅ Conectado al regulador real")
            logger.info(f"Conectado a regulador {self.regulador_ip}:{self.regulador_puerto}")
            
            # Crear hilos para cada dirección
            t1 = threading.Thread(
                target=self.reenviar_datos,
                args=(central_socket, regulador_socket, "C→R", "Central", "Regulador")
            )
            t2 = threading.Thread(
                target=self.reenviar_datos,
                args=(regulador_socket, central_socket, "R→C", "Regulador", "Central")
            )
            
            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()
            
            # Esperar a que terminen
            t1.join()
            t2.join()
            
        except Exception as e:
            print(f"❌ Error en conexión: {e}")
            logger.error(f"Error en conexión: {e}")
        finally:
            if regulador_socket:
                regulador_socket.close()
            central_socket.close()
            print(f"\n🔌 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Conexión cerrada con {central_addr}")
            print(f"⏳ Esperando nueva conexión de la central...")
            logger.info(f"="*60)
            logger.info(f"CONEXIÓN CERRADA con {central_addr}")
            logger.info(f"Esperando nueva conexión...")
            logger.info(f"="*60)
            logger.info(f"Conexión cerrada con {central_addr}")
    
    def reenviar_datos(self, origen, destino, direccion, nombre_origen, nombre_destino):
        """Reenvía datos de origen a destino, capturando y decodificando"""
        
        try:
            origen.settimeout(1)
            
            while self.activo:
                try:
                    datos = origen.recv(4096)
                    if not datos:
                        break
                    
                    # Registrar y decodificar
                    self.procesar_mensaje(datos, direccion, nombre_origen)
                    
                    # Reenviar
                    destino.sendall(datos)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.activo:
                        logger.debug(f"Error en {direccion}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error fatal en reenvío {direccion}: {e}")
    
    def procesar_mensaje(self, datos, direccion, origen):
        """Procesa y registra un mensaje capturado"""
        
        # Verificar rotación de log diaria
        rotar_log_si_necesario()
        
        # Actualizar estadísticas
        if direccion == "C→R":
            self.stats["mensajes_central"] += 1
            self.stats["bytes_central"] += len(datos)
        else:
            self.stats["mensajes_regulador"] += 1
            self.stats["bytes_regulador"] += len(datos)
        
        # Detectar y separar mensajes concatenados
        mensajes = self.separar_mensajes(datos)
        
        for msg in mensajes:
            # Decodificar
            info = self.decodificador.decodificar_mensaje(msg, direccion)
            
            # Registrar código en estadísticas
            if "codigo" in info:
                if direccion == "C→R":
                    self.stats["codigos_central"][info["codigo"]] += 1
                else:
                    self.stats["codigos_regulador"][info["codigo"]] += 1
            
            # Detectar eventos importantes
            self.detectar_eventos(info, direccion)
            
            # Mostrar en consola
            self.mostrar_mensaje(info, direccion, origen)
            
            # Registrar en log
            self.registrar_mensaje(info, direccion, origen)
    
    def detectar_eventos(self, info, direccion):
        """Detecta eventos importantes en la comunicación"""
        
        # Primer mensaje = inicio de conexión
        if not self.estado_actual["conexion_iniciada"]:
            self.estado_actual["conexion_iniciada"] = True
            self.eventos.append({
                "tiempo": datetime.now(),
                "tipo": "CONEXIÓN",
                "descripcion": "🔌 INICIO DE CONEXIÓN",
                "direccion": direccion
            })
        
        # Detectar cambios de plan
        if "codigo" in info and info["codigo"] in [0x92, 0x12, 0xD1, 0x51]:
            # Extraer plan de los detalles
            for detalle in info.get("detalles", []):
                if "CAMBIO A PLAN:" in detalle:
                    plan = detalle.split(":")[-1].strip()
                    if self.estado_actual["plan"] != plan:
                        self.eventos.append({
                            "tiempo": datetime.now(),
                            "tipo": "CAMBIO_PLAN",
                            "descripcion": f"🔔 CAMBIO DE PLAN: {self.estado_actual['plan']} → {plan}",
                            "direccion": direccion,
                            "plan_anterior": self.estado_actual["plan"],
                            "plan_nuevo": plan
                        })
                        self.estado_actual["plan"] = plan
        
        # Detectar sincronización con plan
        if "codigo" in info and info["codigo"] in [0x91, 0x11]:
            for detalle in info.get("detalles", []):
                if "PLAN:" in detalle:
                    plan = detalle.split(":")[-1].strip()
                    if self.estado_actual["plan"] is None:
                        # Primer plan detectado
                        self.eventos.append({
                            "tiempo": datetime.now(),
                            "tipo": "PLAN_INICIAL",
                            "descripcion": f"📋 PLAN INICIAL: {plan}",
                            "direccion": direccion,
                            "plan": plan
                        })
                        self.estado_actual["plan"] = plan
        
        # Detectar cambios de modo
        if "codigo" in info and info["codigo"] in [0xB3, 0x33, 0xD4, 0x54]:
            modo_detectado = None
            for detalle in info.get("detalles", []):
                if "MODO:" in detalle or "Control" in detalle:
                    if "ORDENADOR" in detalle or "CENTRALIZADO" in detalle:
                        modo_detectado = "ORDENADOR"
                    elif "MANUAL" in detalle:
                        modo_detectado = "MANUAL"
                    elif "LOCAL" in detalle:
                        modo_detectado = "LOCAL"
                    
                    if modo_detectado and self.estado_actual["modo"] != modo_detectado:
                        self.eventos.append({
                            "tiempo": datetime.now(),
                            "tipo": "CAMBIO_MODO",
                            "descripcion": f"🔄 CAMBIO DE MODO: {self.estado_actual['modo']} → {modo_detectado}",
                            "direccion": direccion,
                            "modo_anterior": self.estado_actual["modo"],
                            "modo_nuevo": modo_detectado
                        })
                        self.estado_actual["modo"] = modo_detectado
                        break
    
    def separar_mensajes(self, datos):
        """Separa mensajes concatenados"""
        mensajes = []
        i = 0
        
        while i < len(datos):
            # ACK o NAK suelto
            if datos[i] == 0x06 or datos[i] == 0x15:
                mensajes.append(bytes([datos[i]]))
                i += 1
                continue
            
            # Mensaje UNE (empieza con STX=0x02)
            if datos[i] == 0x02:
                # Buscar ETX
                j = i + 1
                while j < len(datos) and datos[j] != 0x03:
                    j += 1
                if j < len(datos):
                    mensajes.append(datos[i:j+1])
                    i = j + 1
                else:
                    mensajes.append(datos[i:])
                    break
            else:
                # Dato suelto
                mensajes.append(bytes([datos[i]]))
                i += 1
        
        return mensajes
    
    def mostrar_mensaje(self, info, direccion, origen):
        """Muestra mensaje decodificado en consola"""
        
        if direccion == "C→R":
            flecha = "📤 CENTRAL → REGULADOR"
            color = "\033[94m"  # Azul
        else:
            flecha = "📥 REGULADOR → CENTRAL"
            color = "\033[92m"  # Verde
        
        reset = "\033[0m"
        
        print(f"\n{color}{flecha}{reset}")
        print(f"   HEX: {info['hex']}")
        print(f"   {info['descripcion']}")
        
        if info.get('detalles'):
            for detalle in info['detalles']:
                print(f"      {detalle}")
    
    def registrar_mensaje(self, info, direccion, origen):
        """Registra mensaje en archivo de log"""
        
        logger.info(f"{direccion} | {info['hex']} | {info['descripcion']}")
        
        if info.get('detalles'):
            for detalle in info['detalles']:
                logger.debug(f"  {direccion} | {detalle}")
    
    def mostrar_estadisticas(self):
        """Muestra estadísticas de la sesión"""
        
        duracion = (datetime.now() - self.stats["inicio"]).total_seconds()
        horas = int(duracion // 3600)
        minutos = int((duracion % 3600) // 60)
        segundos = int(duracion % 60)
        
        print("\n" + "="*70)
        print("📊 ESTADÍSTICAS DE SESIÓN - CAPTURA PROLONGADA")
        print("="*70)
        print(f"⏱️  Duración: {horas}h {minutos}m {segundos}s ({duracion:.0f} segundos)")
        print(f"🔌 Conexiones totales: {self.conexiones_totales}")
        
        # Mostrar eventos importantes
        if self.eventos:
            print(f"\n🎯 EVENTOS IMPORTANTES DETECTADOS ({len(self.eventos)}):")
            print("-" * 70)
            for evento in self.eventos[-20:]:  # Últimos 20 eventos
                tiempo_rel = (evento["tiempo"] - self.stats["inicio"]).total_seconds()
                print(f"[{tiempo_rel:6.1f}s] {evento['descripcion']} ({evento['direccion']})")
            if len(self.eventos) > 20:
                print(f"   ... y {len(self.eventos) - 20} eventos más (ver log completo)")
            print("-" * 70)
        
        print(f"\n📤 Central → Regulador:")
        print(f"   Mensajes: {self.stats['mensajes_central']}")
        print(f"   Bytes: {self.stats['bytes_central']}")
        if self.stats['codigos_central']:
            print(f"   Códigos usados:")
            for codigo, count in sorted(self.stats['codigos_central'].items()):
                nombre = CODIGOS_UNE.get(codigo, f"0x{codigo:02X}")
                print(f"      {nombre}: {count}")
        
        print(f"\n📥 Regulador → Central:")
        print(f"   Mensajes: {self.stats['mensajes_regulador']}")
        print(f"   Bytes: {self.stats['bytes_regulador']}")
        if self.stats['codigos_regulador']:
            print(f"   Códigos usados:")
            for codigo, count in sorted(self.stats['codigos_regulador'].items()):
                nombre = CODIGOS_UNE.get(codigo, f"0x{codigo:02X}")
                print(f"      {nombre}: {count}")
        
        print("\n📋 RESUMEN:")
        print("-" * 70)
        print(f"Plan detectado: {self.estado_actual.get('plan', 'No detectado')}")
        print(f"Modo detectado: {self.estado_actual.get('modo', 'No detectado')}")
        print(f"Eventos totales: {len(self.eventos)}")
        print("="*70)
        
        # También al log
        logger.info("="*60)
        logger.info("ESTADÍSTICAS FINALES - CAPTURA PROLONGADA")
        logger.info(f"Duración: {horas}h {minutos}m {segundos}s")
        logger.info(f"Conexiones totales: {self.conexiones_totales}")
        logger.info(f"Mensajes Central: {self.stats['mensajes_central']}")
        logger.info(f"Mensajes Regulador: {self.stats['mensajes_regulador']}")
        
        if self.eventos:
            logger.info(f"\nEVENTOS IMPORTANTES ({len(self.eventos)} total):")
            for evento in self.eventos:
                tiempo_rel = (evento["tiempo"] - self.stats["inicio"]).total_seconds()
                logger.info(f"[{tiempo_rel:8.1f}s] {evento['descripcion']}")
        
        logger.info("="*60)
    
    def detener(self):
        """Detiene el proxy"""
        self.activo = False
        
        if self.server_socket:
            self.server_socket.close()
        
        self.mostrar_estadisticas()
        print("\n👋 Proxy sniffer detenido")
        logger.info("Proxy sniffer detenido")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Proxy Sniffer para protocolo UNE 135401-4',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python ProxySnifferUNE.py --regulador-ip 192.168.1.100
  python ProxySnifferUNE.py --regulador-ip 192.168.1.100 --regulador-puerto 19000 --puerto-local 19001
  
El proxy escuchará en el puerto local y reenviará todo al regulador real,
capturando y decodificando todos los mensajes en ambas direcciones.
        """
    )
    
    parser.add_argument(
        '--regulador-ip', '-r',
        required=True,
        help='IP del regulador real'
    )
    
    parser.add_argument(
        '--regulador-puerto', '-rp',
        type=int,
        default=19000,
        help='Puerto del regulador real (default: 19000)'
    )
    
    parser.add_argument(
        '--puerto-local', '-p',
        type=int,
        default=19000,
        help='Puerto local para escuchar la central (default: 19000)'
    )
    
    args = parser.parse_args()
    
    # Verificar que no sean el mismo
    if args.puerto_local == args.regulador_puerto and args.regulador_ip in ['127.0.0.1', 'localhost']:
        print("❌ Error: El puerto local y el del regulador no pueden ser el mismo en localhost")
        return
    
    # Crear e iniciar proxy
    proxy = ProxySniffer(
        puerto_local=args.puerto_local,
        regulador_ip=args.regulador_ip,
        regulador_puerto=args.regulador_puerto
    )
    
    try:
        proxy.iniciar()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
