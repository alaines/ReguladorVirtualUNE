# Protocolo UNE 135401-4 - Referencia Técnica

## Documento de Conocimiento Acumulado

Este documento contiene las especificaciones técnicas descubiertas y validadas durante la implementación del regulador virtual. **Usar como referencia para futuras implementaciones.**

---

## 1. CODIFICACIÓN DE BYTES UNE

### 1.1 Regla del Bit 7
Todos los bytes de datos en el protocolo UNE tienen el **bit 7 activo** (OR con 0x80).

```python
def codificar_byte_une(valor):
    """Codifica un byte añadiendo bit 7"""
    return (valor & 0x7F) | 0x80

def decodificar_byte_une(byte):
    """Decodifica un byte quitando bit 7"""
    return byte & 0x7F
```

### 1.2 Ejemplos de Codificación
| Valor Original | Codificado (hex) | Binario |
|----------------|------------------|---------|
| 0x00           | 0x80             | 10000000 |
| 0x01           | 0x81             | 10000001 |
| 0x04           | 0x84             | 10000100 |
| 0x10           | 0x90             | 10010000 |
| 0x39           | 0xB9             | 10111001 |

### 1.3 Bytes que NO se codifican
- **STX** (0x02): Inicio de mensaje
- **ETX** (0x03): Fin de mensaje
- **ACK** (0x06): Confirmación
- **NAK** (0x15): Rechazo

---

## 2. ESTRUCTURA DE MENSAJES

### 2.1 Formato General
```
[STX] [SUBREGULADOR] [CÓDIGO] [DATOS...] [CHECKSUM] [ETX]
  02      0x80+ID      0x80+cod   ...        XX        03
```

### 2.2 Checksum
- **Cálculo**: XOR de todos los bytes desde SUBREGULADOR hasta el último byte de DATOS (inclusive)
- **NO incluye**: STX ni ETX
- **SÍ se codifica**: El checksum también lleva bit 7 activo

```python
def calcular_checksum(datos):
    """Calcula checksum XOR de los datos"""
    checksum = 0
    for byte in datos:
        checksum ^= byte
    return checksum | 0x80  # Codificar con bit 7
```

### 2.3 Ejemplo de Mensaje Completo
```
Mensaje B9 (estado grupos): 02 80 B9 90 81 81 81 XX 03
                            │  │  │  │  │  │  │  │  └─ ETX
                            │  │  │  │  │  │  │  └─ Checksum
                            │  │  │  │  │  │  └─ G4 = Rojo (1)
                            │  │  │  │  │  └─ G3 = Rojo (1)
                            │  │  │  │  └─ G2 = Rojo (1)
                            │  │  │  └─ G1 = Verde (16)
                            │  │  └─ Código B9 (0x39 codificado)
                            │  └─ Subregulador 128 (0x00 codificado)
                            └─ STX
```

---

## 3. SUBREGULADORES

### 3.1 Asignación de Subreguladores
| ID | ID Codificado | Función | Uso |
|----|---------------|---------|-----|
| 128 | 0x80 | CPU / Estado | Mensajes de estado de grupos (B9), alarmas |
| 129 | 0x81 | Planes / Sync | Sincronización, cambio de fase |

### 3.2 Regla de Uso
- **B9 (estado grupos)**: Siempre usar subregulador **128 (0x80)**
- **Sincronización/Fases**: Usar subregulador **129 (0x81)**

---

## 4. MENSAJE B9 - ESTADO DE GRUPOS

### 4.1 Especificación
Este es el mensaje más importante para el reporte en tiempo real de colores.

| Campo | Valor | Descripción |
|-------|-------|-------------|
| Código | 0xB9 | 0x39 con bit 7 = estado de grupos |
| Formato | 1 byte/grupo | NO es nibble-packed |
| Subregulador | 128 (0x80) | CPU estado |

### 4.2 Valores de Color (CONFIRMADOS)
```python
COLORES_PROTOCOLO_UNE = {
    0:  0x00,  # Apagado → 0x80 codificado
    1:  0x01,  # Rojo → 0x81 codificado
    4:  0x04,  # Ámbar → 0x84 codificado
    16: 0x10,  # Verde → 0x90 codificado
}
```

| Color | Valor Sin Codificar | Valor Codificado | Binario |
|-------|---------------------|------------------|---------|
| Apagado | 0 | 0x80 | 10000000 |
| Rojo | 1 | 0x81 | 10000001 |
| Ámbar | 4 | 0x84 | 10000100 |
| Verde | 16 | 0x90 | 10010000 |

### 4.3 Mapeo de Estados Internos a Protocolo
```python
def mapear_estado_a_protocolo(estado_interno):
    """
    Convierte estado interno del regulador a valor de protocolo UNE
    
    Estados internos:
        0 = Apagado
        1 = Verde
        2 = Ámbar
        3 = Rojo
        4 = Rojo intermitente
        5 = Verde intermitente
        6 = Ámbar intermitente
    """
    if estado_interno == 0:  # Apagado
        return 0
    elif estado_interno in (1, 5):  # Verde o Verde intermitente
        return 16
    elif estado_interno in (2, 6):  # Ámbar o Ámbar intermitente
        return 4
    elif estado_interno in (3, 4):  # Rojo o Rojo intermitente
        return 1
    else:
        return 1  # Default: rojo (seguridad)
```

### 4.4 Construcción del Mensaje B9
```python
def mensaje_estado_grupos(estado_regulador, subregulador_id=128):
    """Construye mensaje B9 con estado de todos los grupos"""
    STX = bytes([0x02])
    ETX = bytes([0x03])
    
    # Subregulador codificado
    sub = codificar_byte_une(subregulador_id & 0x7F)  # 128 → 0x80
    
    # Código B9 codificado
    codigo = codificar_byte_une(0x39)  # 0x39 → 0xB9
    
    # Estados de grupos
    estados = estado_regulador.get_estado_grupos()
    datos = []
    for estado in estados:
        valor_protocolo = mapear_estado_a_protocolo(estado)
        datos.append(codificar_byte_une(valor_protocolo))
    
    # Construir mensaje sin STX/ETX para checksum
    mensaje_sin_stx = bytes([sub, codigo] + datos)
    checksum = calcular_checksum(mensaje_sin_stx)
    
    return STX + mensaje_sin_stx + bytes([checksum]) + ETX
```

---

## 5. CÓDIGOS DE MENSAJE

### 5.1 Códigos Identificados
| Código | Codificado | Función | Dirección |
|--------|------------|---------|-----------|
| 0x11 | 0x91 | Sincronización | Central → Regulador |
| 0x14 | 0x94 | Datos tráfico | Central → Regulador |
| 0x33 | 0xB3 | Cambio de modo | Central → Regulador |
| 0x34 | 0xB4 | Solicitud alarmas | Central → Regulador |
| 0x35 | 0xB5 | Solicitud configuración | Central → Regulador |
| 0x36 | 0xB6 | Tablas programación | Central → Regulador |
| 0x37 | 0xB7 | Incompatibilidades | Central → Regulador |
| 0x39 | 0xB9 | Estado de grupos | Regulador → Central |

### 5.2 Decodificación de Códigos Recibidos
```python
def procesar_codigo(codigo_recibido):
    """Decodifica el código y determina la acción"""
    codigo = decodificar_byte_une(codigo_recibido)
    
    acciones = {
        0x11: 'sincronizacion',
        0x14: 'datos_trafico',
        0x33: 'cambio_modo',
        0x34: 'alarmas',
        0x35: 'configuracion',
        0x36: 'tablas',
        0x37: 'incompatibilidades',
        0x39: 'estado_grupos',
    }
    return acciones.get(codigo, 'desconocido')
```

---

## 6. TEMPORIZACIÓN

### 6.1 Envío Periódico de Estado
- **Mensaje B9**: Enviar cada **2 segundos**
- **Actualización de ciclo**: Cada **1 segundo**
- **Envío inmediato**: Al cambiar de fase

### 6.2 Secuencia de Cambio de Fase
```python
# Al detectar cambio de fase:
1. Actualizar estado interno
2. Enviar mensaje de cambio de fase (código específico)
3. Esperar 100ms
4. Enviar mensaje B9 con nuevos estados
```

---

## 7. MODOS DE OPERACIÓN Y PLANES

### 7.1 Modos de Control
| Modo | Valor Interno | Descripción |
|------|---------------|-------------|
| LOCAL | 1 | Regulador autónomo, selecciona planes por horario |
| ORDENADOR | 2 | Central controla, decide el plan activo |
| MANUAL | 3 | Operador local controla |

### 7.2 Mensaje B3 - Directiva Estados (4 bytes)
Según norma UNE 135401-4, la directiva Estados (0x54/0xD4 codificado como 0xB3) 
tiene **4 bytes de datos**:

```
BYTE 1 - Estado de representación:
  0 = Apagado
  1 = Intermitente
  2 = Colores

BYTE 2 - Selección de planes:
  0 = Control LOCAL de planes (horario)
  1 = Control externo seleccionado
  2 = Control externo por ICF
  4 = Plan seleccionado por ORDENADOR

BYTE 3 - Coordinación/Control:
  0 = Coordinado señal externa
  1 = Coordinado reloj interno
  2 = Coordinado por ordenador
  4 = Control CENTRALIZADO
  8 = Control MANUAL
  16 = Control ordenador grupos mando directo

BYTE 4 - Método de control:
  0 = Tiempos fijos
  1 = Semiactuado
  2 = Actuado total
  4 = Habilitación emergencia
```

**Ejemplos de mensajes B3:**
| Modo | Mensaje Hex | Byte2 | Byte3 | Interpretación |
|------|-------------|-------|-------|----------------|
| ORDENADOR | 0280B382848480XX03 | 4 | 4 | Centralizado |
| LOCAL | 0280B382808180XX03 | 0 | 1 | Local + reloj interno |
| MANUAL | 0280B382808880XX03 | 0 | 8 | Manual |

### 7.3 Selección de Planes
**IMPORTANTE**: Los planes almacenados en el regulador SOLO se seleccionan 
automáticamente cuando el regulador está en **modo LOCAL**.

En **modo ORDENADOR**, la central es quien ordena qué plan debe ejecutarse.
Esto permite el concepto de **"subareas"**: grupos de reguladores que trabajan
en malla con tiempos de ciclo y planes en común.

### 7.4 Horarios de Planes
Los planes solo tienen **hora de inicio** (no hora de fin).
El plan activo es el último cuya hora de inicio ya pasó.

```python
# Ejemplo de horarios:
horarios = [
    {"inicio": "06:00"},  # Plan se activa a las 6:00
    {"inicio": "09:00"},  # Se mantiene hasta las 9:00
    {"inicio": "14:00"},  # Siguiente cambio a las 14:00
    {"inicio": "21:00"},  # Nocturno
]

# A las 10:30, el plan activo sería el de "09:00"
# A las 22:00, el plan activo sería el de "21:00"
```

### 7.4 Lógica de Selección por Horario (Solo modo LOCAL)
```python
def seleccionar_plan_por_horario(self):
    # Solo en modo LOCAL
    if self.modo_control != 1:
        return self.plan_actual  # Central decide
    
    hora_actual = datetime.now().strftime("%H:%M")
    
    # Ordenar planes por hora de inicio
    planes_ordenados = sorted(planes_horarios, key=lambda x: x[0])
    
    # Encontrar el plan cuya hora ya pasó (el más reciente)
    for hora_inicio, plan_id in planes_ordenados:
        if hora_inicio <= hora_actual:
            plan_seleccionado = plan_id
    
    return plan_seleccionado
```

---

## 8. TRANSITORIOS

### 8.1 Secuencia de Transitorio Vehicular
```
Fase Verde → ÁMBAR (3 seg) → ROJO SEGURIDAD (2 seg) → Siguiente Fase
```

### 8.2 Lógica de Transitorio
```python
def get_estado_transitorio(self):
    """Estado de grupos durante transitorio"""
    t_ambar = 3  # segundos
    t_rojo = 2   # segundos
    
    # Obtener fase anterior
    fase_anterior = self.fases_config.get(self.fase_actual, {})
    grupos_fase = fase_anterior.get('grupos', {})
    
    estados = [3] * self.num_grupos  # Default rojo
    
    if self.tiempo_en_paso <= t_ambar:
        # Fase ámbar: grupos que estaban en verde → ámbar
        for g_str, color in grupos_fase.items():
            g = int(g_str)
            if color == 1:  # Era verde
                estados[g - 1] = 2  # Ámbar
            else:
                estados[g - 1] = 3  # Rojo
    else:
        # Fase rojo seguridad: todos en rojo
        estados = [3] * self.num_grupos
    
    return estados
```

---

## 9. ERRORES COMUNES Y SOLUCIONES

### 9.1 Colores No Aparecen en Central
**Causa**: Subregulador incorrecto en mensaje B9
**Solución**: Usar subregulador 128 (no 129)

### 9.2 Colores Incorrectos
**Causa**: Valores de color incorrectos
**Solución**: Verde=16, Rojo=1, Ámbar=4, Apagado=0

### 9.3 Mensaje No Reconocido
**Causa**: Falta bit 7 en bytes de datos
**Solución**: Aplicar `| 0x80` a todos los bytes de datos

### 9.4 Checksum Inválido
**Causa**: Incluir STX/ETX en cálculo o no codificar checksum
**Solución**: XOR solo de datos (sin STX/ETX), luego aplicar `| 0x80`

---

## 10. TEMPLATE DE IMPLEMENTACIÓN

### 10.1 Nueva Funcionalidad - Checklist
```
□ Identificar código de mensaje (decodificado)
□ Determinar subregulador correcto
□ Definir estructura de datos
□ Codificar todos los bytes con bit 7
□ Calcular checksum correctamente
□ Probar sin afectar funcionalidad existente
```

### 10.2 Código Base para Nuevo Mensaje
```python
def nuevo_mensaje(estado, subregulador_id, codigo_mensaje):
    """Template para crear un nuevo tipo de mensaje"""
    STX = bytes([0x02])
    ETX = bytes([0x03])
    
    # 1. Codificar subregulador
    sub = codificar_byte_une(subregulador_id & 0x7F)
    
    # 2. Codificar código de mensaje
    codigo = codificar_byte_une(codigo_mensaje)
    
    # 3. Preparar datos (TODOS codificados)
    datos = []
    # ... agregar bytes de datos codificados ...
    
    # 4. Calcular checksum
    mensaje_sin_stx = bytes([sub, codigo] + datos)
    checksum = calcular_checksum(mensaje_sin_stx)
    
    # 5. Construir mensaje final
    return STX + mensaje_sin_stx + bytes([checksum]) + ETX
```

---

## 11. HISTORIAL DE VALIDACIÓN

| Fecha | Funcionalidad | Estado | Notas |
|-------|---------------|--------|-------|
| 2026-01-15 | Mensaje B9 formato | ✅ Validado | 1 byte/grupo, no nibbles |
| 2026-01-15 | Colores B9 | ✅ Validado | 0=Off, 1=Rojo, 4=Ámbar, 16=Verde |
| 2026-01-15 | Subregulador B9 | ✅ Validado | Debe ser 128 (0x80) |
| 2026-01-15 | Transitorios | ✅ Validado | 3s ámbar + 2s rojo |
| 2026-01-15 | Codificación bit 7 | ✅ Validado | Todos los datos |
| 2026-01-16 | Horarios solo inicio | ✅ Validado | Sin hora fin |
| 2026-01-16 | Selección solo LOCAL | ✅ Validado | Central decide en modo ORDENADOR |

---

## NOTAS IMPORTANTES

1. **NUNCA** cambiar los valores de color confirmados (16, 4, 1, 0)
2. **SIEMPRE** usar subregulador 128 para mensaje B9
3. **SIEMPRE** codificar bytes de datos con bit 7
4. **PROBAR** nuevas funcionalidades en aislamiento antes de integrar
5. Este documento es la **fuente de verdad** para el protocolo

---

*Última actualización: 2026-01-16*
*Versión del regulador: 1.7.0*
