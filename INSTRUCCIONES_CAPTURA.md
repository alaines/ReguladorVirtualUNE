# INSTRUCCIONES PARA CAPTURAR INICIO DE CONEXIÓN DEL REGULADOR REAL

## Objetivo
Analizar cómo trabaja el regulador real al inicio de conexión con la central, especialmente:
- Estado inicial (plan y modo)
- Secuencia de mensajes de inicio
- Cómo cambia de LOCAL a ORDENADOR
- Cómo la central solicita cambios de plan

## Configuración Actual

### Regulador Real
- **IP**: 172.17.10.103
- **Puerto normal**: 19000
- **Puerto temporal para sniffer**: 19001 (cambiar temporalmente)
- **Protocolo**: UNE 135401-4 Modo A
- **Estado inicial**: LOCAL con plan según horario

### Sniffer (Modo Transparente)
- **Ubicación**: `tools/ProxySnifferUNE.py`
- **Puerto de escucha**: 19000 (el mismo que usa normalmente el regulador)
- **Se conecta al regulador en**: 19001 (puerto temporal del regulador)
- **Transparencia**: La central NO sabe que hay un proxy
- **Log automático**: `sniffer_log_YYYYMMDD_HHMMSS.txt`

## Arquitectura del Sniffer

```
┌─────────┐                  ┌──────────┐                  ┌────────────┐
│ Central │ ────────────────>│  Proxy   │ ────────────────>│ Regulador  │
│         │  172.17.10.103   │ Sniffer  │  172.17.10.103   │   Real     │
│         │     :19000       │          │     :19001       │            │
└─────────┘                  └──────────┘                  └────────────┘
                                   │
                                   v
                            📝 Log capturado
                               y decodificado
```

**La central cree que está conectándose directamente al regulador en el puerto 19000 de siempre.**

## Pasos para Capturar

### ⚠️ PASO 0: Cambiar Puerto del Regulador Real

**IMPORTANTE**: Antes de iniciar el sniffer, debes cambiar temporalmente el puerto del regulador real:

1. Acceder a la configuración del regulador físico (172.17.10.103)
2. Cambiar puerto de comunicación de **19000** a **19001**
3. Guardar y reiniciar el regulador si es necesario
4. Verificar que ahora escucha en puerto 19001

**Verificar conectividad**:
```powershell
Test-NetConnection -ComputerName 172.17.10.103 -Port 19001
```

### 1. Iniciar el Sniffer

**Opción A - Script automático (RECOMENDADO):**
```batch
cd tools
ejecutar_sniffer.bat
```

El script te recordará cambiar el puerto del regulador antes de continuar.

**Opción B - Manual:**
```powershell
cd "d:\Proyectos Soporte\probrarReguladorUNE\tools"
python ProxySnifferUNE.py --regulador-ip 172.17.10.103 --regulador-puerto 19001 --puerto-local 19000
```

Deberías ver:
```
======================================================================
🔍 PROXY SNIFFER UNE 135401-4
======================================================================
📡 Puerto local (para Central): 19000
🎯 Regulador destino: 172.17.10.103:19001
⏳ Esperando conexión de la central en puerto 19000...
```

### 2. Conectar la Central

**SIN CAMBIAR NADA EN LA CENTRAL**

La central debe mantener su configuración original:
- **IP**: 172.17.10.103
- **Puerto**: 19000

El proxy interceptará automáticamente la conexión.

### 3. Observar Secuencia de Inicio

El sniffer mostrará en tiempo real todos los mensajes:

```
======================================================================
📥 REGULADOR → CENTRAL
   HEX: 020034...
   Sub:0 → Estado regulador/Alarmas (0xB4)
      Estado: 0x00 (00000000)
      ✅ Sin alarmas
      Grupos: 4
      Ciclo: 90s

======================================================================
📤 CENTRAL → REGULADOR
   HEX: 02009186850D810481038103EA03
   Sub:0 → Sincronización (0x91)
      ...
```

### 6. Esperar Eventos Importantes

El sniffer detectará y marcará:

- 🔌 **INICIO DE CONEXIÓN**: Primer mensaje
- 📋 **PLAN INICIAL**: Plan en que arranca
- 🔄 **CAMBIO DE MODO**: LOCAL → ORDENADOR
- 🔔 **CAMBIO DE PLAN**: Si la central solicita otro plan

### 7. Detener Captura

Cuando hayas capturado suficiente información:
- Presiona **Ctrl+C** en el terminal del sniffer
- El sniffer mostrará estadísticas finales
- El log completo estará en `tools/sniffer_log_YYYYMMDD_HHMMSS.txt`

### 8. ⚠️ RESTAURAR CONFIGURACIÓN DEL REGULADOR

**MUY IMPORTANTE**: Restaurar el puerto del regulador real:

1. Acceder a configuración del regulador (172.17.10.103)
2. Cambiar puerto de **19001** de vuelta a **19000**
3. Guardar y reiniciar
4. Verificar que la central puede conectarse directamente

La central NO necesita cambios, ya estaba configurada para 172.17.10.103:19000

## Qué Buscar en los Logs

### A. Secuencia de Inicio

1. **Primer mensaje del regulador**:
   - ¿Qué código envía? (¿0xB4 Alarmas? ¿0xD4 Estados?)
   - ¿Reporta plan actual?
   - ¿Reporta modo LOCAL?

2. **Primera respuesta de la central**:
   - ¿Qué solicita? (¿Sincronización 0x91? ¿Modo 0xB3?)
   - ¿Acepta el plan inicial?

3. **Intercambio inicial completo**:
   - ¿Cuántos mensajes se intercambian?
   - ¿En qué orden?

### B. Cambio de Modo (LOCAL → ORDENADOR)

1. **Mensaje de la central**:
   - Código: 0xB3 (Cambio modo control)
   - Byte de modo: ¿Qué valor tiene?
   - Bits activos

2. **Confirmación del regulador**:
   - ¿Envía ACK inmediatamente?
   - ¿Envía 0xD4 (Estados) después?
   - ¿Reporta nuevo modo correctamente?

### C. Cambio de Plan

1. **Solicitud de la central**:
   - Código: 0x92 (Selección plan)
   - Plan solicitado
   - ¿Incluye hora de inicio?

2. **Confirmación del regulador**:
   - ACK
   - ¿Envía 0x91 (Sincronización) con nuevo plan?
   - ¿Cuánto tarda en cambiar?

## Análisis del Log Capturado

Una vez tengas el log, busca:

### Patrón de Inicio Exitoso

```
[T+0.0s] R→C: 0xB4 (Alarmas) - Estado inicial
[T+0.1s] C→R: 0x91 (Sincronización) - Central solicita sync
[T+0.2s] R→C: 0x91 (Sincronización) - Regulador responde
[T+0.3s] C→R: 0xB3 (Cambio modo) - Central pide ORDENADOR
[T+0.4s] R→C: ACK
[T+0.5s] R→C: 0xD4 (Estados) - Confirma modo ORDENADOR
[T+2.0s] C→R: 0x92 (Cambio plan) - Central pide plan 5
[T+2.1s] R→C: ACK
[T+2.2s] R→C: 0x91 (Sincronización) - Confirma plan 5
```

### Bytes Específicos

- **Modo en 0xD4**: 
  - Byte 2: bits que indican LOCAL/ORDENADOR/MANUAL
  - Byte 3: bits de coordinación

- **Plan en 0x91**:
  - Byte 1 de datos: número de plan

## Comparación con Regulador Virtual

Una vez capturado el tráfico real:

1. **Comparar secuencia de inicio**:
   - ¿El regulador virtual envía los mismos mensajes?
   - ¿En el mismo orden?

2. **Comparar bytes exactos**:
   - Mensaje 0xD4: ¿bytes idénticos?
   - Mensaje 0x91: ¿formato igual?

3. **Comparar tiempos**:
   - ¿El virtual responde igual de rápido?

4. **Ajustar regulador virtual**:
   - Copiar secuencia exacta del real
   - Asegurar bytes idénticos
   - Validar con central

## Archivos Generados

Después de la captura tendrás:

```
tools/
├── sniffer_log_20260116_141638.txt  (Log completo con timestamps)
├── ProxySnifferUNE.py                (El sniffer)
├── ejecutar_sniffer.bat              (Script de ejecución)
└── README_SNIFFER.md                 (Documentación)
```

## Troubleshooting

### El sniffer no arranca
```
Error: Address already in use
```
**Solución**: 
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

### No llega tráfico
1. Verificar IP configurada en central
2. Verificar puerto 19001
3. Verificar firewall de Windows

### El regulador no responde
1. Verificar regulador encendido
2. Ping: `ping 172.17.10.103`
3. Verificar puerto 19000 abierto

## Próximo Paso

Después de capturar y analizar:

1. Identificar **secuencia exacta de inicio**
2. Identificar **bytes exactos de modo y plan**
3. Modificar `regulador_gui.py` para replicar comportamiento
4. Probar con central real
5. Validar que funciona idéntico

---

**NOTA**: El sniffer está corriendo en segundo plano. Para detenerlo:
```powershell
Get-Process python | Where-Object {$_.StartInfo.Arguments -like "*ProxySnifferUNE*"} | Stop-Process
```
