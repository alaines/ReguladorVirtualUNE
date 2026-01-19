# ANÁLISIS COMPLETO DEL REGULADOR REAL
## Captura: 14/01/2026 16:58 - 15/01/2026 05:46 (12.8 horas)

================================================================================
## INFORMACIÓN GENERAL
================================================================================

**Duración de captura:** 46,044 segundos (12.8 horas)
**Total mensajes central:** 18,632
**Total mensajes regulador:** 11,991
**Modo del regulador:** Modo A (Síncrono - respuesta a petición)

================================================================================
## ARQUITECTURA DE COMUNICACIÓN
================================================================================

El regulador usa **DUAL SUBREGULADOR:**
- **Subregulador 128 (0x80):** Estado, alarmas, configuración, grupos
- **Subregulador 129 (0x81):** Sincronización, planes, datos de tráfico

================================================================================
## CÓDIGOS UTILIZADOS
================================================================================

### CÓDIGOS ENVIADOS POR LA CENTRAL (peticiones):

| Código | Nombre                    | Frecuencia | Subregulador |
|--------|---------------------------|------------|--------------|
| 0x91   | Sincronización            | 4,677      | 129          |
| 0xB7   | Incompatibilidades        | 793        | 128          |
| 0xB4   | Estado/Alarmas            | 646        | 128          |
| 0xB5   | Parámetros configuración  | 646        | 128          |
| 0xB6   | Tablas programación       | 646        | 128          |
| 0x94   | Datos de tráfico          | 459        | 129          |
| 0xD2   | Puesta en hora            | 30         | 128          |
| 0xD1   | Selección de plan         | 15         | 129          |
| 0x92   | Selección de plan (alt)   | 11         | 129          |
| 0xD4   | Estados (repr)            | 4          | 128          |

**Patrón:**  
La central consulta periódicamente (cada ~15 segundos) el estado del regulador:
- Sincronización (0x91): cada 10-15 seg
- Estado/Config (0xB4/B5/B6/B7): cada ~1 minuto
- Datos de tráfico (0x94): cada ~1 minuto

### CÓDIGOS ENVIADOS POR EL REGULADOR (respuestas):

| Código | Nombre                    | Frecuencia | Tipo          |
|--------|---------------------------|------------|---------------|
| 0x91   | Sincronización            | 4,771      | Respuesta     |
| 0xB9   | Estado de grupos          | 3,248      | **ESPONTÁNEO** |
| 0xB3   | Cambio modo control       | 768        | **ESPONTÁNEO** |
| 0xB7   | Incompatibilidades        | 725        | Respuesta     |
| 0xB4   | Estado/Alarmas            | 641        | Respuesta     |
| 0xB5   | Parámetros configuración  | 641        | Respuesta     |
| 0xB6   | Tablas programación       | 641        | Respuesta     |
| 0x94   | Datos de tráfico          | 441        | Respuesta     |
| 0xD2   | Puesta en hora (conf)     | 26         | Confirmación  |
| 0xD1   | Selección plan (conf)     | 21         | Confirmación  |

**IMPORTANTE:** Aunque es **Modo A**, el regulador envía mensajes **ESPONTÁNEOS**:
- **0xB9** (Estado grupos): 3,248 veces - ¡Envía cambios de luces en tiempo real!
- **0xB3** (Modo control): 768 veces - Notifica cambios de modo

================================================================================
## PARÁMETROS DETECTADOS
================================================================================

### PLANES ACTIVOS:
- Plan 129 (0x81)
- Plan 130 (0x82) ← **Más frecuente**
- Plan 134 (0x86)
- Plan 135 (0x87)
- Plan 136 (0x88)

### CICLOS DE SEMÁFORO:
- 128 segundos
- 129 segundos
- 130 segundos ← **Ciclo principal**

### CONFIGURACIÓN DE GRUPOS:
**Total grupos:** 6 (según mensajes 0xB9)
- Grupos 1, 2, 3: Vehiculares
- Grupos 4, 5, 6: Probablemente peatonales

**Patrones observados de estados:**
1. `G1:Ámbar, G2:Apagado, G3:Apagado, G4:Verde, G5:Ámbar, G6:Apagado`
2. `G1:Ámbar, G2:Verde, G3:Apagado, G4:Apagado, G5:Ámbar, G6:Apagado`
3. `G1:Ámbar, G2:Apagado, G3:Verde, G4:Apagado, G5:Ámbar, G6:Apagado`

**Observación:** Los grupos 1 y 5 están **siempre en ÁMBAR** en todas las muestras.
Esto puede indicar:
- Luces de advertencia permanentes
- Grupos en modo intermitente/falla
- Grupos peatonales con ámbar intermitente

================================================================================
## MENSAJES DECODIFICADOS (EJEMPLOS REALES)
================================================================================

### 1. SINCRONIZACIÓN (0x91)
```
Central: 02 81 91 03
         └─ Solicita sincronización al subregulador 129

Regulador: 02 81 91 82 84 81 9E 82 80 D6 80 D3 03
           │  │  │  │  │  │  │  │  │  └─ Checksum + ETX
           │  │  │  │  │  │  │  └─ Día/Mes?
           │  │  │  │  │  │  └─ Segundos en ciclo: 130
           │  │  │  │  │  └─ Hora: 132:129:158 (valores con bit 7 activo)
           │  │  │  └─ Plan: 130 (0x82)
           │  │  └─ Código 0x91
           │  └─ Subregulador 129
           └─ STX

Plan: 130
Hora: Requiere decodificación (bit 7 activo en bytes)
Segundos ciclo: 130
```

### 2. ESTADO/ALARMAS (0xB4)
```
Central: 02 80 B4 03

Regulador: 02 80 B4 80 80 90 80 A4 03
           │  │  │  │  │  │  └─ Ciclo: 144s (?)
           │  │  │  │  └─ Número de grupos: 128 (?)
           │  │  │  └─ Byte estado: 0x80 (10000000)
           │  │  └─ Código 0xB4
           │  └─ Subregulador 128
           └─ STX

Byte estado 0x80:
- Bit 7 = 1: Posible indicador de "modo normal" o "bit de paridad"
- Bits 0-2 = 0: Sin alarmas de roja/lámpara/conflicto
```

### 3. PARÁMETROS CONFIGURACIÓN (0xB5)
```
Central: 02 80 B5 03

Regulador: 02 80 B5 B5 03
           │  │  │  └─ Checksum
           │  │  └─ Código 0xB5
           │  └─ Subregulador 128
           └─ STX

⚠️ SOLO RESPONDE CON ACK (sin datos)
Esto es común en Modo A cuando no hay datos que reportar
```

### 4. TABLAS PROGRAMACIÓN (0xB6)
```
Central: 02 80 B6 03

Regulador: 02 80 B6 B6 03

⚠️ SOLO RESPONDE CON ACK (sin datos)
```

### 5. ESTADO DE GRUPOS (0xB9) - ¡MENSAJE ESPONTÁNEO!
```
Regulador: 02 80 B9 81 90 90 81 B9 03
           │  │  │  │  │  │  └─ Byte 2 de estados
           │  │  │  │  └─ Byte 1 de estados
           │  │  │  └─ (datos adicionales?)
           │  │  └─ Código 0xB9
           │  └─ Subregulador 128
           └─ STX

Decodificación byte 1 (0x90 = 10010000):
- Bits 7-6: Grupo 1 = 10 = Ámbar
- Bits 5-4: Grupo 2 = 01 = Verde
- Bits 3-2: Grupo 3 = 00 = Apagado
- Bits 1-0: Grupo 4 = 00 = Apagado

Byte 2 (0x81 = 10000001):
- Bits 7-6: Grupo 5 = 10 = Ámbar
- Bits 5-4: Grupo 6 = 00 = Apagado
```

### 6. CAMBIO MODO CONTROL (0xB3) - ¡MENSAJE ESPONTÁNEO!
```
Regulador: 02 80 B3 80 80 80 80... [múltiples 0x80] ...B3 03
           │  │  │  └─ Byte modo: 0x80
           │  │  └─ Código 0xB3
           │  └─ Subregulador 128
           └─ STX

Byte 0x80 (10000000):
- Bits 0-1 = 00: Estado representación = APAGADO (?)
- Bit 7 = 1: Control centralizado ACTIVO

⚠️ Mensaje enviado repetidamente con muchos bytes 0x80
Posible error en el regulador o mensaje de "keep-alive"
```

================================================================================
## DIFERENCIAS CON REGULADOR VIRTUAL (Modo B)
================================================================================

| Aspecto                  | Regulador Real (Modo A)   | Virtual (Modo B)          |
|--------------------------|---------------------------|---------------------------|
| **Modo**                 | A (Síncrono)              | B (Asíncrono)             |
| **Subreguladores**       | 128 y 129                 | 128 y 129 ✓               |
| **Checksum**             | Presente pero raro        | 7 bits UNE                |
| **Mensajes espontáneos** | SÍ (0xB9, 0xB3)          | SÍ (0xD5, 0xB9) ✓        |
| **Estado grupos (0xB9)** | 3,248 veces              | Implementado ✓            |
| **Cambio modo (0xB3)**   | 768 veces                | Implementado ✓            |
| **Plan activo**          | Plan 130                 | Plan 1 (configurable)     |
| **Ciclo**                | 130 segundos             | 60 segundos               |
| **Grupos G1, G5**        | Siempre ÁMBAR            | Cambian con fase          |
| **Respuestas 0xB5/B6**   | Solo ACK (sin datos)     | Con datos completos       |
| **Codificación bytes**   | Bit 7 activo (0x80+)     | Valores directos          |

================================================================================
## HALLAZGOS IMPORTANTES
================================================================================

### ✅ IMPLEMENTACIONES CORRECTAS EN VIRTUAL:
1. **Dual subregulador (128/129)**: ✓ Coincide
2. **Envío espontáneo de 0xB9**: ✓ Coincide (estado grupos)
3. **Cambio de modo 0xB3**: ✓ Implementado
4. **Estructura de mensajes**: ✓ Compatible

### ⚠️ DIFERENCIAS A AJUSTAR:

1. **Codificación de bytes con bit 7:**
   - El regulador real usa bytes con bit 7 activo (0x80+)
   - Valores: 0x80=0, 0x81=1, 0x82=2, etc.
   - Virtual usa valores directos (0, 1, 2)

2. **Ciclo del semáforo:**
   - Real: 130 segundos
   - Virtual: 60 segundos
   - **Ajustar:** Cambiar Plan 1 a ciclo 130s

3. **Plan activo:**
   - Real: Plan 130 (0x82)
   - Virtual: Plan 1 (0x01)
   - **Ajustar:** Numerar planes como 130, 131, 132

4. **Grupos siempre en ámbar:**
   - Real: G1 y G5 siempre en ámbar
   - Virtual: G1 y G5 cambian con fases
   - **Posible:** Grupos de advertencia permanente

5. **Respuestas vacías 0xB5/B6:**
   - Real: Solo ACK (02 80 B5 B5 03)
   - Virtual: Envía datos completos
   - **Opción:** Hacer respuestas más cortas en Modo A

================================================================================
## RECOMENDACIONES PARA MEJORAR REGULADOR VIRTUAL
================================================================================

### ALTA PRIORIDAD:
1. **Implementar codificación con bit 7:**
   ```python
   def codificar_byte(valor):
       return valor | 0x80  # Activar bit 7
   
   def decodificar_byte(byte):
       return byte & 0x7F   # Quitar bit 7
   ```

2. **Ajustar ciclos a valores reales:**
   - Plan 1 (130): ciclo 130s, fase1 65s, fase2 60s
   - Plan 2 (131): ciclo 144s, fase1 72s, fase2 67s

3. **Cambiar numeración de planes:**
   - Usar 130, 131, 132 en lugar de 1, 2, 3

### MEDIA PRIORIDAD:
4. **Grupos con ámbar permanente:**
   - Hacer que G1 y G5 estén siempre en ámbar
   - O agregar modo "advertencia permanente"

5. **Simplificar respuestas 0xB5/B6 en Modo A:**
   - Solo ACK si no hay datos que reportar

### BAJA PRIORIDAD:
6. **Ajustar frecuencia de mensajes espontáneos:**
   - Enviar 0xB9 en cada cambio de grupo (como el real)
   - Enviar 0xB3 periódicamente

================================================================================
## CONCLUSIÓN
================================================================================

El **regulador virtual en Modo B** tiene una arquitectura muy cercana al real,
con las siguientes coincidencias:

✓ Dual subregulador (128/129)
✓ Envío espontáneo de estado de grupos (0xB9)
✓ Cambio de modo de control (0xB3)
✓ Sincronización (0x91)
✓ Estructura de mensajes UNE compatible

Las principales diferencias están en:
- Codificación de bytes (bit 7)
- Valores de ciclo y plan
- Comportamiento de grupos específicos (G1, G5)

Con los ajustes recomendados, el regulador virtual podrá **emular perfectamente**
el comportamiento del regulador real en Modo A.

================================================================================
Fin del análisis
================================================================================
