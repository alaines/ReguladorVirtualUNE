#!/usr/bin/env python3
"""
REGULADOR VIRTUAL UNE 135401-4
Versión modular con configuración externa

Este programa simula un regulador de tráfico según el protocolo UNE 135401-4.
La configuración se carga desde config/regulador_config.json
"""

import socket
import threading
import time
import logging
import json
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import (
    ProtocoloUNE,
    codificar_byte_une,
    decodificar_byte_une,
    calcular_checksum,
    verificar_checksum,
    construir_mensaje,
    separar_mensajes,
    EstadoRegulador,
    GeneradorRespuestas
)


# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================

def configurar_logging(config):
    """Configura el sistema de logging según la configuración"""
    log_config = config.get('logging', {})
    
    # Crear directorio de logs si no existe
    log_file = log_config.get('archivo', 'logs/regulador.log')
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configurar logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_config.get('nivel', 'INFO')))
    
    # Handler para archivo
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=log_config.get('max_bytes', 10485760),
        backupCount=log_config.get('backup_count', 5),
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(
        log_config.get('formato', '%(asctime)s | %(levelname)-8s | %(message)s')
    ))
    logger.addHandler(file_handler)
    
    # Handler para consola (solo errores y warnings críticos)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)


# ============================================================================
# CLASE PRINCIPAL DEL REGULADOR
# ============================================================================

class ReguladorVirtual:
    """Regulador virtual que implementa el protocolo UNE 135401-4"""
    
    def __init__(self, config_path=None):
        """Inicializa el regulador con la configuración especificada"""
        # Cargar configuración
        if config_path is None:
            base_path = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_path, 'config', 'regulador_config.json')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Configurar logging
        self.logger = configurar_logging(self.config)
        
        # Estado del regulador
        self.estado = EstadoRegulador(config_path)
        
        # Suscribir al callback de cambio de plan
        self.estado.set_on_plan_change_callback(self._on_plan_changed)
        
        # Configuración de red
        reg_config = self.config.get('regulador', {})
        self.puerto = reg_config.get('puerto_escucha', 19000)
        self.ip = reg_config.get('ip_escucha', '0.0.0.0')
        self.modo = reg_config.get('modo_operacion', 'A')
        
        # Subreguladores
        sub_config = self.config.get('subreguladores', {})
        self.sub_cpu = sub_config.get('cpu_estado', 128)
        self.sub_planes = sub_config.get('planes_sync', 129)
        
        # Comunicación
        com_config = self.config.get('comunicacion', {})
        self.enviar_keep_alive = com_config.get('enviar_keep_alive', False)
        self.intervalo_keep_alive = com_config.get('intervalo_keep_alive', 5)
        
        # Sockets
        self.server_socket = None
        self.client_socket = None
        self.conectado = False
        
        # Hilos
        self.hilo_recepcion_thread = None
        self.hilo_simulacion_thread = None
        self.hilo_keep_alive_thread = None
        
        self.logger.info(f"Regulador inicializado: puerto={self.puerto}, modo={self.modo}")
    
    def mostrar_banner(self):
        """Muestra el banner de inicio"""
        print("\n" + "=" * 60)
        print("🚦 REGULADOR VIRTUAL TIPO M - MODO " + self.modo)
        print("=" * 60)
        print(f"📍 Subregulador CPU: {self.sub_cpu} (0x{self.sub_cpu:02X})")
        print(f"📍 Subregulador Planes: {self.sub_planes} (0x{self.sub_planes:02X})")
        print(f"🌐 Escuchando en: {self.ip}:{self.puerto}")
        print(f"⚙️  Plan activo: {self.estado.plan_actual}")
        print(f"📋 Modo control: {'LOCAL' if self.estado.modo_control == 1 else 'ORDENADOR' if self.estado.modo_control == 2 else 'MANUAL'}")
        print("=" * 60 + "\n")
    
    def enviar_mensaje(self, mensaje):
        """Envía un mensaje a la central"""
        if self.client_socket and self.conectado:
            try:
                self.client_socket.send(mensaje)
                print(f"📤 Enviado: {mensaje.hex().upper()}")
                self.logger.debug(f"Enviado: {mensaje.hex().upper()}")
            except socket.error as e:
                self.logger.error(f"Error al enviar: {e}")
    
    def enviar_estado_completo(self):
        """
        Envía el estado completo del regulador a la central.
        Igual que al inicio de conexión: alarmas, modo y estado de grupos.
        """
        if not self.conectado:
            return
        
        print("\n📤 Enviando estado completo...")
        
        # 1. Enviar alarmas/estado general
        respuesta = GeneradorRespuestas.respuesta_alarmas(self.estado, self.sub_cpu)
        self.enviar_mensaje(respuesta)
        
        time.sleep(0.1)
        
        # 2. Enviar estados del regulador (0xD4) - modo, coordinación, etc.
        msg_modo = GeneradorRespuestas.mensaje_estados(self.estado, self.sub_cpu)
        self.enviar_mensaje(msg_modo)
        
        time.sleep(0.1)
        
        # 3. Enviar estado de grupos (0xB9)
        msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
        self.enviar_mensaje(msg_grupos)
        
        self.logger.info("Estado completo enviado a la central")
    
    def _on_plan_changed(self, plan_anterior, nuevo_plan):
        """
        Callback invocado cuando cambia el plan (por horario o por orden de central).
        Envía el estado completo al igual que al inicio de conexión.
        """
        print(f"\n🔄 CAMBIO DE PLAN: {plan_anterior} → {nuevo_plan}")
        self.logger.info(f"Cambio de plan detectado: {plan_anterior} → {nuevo_plan}")
        
        # Enviar estado completo a la central
        self.enviar_estado_completo()
    
    def procesar_mensaje_recibido(self, data):
        """Procesa un mensaje recibido de la central"""
        if len(data) < 1:
            return
        
        print(f"📥 Recibido: {data.hex().upper()}")
        self.logger.debug(f"Recibido: {data.hex().upper()}")
        
        # Separar mensajes concatenados
        mensajes = separar_mensajes(data)
        
        if len(mensajes) > 1:
            print(f"   ⚠️ Mensajes concatenados detectados ({len(mensajes)})")
        
        for i, mensaje in enumerate(mensajes):
            if len(mensajes) > 1:
                print(f"   → Procesando mensaje {i+1}/{len(mensajes)}: {mensaje.hex().upper()}")
            self._procesar_mensaje_individual(mensaje)
    
    def _procesar_mensaje_individual(self, mensaje):
        """Procesa un mensaje individual"""
        if len(mensaje) < 5:
            self.logger.warning(f"Mensaje muy corto: {len(mensaje)} bytes")
            return
        
        if mensaje[0] != ProtocoloUNE.STX[0]:
            self.logger.warning(f"Mensaje sin STX - Primer byte: 0x{mensaje[0]:02X}")
            return
        
        if mensaje[-1] not in [ProtocoloUNE.ETX[0], ProtocoloUNE.EOT[0]]:
            self.logger.warning(f"Mensaje sin ETX/EOT - Último byte: 0x{mensaje[-1]:02X}")
            return
        
        subregulador = mensaje[1]
        codigo = mensaje[2]
        checksum_recibido = mensaje[-2]
        datos = mensaje[3:-2] if len(mensaje) > 5 else b''
        
        # Verificar checksum
        cuerpo = mensaje[1:-2]
        valido, _, metodo = verificar_checksum(cuerpo, checksum_recibido)
        
        if not valido:
            self.logger.warning(f"Checksum inválido: recibido=0x{checksum_recibido:02X}")
            # Intentar procesar 0xB3 de todas formas
            if codigo == 0xB3:
                self.logger.warning("Procesando 0xB3 a pesar del checksum inválido")
            else:
                return
        
        # Mostrar información del mensaje
        nombre_codigo = ProtocoloUNE.NOMBRES_CODIGOS.get(codigo, f"DESCONOCIDO")
        print(f"   Subregulador: {subregulador}, Código: 0x{codigo:02X} ({nombre_codigo})")
        
        # Procesar según código
        self._procesar_codigo(subregulador, codigo, datos)
    
    def _procesar_codigo(self, subregulador, codigo, datos):
        """Procesa un código específico"""
        
        if codigo == ProtocoloUNE.SINCRONIZACION:  # 0x91
            print("   → Pregunta: Sincronización")
            respuesta = GeneradorRespuestas.respuesta_sincronizacion(self.estado, subregulador)
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.ALARMAS:  # 0xB4
            print("   → Pregunta: Alarmas")
            respuesta = GeneradorRespuestas.respuesta_alarmas(self.estado, subregulador)
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.CONFIGURACION:  # 0xB5
            print("   → Pregunta: Configuración")
            respuesta = GeneradorRespuestas.respuesta_configuracion(self.estado, subregulador)
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.TABLAS_PROGRAMACION:  # 0xB6
            print("   → Pregunta: Tablas de programación")
            respuesta = GeneradorRespuestas.respuesta_tablas_programacion(self.estado, subregulador)
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.INCOMPATIBILIDADES:  # 0xB7
            print("   → Pregunta: Incompatibilidades")
            respuesta = GeneradorRespuestas.respuesta_incompatibilidades(self.estado, subregulador)
            self.enviar_mensaje(respuesta)
        
        elif codigo == ProtocoloUNE.DATOS_TRAFICO:  # 0x94
            print("   → Pregunta: Datos de tráfico")
            self.enviar_mensaje(ProtocoloUNE.ACK)
        
        elif codigo == ProtocoloUNE.CAMBIO_MODO or codigo == 0x33:  # 0xB3 o 0x33
            self._procesar_cambio_modo(datos, subregulador)
        
        elif codigo == ProtocoloUNE.SELECCION_PLAN or codigo == ProtocoloUNE.SELECCION_PLAN_D1 or codigo == 0x12 or codigo == 0x51:  # 0x92, 0xD1, 0x12, 0x51
            self._procesar_cambio_plan(datos, subregulador)
        
        elif codigo == ProtocoloUNE.PUESTA_EN_HORA:  # 0xD2
            print("   → Orden: Puesta en hora")
            self.enviar_mensaje(ProtocoloUNE.ACK)
        
        else:
            print(f"   ⚠️ Código 0x{codigo:02X} no implementado")
            self.logger.warning(f"Código 0x{codigo:02X} no implementado")
    
    def _procesar_cambio_modo(self, datos, subregulador):
        """Procesa un mensaje de cambio de modo (0xB3)"""
        print(f"\n🔧 CAMBIO DE MODO RECIBIDO")
        
        if len(datos) < 1:
            self.logger.warning("0xB3 sin datos")
            self.enviar_mensaje(ProtocoloUNE.ACK)
            return
        
        modo_byte_recibido = datos[0]
        modo_byte = decodificar_byte_une(modo_byte_recibido)
        
        print(f"   Byte recibido: 0x{modo_byte_recibido:02X} → decodificado: 0x{modo_byte:02X} ({modo_byte:08b})")
        self.logger.info(f"0xB3 - Byte={modo_byte_recibido:02X}, decodificado={modo_byte:02X}")
        
        MODOS = {1: "LOCAL", 2: "ORDENADOR", 3: "MANUAL"}
        ESTADOS = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES"}
        
        # Guardar estado anterior
        modo_anterior = self.estado.modo_control
        estado_repr_anterior = self.estado.estado_representacion
        
        # Decodificar byte
        estado_repr_nuevo = modo_byte & 0x03  # Bits 0-1
        
        # Determinar modo
        if modo_byte & 0x04 or modo_byte & 0x10:  # Bits 2 o 4
            modo_nuevo = 2  # Ordenador
        elif modo_byte & 0x08:  # Bit 3
            modo_nuevo = 3  # Manual
        else:
            modo_nuevo = 1  # Local
        
        # Aplicar cambios
        self.estado.cambiar_modo(modo_nuevo, estado_repr_nuevo)
        
        # Mostrar cambios
        if modo_nuevo != modo_anterior:
            print(f"   ✅ Modo: {MODOS.get(modo_anterior, '?')} → {MODOS.get(modo_nuevo, '?')}")
        else:
            print(f"   ℹ️  Modo mantiene: {MODOS.get(modo_nuevo, '?')}")
        
        if estado_repr_nuevo != estado_repr_anterior:
            print(f"   ✅ Estado: {ESTADOS.get(estado_repr_anterior, '?')} → {ESTADOS.get(estado_repr_nuevo, '?')}")
        
        # Enviar ACK
        self.enviar_mensaje(ProtocoloUNE.ACK)
        
        # Enviar confirmación espontánea 0xD4 (Estados)
        time.sleep(0.1)
        respuesta_d4 = GeneradorRespuestas.mensaje_estados(self.estado, self.sub_cpu)
        print(f"   📤 Confirmación 0xD4 Estados enviada")
        self.enviar_mensaje(respuesta_d4)
        
        # Si cambió estado de representación, enviar estado de grupos
        if estado_repr_nuevo != estado_repr_anterior:
            time.sleep(0.1)
            msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
            print(f"   📤 Estado grupos actualizado")
            self.enviar_mensaje(msg_grupos)
    
    def _procesar_cambio_plan(self, datos, subregulador):
        """Procesa un mensaje de cambio de plan"""
        print("   → Orden: Cambio de plan")
        
        if len(datos) >= 1:
            nuevo_plan = decodificar_byte_une(datos[0])
            
            if self.estado.cambiar_plan(nuevo_plan):
                print(f"   ✅ Plan cambiado a: {nuevo_plan}")
                self.enviar_mensaje(ProtocoloUNE.ACK)
                
                # Enviar sincronización actualizada
                respuesta = GeneradorRespuestas.respuesta_sincronizacion(self.estado, subregulador)
                self.enviar_mensaje(respuesta)
            else:
                print(f"   ❌ Plan {nuevo_plan} no existe")
                self.enviar_mensaje(ProtocoloUNE.NAK)
        else:
            self.enviar_mensaje(ProtocoloUNE.ACK)
    
    def hilo_recepcion(self):
        """Hilo para recibir mensajes de la central"""
        self.logger.debug("Hilo de recepción iniciado")
        
        while self.conectado:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    print("\n⚠️ Conexión cerrada por la central")
                    self.conectado = False
                    break
                
                self.procesar_mensaje_recibido(data)
            
            except socket.timeout:
                continue
            except socket.error as e:
                if self.conectado:
                    self.logger.error(f"Error en recepción: {e}")
                self.conectado = False
                break
        
        self.logger.debug("Hilo de recepción finalizado")
    
    def hilo_simulacion(self):
        """Hilo para simular cambios de fase y enviar estados periódicamente"""
        self.logger.debug("Hilo de simulación iniciado")
        
        contador_envio_estados = 0
        INTERVALO_ENVIO_ESTADOS = 2  # Enviar estado de grupos cada 2 segundos
        
        while self.conectado:
            time.sleep(1)
            
            cambio_fase = self.estado.actualizar_ciclo()
            contador_envio_estados += 1
            
            if cambio_fase:
                fase = self.estado.fase_actual
                print(f"\n🚦 CAMBIO DE FASE → Fase {fase}")
                
                # Enviar 0xD5 (cambio de fase)
                msg_fase = GeneradorRespuestas.mensaje_cambio_fase(fase, self.sub_planes)
                self.enviar_mensaje(msg_fase)
                
                # Enviar 0xB9 (estado de grupos)
                time.sleep(0.1)
                msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
                self.enviar_mensaje(msg_grupos)
                
                contador_envio_estados = 0  # Reset contador
            
            elif contador_envio_estados >= INTERVALO_ENVIO_ESTADOS:
                # Enviar estado de grupos periódicamente aunque no haya cambio de fase
                msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
                self.enviar_mensaje(msg_grupos)
                contador_envio_estados = 0
        
        self.logger.debug("Hilo de simulación finalizado")
    
    def hilo_keep_alive(self):
        """Hilo para enviar keep-alive (si está habilitado)"""
        if not self.enviar_keep_alive:
            self.logger.info("Keep-alive desactivado")
            while self.conectado:
                time.sleep(10)
            return
        
        self.logger.debug("Hilo de keep-alive iniciado")
        
        while self.conectado:
            time.sleep(self.intervalo_keep_alive)
            
            if self.conectado and self.client_socket:
                respuesta = GeneradorRespuestas.respuesta_alarmas(self.estado, self.sub_cpu)
                self.enviar_mensaje(respuesta)
        
        self.logger.debug("Hilo de keep-alive finalizado")
    
    def iniciar_servidor(self):
        """Inicia el servidor TCP"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.ip, self.puerto))
            self.server_socket.listen(1)
            
            print(f"📡 Servidor iniciado en puerto {self.puerto}")
            print("⏳ Esperando conexión de la central...")
            
            self.client_socket, addr = self.server_socket.accept()
            self.client_socket.settimeout(1.0)
            self.conectado = True
            
            print(f"\n✅ Central conectada desde {addr[0]}:{addr[1]}")
            self.logger.info(f"Central conectada: {addr}")
            
            # Enviar estado inicial
            print("\n📤 Enviando estado inicial...")
            
            # 1. Enviar alarmas/estado general
            respuesta = GeneradorRespuestas.respuesta_alarmas(self.estado, self.sub_cpu)
            self.enviar_mensaje(respuesta)
            
            time.sleep(0.2)
            
            # 2. Enviar estados del regulador (0xD4)
            msg_modo = GeneradorRespuestas.mensaje_estados(self.estado, self.sub_cpu)
            self.enviar_mensaje(msg_modo)
            
            time.sleep(0.2)
            
            # 3. Enviar estado de grupos (0xB9)
            msg_grupos = GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
            self.enviar_mensaje(msg_grupos)
            
            return True
            
        except socket.error as e:
            print(f"❌ Error al iniciar servidor: {e}")
            self.logger.error(f"Error al iniciar servidor: {e}")
            return False
    
    def ejecutar(self):
        """Ejecuta el regulador virtual"""
        self.mostrar_banner()
        
        if not self.iniciar_servidor():
            return
        
        print(f"✅ Regulador virtual ejecutándose en Modo {self.modo}")
        print("   Presiona Ctrl+C para detener\n")
        print("=" * 60)
        
        # Iniciar hilos
        self.hilo_recepcion_thread = threading.Thread(target=self.hilo_recepcion, daemon=True)
        self.hilo_simulacion_thread = threading.Thread(target=self.hilo_simulacion, daemon=True)
        self.hilo_keep_alive_thread = threading.Thread(target=self.hilo_keep_alive, daemon=True)
        
        self.hilo_recepcion_thread.start()
        self.hilo_simulacion_thread.start()
        self.hilo_keep_alive_thread.start()
        
        try:
            while self.conectado:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Deteniendo regulador...")
        
        self.detener()
    
    def detener(self):
        """Detiene el regulador"""
        self.conectado = False
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print("👋 Regulador detenido\n")
        self.logger.info("Regulador detenido")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Regulador Virtual UNE 135401-4')
    parser.add_argument('-c', '--config', 
                        default='config/regulador_config.json',
                        help='Ruta al archivo de configuración')
    parser.add_argument('-p', '--puerto',
                        type=int,
                        help='Puerto de escucha (sobreescribe config)')
    
    args = parser.parse_args()
    
    # Buscar archivo de configuración
    config_path = args.config
    if not os.path.isabs(config_path):
        base_path = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_path, config_path)
    
    if not os.path.exists(config_path):
        print(f"❌ Archivo de configuración no encontrado: {config_path}")
        sys.exit(1)
    
    # Crear y ejecutar regulador
    regulador = ReguladorVirtual(config_path)
    
    # Sobreescribir puerto si se especifica
    if args.puerto:
        regulador.puerto = args.puerto
    
    regulador.ejecutar()
