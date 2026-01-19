# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [1.11.0] - 2026-01-19

### Añadido
- **Visualización de parpadeo en modo intermitente:**
  - Los semáforos en la GUI ahora parpadean cuando están en estado intermitente
  - Timer de 500ms (1 Hz) para alternar encendido/apagado
  - Soporte para estados 4 (rojo intermitente), 5 (verde intermitente), 6 (ámbar intermitente)
  - Etiquetas muestran "ROJO ⚡", "VERDE ⚡", "ÁMBAR ⚡" para estados intermitentes

### Corregido
- **Reporte de estado intermitente a la central (Estado de Luces):**
  - El mensaje 0x94 (Datos de tráfico) ahora reporta correctamente el estado de representación
  - Byte 1 = 0x01 cuando está en INTERMITENTE, 0x02 cuando está en COLORES
  - La central Ecotrafix ahora muestra "INTERMITENTE" en el campo "Estado de Luces"
  - Análisis de captura real: `028194818183809603` (INTERMIT) vs `028194828183809503` (COLORES)

- **Mensaje B3 (modo control) siempre envía 0x00:**
  - Según captura del regulador real, B3 siempre envía byte modo 0x00
  - La central determina el estado desde 0x94, no desde B3
  - Corregido tanto el B3 inicial como el de respuesta a petición 0x20

## [1.10.0] - 2026-01-19

### Corregido
- **Modo intermitente ahora funciona correctamente desde la central:
  - El comando D4 con Estado=INTERMITENTE (byte1=0x01) ahora se procesa correctamente
  - El regulador cambia su estado de representación a intermitente
  - Mensaje B9 (estado de grupos) ahora envía el valor correcto para ámbar intermitente

- **Valores B9 corregidos según captura del regulador real:**
  - Ámbar normal: 4 (0x84 codificado)
  - **Ámbar intermitente: 12 (0x8C codificado)** - Antes enviaba 4, ahora 12 como el real
  - Verde intermitente: 24 (16 + 8 bit intermitente)
  - Rojo intermitente: 9 (1 + 8 bit intermitente)
  - El bit 3 (valor 8) indica estado intermitente

### Documentación
- Análisis de captura del regulador real en modo intermitente
- El regulador real envía `0x8C` (12 decimal) para todos los grupos en modo intermitente

## [1.9.0] - 2026-01-19

### Añadido
- **Soporte completo para forzar planes desde la central Ecotrafix:**
  - La central ahora puede cambiar el plan del regulador en modo ORDENADOR
  - Conversión automática de IDs de plan: Central (3,4,5...) ↔ Regulador (131,132,133...)
  - Respuestas ACK + eco para todos los comandos según protocolo real

### Corregido
- **Lógica invertida del bit de modo en mensaje 0xB3:**
  - Antes: bit 2 = 1 significaba ORDENADOR (incorrecto)
  - Ahora: bit 2 = 0 = Central puede controlar (ORDENADOR), bit 2 = 1 = LOCAL
  - Validado contra capturas de sniffer del regulador real

- **Respuestas a comandos de la central con formato correcto:**
  - 0x91 (Sincronización): Ahora envía ACK primero, luego datos
  - 0x94 (Datos tráfico): ACK + mensaje con datos `028194828081809603`
  - 0xD2 (Puesta en hora): ACK + eco vacío
  - 0xB4 (Alarmas): ACK + datos
  - 0xB5 (Configuración): ACK + eco
  - 0xB6 (Tablas programación): ACK + eco
  - 0xB7 (Incompatibilidades): ACK + eco
  - 0xDD (Código propietario Ecotrafix): ACK + eco

- **Conversión de IDs de plan entre central y regulador:**
  - Recepción D1: plan_central + 128 = plan_interno (ej: 3 → 131)
  - Reporte 0x91: plan_interno - 128 = plan_para_central (ej: 132 → 4)

### Documentación
- Análisis detallado de secuencia de inicio del regulador real
- Mapeo de subreguladores: CPU=128 (B3,B4,B9,D2), Planes=129 (91,94,D1,D4)

## [1.8.2] - 2026-01-16

### Corregido
- **Mensaje B3 (cambio de modo) con formato completo según norma UNE 135401-4:**
  - El mensaje ahora tiene 4 bytes de datos según la directiva Estados (0x54/0xD4):
    - Byte 1: Estado de representación (0=Apagado, 1=Intermitente, 2=Colores)
    - Byte 2: Selección de planes (0=LOCAL horario, 4=ORDENADOR)
    - Byte 3: Coordinación (1=Reloj interno, 4=CENTRALIZADO, 8=MANUAL)
    - Byte 4: Método de control (0=Tiempos fijos)
  - Antes: solo 1 byte, la central interpretaba siempre como LOCAL
  - Ahora: 4 bytes, la central reconoce correctamente modo CENTRALIZADO

## [1.8.1] - 2026-01-16

### Corregido
- **Mensaje B3 (cambio de modo) reportaba modo incorrecto:**
  - Corregida la codificación del byte de modo según protocolo UNE real
  - Antes: bit 2 activo = ORDENADOR (incorrecto)
  - Ahora: bit 2 activo = LOCAL, ningún bit = ORDENADOR/Centralizado
  - Validado contra sniffer de regulador real (byte 0x00 = Control Centralizado)

## [1.8.0] - 2026-01-15

### Añadido
- **Notificación de estado completo al cambiar de plan:**
  - Cuando el plan cambia (por horario en modo LOCAL o por orden de la central en modo ORDENADOR), el regulador envía su estado completo a la central
  - Se envía: alarmas (0xB2), modo actual (0xB3) y estado de grupos (0xB9)
  - Igual comportamiento que al iniciar la conexión
  - Nuevo método `enviar_estado_completo()` reutilizable
  - Callback `_on_plan_changed(plan_anterior, nuevo_plan)` en EstadoRegulador

### Mejorado
- `EstadoRegulador.cambiar_plan()` ahora soporta callbacks para notificar cambios
- `ReguladorVirtual` y `ReguladorVirtualGUI` suscritos al callback de cambio de plan

## [1.7.0] - 2026-01-15

### Añadido
- **Reporte en tiempo real de estados de grupos (mensaje B9):**
  - Envío periódico cada 2 segundos a la central
  - Formato corregido: 1 byte por grupo (no nibble-packed)
  - Mapeo de colores UNE confirmado: 0=Apagado, 1=Rojo, 4=Ámbar, 16=Verde
  - Subregulador 128 (CPU) para envío de estados
  
- **Transitorios funcionales entre fases:**
  - Fase ámbar (3 seg): grupos que estaban en verde pasan a ámbar
  - Fase rojo de seguridad (2 seg): todos los grupos en rojo
  - Método `_get_estado_transitorio()` en estado_regulador.py
  - Tiempos configurables por plan

- **Nueva pestaña 📊 Timeline en editor de planes:**
  - Vista unificada con una barra horizontal por grupo
  - Cada grupo muestra sus colores a lo largo del ciclo completo
  - Escala de tiempo con marcas de fases (F1, F2) y transitorios (T1, T2)
  - Transitorios divididos en ámbar y rojo según el estado anterior
  - Leyenda de colores: Verde, Ámbar, Rojo
  - Actualización automática al cambiar estructura, duraciones o transitorios

- **Plan 7 reconfigurado como ejemplo:**
  - Estructura 1 (2 fases), desfase 0, ciclo 120 seg
  - Fase 1 (40 seg): G1 y G4 verde, G2 y G3 rojo
  - Transitorio 1 (5 seg): G1 y G4 ámbar 3s → rojo 2s
  - Fase 2 (70 seg): G2 y G3 verde, G1 y G4 rojo
  - Transitorio 2 (5 seg): G2 y G3 ámbar 3s → rojo 2s

### Corregido
- Formato de mensaje B9: de nibbles (2 grupos/byte) a bytes (1 grupo/byte)
- Valores de color en protocolo UNE: Verde=16, Rojo=1, Ámbar=4
- Definición de fases 1 y 2 para coincidir con Plan 7

### Modificado
- `modules/generador_respuestas.py`: mapear_estado() con valores correctos
- `modules/estado_regulador.py`: get_estado_grupos() ahora aplica transitorios
- `config/regulador_config.json`: fases y Plan 135 actualizados
- `regulador_gui.py`: nueva pestaña Timeline en editor de planes
- `regulador_gui.py`: corregido subregulador en mensaje B9 (128 en lugar de 129)

### Documentación
- **Nuevo**: `docs/PROTOCOLO_UNE_REFERENCIA.md` - Referencia técnica completa del protocolo
  - Codificación de bytes con bit 7
  - Estructura de mensajes
  - Valores de colores confirmados (Verde=16, Rojo=1, Ámbar=4)
  - Subreguladores y sus funciones
  - Templates para nuevas implementaciones
  - Historial de validación

## [1.6.0] - 2026-01-15

### Añadido
- **Modelo completo UNE 135401-4:**
  - Fases como entidad separada (hasta 32 fases)
  - Estructuras como secuencias reutilizables de fases + transitorios
  - Planes que referencian estructuras y definen duraciones por fase
  - Soporte para tipo de grupo "ciclista" (además de vehicular y peatonal)
  
- **Nueva pestaña 🎨 Fases:**
  - Editor visual de fases con todos los colores UNE (0-8)
  - Asignación de color por grupo con preview en tiempo real
  - Códigos de color: Apagado, Verde, Ámbar, Rojo, intermitentes, etc.
  
- **Nueva pestaña 🔄 Estructuras:**
  - Definición de secuencias de fases + transitorios
  - Editor de secuencia con botones agregar/eliminar/mover
  - Cada plan referencia una estructura reutilizable
  
- **Pestaña 📋 Planes mejorada:**
  - Selector de estructura (en lugar de definir fases inline)
  - Duraciones de fase dinámicas según estructura seleccionada
  - Transitorios por tipo: vehicular, peatonal, ciclista

### Modificado
- JSON de configuración con nuevo esquema:
  - `fases.lista[]`: definiciones de fases con colores por grupo
  - `estructuras.lista[]`: secuencias de fases y transitorios
  - `planes.lista[].estructura_id`: referencia a estructura
  - `planes.lista[].duraciones_fases{}`: duración por fase
- `estado_regulador.py` actualizado para usar nuevo modelo
- Límites configurables: max_grupos=32, max_fases=32, max_estructuras=16

## [1.5.0] - 2026-01-15

### Añadido
- **Semáforos gráficos en Monitor:**
  - Visualización en tiempo real de cada grupo
  - Semáforos vehiculares (3 luces: rojo, ámbar, verde)
  - Semáforos peatonales (2 luces: rojo, verde)
  - Colores que cambian según fase actual
  - Etiqueta de estado debajo de cada semáforo
- **Contador de ciclo** visible en el monitor
- Actualización de semáforos cada 2 segundos y en cambio de fase

### Corregido
- Estado "Conectado" ahora se mantiene visible al actualizar otros parámetros

## [1.4.0] - 2026-01-15

### Añadido
- **Editor de planes mejorado** con pestañas:
  - 📋 General: ID, nombre, ciclo, fases, horarios
  - 🚦 Fases y Grupos: Selección de qué grupos salen en verde en cada fase
  - ⏱️ Transitorios: Tiempos de ámbar/rojo (vehicular) y verde intermitente/rojo (peatonal)
- **Botón "Editar Grupos"** en configuración:
  - Editar nombre, tipo (vehicular/peatonal) y siempre ámbar por cada grupo
- Transitorios guardados por plan en el JSON
- Cálculo automático del tiempo total de transitorio

## [1.3.0] - 2026-01-15

### Añadido
- **Tabla de transitorios** en `regulador_config.json`
  - Tiempos de ámbar y rojo de seguridad para grupos vehiculares
  - Tiempos de verde intermitente y rojo para grupos peatonales
  - Secuencia configurable de transitorios entre fases
- **Logs mejorados para cambio de modo** en GUI
  - Log cuando llega petición 0xB3 de la central
  - Log detallado: "CENTRAL SOLICITA: LOCAL → ORDENADOR"
  - Log cuando se reporta el cambio confirmado
- Estado de conexión "⏳ Esperando conexión..." (naranja) cuando servidor escucha
- ID automático de planes al crear uno nuevo (siguiente correlativo)

### Corregido
- Decodificación de códigos de protocolo con bit 7 activo
- Colores en indicadores de estado (verde/naranja/gris)

## [1.2.0] - 2026-01-15

### Añadido
- **Interfaz gráfica (GUI)** `regulador_gui.py` con tkinter
  - Control de inicio/parada del regulador
  - Monitor de estado en tiempo real (plan, fase, modo)
  - Log de comunicaciones con colores
  - Editor visual de configuración
  - Gestión de planes con horarios
  - Campo editable para grupos siempre en ámbar
- Selección automática de planes por horario en configuración JSON

### Cambiado
- Campo "Grupos siempre ámbar" ahora se guarda correctamente al JSON

## [1.1.0] - 2026-01-14

### Añadido
- **Estructura modular** del código
  - `modules/protocolo_une.py` - Constantes y funciones del protocolo
  - `modules/estado_regulador.py` - Gestión de estado del regulador
  - `modules/generador_respuestas.py` - Generación de respuestas UNE
- **Configuración externa** `config/regulador_config.json`
  - Planes con horarios configurables
  - Grupos con flag `siempre_ambar`
  - Subreguladores 128 (CPU) y 129 (Planes)
- `regulador_virtual.py` - Versión modular del regulador

### Cambiado
- Separación de lógica en módulos independientes
- Configuración movida de código a archivo JSON externo

## [1.0.0] - 2026-01-13

### Añadido
- **Modo A** (síncrono) con mensajes espontáneos 0xB9 y 0xB3
- **Codificación Bit 7** correcta: `(valor & 0x7F) | 0x80` para todos los bytes
- **Checksum corregido**: XOR de todos los bytes con bit 7 activado
- Soporte para **dual subregulador** (128 y 129)
- Planes 130, 131, 132, 133 (numeración real)
- Grupos G1 y G5 siempre en ámbar (según regulador real)
- Handler mejorado para código **0xB3** (cambio de modo) con confirmación

### Corregido
- Cálculo de checksum según comportamiento real capturado
- Decodificación de bytes en mensajes recibidos
- Envío de confirmación tras cambio de modo

## [0.3.0] - 2026-01-12

### Añadido
- **ProxySnifferUNE.py** - Proxy para capturar tráfico real
- Captura de **12.8 horas** de tráfico (46,044 segundos, 30,623 mensajes)
- Scripts de análisis de tráfico capturado
- Documentación del protocolo basada en tráfico real

### Descubierto
- Patrón de codificación bit 7 en regulador real
- Comportamiento de grupos G1/G5 siempre en ámbar
- Estructura de mensajes 0xB9 y 0xB3

## [0.2.0] - 2026-01-11

### Añadido
- Soporte para **Modo B** (asíncrono con keep-alive)
- Respuestas para todos los códigos principales:
  - 0x91 (Sincronización)
  - 0xB4 (Alarmas)
  - 0xB5 (Configuración)
  - 0xB6 (Tablas programación)
  - 0xB7 (Incompatibilidades)
  - 0x94 (Datos tráfico)
- `ReguladorVirtual_ModoB.py` - Primera versión funcional

## [0.1.0] - 2026-01-10

### Añadido
- Extracción del protocolo UNE 135401-4:2003 desde PDF
- Documentación inicial del protocolo
- Estructura básica del proyecto
- Scripts de prueba iniciales (`intento1` a `intento7`)

---

## Tipos de cambios

- **Añadido** para funcionalidades nuevas
- **Cambiado** para cambios en funcionalidades existentes
- **Obsoleto** para funcionalidades que serán eliminadas próximamente
- **Eliminado** para funcionalidades eliminadas
- **Corregido** para corrección de errores
- **Seguridad** para vulnerabilidades

## Versiones

- **Major (X.0.0)**: Cambios incompatibles con versiones anteriores
- **Minor (0.X.0)**: Nuevas funcionalidades compatibles
- **Patch (0.0.X)**: Correcciones de errores compatibles
