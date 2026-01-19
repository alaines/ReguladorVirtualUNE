# 🚦 Regulador Virtual UNE & Central Virtual

Suite de herramientas para simulación y gestión de reguladores de tráfico compatibles con el protocolo **UNE 135401-4** (Modo A/B).

**Versión Regulador: 1.11.0** | **Versión Central: 1.0.0** | [Ver cambios](CHANGELOG.md)

---

## 📁 Estructura del Proyecto

```
ReguladorVirtualUNE/
│
├── regulador/                    # 🚦 Regulador Virtual
│   ├── regulador_gui.py         # GUI principal del regulador
│   ├── modules/
│   │   ├── estado_regulador.py
│   │   ├── generador_respuestas.py
│   │   └── protocolo_une.py
│   ├── config/
│   │   └── regulador_config.json
│   └── logs/
│
├── central/                      # 🖥️ Central Virtual
│   ├── central_gui.py           # GUI principal de la central
│   ├── modules/
│   │   ├── conexion_manager.py   # Gestión TCP/Serial
│   │   ├── protocolo_central.py  # Comandos UNE
│   │   ├── decodificador.py      # Parseo de respuestas
│   │   └── estado_reguladores.py # Estado de reguladores
│   ├── config/
│   │   └── central_config.json
│   └── logs/
│
├── docs/                         # 📚 Documentación compartida
│   ├── PROTOCOLO_UNE_REFERENCIA.md
│   └── RESUMEN_PROTOCOLO_UNE_135401-4.md
│
├── tools/                        # 🔧 Herramientas
│   ├── ProxySnifferUNE.py       # Sniffer de tráfico
│   └── analizar_*.py            # Analizadores
│
├── README.md
└── CHANGELOG.md
```

---

## 🚀 Uso

### Ejecutar el Regulador Virtual
```bash
cd regulador
python regulador_gui.py
```

### Ejecutar la Central Virtual
```bash
cd central
python central_gui.py
```

### Probar ambos juntos
1. Iniciar el **Regulador Virtual** (puerto TCP 5000 por defecto)
2. Iniciar la **Central Virtual**
3. Agregar un regulador con IP `127.0.0.1` puerto `5000`
4. Conectar y probar comandos

---

## 🚦 Regulador Virtual

Simula un regulador de tráfico semafórico compatible con centrales UNE.

### Características
- Protocolo UNE 135401-4 Modo A y B
- Interfaz gráfica con visualización de semáforos
- Configuración de planes, fases y grupos
- Conexión TCP/IP y Serial RS-232
- Mensajes espontáneos (B9, B3)
- Modos: LOCAL, CENTRALIZADO, MANUAL, INTERMITENTE

### Configuración
Editar `regulador/config/regulador_config.json`:
- Planes de regulación (hasta 32)
- Grupos de semáforos (hasta 16)
- Fases y tiempos
- Puerto TCP/COM

---

## 🖥️ Central Virtual

Gestiona múltiples reguladores de tráfico simultáneamente.

### Características
- Hasta 48 reguladores por central
- Conexión TCP/IP y Serial RS-232
- Polling automático configurable
- Comandos individuales y en bloque
- Visualización de estado en tiempo real
- Log de comunicaciones

### Comandos disponibles
| Comando | Código | Descripción |
|---------|--------|-------------|
| Sincronización | 0x91 | Consulta plan, hora, ciclo |
| Cambio de Plan | 0xD1 | Selecciona plan de regulación |
| Puesta en Hora | 0xD2 | Sincroniza reloj |
| Estados | 0xD4 | Cambia modo (colores/intermitente/apagado) |
| Alarmas | 0xB4 | Consulta alarmas |
| Borrar Alarmas | 0xDD | Limpia alarmas |

### Comandos en bloque
- Cambiar plan a todos los reguladores
- Poner todos en intermitente
- Apagar todos
- Sincronizar hora global

---

## 📡 Protocolo UNE 135401-4

### Modos de operación
- **Modo A**: Síncrono - Regulador responde solo a peticiones
- **Modo B**: Asíncrono - Regulador envía mensajes espontáneos

### Subreguladores
| ID | Hex | Responsabilidad |
|----|-----|-----------------|
| 128 | 0x80 | CPU: Alarmas, configuración, grupos, modo |
| 129 | 0x81 | Planes: Sincronización, tráfico, selección |

### Estructura de mensajes
```
[STX 0x02] [SUBREG] [CÓDIGO] [DATOS...] [CHECKSUM] [ETX 0x03]
```

### Códigos principales
| Código | Dirección | Descripción |
|--------|-----------|-------------|
| 0x91 | C↔R | Sincronización |
| 0x94 | C↔R | Datos de tráfico |
| 0xB3 | R→C | Modo de control (espontáneo) |
| 0xB4 | C↔R | Alarmas |
| 0xB9 | R→C | Estado de grupos (espontáneo) |
| 0xD1 | C→R | Selección de plan |
| 0xD2 | C→R | Puesta en hora |
| 0xD4 | C→R | Estados (intermitente/colores/apagado) |

---

## 🔧 Herramientas

### Sniffer UNE
Captura y analiza tráfico entre central y regulador real:
```bash
python tools/ProxySnifferUNE.py
```

---

## 📋 Requisitos

- Python 3.8+
- tkinter (incluido en Python)
- pyserial (opcional, para conexión serial): `pip install pyserial`

---

## 📄 Licencia

Este proyecto es software libre para uso educativo y de desarrollo.

---

## 🔗 Enlaces

- [Changelog](CHANGELOG.md)
- [Documentación del protocolo](docs/RESUMEN_PROTOCOLO_UNE_135401-4.md)
