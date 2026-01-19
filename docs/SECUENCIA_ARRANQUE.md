# 🚦 Secuencia de Arranque del Regulador

## 📋 Descripción

Los reguladores reales tienen una **secuencia de seguridad** al encenderse que garantiza un arranque controlado y visible. Esta secuencia dura **12 segundos** en total antes de iniciar la operación normal.

---

## ⏱️ Fases de la Secuencia

### **Fase 1: Ámbar Intermitente** (5 segundos)
- **Grupos vehiculares (verticales)**: 🟡 Ámbar intermitente (código 6)
- **Grupos peatonales**: ⚫ Apagados (código 0)
- **Objetivo**: Advertir que el semáforo está iniciando

### **Fase 2: Ámbar Fijo** (4 segundos)
- **Grupos vehiculares (verticales)**: 🟡 Ámbar fijo (código 2)
- **Grupos peatonales**: ⚫ Apagados (código 0)
- **Objetivo**: Transición suave hacia el rojo

### **Fase 3: Todo Rojo** (3 segundos)
- **Todos los grupos**: 🔴 Rojo (código 3)
- **Objetivo**: Seguridad antes de iniciar el plan normal

### **Inicio del Plan Normal**
Después de completar la fase 3, el regulador inicia el plan configurado en modo normal.

---

## 💻 Implementación

### 1. **Estado del Regulador** ([estado_regulador.py](../modules/estado_regulador.py))

Se agregaron variables de control:

```python
self.en_secuencia_arranque = False
self.fase_arranque = 0  # 0=ninguna, 1=ámbar inter, 2=ámbar, 3=todo rojo
self.tiempo_fase_arranque = 0
self.arranque_completado = False
```

### 2. **Método `iniciar_secuencia_arranque()`**

Inicia la secuencia al conectarse la central:

```python
def iniciar_secuencia_arranque(self):
    """Inicia la secuencia de arranque del regulador"""
    self.en_secuencia_arranque = True
    self.fase_arranque = 1
    self.tiempo_fase_arranque = 0
    self._aplicar_fase_arranque()
```

### 3. **Método `_aplicar_fase_arranque()`**

Configura los estados de los grupos según la fase actual:

```python
def _aplicar_fase_arranque(self):
    if self.fase_arranque == 1:
        # Ámbar intermitente en vehiculares, apagado en peatonales
        for i in range(self.num_grupos):
            es_peatonal = self._es_grupo_peatonal(i+1)
            self.estado_grupos[i] = 0 if es_peatonal else 6
    
    elif self.fase_arranque == 2:
        # Ámbar fijo en vehiculares, apagado en peatonales
        for i in range(self.num_grupos):
            es_peatonal = self._es_grupo_peatonal(i+1)
            self.estado_grupos[i] = 0 if es_peatonal else 2
    
    elif self.fase_arranque == 3:
        # Todo rojo
        for i in range(self.num_grupos):
            self.estado_grupos[i] = 3
```

### 4. **Método `actualizar_arranque()`**

Se ejecuta cada segundo para avanzar en la secuencia:

```python
def actualizar_arranque(self):
    """Actualiza el estado de la secuencia de arranque"""
    self.tiempo_fase_arranque += 1
    
    # Fase 1: 5 segundos
    if self.fase_arranque == 1 and self.tiempo_fase_arranque >= 5:
        self.fase_arranque = 2
        self._aplicar_fase_arranque()
        return True
    
    # Fase 2: 4 segundos
    elif self.fase_arranque == 2 and self.tiempo_fase_arranque >= 4:
        self.fase_arranque = 3
        self._aplicar_fase_arranque()
        return True
    
    # Fase 3: 3 segundos - COMPLETAR
    elif self.fase_arranque == 3 and self.tiempo_fase_arranque >= 3:
        self.en_secuencia_arranque = False
        self.arranque_completado = True
        # Dejar que el ciclo normal tome control
        return False
```

### 5. **Integración en el Bucle Principal** ([regulador_gui.py](../regulador_gui.py))

Al conectarse la central:

```python
# Conexión establecida
self.client_socket, addr = self.server_socket.accept()

# INICIAR SECUENCIA DE ARRANQUE
self.estado.iniciar_secuencia_arranque()
```

En el bucle de actualización cada segundo:

```python
if ahora - ultimo_ciclo >= 1:
    # Si estamos en secuencia de arranque, procesarla primero
    if self.estado.en_secuencia_arranque:
        cambio_arranque = self.estado.actualizar_arranque()
        if cambio_arranque:
            # Actualizar y enviar estados
            estados = self.estado.get_estado_grupos()
            self.message_queue.put(('semaforos', estados))
            msg = self.GeneradorRespuestas.mensaje_estado_grupos(
                self.estado, self.sub_cpu)
            self.enviar_mensaje(msg)
        continue  # No procesar ciclo normal durante arranque
    
    # Ciclo normal solo después del arranque
    cambio = self.estado.actualizar_ciclo()
```

---

## 🎨 Códigos de Color UNE

| Código | Color | Uso en Arranque |
|--------|-------|----------------|
| 0 | Apagado | Peatonales F1 y F2 |
| 2 | Ámbar | Vehiculares F2 |
| 3 | Rojo | Todos F3 |
| 6 | Ámbar Intermitente | Vehiculares F1 |

---

## 🔍 Identificación de Grupos

La configuración diferencia grupos vehiculares y peatonales mediante el campo `tipo`:

```json
"grupos": {
    "descripcion": [
        {
            "id": 1,
            "nombre": "Grupo 1 - Vehículos Principal",
            "tipo": "vehicular"  ← Muestra ámbar en F1 y F2
        },
        {
            "id": 4,
            "nombre": "Grupo 4 - Peatones",
            "tipo": "peatonal"  ← Se apaga en F1 y F2
        }
    ]
}
```

---

## 📊 Timeline de la Secuencia

```
t=0s   ┌─────────────────────────────┐
       │ Conexión establecida        │
       └─────────────────────────────┘
              ↓
t=0s   ┌─────────────────────────────┐
       │ FASE 1: Ámbar Intermitente  │
       │ Vehiculares: 🟡 (parpadeo)  │
       │ Peatonales:  ⚫             │
       └─────────────────────────────┘
              ↓ (5 segundos)
t=5s   ┌─────────────────────────────┐
       │ FASE 2: Ámbar Fijo          │
       │ Vehiculares: 🟡             │
       │ Peatonales:  ⚫             │
       └─────────────────────────────┘
              ↓ (4 segundos)
t=9s   ┌─────────────────────────────┐
       │ FASE 3: Todo Rojo           │
       │ Todos:       🔴             │
       └─────────────────────────────┘
              ↓ (3 segundos)
t=12s  ┌─────────────────────────────┐
       │ OPERACIÓN NORMAL            │
       │ Ejecutando plan configurado │
       └─────────────────────────────┘
```

---

## ✅ Validación

Para verificar que funciona:

1. **Inicia el regulador virtual**
2. **Conecta la central** (o una herramienta de prueba)
3. **Observa los logs:**

```
🚦 INICIANDO SECUENCIA DE ARRANQUE DEL REGULADOR
  Fase 1 (5s): Grupos verticales Ámbar intermitente, peatonales Apagados
  Fase 2 (4s): Grupos verticales Ámbar, peatonales Apagados
  Fase 3 (3s): Todos los grupos en Rojo

🔶 ARRANQUE FASE 1: Ámbar intermitente en grupos verticales
✅ Fase 1 completada (5s)

🟡 ARRANQUE FASE 2: Ámbar en grupos verticales
✅ Fase 2 completada (4s)

🔴 ARRANQUE FASE 3: Todos los grupos en Rojo
✅ Fase 3 completada (3s)

🎉 SECUENCIA DE ARRANQUE COMPLETADA
   Iniciando operación normal con Plan 130
```

4. **Verifica en la GUI** que los semáforos muestren la secuencia correcta
5. **Después de 12 segundos** debe iniciar el plan normal

---

## 📝 Notas Importantes

1. **Solo se ejecuta al conectarse**: La secuencia solo ocurre cuando la central se conecta por primera vez, no en cada cambio de plan.

2. **No interrumpible**: Durante los 12 segundos de arranque, el regulador no procesa cambios de plan ni modos.

3. **Sincronización con central**: La central recibirá mensajes de estado de grupos mostrando la secuencia en tiempo real.

4. **Modo inicial**: El regulador inicia en el modo configurado en `estado_inicial.modo_control` (normalmente LOCAL=1).

5. **Plan inicial**: Usa el plan definido en `planes.plan_activo` o selecciona según horario si `seleccion_automatica=true`.

---

## 🔄 Flujo Completo al Iniciar

```
1. Regulador inicia y carga configuración
   ├─ Modo: estado_inicial.modo_control (1=LOCAL)
   ├─ Plan: planes.plan_activo o según horario
   └─ Estado: Esperando conexión

2. Central se conecta
   └─ Inicia secuencia de arranque (12s)

3. Fase 1 (5s): Ámbar intermitente
   └─ Envía estados cada segundo a la central

4. Fase 2 (4s): Ámbar fijo
   └─ Envía estados cada segundo a la central

5. Fase 3 (3s): Todo rojo
   └─ Envía estados cada segundo a la central

6. Operación normal
   ├─ Ejecuta plan según estructura
   ├─ Responde a comandos de la central
   └─ Modo puede cambiar según 0xD4
```

---

## 🛠️ Archivos Modificados

1. **[modules/estado_regulador.py](../modules/estado_regulador.py)**
   - Variables de secuencia de arranque
   - Métodos: `iniciar_secuencia_arranque()`, `_aplicar_fase_arranque()`, `actualizar_arranque()`

2. **[regulador_gui.py](../regulador_gui.py)**
   - Llamada a `iniciar_secuencia_arranque()` al conectarse
   - Procesamiento en bucle principal

3. **[config/regulador_config.json](../config/regulador_config.json)**
   - Corrección de tipo de grupo 4 de "vehicular" a "peatonal"
   - Comentario explicativo sobre tipos de grupos
