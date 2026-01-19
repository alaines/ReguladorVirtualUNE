# Proxy Sniffer UNE 135401-4

## Descripción

Herramienta para capturar y analizar el tráfico entre una central de tráfico y un regulador real UNE 135401-4. Actúa como intermediario **transparente** (man-in-the-middle) decodificando todos los mensajes en ambas direcciones.

## Objetivo

Analizar cómo funciona el regulador real cuando se conecta a la central, especialmente:
- **Inicio de conexión**: Qué mensajes se intercambian al conectarse
- **Estado inicial**: Plan y modo en que arranca el regulador
- **Cambio de modo**: Cómo la central cambia de LOCAL a ORDENADOR
- **Cambio de plan**: Cómo la central solicita cambios de plan

## Configuración

### Regulador Real
- **IP**: 172.17.10.103
- **Puerto normal**: 19000
- **Puerto temporal**: 19001 (durante captura)
- **Modo UNE**: A (Modo A)

### Proxy Sniffer (Modo Transparente)
- **Puerto local**: 19000 (mismo que regulador, intercepta conexiones)
- **Puerto destino**: 19001 (regulador con puerto temporal)
- **Función**: Intercepta y reenvía tráfico SIN que la central lo sepa

## Modo Transparente

```
┌─────────┐                  ┌──────────┐                  ┌────────────┐
│ Central │ ────────────────>│  Proxy   │ ────────────────>│ Regulador  │
│         │  172.17.10.103   │ Sniffer  │  172.17.10.103   │   Real     │
│         │     :19000       │          │     :19001       │  (temporal)│
└─────────┘                  └──────────┘                  └────────────┘
    │                             │                              │
    │                             v                              │
    │                      📝 Captura y                          │
    │                         decodifica                         │
    │                                                            │
    └─────────────── Central NO sabe del proxy ─────────────────┘
```

**La central se conecta normalmente a 172.17.10.103:19000 sin cambiar nada.**

## Uso

### ⚠️ PRE-REQUISITO: Cambiar Puerto del Regulador

**ANTES de ejecutar el sniffer**, cambiar temporalmente el puerto del regulador real:

1. Acceder al regulador físico (172.17.10.103)
2. Cambiar puerto TCP de **19000** → **19001**
3. Guardar y reiniciar si es necesario

### Método 1: Script Automático (Recomendado)

```batch
cd tools
ejecutar_sniffer.bat
```

El script:
- Te recordará cambiar el puerto del regulador
- Escuchará en puerto 19000 (transparente para la central)
- Se conectará al regulador en puerto 19001

### Método 2: Comando Manual

```powershell
cd tools
python ProxySnifferUNE.py --regulador-ip 172.17.10.103 --regulador-puerto 19001 --puerto-local 19000
```

### Método 3: Con parámetros personalizados

```bash
python ProxySnifferUNE.py --help
python ProxySnifferUNE.py -r 172.17.10.103 -rp 19001 -p 19000
```

## Configuración de la Central

**¡NO HAY QUE CAMBIAR NADA EN LA CENTRAL!**

La central mantiene su configuración original:
- **IP**: 172.17.10.103
- **Puerto**: 19000

El proxy intercepta automáticamente la conexión de forma transparente.

## Qué captura el sniffer

### Mensajes decodificados

El sniffer decodifica automáticamente:

- ✅ **Sincronización (0x91)**: Plan actual, hora, fase, tiempo de ciclo
- ✅ **Selección de plan (0x92)**: Plan solicitado
- ✅ **Cambio de modo (0xB3)**: LOCAL/ORDENADOR/MANUAL
- ✅ **Estados (0xD4)**: Modo de control, coordinación, método
- ✅ **Estado grupos (0xB9)**: Colores de semáforos
- ✅ **Alarmas (0xB4)**: Estado del regulador
- ✅ **Configuración (0xB5)**: Parámetros del regulador

### Eventos importantes

El sniffer detecta y marca:

- 🔌 **INICIO DE CONEXIÓN**
- 📋 **PLAN INICIAL**
- 🔄 **CAMBIO DE MODO** (LOCAL → ORDENADOR → MANUAL)
- 🔔 **CAMBIO DE PLAN**

## Salida del Sniffer

### Consola (tiempo real)

```
======================================================================
📤 CENTRAL → REGULADOR
   HEX: 020092C50003
   Sub:0 → Selección de plan (0x92)
      🔔 CAMBIO A PLAN: 5

======================================================================
📥 REGULADOR → CENTRAL
   HEX: 06
   ✓ Confirmación (ACK)
```

### Archivo de log

Se guarda automáticamente en:
```
sniffer_log_20260116_143022.txt
```

Contiene:
- Registro completo de todos los mensajes
- Decodificación detallada
- Eventos importantes con timestamps
- Estadísticas finales

## Estadísticas Finales

Al finalizar (Ctrl+C), muestra:

```
📊 ESTADÍSTICAS DE SESIÓN
======================================================================
⏱️  Duración: 45.3 segundos

🎯 EVENTOS IMPORTANTES DETECTADOS (4):
----------------------------------------------------------------------
[   0.1s] 🔌 INICIO DE CONEXIÓN (R→C)
[   0.3s] 📋 PLAN INICIAL: 2 (R→C)
[   2.5s] 🔄 CAMBIO DE MODO: LOCAL → ORDENADOR (C→R)
[   3.2s] 🔔 CAMBIO DE PLAN: 2 → 5 (C→R)
----------------------------------------------------------------------

📤 Central → Regulador:
   Mensajes: 12
   Bytes: 156
   Códigos usados:
      Sincronización (0x91): 4
      Selección de plan (0x92): 1
      Cambio modo control (0xB3): 2

📥 Regulador → Central:
   Mensajes: 15
   Bytes: 234
   Códigos usados:
      Estado regulador/Alarmas (0xB4): 1
      Estados (0xD4): 3
      Estado grupos (0xB9): 4

📋 RESUMEN DE SECUENCIA DE INICIO:
Plan inicial detectado: 2
Modo actual: ORDENADOR
```

## Análisis de Secuencia de Inicio

### Lo que buscamos

1. **Primer mensaje del regulador al conectarse**
   - ¿Envía estado actual?
   - ¿En qué plan está?
   - ¿En qué modo está?

2. **Respuesta de la central**
   - ¿Acepta el estado inicial?
   - ¿Solicita cambio de modo inmediatamente?
   - ¿Solicita cambio de plan?

3. **Secuencia de cambio**
   - ¿Primero cambia el modo?
   - ¿Luego cambia el plan?
   - ¿Qué confirmaciones se envían?

## Solución de Problemas

### El sniffer no inicia

```
Error: Address already in use
```

**Solución**: Otro proceso usa el puerto 19001
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

### No se conecta al regulador

```
Error: Connection refused
```

**Verificar**:
1. Regulador está encendido
2. Puerto del regulador cambiado a **19001** (no 19000)
3. IP correcta: `ping 172.17.10.103`
4. Firewall no bloquea puerto 19001

**Probar conexión al nuevo puerto**:
```powershell
Test-NetConnection -ComputerName 172.17.10.103 -Port 19001
```

### La central no se conecta

**Verificar**:
1. Proxy está corriendo y escuchando en puerto 19000
2. Central mantiene configuración: 172.17.10.103:19000
3. Firewall permite conexiones en puerto 19000

```powershell
# Verificar que el proxy está escuchando
netstat -an | findstr :19000

# Debe mostrar:
# TCP    0.0.0.0:19000    0.0.0.0:0    LISTENING
```

### Puerto 19000 ya en uso

```
Error: Address already in use
```

**Causa**: Otro proceso (posiblemente otro sniffer) usa el puerto 19000

**Solución**:
```powershell
# Detener todos los procesos Python
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# O encontrar qué proceso usa el puerto 19000
netstat -ano | findstr :19000
# Tomar el PID de la última columna y detenerlo:
Stop-Process -Id [PID] -Force
```

## Códigos UNE Importantes

| Código | Nombre | Descripción |
|--------|--------|-------------|
| 0x91 | Sincronización | Estado completo: plan, hora, fase |
| 0x92 | Selección plan | Solicitud de cambio de plan |
| 0xB3 | Cambio modo | LOCAL/ORDENADOR/MANUAL |
| 0xB4 | Alarmas | Estado y alarmas del regulador |
| 0xB5 | Configuración | Parámetros: fases, grupos, planes |
| 0xB9 | Estado grupos | Colores actuales de semáforos |
| 0xD4 | Estados | Modo actual detallado |

## Próximos Pasos

Una vez capturado el inicio de conexión:

1. **Analizar logs** generados
2. **Comparar** con comportamiento del regulador virtual
3. **Ajustar** regulador virtual para que coincida exactamente
4. **Validar** que la central acepta el regulador virtual

## Contacto

Para preguntas sobre el sniffer o análisis de logs, consultar con el equipo de desarrollo.
