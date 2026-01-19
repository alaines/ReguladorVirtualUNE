# Regulador Virtual UNE 135401-4

Simulador de regulador de tráfico compatible con el protocolo UNE 135401-4 (Modo A/B).

**Versión actual: 1.11.0** | [Ver cambios](CHANGELOG.md)

## 📁 Estructura del Proyecto

```
probrarReguladorUNE/
├── regulador_gui.py          # 🎯 ARCHIVO PRINCIPAL - GUI del regulador
├── modules/                   # Módulos del sistema
│   ├── estado_regulador.py   # Estado y lógica del regulador
│   ├── generador_respuestas.py # Generación de mensajes UNE
│   └── protocolo_une.py      # Constantes y funciones del protocolo
├── config/                    # Configuración
│   └── regulador_config.json # Configuración del regulador (planes, grupos, etc.)
├── docs/                      # Documentación
│   └── UNE_extraido.txt      # Extracto de la norma UNE 135401-4
├── logs/                      # Logs de ejecución
├── tools/                     # Herramientas auxiliares
│   ├── ProxySnifferUNE.py    # Sniffer de tráfico UNE
│   ├── analizar_b9.py        # Analizador de mensajes B9
│   └── analizar_log.py       # Analizador de logs
├── tests/                     # Tests
│   └── test_plan.py
└── legacy/                    # Código obsoleto (no usar)
```

## 🚀 Uso

### Ejecutar el Regulador (GUI)
```bash
python regulador_gui.py
```

### Herramientas
```bash
# Sniffer para capturar tráfico entre central y regulador real
python tools/ProxySnifferUNE.py
```

## ⚙️ Configuración

Editar `config/regulador_config.json` para:
- Cambiar planes de regulación
- Configurar grupos de semáforos
- Establecer horarios
- Configurar modo de control (LOCAL/ORDENADOR/MANUAL)

### Modos de Control
- **modo_control: 1** = LOCAL (planes por horario interno)
- **modo_control: 2** = ORDENADOR/CENTRALIZADO (planes por central)
- **modo_control: 3** = MANUAL

## 📡 Protocolo UNE 135401-4

### Códigos principales
| Código | Dirección | Descripción |
|--------|-----------|-------------|
| 0x91   | C→R / R→C | Sincronización (Plan en curso) |
| 0x94   | C→R / R→C | Datos de tráfico |
| 0xB3   | R→C       | Modo de control (respuesta a 0x20) |
| 0xB4   | C→R / R→C | Alarmas |
| 0xB5   | C→R / R→C | Parámetros de configuración |
| 0xB6   | C→R / R→C | Tablas de programación |
| 0xB7   | C→R / R→C | Incompatibilidades |
| 0xB9   | R→C       | Estado de grupos |
| 0xD1   | C→R / R→C | Selección de plan |
| 0xD2   | C→R / R→C | Puesta en hora |
| 0xD4   | C→R / R→C | Estados (modo, coordinación) |
| 0x20   | C→R       | Petición de estado |

### Subreguladores
- **128 (0x80)**: CPU - Alarmas, configuración, grupos, modo (B3, B4, B9, D2)
- **129 (0x81)**: Planes - Sincronización, tráfico, selección (91, 94, D1, D4)

### Conversión de IDs de Plan
La central usa IDs 3, 4, 5... mientras el regulador usa 131, 132, 133...
- **Recepción (D1)**: plan_central + 128 = plan_interno
- **Reporte (0x91)**: plan_interno - 128 = plan_para_central

### Formato de mensajes
```
STX(02) + Subregulador + Código + [Datos...] + Checksum + ETX(03)
```

Todos los bytes de datos tienen el bit 7 activo (valor | 0x80).

## 📋 Cambios Recientes

Ver [CHANGELOG.md](CHANGELOG.md) para historial de cambios.
