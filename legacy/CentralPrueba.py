#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CENTRAL DE TRÁFICO - PROGRAMA DE PRUEBA
Para testear el ReguladorVirtual_ModoB.py

Este programa actúa como central de tráfico y se conecta al regulador
en el puerto 19000 para probar la comunicación según norma UNE 135401-4
"""

import socket
import threading
import time

# ============================================================================
# CONSTANTES DEL PROTOCOLO
# ============================================================================

class ProtocoloUNE:
    """Constantes del protocolo UNE 135401-4"""
    
    # Caracteres de control
    STX = b'\x02'
    ETX = b'\x03'
    EOT = b'\x04'
    ACK = b'\x06'
    NACK = b'\x15'
    DC1 = b'\x11'
    DC3 = b'\x13'
    
    # Mensajes especiales
    DET = 0x20
    TRCAM = 0x30
    HTR = 0x33
    PRH = 0x40
    
    # Directivas de control
    PLAN_REGISTRABLE = 0x50
    SELECCION_PLAN = 0x51
    PUESTA_HORA = 0x52
    DET_TIEMPO_REAL = 0xD3
    ESTADOS = 0x54
    CRUCE_TIEMPO_REAL = 0xDB
    CANCELAR_TIEMPO_REAL = 0xDC
    
    # Directivas de información
    PLAN_EN_CURSO = 0xC9
    DET_FISICOS_PRESENCIA = 0xB0
    ALARMAS = 0xB4


# ============================================================================
# UTILIDADES
# ============================================================================

def calcular_checksum(datos):
    """Calcula el checksum XOR de 7 bits LSB"""
    checksum = 0
    for byte in datos:
        checksum ^= (byte & 0x7F)
    return bytes([checksum & 0x7F])


def construir_mensaje(subregulador, codigo, datos=b''):
    """Construye un mensaje completo"""
    cuerpo = bytes([subregulador, codigo]) + datos
    checksum = calcular_checksum(cuerpo)
    return ProtocoloUNE.STX + cuerpo + checksum + ProtocoloUNE.ETX


def decodificar_mensaje(data):
    """Decodifica un mensaje recibido"""
    if len(data) < 5:
        return None
    
    if not data.startswith(ProtocoloUNE.STX):
        return None
    
    if not (data.endswith(ProtocoloUNE.ETX) or data.endswith(ProtocoloUNE.EOT)):
        return None
    
    subregulador = data[1]
    codigo = data[2]
    datos = data[3:-2] if len(data) > 5 else b''
    checksum_recibido = data[-2]
    
    checksum_calc = calcular_checksum(data[1:-2])[0]
    
    return {
        'subregulador': subregulador,
        'codigo': codigo,
        'datos': datos,
        'checksum_ok': checksum_recibido == checksum_calc
    }


# ============================================================================
# CENTRAL DE PRUEBA
# ============================================================================

class CentralPrueba:
    """Central de tráfico para probar el regulador"""
    
    def __init__(self, puerto=19000):
        self.puerto = puerto
        self.server_socket = None
        self.client_socket = None
        self.conectado = False
        self.lock = threading.Lock()
    
    def iniciar_servidor(self):
        """Inicia el servidor en el puerto 19000"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('', self.puerto))
            self.server_socket.listen(1)
            
            print(f"\n{'='*60}")
            print(f"🏢 CENTRAL DE TRÁFICO - SERVIDOR DE PRUEBA")
            print(f"{'='*60}")
            print(f"📡 Escuchando en puerto {self.puerto}")
            print(f"⏳ Esperando conexión del regulador...")
            print(f"{'='*60}\n")
            
            return True
            
        except socket.error as e:
            print(f"❌ Error al iniciar servidor: {e}")
            return False
    
    def esperar_regulador(self):
        """Espera la conexión de un regulador"""
        try:
            self.client_socket, addr = self.server_socket.accept()
            self.conectado = True
            print(f"✅ Regulador conectado desde {addr[0]}:{addr[1]}\n")
            return True
        except socket.error as e:
            print(f"❌ Error al aceptar conexión: {e}")
            return False
    
    def enviar_mensaje(self, mensaje):
        """Envía un mensaje al regulador"""
        if not self.conectado:
            print("⚠️ No hay regulador conectado")
            return False
        
        try:
            with self.lock:
                self.client_socket.sendall(mensaje)
            print(f"📤 Enviado: {mensaje.hex().upper()}")
            return True
        except socket.error as e:
            print(f"❌ Error al enviar: {e}")
            self.conectado = False
            return False
    
    def enviar_ack(self):
        """Envía ACK al regulador"""
        return self.enviar_mensaje(ProtocoloUNE.ACK)
    
    def hilo_recepcion(self):
        """Hilo para recibir mensajes del regulador"""
        print("🔄 Hilo de recepción iniciado\n")
        
        while self.conectado:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    print("\n⚠️ Regulador desconectado")
                    self.conectado = False
                    break
                
                print(f"\n📥 Recibido: {data.hex().upper()}")
                
                # Mensajes especiales de 1 byte
                if len(data) == 1:
                    if data[0] == ProtocoloUNE.TRCAM or (data[0] & 0xF0) == 0x30:
                        # Mensaje TRCAM - Estado de detectores
                        det_bits = data[0] & 0x0F
                        print(f"   🚨 TRCAM - Detectores: ", end="")
                        for i in range(4):
                            estado = "●" if (det_bits & (1 << i)) else "○"
                            print(f"D{i+1}:{estado} ", end="")
                        print()
                    continue
                
                # Decodificar mensaje
                msg = decodificar_mensaje(data)
                if msg is None:
                    print("   ⚠️ Formato de mensaje inválido")
                    continue
                
                if not msg['checksum_ok']:
                    print("   ⚠️ Checksum incorrecto")
                    self.enviar_mensaje(ProtocoloUNE.NACK)
                    continue
                
                # Mostrar información del mensaje
                print(f"   Subregulador: {msg['subregulador']}")
                print(f"   Código: 0x{msg['codigo']:02X}")
                print(f"   Datos: {msg['datos'].hex().upper()}")
                
                # Decodificar respuestas conocidas
                self.decodificar_respuesta(msg['codigo'], msg['datos'])
                
                # Enviar ACK
                self.enviar_ack()
                
            except socket.timeout:
                continue
            except socket.error as e:
                print(f"❌ Error en recepción: {e}")
                self.conectado = False
                break
    
    def decodificar_respuesta(self, codigo, datos):
        """Decodifica respuestas del regulador"""
        
        if codigo == ProtocoloUNE.PLAN_EN_CURSO:  # 0xC9
            if len(datos) >= 9:
                plan = datos[0]
                hora = datos[1]
                minuto = datos[2]
                segundo = datos[3]
                fase = datos[4]
                tiempo_trans = ((datos[5] & 0x7F) << 7) | (datos[6] & 0x7F)
                tiempo_rest = datos[7]
                ajuste = datos[8]
                
                print(f"   📊 PLAN EN CURSO:")
                print(f"      Plan: {plan}")
                print(f"      Inicio: {hora:02d}:{minuto:02d}:{segundo:02d}")
                print(f"      Fase actual: {fase}")
                print(f"      Tiempo transcurrido ciclo: {tiempo_trans}s")
                print(f"      Tiempo restante fase: {tiempo_rest}s")
        
        elif codigo == ProtocoloUNE.DET_FISICOS_PRESENCIA:  # 0xB0
            if len(datos) >= 3:
                print(f"   🚗 DETECTORES:")
                for byte_idx, byte_val in enumerate(datos[:3]):
                    for bit_idx in range(7):
                        det_num = byte_idx * 7 + bit_idx + 1
                        estado = "●" if (byte_val & (1 << bit_idx)) else "○"
                        print(f"      D{det_num}: {estado}", end=" ")
                        if (bit_idx + 1) % 4 == 0:
                            print()
                print()
        
        elif codigo == ProtocoloUNE.ALARMAS:  # 0xB4
            if len(datos) >= 4:
                print(f"   🚨 ALARMAS:")
                byte1, byte2, byte3, byte4 = datos[:4]
                
                if byte1 & 0x01: print("      - Incompatibilidad")
                if byte1 & 0x02: print("      - Sincronización")
                if byte1 & 0x04: print("      - Transmisión")
                if byte1 & 0x08: print("      - Grupo averiado")
                if byte1 & 0x10: print("      - Lámpara fundida")
                if byte1 & 0x20: print("      - Detector averiado")
                if byte1 & 0x40: print("      - Puerta abierta")
                
                if byte2 & 0x01: print("      - Control manual")
                if byte2 & 0x02: print("      - Autodiagnóstico")
                if byte2 & 0x04: print("      - Reset")
                if byte2 & 0x08: print("      - Reloj sin inicializar")
                if byte2 & 0x10: print("      - Temperatura")
                if byte2 & 0x20: print("      - Check de datos")
                if byte2 & 0x40: print("      - Tensión fuera de límites")
                
                if byte1 == 0 and byte2 == 0:
                    print("      ✅ Sin alarmas")
    
    def menu_interactivo(self):
        """Menú interactivo para enviar comandos al regulador"""
        print("\n" + "="*60)
        print("🎮 MENÚ DE COMANDOS")
        print("="*60)
        print("1️⃣  - Consultar Plan en Curso")
        print("2️⃣  - Consultar Estado de Detectores")
        print("3️⃣  - Consultar Alarmas")
        print("4️⃣  - Cambiar a Plan 1")
        print("5️⃣  - Cambiar a Plan 2")
        print("6️⃣  - Cambiar a Plan 3")
        print("7️⃣  - Activar Detectores en Tiempo Real")
        print("8️⃣  - Cancelar Tiempo Real")
        print("9️⃣  - Enviar DET (Petición detectores)")
        print("0️⃣  - Salir")
        print("="*60)
        
        while self.conectado:
            opcion = input("\n🎯 Seleccione opción: ")
            
            if opcion == "1":
                msg = construir_mensaje(1, ProtocoloUNE.PLAN_EN_CURSO)
                self.enviar_mensaje(msg)
            
            elif opcion == "2":
                msg = construir_mensaje(1, ProtocoloUNE.DET_FISICOS_PRESENCIA)
                self.enviar_mensaje(msg)
            
            elif opcion == "3":
                msg = construir_mensaje(1, ProtocoloUNE.ALARMAS)
                self.enviar_mensaje(msg)
            
            elif opcion in ["4", "5", "6"]:
                plan = int(opcion) - 3
                from datetime import datetime
                now = datetime.now()
                datos = bytes([plan, now.hour, now.minute, now.second])
                msg = construir_mensaje(1, ProtocoloUNE.SELECCION_PLAN, datos)
                self.enviar_mensaje(msg)
            
            elif opcion == "7":
                msg = construir_mensaje(1, ProtocoloUNE.DET_TIEMPO_REAL)
                self.enviar_mensaje(msg)
                print("   ℹ️  Detectores en tiempo real activados")
                print("   ℹ️  El regulador enviará TRCAM automáticamente al detectar cambios")
            
            elif opcion == "8":
                msg = construir_mensaje(1, ProtocoloUNE.CANCELAR_TIEMPO_REAL)
                self.enviar_mensaje(msg)
                print("   ℹ️  Tiempo real cancelado")
            
            elif opcion == "9":
                self.enviar_mensaje(bytes([ProtocoloUNE.DET]))
            
            elif opcion == "0":
                print("\n👋 Cerrando central...")
                break
            
            else:
                print("⚠️ Opción inválida")
            
            time.sleep(0.1)
    
    def ejecutar(self):
        """Ejecuta la central de prueba"""
        if not self.iniciar_servidor():
            return
        
        if not self.esperar_regulador():
            return
        
        # Iniciar hilo de recepción
        hilo_rx = threading.Thread(target=self.hilo_recepcion, daemon=True)
        hilo_rx.start()
        
        # Esperar un momento para que se estabilice la conexión
        time.sleep(1)
        
        # Menú interactivo
        try:
            self.menu_interactivo()
        except KeyboardInterrupt:
            print("\n\n🛑 Interrumpido por usuario")
        finally:
            if self.client_socket:
                self.client_socket.close()
            if self.server_socket:
                self.server_socket.close()
            print("👋 Central detenida")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    central = CentralPrueba(puerto=19000)
    central.ejecutar()
