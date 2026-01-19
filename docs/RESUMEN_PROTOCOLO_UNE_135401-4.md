# RESUMEN PROTOCOLO UNE 135401-4
## Comunicación Central de Tráfico - Regulador Tipo M

### INTRODUCCIÓN
La norma UNE 135401-4 define el protocolo de comunicaciones entre una **Central de Gestión de Tráfico** y los **Reguladores Semafóricos Tipo M**. Este documento resume los aspectos principales para implementar un programa en Python que actúe como central de tráfico.

---

## 1. ESTRUCTURA GENERAL DEL PROTOCOLO

### 1.1 Modos de Operación
El protocolo define dos modos de operación que establecen diferencias en la gestión de respuestas:

- **MODO A**: Comunicación síncrona - El regulador responde con ACK/directiva sin datos a cada comando
- **MODO B**: Comunicación asíncrona - El regulador puede enviar mensajes espontáneamente cuando detecta cambios

**Diferencias Clave:**

| Aspecto | Modo A | Modo B |
|---------|--------|--------|
| **Respuesta a comandos** | Siempre ACK o directiva sin datos | Solo si hay datos relevantes |
| **Mensajes espontáneos** | No | Sí (alarmas, estado, detectores) |
| **Envío automático de alarmas** | Solo bajo petición | Automático al detectar cambios |
| **Detectores en tiempo real** | Solo bajo petición | Envío continuo hasta cancelación |
| **Estado del regulador** | Solo bajo petición | Envío automático al cambiar |

**Configuración del Modo**: Se establece mediante parámetro en la Tabla 10001000 (Modo de funcionamiento)

### 1.2 Tipo de Comunicación
- **Protocolo**: TCP/IP
- **Puerto por defecto**: 3000 o 19000 (según configuración)
- **Codificación**: Bytes hexadecimales

---

## 2. ESTRUCTURA DE LOS MENSAJES (TELEGRAMAS)

### 2.1 Formato General del Telegrama
```
[STX] [DEST] [CÓDIGO] [DATOS...] [CHECKSUM] [ETX/EOT]
```

**Descripción de campos:**

| Campo | Tamaño | Descripción | Valor |
|-------|--------|-------------|-------|
| **STX** | 1 byte | Inicio de telegrama | `0x02` |
| **DEST** | 1 byte | Identificador del destinatario (Subregulador) | `0x00` - `0xFF` |
| **CÓDIGO** | 1 byte | Código de función del mensaje | Ver tabla de códigos |
| **DATOS** | Variable | Información adicional del comando | Depende del código |
| **CHECKSUM** | 1 byte | Verificación de integridad (XOR) | Calculado |
| **ETX/EOT** | 1 byte | Fin de telegrama | `0x03` (ETX) o `0x04` (EOT) |

**Nota sobre ETX vs EOT:**
- **ETX (0x03)**: Fin de mensaje completo
- **EOT (0x04)**: Fin de mensaje parcial (para mensajes largos divididos en bloques)

### 2.1.1 Mensajes Central ↔ Regulador

Cuando la comunicación es entre **central y regulador** (no ordenador):
```
[STX] [SUBREGULADOR] [CÓDIGO] [DATOS...] [CHECKSUM] [ETX/EOT]
```

**Subregulador = 0**: Mensaje dirigido a TODOS los subreguladores
**Central**: Tiene código fijo = **50 decimal (0x32 hex)**

### 2.2 Cálculo del CHECKSUM
El checksum se calcula mediante operación **XOR** de todos los bytes del mensaje, **excluyendo STX y ETX/EOT**, usando solo los **7 bits menos significativos (LSB)** de cada byte:

```python
def calcular_checksum(mensaje):
    """
    Calcula checksum XOR de todos los bytes excepto STX y ETX/EOT
    Solo afecta a los 7 bits de menor peso de cada byte
    """
    checksum = 0
    # Mensaje sin STX (primer byte) y sin ETX/EOT (último byte)
    for byte in mensaje[1:-1]:
        checksum ^= (byte & 0x7F)  # Solo 7 bits LSB
    return bytes([checksum & 0x7F])
```

**Importante**: La norma especifica que el CHECK es la función EXCLUSIVE OR de todos los bytes excepto mensajes especiales de un byte, y **solo afecta a los 7 bits de menor peso de cada byte**.

---

## 3. CÓDIGOS DE CONTROL Y FUNCIÓN

### 3.1 Códigos de Control del Protocolo

| Código | Valor Hex | Descripción |
|--------|-----------|-------------|
| **STX** | `0x02` | Inicio de transmisión |
| **ETX** | `0x03` | Fin de transmisión |
| **ACK** | `0x06` | Acuse de recibo positivo |
| **NACK** | `0x15` | Acuse de recibo negativo |
| **DC1** | `0x11` | Activar comunicaciones |
| **DC3** | `0x13` | Desactivar comunicaciones |
| **EOT** | `0x04` | Fin de transmisión alternativo |

### 3.2 Códigos de Función Principales

**Estructura del byte de código:**
```
Bit 7 | Bits 6-5 | Bits 4-1 | Bit 0
  1   |    XX    |  XXXX    |  X
      |          |          |
      |          |          └─ 0: Pregunta, 1: Envío
      |          |
      |          └─ Identificador del código
      |
      └─ 00: Libre, 01: Control, 10: Tablas, 11: Información
```

#### **Mensajes Especiales de un Byte**

Estos mensajes NO participan del protocolo DC1/DC3 ni ACK/NACK y pueden enviarse en cualquier momento:

| Código | Valor Hex | Descripción |
|--------|-----------|-------------|
| **STX** | `0x02` | Cabecera de mensaje |
| **ETX** | `0x03` | Fin de mensaje |
| **EOT** | `0x04` | Fin de mensaje parcial |
| **ACK** | `0x06` | Acuse de recibo positivo |
| **DC1 (XON)** | `0x11` | Comunicaciones ON (activar transmisión) |
| **DC3 (XOFF)** | `0x13` | Comunicaciones OFF (detener transmisión) |
| **NACK** | `0x15` | Acuse de recibo negativo |
| **DET** | `0x20` | Petición de detectores |
| **TRCAM** | `0x30` | Estado detectores en tiempo real |
| **HTR** | `0x33` | Hora en tiempo real (ejecución) |
| **PRH** | `0x40 + NNNNNN` | Petición hora (NNNNNN = número regulador) |

**DET (0x20)**: Al recibir, el regulador almacena datos de detectores, pone a cero los registros y envía los datos almacenados

**TRCAM (0b00110000)**: Codifica estado de 4 detectores en los 4 bits menos significativos:
- Bit 0: Detector 1 (1=activado, 0=desactivado)
- Bit 1: Detector 2
- Bit 2: Detector 3
- Bit 3: Detector 4

**HTR (0x33)**: El regulador actualiza la hora previamente recibida

**PRH (0x40)**: Formato `01NNNNNN` donde NNNNNN es el número binario del regulador (000000 = todos)

#### **Consultas al Regulador (Central → Regulador)**

**DIRECTIVAS DE INFORMACIÓN (Bit 7=1, Bits 6-5=11)**

| Código | Valor Hex | Pregunta/Envío | Descripción | Respuesta Modo A | Respuesta Modo B |
|--------|-----------|----------------|-------------|------------------|------------------|
| **PLN** | `0xC9` | Pregunta | Plan en curso | Datos del plan | Datos del plan o ninguna si no existe |
| **DFP** | `0xB0` | Pregunta | Detectores físicos (presencia) | 3 bytes bit a bit | 3 bytes bit a bit |
| **DFC** | `0xB1` | Pregunta | Detector físico N (contaje) | Intensidad+Ocupación | Intensidad+Ocupación |
| **ALR** | `0xB4` | Pregunta | Alarmas | 4 bytes de alarmas | Envío automático al cambiar |
| **EST** | `0xD4` | Envío | Estado del regulador | ACK | Envío automático al cambiar |

**DIRECTIVAS DE CONTROL (Bit 7=1, Bits 6-5=01)**

| Código | Valor Hex | Descripción | Modo A | Modo B |
|--------|-----------|-------------|--------|--------|
| **PLR** | `0x50` | Plan registrable | Directiva sin datos (0xD0) | No hay |
| **SEP** | `0x51` | Selección de plan | Directiva sin datos (0xD1) | Ver respuesta 0xC9 |
| **PHF** | `0x52` | Puesta en hora y fecha | Directiva sin datos (0xD2) | No hay |
| **DTR** | `0xD3` | Detectores en tiempo real | Directiva sin datos (0xD3) | Envío TRCAM automático |
| **EST** | `0x54` | Estados | Directiva sin datos (0xD4) | No hay |
| **CFA** | `0xD5` | Cambio de fase | Directiva sin datos (0xD5) | No hay |
| **MDS** | `0x56` | Mando directo salidas | Directiva sin datos (0xD6) | No hay |
| **CRT** | `0xDB` | Cruce en tiempo real | Directiva sin datos (0xDB) | Envío automático al cambiar |
| **CTR** | `0xDC` | Cancelación tiempo real | Directiva sin datos (0xDC) | No hay |
| **BAL** | `0xDD` | Borrado de alarmas | Directiva sin datos (0xDD) | No hay |

#### **Comandos de Control (Central → Regulador)**

| Código | Valor Hex | Descripción |
|--------|-----------|-------------|
| **CPL** | `0x10` | Cambio de plan de funcionamiento |
| **CFI** | `0x11` | Cambio a funcionamiento intermitente |
| **CFF** | `0x12` | Cambio a tiempos fijos |
| **APA** | `0x13` | Apagado del regulador |
| **ACT** | `0x14` | Activación del regulador |

---

## 4. EJEMPLOS DE MENSAJES

### 4.1 Ejemplo: Consulta de Estado del Regulador

**Mensaje enviado por la Central:**
```python
# [STX] [Subregulador] [Código EST] [Checksum] [ETX]
mensaje = bytes([0x02, 0x01, 0xB4, 0xB5, 0x03])
#                STX   Sub=1   EST   CHK   ETX
```

**Respuesta del Regulador:**
```python
# [STX] [Sub] [EST] [Plan] [Grupos] [Ciclo] [Fase1] [Fase2] [Estructura] [Transitorio] [Desfase] [CHK] [ETX]
respuesta = bytes([0x02, 0x01, 0xB4, 0x02, 0x04, 0x46, 0x20, 0x1E, 0x01, 0x08, 0x00, 0xXX, 0x03])
#                  STX   Sub   EST   Plan2  4grp  70s   32s   30s    Estr  Trans Desf  CHK   ETX
```

### 4.2 Ejemplo: Petición de Hora

**Mensaje de la Central:**
```python
mensaje = bytes([0x02, 0x01, 0x40, 0x43, 0x03])
#                STX   Sub   PRH   CHK   ETX
```

**Respuesta del Regulador (formato BCD):**
```python
respuesta = bytes([0x02, 0x01, 0x91, 0x01, 0x00, 0x14, 0x23, 0x45, 0xXX, 0x03])
#                  STX   Sub   SNC   Modo  Dif   14h   23m   45s   CHK   ETX
#                                          (14:23:45 en BCD)
```

### 4.3 Ejemplo: Petición de Detectores

**Mensaje de la Central:**
```python
mensaje = bytes([0x02, 0x01, 0x20, 0x23, 0x03])
#                STX   Sub   DET   CHK   ETX
```

**Respuesta del Regulador:**
```python
respuesta = bytes([0x02, 0x01, 0x30, 0x0F, 0xXX, 0x03])
#                  STX   Sub   TRCAM Estado CHK  ETX
#                              (Detectores 1,2,3,4 = 0000 1111 = 0x0F activos)
```

---

## 5. IMPLEMENTACIÓN EN PYTHON

### 5.1 Clase Base para la Central

```python
import socket
import threading

class CentralTrafico:
    # Constantes del protocolo
    STX = b'\x02'
    ETX = b'\x03'
    ACK = b'\x06'
    NACK = b'\x15'
    DC1 = b'\x11'
    DC3 = b'\x13'
    
    def __init__(self, regulador_ip, regulador_puerto):
        self.ip = regulador_ip
        self.puerto = regulador_puerto
        self.socket = None
        self.conectado = False
    
    def conectar(self):
        """Establece conexión TCP con el regulador"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.ip, self.puerto))
            self.conectado = True
            print(f"✅ Conectado a regulador {self.ip}:{self.puerto}")
            return True
        except socket.error as e:
            print(f"❌ Error de conexión: {e}")
            return False
    
    def calcular_checksum(self, datos):
        """Calcula checksum XOR (7 bits LSB)"""
        checksum = 0
        for byte in datos:
            checksum ^= byte
        return bytes([checksum & 0x7F])
    
    def construir_mensaje(self, subregulador, codigo, datos=b''):
        """Construye un mensaje según el protocolo UNE"""
        mensaje = bytes([subregulador, codigo]) + datos
        checksum = self.calcular_checksum(mensaje)
        return self.STX + mensaje + checksum + self.ETX
    
    def enviar_mensaje(self, subregulador, codigo, datos=b''):
        """Envía mensaje al regulador"""
        if not self.conectado:
            print("⚠️ No hay conexión establecida")
            return False
        
        mensaje = self.construir_mensaje(subregulador, codigo, datos)
        try:
            self.socket.sendall(mensaje)
            print(f"📤 Enviado: {mensaje.hex()}")
            return True
        except socket.error as e:
            print(f"❌ Error al enviar: {e}")
            return False
    
    def recibir_respuesta(self, timeout=5):
        """Recibe respuesta del regulador"""
        if not self.conectado:
            return None
        
        self.socket.settimeout(timeout)
        try:
            respuesta = self.socket.recv(1024)
            print(f"📥 Recibido: {respuesta.hex()}")
            return respuesta
        except socket.timeout:
            print("⚠️ Timeout esperando respuesta")
            return None
        except socket.error as e:
            print(f"❌ Error al recibir: {e}")
            return None
    
    def consultar_estado(self, subregulador=1):
        """Consulta el estado del regulador"""
        self.enviar_mensaje(subregulador, 0xB4)
        return self.recibir_respuesta()
    
    def consultar_hora(self, subregulador=1):
        """Consulta la hora del regulador"""
        self.enviar_mensaje(subregulador, 0x40)
        return self.recibir_respuesta()
    
    def consultar_detectores(self, subregulador=1):
        """Consulta estado de detectores"""
        self.enviar_mensaje(subregulador, 0x20)
        return self.recibir_respuesta()
    
    def cambiar_plan(self, subregulador, numero_plan):
        """Cambia el plan de funcionamiento"""
        datos = bytes([numero_plan])
        self.enviar_mensaje(subregulador, 0x10, datos)
        return self.recibir_respuesta()
    
    def cerrar_conexion(self):
        """Cierra la conexión con el regulador"""
        if self.socket:
            self.socket.close()
            self.conectado = False
            print("🔌 Conexión cerrada")
```

### 5.2 Ejemplo de Uso

```python
# Crear instancia de la central
central = CentralTrafico(
    regulador_ip="192.168.1.100",
    regulador_puerto=3000
)

# Conectar al regulador
if central.conectar():
    # Consultar estado
    respuesta = central.consultar_estado(subregulador=1)
    
    # Consultar hora
    respuesta = central.consultar_hora(subregulador=1)
    
    # Consultar detectores
    respuesta = central.consultar_detectores(subregulador=1)
    
    # Cambiar a plan 2
    respuesta = central.cambiar_plan(subregulador=1, numero_plan=2)
    
    # Cerrar conexión
    central.cerrar_conexion()
```

---

## 6. FLUJO DE COMUNICACIÓN TÍPICO

### 6.1 Secuencia de Inicio de Comunicación

1. **Central** establece conexión TCP al regulador
2. **Central** envía comando DC1 (0x11) para activar comunicaciones
3. **Regulador** responde con ACK (0x06)
4. **Central** puede enviar consultas y comandos
5. **Regulador** responde a cada petición
6. **Central** envía DC3 (0x13) para cerrar comunicaciones
7. **Central** cierra conexión TCP

### 6.2 Diagrama de Flujo

```
Central                          Regulador
  |                                  |
  |-------- Conexión TCP ----------->|
  |                                  |
  |-------- DC1 (0x11) ------------->|
  |<------- ACK (0x06) --------------|
  |                                  |
  |-------- Consulta EST ----------->|
  |<------- Respuesta datos ---------|
  |                                  |
  |-------- Consulta DET ----------->|
  |<------- Estado detectores -------|
  |                                  |
  |-------- DC3 (0x13) ------------->|
  |<------- ACK (0x06) --------------|
  |                                  |
  |-------- Cierre TCP ------------->|
```

---

## 7. FORMATO DE RESPUESTAS IMPORTANTES

### 7.1 Respuesta Estado del Regulador (0xB4)

```
Byte 0: STX (0x02)
Byte 1: Subregulador
Byte 2: Código 0xB4
Byte 3: Plan actual (1-255)
Byte 4: Número de grupos semafóricos
Byte 5: Tiempo de ciclo (segundos)
Byte 6: Tiempo fase 1 (segundos)
Byte 7: Tiempo fase 2 (segundos)
Byte 8: Tipo de estructura
Byte 9: Tiempo transitorio
Byte 10: Desfase
Byte 11: Checksum
Byte 12: ETX (0x03)
```

### 7.2 Respuesta Sincronización (0x91)

```
Byte 0: STX (0x02)
Byte 1: Subregulador
Byte 2: Código 0x91
Byte 3: Modo sincronización
Byte 4: Diferencia tiempo
Byte 5: Hora (BCD)
Byte 6: Minutos (BCD)
Byte 7: Segundos (BCD)
Byte 8: Checksum
Byte 9: ETX (0x03)
```

**Nota**: Los valores de hora, minutos y segundos están en formato **BCD** (Binary Coded Decimal)

```python
def to_bcd(value):
    """Convierte decimal a BCD"""
    return (value // 10) << 4 | (value % 10)

def from_bcd(bcd_value):
    """Convierte BCD a decimal"""
    return ((bcd_value >> 4) * 10) + (bcd_value & 0x0F)
```

---

## 8. CONSIDERACIONES IMPORTANTES

### 8.1 Gestión de Conexiones
- **Mantener conexión persistente**: El protocolo está diseñado para mantener la conexión TCP abierta
- **Timeout**: Configurar timeouts adecuados (3-5 segundos recomendado)
- **Reconexión automática**: Implementar lógica de reconexión en caso de pérdida de conexión

### 8.2 Manejo de Errores
- Validar siempre la presencia de STX y ETX
- Verificar el checksum de los mensajes recibidos
- Responder con NACK si el mensaje es inválido
- Implementar reintentos para comandos críticos

### 8.3 Multithreading
- Usar hilos separados para envío y recepción de mensajes
- Proteger recursos compartidos con locks
- Implementar cola de mensajes para evitar colisiones

### 8.4 Logging
- Registrar todas las comunicaciones para auditoría
- Incluir timestamp en cada registro
- Guardar tanto mensajes enviados como recibidos

---

## 9. CÓDIGOS DE ERROR Y ALARMAS

### 9.1 Códigos de Alarma Comunes

| Código | Descripción |
|--------|-------------|
| `0x01` | Fallo en detector |
| `0x02` | Fallo en lámpara |
| `0x03` | Conflicto de fases |
| `0x04` | Pérdida de sincronización |
| `0x05` | Fallo de alimentación |
| `0x10` | Modo manual activado |
| `0x20` | Modo intermitente |

---

## 10. REFERENCIAS Y RECURSOS

### 10.1 Archivos de Referencia en el Proyecto
- `SoyRegulador.py`: Implementación simulada de regulador
- `IntentoCentral_Interactiva.py`: Central interactiva
- `main4_1.py`: Gestión de múltiples reguladores
- `Regulador_con_respuesta_2.py`: Simulador con respuestas completas

### 10.2 Documentación Adicional
- Norma UNE 135401-4:2003 (documento PDF en carpeta docs)
- Especificaciones técnicas del fabricante del regulador

---

## CONCLUSIÓN

Este protocolo permite una comunicación robusta entre centrales de gestión de tráfico y reguladores semafóricos. La implementación en Python requiere:

1. **Gestión de sockets TCP/IP**
2. **Construcción correcta de telegramas** con STX, código, datos, checksum y ETX
3. **Cálculo de checksum** mediante XOR
4. **Decodificación de respuestas** según el código de función
5. **Manejo de excepciones** y reconexiones
6. **Threading** para comunicación asíncrona

Con estos elementos, es posible desarrollar un software completo de gestión de tráfico compatible con reguladores tipo M según la norma UNE 135401-4.

---

**Fecha del documento**: Enero 2026  
**Versión**: 1.0  
**Autor**: Documentación basada en norma UNE 135401-4 y análisis de código existente
