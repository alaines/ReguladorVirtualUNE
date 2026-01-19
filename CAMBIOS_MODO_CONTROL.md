# 🔧 CAMBIOS EN EL MODO DE CONTROL - Análisis del Regulador Real

**Fecha:** 16 de enero de 2026  
**Basado en:** Análisis de tráfico real capturado con ProxySnifferUNE

---

## 📊 HALLAZGOS DEL ANÁLISIS

### 1. El regulador NO recibe comandos 0xB3 para cambiar modo

❌ **Incorrecto (antes):** Se pensaba que la central enviaba 0xB3 para cambiar el modo  
✅ **Correcto (ahora):** La central usa **0xD4 (Estados)** para cambiar el modo

### 2. El mensaje 0xB3 es solo REPORTE del regulador

El regulador REAL envía automáticamente un mensaje 0xB3 cada 60 segundos:
- **14:42:00** → R→C 0xB3 → MODO: LOCAL
- **14:43:00** → R→C 0xB3 → MODO: LOCAL
- **14:44:00** → R→C 0xB3 → MODO: LOCAL

**Esto es informativo**, no un comando de cambio.

### 3. El comando 0xD4 controla el modo

La central envía **0xD4 (Estados)** con 4 bytes de datos:

```
02 81 D4 82 81 83 80 D5 03
         ^  ^  ^  ^
         |  |  |  |
         |  |  |  +-- Byte 4: Método de control (0=Tiempos fijos)
         |  |  +----- Byte 3: Coordinación (1=Local, 3=Ordenador)
         |  +-------- Byte 2: Control planes (0=Local, 2=Ordenador) ⭐ CLAVE
         +----------- Byte 1: Estado representación (2=Colores)
```

---

## 🔑 BYTE 2 - EL INDICADOR CLAVE

**Valores observados en el regulador real:**

| Byte 2 (codificado) | Byte 2 (valor) | Modo |
|---------------------|----------------|------|
| `0x82` | `0x02` | **ORDENADOR** (Control externo) |
| `0x80` | `0x00` | **LOCAL** (Control local) |

### Ejemplos del log:

**A las 14:42:24 - Cambio a ORDENADOR:**
```
C→R | 0281D482818380D503 | Sub:129 → Estados (0xD4)
              ^  ^  ^
              |  |  +-- 0x83 → 0x03 = Control externo
              |  +----- 0x81 → 0x01 = Colores
              +-------- 0x82 → 0x02 = ORDENADOR ⭐
  📡 Control externo
```

**A las 14:44:28 - Cambio a LOCAL:**
```
C→R | 0281D482808180D603 | Sub:129 → Estados (0xD4)
              ^  ^  ^
              |  |  +-- 0x81 → 0x01 = Coordinado local
              |  +----- 0x80 → 0x00 = Control local planes
              +-------- 0x82 → 0x02 = Colores
  🏠 Control LOCAL de planes
```

---

## 💻 CAMBIOS IMPLEMENTADOS

### 1. `regulador_gui.py` - Función `_procesar_cambio_modo()`

**ANTES:**
```python
# Procesaba incorrectamente 0xB3 como comando de cambio
modo_byte = self.decodificar_byte_une(datos[0])
if modo_byte & 0x04 or modo_byte & 0x10:
    modo_nuevo = 2  # Ordenador
```

**AHORA:**
```python
# Extrae correctamente el byte 2 del mensaje 0xD4
byte2 = self.decodificar_byte_une(datos[1])  # Control planes

# Según análisis del log real:
if byte2 == 0x02:
    modo_nuevo = 2  # ORDENADOR
else:
    modo_nuevo = 1  # LOCAL
```

### 2. `regulador_gui.py` - Procesamiento de códigos

**ANTES:**
```python
elif codigo_decodificado == 0x33:  # 0xB3
    self._procesar_cambio_modo(datos, subregulador)  # ❌ Incorrecto
```

**AHORA:**
```python
elif codigo_decodificado == 0x33:  # 0xB3
    # Solo es reporte del regulador, no comando
    self.enviar_mensaje(self.ProtocoloUNE.ACK)

elif codigo_decodificado == 0x54:  # 0xD4 ✅ Correcto
    self._procesar_cambio_modo(datos, subregulador)
```

### 3. `generador_respuestas.py` - Mensaje Estados 0xD4

**ANTES:**
```python
if estado.modo_control == 2:
    byte2_planes = 4  # ❌ Incorrecto
    byte3_coord = 4   # ❌ Incorrecto
```

**AHORA:**
```python
if estado.modo_control == 2:
    byte2_planes = 2  # ✅ 0x02 = ORDENADOR (según log real)
    byte3_coord = 3   # ✅ 0x03 = Control externo (según log real)
```

---

## ✅ RESULTADO ESPERADO

Ahora el regulador virtual:

1. ✅ **Ignora 0xB3** de la central (solo ACK)
2. ✅ **Procesa 0xD4** correctamente
3. ✅ **Lee el byte 2** para determinar el modo
4. ✅ **Cambia a ORDENADOR** cuando byte2 = 0x02
5. ✅ **Cambia a LOCAL** cuando byte2 = 0x00
6. ✅ **Responde con 0xD4** usando los valores correctos

---

## 📝 LOGS DE PRUEBA

Para verificar, busca en los logs:

```
COMANDO 0xD4 (ESTADOS) RECIBIDO
  Byte 2 (Control): 0x82 → 0x02
🔄 CAMBIO DE MODO: LOCAL → ORDENADOR
```

Y en la respuesta:

```
📤 REPORTANDO ESTADOS 0xD4: Modo ORDENADOR
Generando mensaje 0xD4 Estados: modo=2, bytes=[2, 2, 3, 0]
```

---

## 🎯 VALIDACIÓN

Para validar que funciona correctamente:

1. **Conecta la central** al regulador virtual
2. **Cambia el modo desde la central** (botón LOCAL/ORDENADOR)
3. **Observa los logs** → debe mostrar recepción de 0xD4
4. **Verifica el cambio** → la GUI debe actualizar el modo

---

## 📚 REFERENCIAS

- **Log capturado:** `tools/sniffer_log_20260116_143751.txt`
- **Capturas analizadas:** 14:42-14:48 (cambios manuales de modo)
- **Norma:** UNE 135401-4 (interpretación basada en comportamiento real)
