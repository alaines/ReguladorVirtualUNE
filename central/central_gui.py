#!/usr/bin/env python3
"""
CENTRAL VIRTUAL UNE 135401-4
Interfaz gráfica para gestión de múltiples reguladores de tráfico
Versión 1.5.3

Cambios v1.5.3:
- Soporte para ACK/NACK de un solo byte (0x06/0x15)
- Receptor de conexión ahora procesa ACKs correctamente
- Decodificador maneja mensajes ACK de 1 byte
- Subregulador 129 para sincronización/tráfico (compatible con regulador real)

Cambios v1.5.2:
- Mostrar "--" en plan, ciclo, fase, hora cuando no hay datos del regulador
- Log de depuración en _actualizar_estado_visual
- Log de TX/RX también al archivo de log

Cambios v1.5.1:
- Log de comunicación más detallado (muestra Raw hex y todos los datos decodificados)
- Agregado logging de depuración en procesamiento de respuestas

Cambios v1.5.0:
- Corregido decodificador de sincronización (0x91): orden correcto de bytes
- Corregido decodificador de grupos (0xB9): ahora procesa 1 byte/grupo en lugar de 2 bits/grupo
- Corregido decodificador de tráfico (0x94): ya no espera grupos (vienen en 0xB9)
- Mejorado _enviar_comando: ahora procesa TODOS los mensajes en cola (incluye B9 espontáneos)
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import sys
import threading
import queue
import time
from datetime import datetime
import logging

# Configuración de logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(log_dir, f'central_{timestamp}.log')

# Logger principal
logger = logging.getLogger('Central')
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Agregar directorio al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import (
    ProtocoloCentral,
    ConexionManager, ConexionTCP, ConexionSerial,
    EstadoRegulador, GestorReguladores, EstadoConexion, EstadoRepresentacion, ModoControl,
    DecodificadorUNE
)


# ============================================================================
# CONSTANTES DE ESTILO
# ============================================================================
COLORES = {
    'fondo': '#1a1a2e',
    'panel': '#16213e',
    'panel_claro': '#1f3460',
    'texto': '#e8e8e8',
    'texto_dim': '#888888',
    'acento': '#0f4c75',
    'acento_hover': '#3282b8',
    'exito': '#00a86b',
    'error': '#e74c3c',
    'advertencia': '#f39c12',
    'borde': '#2d4263',
    'seleccion': '#3282b8',
    
    # Colores de semáforo
    'rojo': '#ff0000',
    'verde': '#00ff00',
    'ambar': '#ffaa00',
    'apagado': '#333333'
}

ESTILOS_GRUPOS = {
    0: ('#333333', '⚫'),  # Apagado
    1: ('#00ff00', '🟢'),  # Verde
    2: ('#ffaa00', '🟡'),  # Ámbar
    3: ('#ff0000', '🔴'),  # Rojo
    4: ('#ff0000', '🔴'),  # Rojo Int.
    5: ('#00ff00', '🟢'),  # Verde Int.
    6: ('#ffaa00', '🟡'),  # Ámbar Int.
}


class CentralGUI:
    """Interfaz gráfica principal de la Central"""
    
    VERSION = "1.5.6"
    
    def __init__(self, root):
        self.root = root
        self.root.title(f"🚦 Central Virtual UNE v{self.VERSION}")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Configuración de rutas
        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'config', 'central_config.json'
        )
        
        # Componentes principales
        self.protocolo = ProtocoloCentral()
        self.decodificador = DecodificadorUNE()
        self.conexiones = ConexionManager()
        self.gestor_reguladores = GestorReguladores()
        
        # Estado
        self.regulador_seleccionado = None
        self.polling_activo = False
        self.polling_threads = {}
        self.log_queue = queue.Queue()
        
        # Lock por regulador para serializar comandos (evita race conditions)
        self._reg_locks = {}  # {reg_id: threading.Lock()}
        self._reg_locks_lock = threading.Lock()  # Lock para acceder al diccionario de locks
        
        # Cargar configuración
        self.config = self._cargar_config()
        self._cargar_reguladores()
        
        # Crear interfaz
        self._configurar_estilos()
        self._crear_widgets()
        
        # Iniciar procesamiento de logs
        self._procesar_logs()
        
        # Iniciar reloj del sistema
        self._actualizar_reloj_sistema()
        
        # Cerrar correctamente
        self.root.protocol("WM_DELETE_WINDOW", self._on_cerrar)
        
        logger.info(f"Central Virtual UNE v{self.VERSION} iniciada")
        self._log("Sistema iniciado", "INFO")
    
    def _cargar_config(self) -> dict:
        """Carga la configuración desde archivo"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("Archivo de configuración no encontrado, usando valores por defecto")
            return {
                "central": {"nombre": "Central Virtual UNE", "max_reguladores": 48},
                "polling": {"intervalo_base_ms": 5000},
                "reguladores": [],
                "gui": {"tema": "oscuro", "log_max_lines": 500}
            }
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            return {}
    
    def _guardar_config(self):
        """Guarda la configuración a archivo"""
        try:
            self.config['reguladores'] = self.gestor_reguladores.guardar_a_config()
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("Configuración guardada")
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
    
    def _cargar_reguladores(self):
        """Carga los reguladores desde la configuración"""
        reguladores_config = self.config.get('reguladores', [])
        self.gestor_reguladores.cargar_desde_config(reguladores_config)
    
    def _configurar_estilos(self):
        """Configura los estilos de la interfaz"""
        self.root.configure(bg=COLORES['fondo'])
        
        style = ttk.Style()
        style.theme_use('clam')
        
        # Frame
        style.configure('Dark.TFrame', background=COLORES['fondo'])
        style.configure('Panel.TFrame', background=COLORES['panel'])
        style.configure('PanelClaro.TFrame', background=COLORES['panel_claro'])
        
        # Labels
        style.configure('Dark.TLabel', 
                        background=COLORES['fondo'], 
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 10))
        style.configure('Panel.TLabel', 
                        background=COLORES['panel'], 
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 10))
        style.configure('Titulo.TLabel',
                        background=COLORES['panel'],
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 12, 'bold'))
        style.configure('Grande.TLabel',
                        background=COLORES['panel'],
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 14, 'bold'))
        
        # Buttons
        style.configure('Acento.TButton',
                        background=COLORES['acento'],
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 10),
                        padding=(10, 5))
        style.map('Acento.TButton',
                  background=[('active', COLORES['acento_hover'])])
        
        # Entry
        style.configure('Dark.TEntry',
                        fieldbackground=COLORES['panel_claro'],
                        foreground=COLORES['texto'],
                        insertcolor=COLORES['texto'])
        
        # Combobox
        style.configure('Dark.TCombobox',
                        fieldbackground=COLORES['panel_claro'],
                        background=COLORES['panel'],
                        foreground=COLORES['texto'])
        
        # Radiobutton
        style.configure('Dark.TRadiobutton',
                        background=COLORES['panel'],
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 10))
        
        # Checkbutton
        style.configure('Dark.TCheckbutton',
                        background=COLORES['panel'],
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 10))
        
        # LabelFrame
        style.configure('Dark.TLabelframe',
                        background=COLORES['panel'],
                        foreground=COLORES['texto'])
        style.configure('Dark.TLabelframe.Label',
                        background=COLORES['panel'],
                        foreground=COLORES['texto'],
                        font=('Segoe UI', 10, 'bold'))
    
    def _crear_widgets(self):
        """Crea todos los widgets de la interfaz"""
        # Barra de menú
        self._crear_menu()
        
        # Frame principal
        self.main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        self.main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Panel izquierdo - Lista de reguladores
        self._crear_panel_reguladores()
        
        # Panel derecho - Detalle y controles (con scroll)
        self._crear_panel_detalle()
        
        # Ventana de log (inicialmente oculta)
        self.log_window = None
        self._crear_panel_log_interno()
    
    def _crear_menu(self):
        """Crea la barra de menú"""
        menubar = tk.Menu(self.root, bg=COLORES['panel'], fg=COLORES['texto'])
        self.root.config(menu=menubar)
        
        # Menú Ver
        menu_ver = tk.Menu(menubar, tearoff=0, bg=COLORES['panel'], fg=COLORES['texto'])
        menubar.add_cascade(label="Ver", menu=menu_ver)
        menu_ver.add_command(label="Ventana de Log", command=self._mostrar_ventana_log)
        menu_ver.add_command(label="Cargar Planes...", command=self._cargar_planes_archivo)
        menu_ver.add_separator()
        menu_ver.add_command(label="Cargar Config Regulador Virtual", command=self._cargar_config_regulador)
        
        # Menú Conexión
        menu_conexion = tk.Menu(menubar, tearoff=0, bg=COLORES['panel'], fg=COLORES['texto'])
        menubar.add_cascade(label="Conexión", menu=menu_conexion)
        menu_conexion.add_command(label="Conectar Seleccionado", command=self._conectar_regulador)
        menu_conexion.add_command(label="Desconectar Seleccionado", command=self._desconectar_regulador)
        menu_conexion.add_separator()
        menu_conexion.add_command(label="Conectar Todos", command=self._conectar_todos)
        menu_conexion.add_command(label="Desconectar Todos", command=self._desconectar_todos)
        
        # Menú Ayuda
        menu_ayuda = tk.Menu(menubar, tearoff=0, bg=COLORES['panel'], fg=COLORES['texto'])
        menubar.add_cascade(label="Ayuda", menu=menu_ayuda)
        menu_ayuda.add_command(label="Acerca de", command=self._mostrar_acerca_de)
    
    def _mostrar_ventana_log(self):
        """Muestra la ventana de log en una ventana separada"""
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus_force()
            return
        
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("Log de Comunicaciones - Central Virtual UNE")
        self.log_window.geometry("900x500")
        self.log_window.configure(bg=COLORES['fondo'])
        
        # Frame principal
        log_frame = ttk.Frame(self.log_window, style='Panel.TFrame')
        log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Barra de herramientas
        toolbar = ttk.Frame(log_frame, style='Panel.TFrame')
        toolbar.pack(fill='x', padx=5, pady=5)
        
        self.var_auto_scroll_ext = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Auto-scroll", variable=self.var_auto_scroll_ext,
                        style='Dark.TCheckbutton').pack(side='left', padx=5)
        
        tk.Button(toolbar, text="Limpiar Log",
                  bg=COLORES['panel_claro'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._limpiar_log_externo).pack(side='left', padx=5)
        
        tk.Button(toolbar, text="Guardar Log",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._guardar_log).pack(side='left', padx=5)
        
        # Filtros
        ttk.Label(toolbar, text="  Filtro:", style='Panel.TLabel').pack(side='left', padx=5)
        self.var_filtro_log = tk.StringVar(value='Todos')
        filtro_combo = ttk.Combobox(toolbar, textvariable=self.var_filtro_log, 
                                     values=['Todos', 'TX', 'RX', 'INFO', 'ERROR'],
                                     width=10, state='readonly')
        filtro_combo.pack(side='left', padx=5)
        
        # Text widget para log extendido
        self.log_text_ext = scrolledtext.ScrolledText(
            log_frame,
            bg=COLORES['panel_claro'],
            fg=COLORES['texto'],
            font=('Consolas', 10),
            state='disabled',
            relief='flat',
            wrap='word'
        )
        self.log_text_ext.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Configurar tags
        self.log_text_ext.tag_configure('INFO', foreground=COLORES['texto'])
        self.log_text_ext.tag_configure('ERROR', foreground=COLORES['error'])
        self.log_text_ext.tag_configure('WARNING', foreground=COLORES['advertencia'])
        self.log_text_ext.tag_configure('TX', foreground='#3282b8')
        self.log_text_ext.tag_configure('RX', foreground='#00a86b')
        self.log_text_ext.tag_configure('HEX', foreground='#888888')
        
        # Barra de estado
        status_frame = ttk.Frame(log_frame, style='Panel.TFrame')
        status_frame.pack(fill='x', padx=5, pady=2)
        
        self.lbl_log_status = ttk.Label(status_frame, text="Líneas: 0", style='Panel.TLabel')
        self.lbl_log_status.pack(side='left')
    
    def _limpiar_log_externo(self):
        """Limpia el log de la ventana externa"""
        if hasattr(self, 'log_text_ext') and self.log_text_ext.winfo_exists():
            self.log_text_ext.config(state='normal')
            self.log_text_ext.delete(1.0, tk.END)
            self.log_text_ext.config(state='disabled')
    
    def _guardar_log(self):
        """Guarda el log a un archivo"""
        from tkinter import filedialog
        from datetime import datetime
        
        archivo = filedialog.asksaveasfilename(
            title="Guardar Log",
            filetypes=[("Text files", "*.txt"), ("Log files", "*.log")],
            defaultextension=".txt",
            initialfile=f"central_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if archivo:
            try:
                with open(archivo, 'w', encoding='utf-8') as f:
                    if hasattr(self, 'log_text_ext'):
                        f.write(self.log_text_ext.get(1.0, tk.END))
                    else:
                        f.write(self.log_text.get(1.0, tk.END))
                self._log(f"Log guardado en {archivo}", "INFO")
            except Exception as e:
                messagebox.showerror("Error", f"Error guardando log: {e}")
    
    def _mostrar_acerca_de(self):
        """Muestra información de la aplicación"""
        messagebox.showinfo("Acerca de", 
            f"Central Virtual UNE v{self.VERSION}\n\n"
            "Gestión de reguladores de tráfico\n"
            "Protocolo UNE 135401-4\n\n"
            "Autor: Aland Laines Calonge\n"
            "Email: alaines@movingenia.com\n"
            "Web: https://movingenia.com")

    def _crear_panel_reguladores(self):
        """Crea el panel izquierdo con lista de reguladores"""
        self.panel_izq = ttk.Frame(self.main_frame, style='Panel.TFrame', width=280)
        self.panel_izq.pack(side='left', fill='y', padx=(0, 5))
        self.panel_izq.pack_propagate(False)
        
        # Título
        titulo_frame = ttk.Frame(self.panel_izq, style='Panel.TFrame')
        titulo_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(titulo_frame, text="REGULADORES", style='Titulo.TLabel').pack(side='left')
        
        # Botones de agregar/quitar
        btn_frame = ttk.Frame(titulo_frame, style='Panel.TFrame')
        btn_frame.pack(side='right')
        
        self.btn_agregar = tk.Button(btn_frame, text="➕", 
                                     bg=COLORES['acento'], fg=COLORES['texto'],
                                     font=('Segoe UI', 10), width=3, relief='flat',
                                     command=self._agregar_regulador)
        self.btn_agregar.pack(side='left', padx=2)
        
        self.btn_eliminar = tk.Button(btn_frame, text="➖",
                                      bg=COLORES['error'], fg=COLORES['texto'],
                                      font=('Segoe UI', 10), width=3, relief='flat',
                                      command=self._eliminar_regulador)
        self.btn_eliminar.pack(side='left', padx=2)
        
        # Lista de reguladores (usando Listbox con estilo personalizado)
        lista_frame = ttk.Frame(self.panel_izq, style='Panel.TFrame')
        lista_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.lista_reguladores = tk.Listbox(
            lista_frame,
            bg=COLORES['panel_claro'],
            fg=COLORES['texto'],
            selectbackground=COLORES['seleccion'],
            selectforeground=COLORES['texto'],
            font=('Consolas', 10),
            relief='flat',
            highlightthickness=1,
            highlightbackground=COLORES['borde'],
            activestyle='none'
        )
        self.lista_reguladores.pack(fill='both', expand=True)
        self.lista_reguladores.bind('<<ListboxSelect>>', self._on_seleccionar_regulador)
        
        # Botones de conexión global
        btn_global_frame = ttk.Frame(self.panel_izq, style='Panel.TFrame')
        btn_global_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Button(btn_global_frame, text="Conectar Todos",
                  bg=COLORES['exito'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._conectar_todos).pack(fill='x', pady=2)
        
        tk.Button(btn_global_frame, text="Desconectar Todos",
                  bg=COLORES['error'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._desconectar_todos).pack(fill='x', pady=2)
        
        # Actualizar lista
        self._actualizar_lista_reguladores()
    
    def _crear_panel_detalle(self):
        """Crea el panel derecho con detalle del regulador seleccionado (con scroll)"""
        self.panel_der = ttk.Frame(self.main_frame, style='Panel.TFrame')
        self.panel_der.pack(side='left', fill='both', expand=True)
        
        # Título del regulador (fijo, fuera del scroll)
        self.titulo_regulador = ttk.Label(
            self.panel_der, 
            text="Seleccione un regulador",
            style='Grande.TLabel'
        )
        self.titulo_regulador.pack(fill='x', padx=10, pady=10)
        
        # Canvas con scrollbar para el contenido
        canvas_frame = ttk.Frame(self.panel_der, style='Panel.TFrame')
        canvas_frame.pack(fill='both', expand=True)
        
        self.canvas_detalle = tk.Canvas(canvas_frame, bg=COLORES['panel'], 
                                         highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical', 
                                   command=self.canvas_detalle.yview)
        
        self.canvas_detalle.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        self.canvas_detalle.configure(yscrollcommand=scrollbar.set)
        
        # Frame interno para contenido
        content_frame = ttk.Frame(self.canvas_detalle, style='Panel.TFrame')
        self.canvas_window = self.canvas_detalle.create_window((0, 0), window=content_frame, 
                                                                anchor='nw')
        
        # Configurar scroll
        def configure_scroll(event):
            self.canvas_detalle.configure(scrollregion=self.canvas_detalle.bbox('all'))
            # Ajustar ancho del frame interno al canvas
            self.canvas_detalle.itemconfig(self.canvas_window, width=event.width)
        
        content_frame.bind('<Configure>', lambda e: self.canvas_detalle.configure(
            scrollregion=self.canvas_detalle.bbox('all')))
        self.canvas_detalle.bind('<Configure>', configure_scroll)
        
        # Scroll con rueda del mouse
        def on_mousewheel(event):
            self.canvas_detalle.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.canvas_detalle.bind_all("<MouseWheel>", on_mousewheel)
        
        # Panel de configuración
        self._crear_panel_config(content_frame)
        
        # Panel de estado en tiempo real
        self._crear_panel_estado(content_frame)
        
        # Panel de planes y fases
        self._crear_panel_planes(content_frame)
        
        # Panel de comandos
        self._crear_panel_comandos(content_frame)
    
    def _crear_panel_config(self, parent):
        """Crea el panel de configuración del regulador"""
        config_frame = ttk.LabelFrame(parent, text="⚙️ CONFIGURACIÓN", style='Dark.TLabelframe')
        config_frame.pack(fill='x', pady=5)
        
        # Grid de configuración
        grid_frame = ttk.Frame(config_frame, style='Panel.TFrame')
        grid_frame.pack(fill='x', padx=10, pady=10)
        
        # Nombre
        ttk.Label(grid_frame, text="Nombre:", style='Panel.TLabel').grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.entry_nombre = ttk.Entry(grid_frame, style='Dark.TEntry', width=30)
        self.entry_nombre.grid(row=0, column=1, columnspan=3, sticky='w', padx=5, pady=3)
        
        # Tipo de conexión
        ttk.Label(grid_frame, text="Conexión:", style='Panel.TLabel').grid(row=1, column=0, sticky='e', padx=5, pady=3)
        
        self.var_tipo_conexion = tk.StringVar(value='tcp')
        ttk.Radiobutton(grid_frame, text="TCP/IP", variable=self.var_tipo_conexion, 
                        value='tcp', style='Dark.TRadiobutton',
                        command=self._on_cambio_tipo_conexion).grid(row=1, column=1, sticky='w')
        ttk.Radiobutton(grid_frame, text="Serial", variable=self.var_tipo_conexion,
                        value='serial', style='Dark.TRadiobutton',
                        command=self._on_cambio_tipo_conexion).grid(row=1, column=2, sticky='w')
        
        # IP y Puerto (TCP)
        self.frame_tcp = ttk.Frame(grid_frame, style='Panel.TFrame')
        self.frame_tcp.grid(row=2, column=0, columnspan=4, sticky='w', pady=3)
        
        ttk.Label(self.frame_tcp, text="IP:", style='Panel.TLabel').pack(side='left', padx=5)
        self.entry_ip = ttk.Entry(self.frame_tcp, style='Dark.TEntry', width=15)
        self.entry_ip.pack(side='left', padx=5)
        
        ttk.Label(self.frame_tcp, text="Puerto:", style='Panel.TLabel').pack(side='left', padx=5)
        self.entry_puerto = ttk.Entry(self.frame_tcp, style='Dark.TEntry', width=8)
        self.entry_puerto.pack(side='left', padx=5)
        
        # COM y Baudrate (Serial)
        self.frame_serial = ttk.Frame(grid_frame, style='Panel.TFrame')
        self.frame_serial.grid(row=3, column=0, columnspan=4, sticky='w', pady=3)
        
        ttk.Label(self.frame_serial, text="Puerto COM:", style='Panel.TLabel').pack(side='left', padx=5)
        self.combo_com = ttk.Combobox(self.frame_serial, style='Dark.TCombobox', width=10,
                                       values=['COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8'])
        self.combo_com.pack(side='left', padx=5)
        
        ttk.Label(self.frame_serial, text="Baudrate:", style='Panel.TLabel').pack(side='left', padx=5)
        self.combo_baud = ttk.Combobox(self.frame_serial, style='Dark.TCombobox', width=8,
                                        values=['9600', '19200', '38400', '57600', '115200'])
        self.combo_baud.pack(side='left', padx=5)
        self.combo_baud.set('9600')
        
        # Modo
        ttk.Label(grid_frame, text="Modo:", style='Panel.TLabel').grid(row=4, column=0, sticky='e', padx=5, pady=3)
        self.combo_modo = ttk.Combobox(grid_frame, style='Dark.TCombobox', width=20,
                                        values=['Modo A (Síncrono)', 'Modo B (Asíncrono)'])
        self.combo_modo.grid(row=4, column=1, columnspan=2, sticky='w', padx=5, pady=3)
        self.combo_modo.set('Modo A (Síncrono)')
        
        # Número de grupos
        ttk.Label(grid_frame, text="Grupos:", style='Panel.TLabel').grid(row=5, column=0, sticky='e', padx=5, pady=3)
        self.combo_num_grupos = ttk.Combobox(grid_frame, style='Dark.TCombobox', width=5,
                                          values=[str(i) for i in range(1, 17)])
        self.combo_num_grupos.grid(row=5, column=1, sticky='w', padx=5, pady=3)
        self.combo_num_grupos.set('4')
        self.combo_num_grupos.bind('<<ComboboxSelected>>', self._on_cambio_num_grupos)
        
        # Polling
        ttk.Label(grid_frame, text="Polling (ms):", style='Panel.TLabel').grid(row=6, column=0, sticky='e', padx=5, pady=3)
        self.entry_polling = ttk.Entry(grid_frame, style='Dark.TEntry', width=8)
        self.entry_polling.grid(row=6, column=1, sticky='w', padx=5, pady=3)
        self.entry_polling.insert(0, '5000')
        
        self.var_habilitado = tk.BooleanVar(value=True)
        ttk.Checkbutton(grid_frame, text="Habilitado", variable=self.var_habilitado,
                        style='Dark.TCheckbutton').grid(row=6, column=2, sticky='w', padx=5)
        
        # Botones de configuración
        btn_config_frame = ttk.Frame(config_frame, style='Panel.TFrame')
        btn_config_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Button(btn_config_frame, text="💾 Guardar Config",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._guardar_config_regulador).pack(side='left', padx=5)
        
        tk.Button(btn_config_frame, text="🔌 Conectar",
                  bg=COLORES['exito'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._conectar_regulador).pack(side='left', padx=5)
        
        tk.Button(btn_config_frame, text="❌ Desconectar",
                  bg=COLORES['error'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._desconectar_regulador).pack(side='left', padx=5)
        
        # Ocultar frame serial por defecto
        self.frame_serial.grid_remove()
    
    def _crear_panel_estado(self, parent):
        """Crea el panel de estado en tiempo real"""
        estado_frame = ttk.LabelFrame(parent, text="📊 ESTADO EN TIEMPO REAL", style='Dark.TLabelframe')
        estado_frame.pack(fill='x', pady=5)
        
        # Info de estado
        info_frame = ttk.Frame(estado_frame, style='Panel.TFrame')
        info_frame.pack(fill='x', padx=10, pady=10)
        
        # Fila 1: Estado, Plan, Ciclo
        row1 = ttk.Frame(info_frame, style='Panel.TFrame')
        row1.pack(fill='x', pady=2)
        
        self.lbl_estado_conexion = ttk.Label(row1, text="Estado: ⚪ Desconectado", style='Panel.TLabel')
        self.lbl_estado_conexion.pack(side='left', padx=10)
        
        self.lbl_plan = ttk.Label(row1, text="Plan: --", style='Panel.TLabel')
        self.lbl_plan.pack(side='left', padx=10)
        
        self.lbl_ciclo = ttk.Label(row1, text="Ciclo: --s", style='Panel.TLabel')
        self.lbl_ciclo.pack(side='left', padx=10)
        
        self.lbl_fase = ttk.Label(row1, text="Fase: --", style='Panel.TLabel')
        self.lbl_fase.pack(side='left', padx=10)
        
        # Fila 2: Modo, Hora Plan
        row2 = ttk.Frame(info_frame, style='Panel.TFrame')
        row2.pack(fill='x', pady=2)
        
        self.lbl_modo = ttk.Label(row2, text="Modo: --", style='Panel.TLabel')
        self.lbl_modo.pack(side='left', padx=10)
        
        self.lbl_hora = ttk.Label(row2, text="H.Plan: --:--:--", style='Panel.TLabel')
        self.lbl_hora.pack(side='left', padx=10)
        
        self.lbl_seg_ciclo = ttk.Label(row2, text="Seg. Ciclo: --", style='Panel.TLabel')
        self.lbl_seg_ciclo.pack(side='left', padx=10)
        
        # Fila 3: Modo Control (LOCAL/ORDENADOR) con botón de cambio
        row3 = ttk.Frame(info_frame, style='Panel.TFrame')
        row3.pack(fill='x', pady=2)
        
        self.lbl_modo_control = tk.Label(row3, text="Control: --", bg=COLORES['panel'], 
                                         fg=COLORES['texto'], font=('Segoe UI', 10, 'bold'))
        self.lbl_modo_control.pack(side='left', padx=10)
        
        # Botón para cambiar modo
        self.btn_cambiar_modo = tk.Button(row3, text="🔄 Cambiar Modo", command=self._cmd_cambiar_modo,
                                          bg=COLORES['acento'], fg=COLORES['texto'],
                                          activebackground=COLORES['acento_hover'],
                                          activeforeground=COLORES['texto'],
                                          font=('Segoe UI', 8), padx=5, pady=1,
                                          relief='flat', cursor='hand2')
        self.btn_cambiar_modo.pack(side='left', padx=5)
        
        # Aviso de modo LOCAL
        self.lbl_aviso_local = tk.Label(row3, text="", bg=COLORES['panel'], 
                                        fg=COLORES['advertencia'], font=('Segoe UI', 8, 'italic'))
        self.lbl_aviso_local.pack(side='left', padx=5)
        
        # Fila 4: Hora actual del sistema
        row4 = ttk.Frame(info_frame, style='Panel.TFrame')
        row4.pack(fill='x', pady=2)
        
        self.lbl_hora_sistema = ttk.Label(row4, text="🕐 Hora Sistema: --:--:--", style='Panel.TLabel')
        self.lbl_hora_sistema.pack(side='left', padx=10)
        
        # Frame contenedor para grupos de semáforos
        self.grupos_container = ttk.Frame(estado_frame, style='Panel.TFrame')
        self.grupos_container.pack(fill='x', padx=10, pady=10)
        
        # Inicializar estructura de semáforos
        self.semaforos_canvas = {}
        self.num_grupos_actual = 8
        
        # Crear grupos iniciales
        self._crear_semaforos_grupos(8)
        
        # Alarmas
        alarmas_frame = ttk.Frame(estado_frame, style='Panel.TFrame')
        alarmas_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(alarmas_frame, text="ALARMAS:", bg=COLORES['panel'], fg=COLORES['texto'],
                 font=('Segoe UI', 9, 'bold')).pack(side='left', padx=5)
        
        self.alarmas_labels = {}
        alarmas_info = [
            ('lamp', '💡 Lámpara', 'lampara_fundida'),
            ('conf', '⚠️ Conflicto', 'conflicto'), 
            ('puerta', '🚪 Puerta', 'puerta_abierta'),
            ('24v', '🔌 24V', 'fallo_24v'),
            ('rojo', '🔴 F.Rojo', 'fallo_rojo')
        ]
        
        for key, texto, attr in alarmas_info:
            # Usar tk.Label para poder cambiar fg dinámicamente
            lbl = tk.Label(alarmas_frame, text=texto, bg=COLORES['panel'], 
                          fg=COLORES['texto_dim'], font=('Segoe UI', 9))
            lbl.pack(side='left', padx=8)
            self.alarmas_labels[key] = {'label': lbl, 'texto': texto, 'attr': attr}
    
    def _crear_semaforos_grupos(self, num_grupos: int):
        """Crea los semáforos visuales para los grupos"""
        # Limpiar semáforos existentes
        for widget in self.grupos_container.winfo_children():
            widget.destroy()
        
        self.semaforos_canvas = {}
        self.num_grupos_actual = num_grupos
        
        # Título
        ttk.Label(self.grupos_container, text="GRUPOS:", 
                  style='Panel.TLabel').pack(side='left', padx=5)
        
        # Colores de semáforo
        colores_off = {
            'rojo': '#4a0000',
            'ambar': '#4a4a00', 
            'verde': '#004a00'
        }
        
        for i in range(num_grupos):
            frame_grupo = tk.Frame(self.grupos_container, bg=COLORES['panel'])
            frame_grupo.pack(side='left', padx=3)
            
            # Número del grupo
            lbl_num = tk.Label(frame_grupo, text=f"G{i+1}", font=('Segoe UI', 8, 'bold'),
                               bg=COLORES['panel'], fg=COLORES['texto'])
            lbl_num.pack()
            
            # Canvas para el semáforo vehicular (3 luces)
            canvas = tk.Canvas(frame_grupo, width=30, height=70, bg='#333333',
                               highlightthickness=1, highlightbackground='#555555')
            canvas.pack(pady=2)
            
            # Crear las 3 luces (apagadas inicialmente)
            luz_rojo = canvas.create_oval(5, 3, 25, 23, fill=colores_off['rojo'], outline='#222222')
            luz_ambar = canvas.create_oval(5, 25, 25, 45, fill=colores_off['ambar'], outline='#222222')
            luz_verde = canvas.create_oval(5, 47, 25, 67, fill=colores_off['verde'], outline='#222222')
            
            # Etiqueta de estado
            lbl_estado = tk.Label(frame_grupo, text="--", font=('Segoe UI', 7),
                                  bg=COLORES['panel'], fg=COLORES['texto_dim'])
            lbl_estado.pack()
            
            self.semaforos_canvas[i] = {
                'canvas': canvas,
                'rojo': luz_rojo,
                'ambar': luz_ambar,
                'verde': luz_verde,
                'label': lbl_estado
            }
    
    def _on_cambio_num_grupos(self, event=None):
        """Handler cuando cambia el número de grupos"""
        try:
            num_grupos = int(self.combo_num_grupos.get())
            if num_grupos != self.num_grupos_actual:
                self._crear_semaforos_grupos(num_grupos)
                
                # Actualizar regulador si hay uno seleccionado
                if self.regulador_seleccionado:
                    self.regulador_seleccionado.num_grupos = num_grupos
        except ValueError:
            pass
    
    def _actualizar_semaforo_grupo(self, grupo_idx: int, estado):
        """Actualiza el color del semáforo de un grupo
        
        Args:
            grupo_idx: Índice del grupo (0-based)
            estado: Puede ser int (0-6) o str (VERDE, ROJO, etc.)
        """
        if grupo_idx not in self.semaforos_canvas:
            return
        
        sem = self.semaforos_canvas[grupo_idx]
        canvas = sem['canvas']
        
        # Colores apagados
        colores_off = {'rojo': '#4a0000', 'ambar': '#4a4a00', 'verde': '#004a00'}
        # Colores encendidos
        colores_on = {'rojo': '#ff0000', 'ambar': '#ffcc00', 'verde': '#00ff00'}
        
        # Resetear todos a apagado
        canvas.itemconfig(sem['rojo'], fill=colores_off['rojo'])
        canvas.itemconfig(sem['ambar'], fill=colores_off['ambar'])
        canvas.itemconfig(sem['verde'], fill=colores_off['verde'])
        
        # Si es int, convertir a string de estado
        if isinstance(estado, int):
            # 0=Apagado, 1=Verde, 2=Ámbar, 3=Rojo, 4=Rojo Int., 5=Verde Int., 6=Ámbar Int.
            estado_map = {0: 'APAGADO', 1: 'VERDE', 2: 'AMBAR', 3: 'ROJO', 
                          4: 'ROJO', 5: 'VERDE', 6: 'AMBAR'}
            estado_str = estado_map.get(estado, 'APAGADO')
            # Marcar si es intermitente
            is_intermitente = estado in [4, 5, 6]
        else:
            estado_str = str(estado).upper() if estado else ''
            is_intermitente = 'INT' in estado_str or estado_str in ['INTERMITENTE', 'FLASH', 'F']
        
        # Actualizar según estado
        if estado_str in ['ROJO', 'R', 'RED']:
            canvas.itemconfig(sem['rojo'], fill=colores_on['rojo'])
            lbl_text = 'R⚡' if is_intermitente else 'R'
            sem['label'].config(text=lbl_text, fg=colores_on['rojo'])
        elif estado_str in ['AMBAR', 'A', 'AMBER', 'YELLOW']:
            canvas.itemconfig(sem['ambar'], fill=colores_on['ambar'])
            lbl_text = 'A⚡' if is_intermitente else 'A'
            sem['label'].config(text=lbl_text, fg=colores_on['ambar'])
        elif estado_str in ['VERDE', 'V', 'GREEN', 'G']:
            canvas.itemconfig(sem['verde'], fill=colores_on['verde'])
            lbl_text = 'V⚡' if is_intermitente else 'V'
            sem['label'].config(text=lbl_text, fg=colores_on['verde'])
        elif estado_str in ['ROJO_AMBAR', 'RA', 'RED_AMBER']:
            canvas.itemconfig(sem['rojo'], fill=colores_on['rojo'])
            canvas.itemconfig(sem['ambar'], fill=colores_on['ambar'])
            sem['label'].config(text='RA', fg=colores_on['ambar'])
        elif estado_str in ['APAGADO', 'OFF', '-', '']:
            sem['label'].config(text='--', fg=COLORES['texto_dim'])
        elif estado_str in ['INTERMITENTE', 'FLASH', 'F']:
            canvas.itemconfig(sem['ambar'], fill=colores_on['ambar'])
            sem['label'].config(text='⚡', fg=colores_on['ambar'])
        else:
            text_show = str(estado)[:2] if estado else '--'
            sem['label'].config(text=text_show, fg=COLORES['texto_dim'])

    def _crear_panel_planes(self, parent):
        """Crea el panel de planes y configuración del regulador"""
        # Frame colapsable para planes
        planes_frame = ttk.LabelFrame(parent, text="📋 PLANES Y CONFIGURACIÓN", style='Dark.TLabelframe')
        planes_frame.pack(fill='x', pady=5)
        
        # Frame principal con dos columnas
        main_planes = ttk.Frame(planes_frame, style='Panel.TFrame')
        main_planes.pack(fill='x', padx=10, pady=5)
        
        # Columna izquierda: Lista de planes
        left_frame = ttk.Frame(main_planes, style='Panel.TFrame')
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        ttk.Label(left_frame, text="Planes:", style='Panel.TLabel').pack(anchor='w')
        
        # Listbox de planes
        planes_list_frame = ttk.Frame(left_frame, style='Panel.TFrame')
        planes_list_frame.pack(fill='both', expand=True)
        
        self.lista_planes = tk.Listbox(
            planes_list_frame,
            bg=COLORES['panel_claro'],
            fg=COLORES['texto'],
            font=('Consolas', 9),
            height=6,
            selectmode='single',
            relief='flat',
            highlightthickness=1,
            highlightbackground=COLORES['borde']
        )
        self.lista_planes.pack(side='left', fill='both', expand=True)
        self.lista_planes.bind('<<ListboxSelect>>', self._on_seleccionar_plan)
        
        scrollbar_planes = ttk.Scrollbar(planes_list_frame, orient='vertical', 
                                          command=self.lista_planes.yview)
        scrollbar_planes.pack(side='right', fill='y')
        self.lista_planes.config(yscrollcommand=scrollbar_planes.set)
        
        # Columna derecha: Detalles del plan seleccionado
        right_frame = ttk.Frame(main_planes, style='Panel.TFrame')
        right_frame.pack(side='left', fill='both', expand=True, padx=(5, 0))
        
        ttk.Label(right_frame, text="Detalle del Plan:", style='Panel.TLabel').pack(anchor='w')
        
        # Grid de detalles
        detail_grid = ttk.Frame(right_frame, style='Panel.TFrame')
        detail_grid.pack(fill='x', pady=5)
        
        # Fila 1: ID y Nombre
        ttk.Label(detail_grid, text="ID:", style='Panel.TLabel').grid(row=0, column=0, sticky='e', padx=3, pady=2)
        self.lbl_plan_id = ttk.Label(detail_grid, text="--", style='Panel.TLabel')
        self.lbl_plan_id.grid(row=0, column=1, sticky='w', padx=3, pady=2)
        
        ttk.Label(detail_grid, text="Nombre:", style='Panel.TLabel').grid(row=0, column=2, sticky='e', padx=3, pady=2)
        self.lbl_plan_nombre = ttk.Label(detail_grid, text="--", style='Panel.TLabel')
        self.lbl_plan_nombre.grid(row=0, column=3, sticky='w', padx=3, pady=2)
        
        # Fila 2: Ciclo y Desfase
        ttk.Label(detail_grid, text="Ciclo:", style='Panel.TLabel').grid(row=1, column=0, sticky='e', padx=3, pady=2)
        self.lbl_plan_ciclo = ttk.Label(detail_grid, text="--s", style='Panel.TLabel')
        self.lbl_plan_ciclo.grid(row=1, column=1, sticky='w', padx=3, pady=2)
        
        ttk.Label(detail_grid, text="Desfase:", style='Panel.TLabel').grid(row=1, column=2, sticky='e', padx=3, pady=2)
        self.lbl_plan_desfase = ttk.Label(detail_grid, text="--s", style='Panel.TLabel')
        self.lbl_plan_desfase.grid(row=1, column=3, sticky='w', padx=3, pady=2)
        
        # Fila 3: Estructura y Horario
        ttk.Label(detail_grid, text="Estructura:", style='Panel.TLabel').grid(row=2, column=0, sticky='e', padx=3, pady=2)
        self.lbl_plan_estructura = ttk.Label(detail_grid, text="--", style='Panel.TLabel')
        self.lbl_plan_estructura.grid(row=2, column=1, sticky='w', padx=3, pady=2)
        
        ttk.Label(detail_grid, text="Horario:", style='Panel.TLabel').grid(row=2, column=2, sticky='e', padx=3, pady=2)
        self.lbl_plan_horario = ttk.Label(detail_grid, text="--", style='Panel.TLabel')
        self.lbl_plan_horario.grid(row=2, column=3, sticky='w', padx=3, pady=2)
        
        # Fila 4: Duraciones de fases
        ttk.Label(detail_grid, text="Fases:", style='Panel.TLabel').grid(row=3, column=0, sticky='e', padx=3, pady=2)
        self.lbl_plan_fases = ttk.Label(detail_grid, text="--", style='Panel.TLabel')
        self.lbl_plan_fases.grid(row=3, column=1, columnspan=3, sticky='w', padx=3, pady=2)
        
        # Fila 5: Transitorios
        ttk.Label(detail_grid, text="Trans.:", style='Panel.TLabel').grid(row=4, column=0, sticky='e', padx=3, pady=2)
        self.lbl_plan_trans = ttk.Label(detail_grid, text="Ámbar: --s, Rojo seg: --s", style='Panel.TLabel')
        self.lbl_plan_trans.grid(row=4, column=1, columnspan=3, sticky='w', padx=3, pady=2)
        
        # Botones de acciones
        btn_frame = ttk.Frame(planes_frame, style='Panel.TFrame')
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Button(btn_frame, text="📥 Cargar desde Archivo",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cargar_planes_archivo).pack(side='left', padx=3)
        
        tk.Button(btn_frame, text="📤 Exportar Planes",
                  bg=COLORES['panel_claro'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._exportar_planes).pack(side='left', padx=3)
        
        tk.Button(btn_frame, text="🔄 Cargar de Regulador",
                  bg=COLORES['exito'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cargar_config_regulador).pack(side='left', padx=3)
        
        # Inicializar almacén de planes
        self.planes_regulador = {}
        self.plan_seleccionado = None
    
    def _on_seleccionar_plan(self, event=None):
        """Maneja la selección de un plan en la lista"""
        selection = self.lista_planes.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not self.regulador_seleccionado:
            return
        
        reg_id = self.regulador_seleccionado.id
        if reg_id not in self.planes_regulador:
            return
        
        planes = self.planes_regulador[reg_id].get('lista', [])
        if idx < len(planes):
            plan = planes[idx]
            self.plan_seleccionado = plan
            self._mostrar_detalle_plan(plan)
    
    def _mostrar_detalle_plan(self, plan: dict):
        """Muestra los detalles de un plan"""
        self.lbl_plan_id.config(text=str(plan.get('id', '--')))
        self.lbl_plan_nombre.config(text=plan.get('nombre', '--'))
        self.lbl_plan_ciclo.config(text=f"{plan.get('ciclo', '--')}s")
        self.lbl_plan_desfase.config(text=f"{plan.get('desfase', 0)}s")
        self.lbl_plan_estructura.config(text=f"Est. {plan.get('estructura_id', '--')}")
        
        # Horarios
        horarios = plan.get('horarios', [])
        if horarios:
            h_str = ', '.join([h.get('inicio', '') for h in horarios])
            self.lbl_plan_horario.config(text=h_str)
        else:
            self.lbl_plan_horario.config(text="--")
        
        # Duraciones de fases
        duraciones = plan.get('duraciones_fases', {})
        if duraciones:
            fases_str = ', '.join([f"F{k}:{v}s" for k, v in duraciones.items()])
            self.lbl_plan_fases.config(text=fases_str)
        else:
            self.lbl_plan_fases.config(text="--")
        
        # Transitorios
        trans = plan.get('transitorios', {}).get('vehicular', {})
        ambar = trans.get('tiempo_ambar', '--')
        rojo = trans.get('tiempo_rojo_seguridad', '--')
        self.lbl_plan_trans.config(text=f"Ámbar: {ambar}s, Rojo seg: {rojo}s")
    
    def _actualizar_lista_planes(self):
        """Actualiza la lista de planes del regulador seleccionado"""
        self.lista_planes.delete(0, tk.END)
        
        if not self.regulador_seleccionado:
            return
        
        reg_id = self.regulador_seleccionado.id
        if reg_id not in self.planes_regulador:
            return
        
        planes = self.planes_regulador[reg_id].get('lista', [])
        for plan in planes:
            activo = "✓" if plan.get('activo', True) else " "
            texto = f"[{activo}] {plan.get('id', '?'):3d} - {plan.get('nombre', 'Sin nombre')} ({plan.get('ciclo', 0)}s)"
            self.lista_planes.insert(tk.END, texto)
    
    def _cargar_planes_archivo(self):
        """Carga planes desde un archivo de configuración"""
        from tkinter import filedialog
        
        archivo = filedialog.askopenfilename(
            title="Cargar configuración de planes",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=os.path.dirname(os.path.abspath(__file__))
        )
        
        if not archivo:
            return
        
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Extraer planes
            planes_data = config.get('planes', {})
            if planes_data and self.regulador_seleccionado:
                reg_id = self.regulador_seleccionado.id
                self.planes_regulador[reg_id] = planes_data
                self._actualizar_lista_planes()
                
                # Actualizar número de grupos si existe
                grupos = config.get('grupos', {})
                if grupos:
                    num_grupos = grupos.get('cantidad', 4)
                    self.regulador_seleccionado.num_grupos = num_grupos
                    self.combo_num_grupos.set(str(num_grupos))
                    self._crear_semaforos_grupos(num_grupos)
                
                self._log(f"Cargados {len(planes_data.get('lista', []))} planes desde {os.path.basename(archivo)}", "INFO")
        except Exception as e:
            self._log(f"Error al cargar archivo: {e}", "ERROR")
            messagebox.showerror("Error", f"No se pudo cargar el archivo:\n{e}")
    
    def _exportar_planes(self):
        """Exporta los planes del regulador a un archivo"""
        from tkinter import filedialog
        
        if not self.regulador_seleccionado:
            messagebox.showwarning("Aviso", "Seleccione un regulador primero")
            return
        
        reg_id = self.regulador_seleccionado.id
        if reg_id not in self.planes_regulador:
            messagebox.showwarning("Aviso", "No hay planes cargados para este regulador")
            return
        
        archivo = filedialog.asksaveasfilename(
            title="Exportar planes",
            filetypes=[("JSON files", "*.json")],
            defaultextension=".json",
            initialfile=f"planes_{self.regulador_seleccionado.nombre.replace(' ', '_')}.json"
        )
        
        if not archivo:
            return
        
        try:
            export_data = {
                'regulador': {
                    'id': reg_id,
                    'nombre': self.regulador_seleccionado.nombre
                },
                'planes': self.planes_regulador[reg_id]
            }
            
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
            
            self._log(f"Planes exportados a {os.path.basename(archivo)}", "INFO")
        except Exception as e:
            self._log(f"Error al exportar: {e}", "ERROR")
    
    def _cargar_config_regulador(self):
        """Carga la configuración desde el regulador virtual local"""
        # Ruta al archivo de configuración del regulador virtual
        ruta_config = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'regulador', 'config', 'regulador_config.json'
        )
        
        if not os.path.exists(ruta_config):
            messagebox.showerror("Error", f"No se encontró el archivo de configuración:\n{ruta_config}")
            return
        
        try:
            with open(ruta_config, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if not self.regulador_seleccionado:
                messagebox.showwarning("Aviso", "Seleccione un regulador primero")
                return
            
            reg_id = self.regulador_seleccionado.id
            
            # Cargar planes
            planes_data = config.get('planes', {})
            if planes_data:
                self.planes_regulador[reg_id] = planes_data
                self._actualizar_lista_planes()
            
            # Cargar configuración de grupos
            grupos = config.get('grupos', {})
            if grupos:
                num_grupos = grupos.get('cantidad', 4)
                self.regulador_seleccionado.num_grupos = num_grupos
                self.combo_num_grupos.set(str(num_grupos))
                self._crear_semaforos_grupos(num_grupos)
            
            # Actualizar nombre si queremos
            reg_config = config.get('regulador', {})
            
            self._log(f"Configuración cargada desde regulador virtual: {len(planes_data.get('lista', []))} planes, {num_grupos} grupos", "INFO")
            messagebox.showinfo("Éxito", f"Configuración cargada:\n- {len(planes_data.get('lista', []))} planes\n- {num_grupos} grupos")
            
        except Exception as e:
            self._log(f"Error al cargar configuración: {e}", "ERROR")
            messagebox.showerror("Error", f"Error al cargar configuración:\n{e}")

    def _crear_panel_comandos(self, parent):
        """Crea el panel de comandos"""
        # Frame contenedor con dos columnas
        cmd_container = ttk.Frame(parent, style='Panel.TFrame')
        cmd_container.pack(fill='x', pady=5)
        
        # Comandos individuales
        cmd_ind_frame = ttk.LabelFrame(cmd_container, text="🎮 COMANDOS INDIVIDUALES", style='Dark.TLabelframe')
        cmd_ind_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        grid_cmd = ttk.Frame(cmd_ind_frame, style='Panel.TFrame')
        grid_cmd.pack(fill='x', padx=10, pady=10)
        
        # Fila 1: Cambio de plan
        ttk.Label(grid_cmd, text="Plan:", style='Panel.TLabel').grid(row=0, column=0, padx=5, pady=3)
        self.combo_plan = ttk.Combobox(grid_cmd, style='Dark.TCombobox', width=8,
                                        values=[str(i) for i in range(129, 161)])
        self.combo_plan.grid(row=0, column=1, padx=5, pady=3)
        self.combo_plan.set('129')
        
        tk.Button(grid_cmd, text="Cambiar Plan",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_cambiar_plan).grid(row=0, column=2, padx=5, pady=3)
        
        # Fila 2: Modos
        tk.Button(grid_cmd, text="🟡 Intermitente",
                  bg=COLORES['advertencia'], fg='black',
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_intermitente).grid(row=1, column=0, padx=5, pady=3)
        
        tk.Button(grid_cmd, text="⚫ Apagar",
                  bg=COLORES['texto_dim'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_apagar).grid(row=1, column=1, padx=5, pady=3)
        
        tk.Button(grid_cmd, text="🚦 Colores",
                  bg=COLORES['exito'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_colores).grid(row=1, column=2, padx=5, pady=3)
        
        # Fila 3: Otros comandos
        tk.Button(grid_cmd, text="🕐 Puesta en Hora",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_puesta_hora).grid(row=2, column=0, padx=5, pady=3)
        
        tk.Button(grid_cmd, text="📋 Solicitar Estado",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_solicitar_estado).grid(row=2, column=1, padx=5, pady=3)
        
        tk.Button(grid_cmd, text="🗑️ Borrar Alarmas",
                  bg=COLORES['error'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_borrar_alarmas).grid(row=2, column=2, padx=5, pady=3)
        
        # Comandos en bloque
        cmd_bloque_frame = ttk.LabelFrame(cmd_container, text="📦 COMANDOS EN BLOQUE", style='Dark.TLabelframe')
        cmd_bloque_frame.pack(side='left', fill='both', expand=True, padx=(5, 0))
        
        grid_bloque = ttk.Frame(cmd_bloque_frame, style='Panel.TFrame')
        grid_bloque.pack(fill='x', padx=10, pady=10)
        
        # Selector de destino
        ttk.Label(grid_bloque, text="Aplicar a:", style='Panel.TLabel').grid(row=0, column=0, padx=5, pady=3)
        self.combo_destino = ttk.Combobox(grid_bloque, style='Dark.TCombobox', width=15,
                                           values=['Todos', 'Solo conectados', 'Seleccionados'])
        self.combo_destino.grid(row=0, column=1, padx=5, pady=3)
        self.combo_destino.set('Todos')
        
        # Botones de bloque
        tk.Button(grid_bloque, text="🔄 Plan a Todos",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_bloque_plan).grid(row=1, column=0, padx=5, pady=3)
        
        tk.Button(grid_bloque, text="🟡 Todos Intermitente",
                  bg=COLORES['advertencia'], fg='black',
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_bloque_intermitente).grid(row=1, column=1, padx=5, pady=3)
        
        tk.Button(grid_bloque, text="⚫ Apagar Todos",
                  bg=COLORES['texto_dim'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_bloque_apagar).grid(row=2, column=0, padx=5, pady=3)
        
        tk.Button(grid_bloque, text="🕐 Hora Global",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 9), relief='flat',
                  command=self._cmd_bloque_hora).grid(row=2, column=1, padx=5, pady=3)
    
    def _crear_panel_log_interno(self):
        """Crea el panel inferior de logs (compacto)"""
        log_frame = ttk.LabelFrame(self.root, text="LOG DE COMUNICACIONES", style='Dark.TLabelframe')
        log_frame.pack(fill='x', padx=5, pady=5)
        
        # Botones de control del log
        btn_log_frame = ttk.Frame(log_frame, style='Panel.TFrame')
        btn_log_frame.pack(fill='x', padx=5, pady=5)
        
        self.var_auto_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_log_frame, text="Auto-scroll", variable=self.var_auto_scroll,
                        style='Dark.TCheckbutton').pack(side='left', padx=5)
        
        tk.Button(btn_log_frame, text="Limpiar",
                  bg=COLORES['panel_claro'], fg=COLORES['texto'],
                  font=('Segoe UI', 8), relief='flat',
                  command=self._limpiar_log).pack(side='right', padx=5)
        
        # Text widget para logs
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            bg=COLORES['panel_claro'],
            fg=COLORES['texto'],
            font=('Consolas', 9),
            height=6,
            state='disabled',
            relief='flat'
        )
        self.log_text.pack(fill='x', padx=5, pady=5)
        
        # Tags para colores
        self.log_text.tag_configure('INFO', foreground=COLORES['texto'])
        self.log_text.tag_configure('ERROR', foreground=COLORES['error'])
        self.log_text.tag_configure('WARNING', foreground=COLORES['advertencia'])
        self.log_text.tag_configure('TX', foreground='#3282b8')
        self.log_text.tag_configure('RX', foreground='#00a86b')
        
        # Botón para abrir ventana de log
        tk.Button(btn_log_frame, text="Abrir en Ventana",
                  bg=COLORES['acento'], fg=COLORES['texto'],
                  font=('Segoe UI', 8), relief='flat',
                  command=self._mostrar_ventana_log).pack(side='right', padx=5)
    
    # =========================================================================
    # EVENTOS Y CALLBACKS
    # =========================================================================
    
    def _on_cambio_tipo_conexion(self):
        """Callback cuando cambia el tipo de conexión"""
        if self.var_tipo_conexion.get() == 'tcp':
            self.frame_serial.grid_remove()
            self.frame_tcp.grid()
        else:
            self.frame_tcp.grid_remove()
            self.frame_serial.grid()
    
    def _on_seleccionar_regulador(self, event):
        """Callback cuando se selecciona un regulador de la lista"""
        selection = self.lista_reguladores.curselection()
        if selection:
            idx = selection[0]
            reguladores = self.gestor_reguladores.listar()
            if idx < len(reguladores):
                self.regulador_seleccionado = reguladores[idx]
                self._mostrar_regulador(self.regulador_seleccionado)
    
    def _on_cerrar(self):
        """Callback al cerrar la ventana"""
        self.polling_activo = False
        self._desconectar_todos()
        self._guardar_config()
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
        self.root.destroy()
    
    # =========================================================================
    # GESTIÓN DE REGULADORES
    # =========================================================================
    
    def _actualizar_lista_reguladores(self):
        """Actualiza la lista visual de reguladores"""
        self.lista_reguladores.delete(0, tk.END)
        
        for reg in self.gestor_reguladores.listar():
            # Icono de estado
            if not reg.habilitado:
                icono = "◌"  # Deshabilitado
            elif reg.conectado:
                icono = "●"  # Conectado
            else:
                icono = "○"  # Desconectado
            
            texto = f"{icono} {reg.id:03d} - {reg.nombre}"
            self.lista_reguladores.insert(tk.END, texto)
    
    def _mostrar_regulador(self, reg: EstadoRegulador):
        """Muestra los datos de un regulador en el panel de detalle"""
        self.titulo_regulador.config(text=f"REGULADOR: {reg.nombre} (ID: {reg.id:03d})")
        
        # Configuración
        self.entry_nombre.delete(0, tk.END)
        self.entry_nombre.insert(0, reg.nombre)
        
        self.var_tipo_conexion.set(reg.tipo_conexion)
        self._on_cambio_tipo_conexion()
        
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, reg.ip)
        
        self.entry_puerto.delete(0, tk.END)
        self.entry_puerto.insert(0, str(reg.puerto))
        
        self.combo_com.set(reg.puerto_com)
        self.combo_baud.set(str(reg.baudrate))
        
        modo_texto = 'Modo A (Síncrono)' if reg.modo == 'A' else 'Modo B (Asíncrono)'
        self.combo_modo.set(modo_texto)
        
        # Número de grupos
        num_grupos = getattr(reg, 'num_grupos', 8)
        self.combo_num_grupos.set(str(num_grupos))
        if num_grupos != self.num_grupos_actual:
            self._crear_semaforos_grupos(num_grupos)
        
        self.entry_polling.delete(0, tk.END)
        self.entry_polling.insert(0, str(reg.polling_intervalo_ms))
        
        self.var_habilitado.set(reg.habilitado)
        
        # Estado
        self._actualizar_estado_visual(reg)
    
    def _actualizar_estado_visual(self, reg: EstadoRegulador):
        """Actualiza los indicadores visuales del estado"""
        logger.debug(f"Actualizando visual para reg {reg.id}: conectado={reg.conectado}, plan={reg.plan_actual}, fase={reg.fase_actual}")
        
        # Estado de conexión
        if reg.conectado:
            self.lbl_estado_conexion.config(text="Estado: 🟢 Conectado")
        else:
            self.lbl_estado_conexion.config(text="Estado: ⚪ Desconectado")
        
        # Verificar si hay datos recibidos (ultima_comunicacion no es None)
        tiene_datos = reg.ultima_comunicacion is not None
        
        # Info del regulador - mostrar valores o -- si no hay datos
        if tiene_datos:
            plan_text = f"Plan: {reg.plan_actual}"
            ciclo_text = f"Ciclo: {reg.ciclo_total}s"
            fase_text = f"Fase: {reg.fase_actual}"
            # La hora del 0x91 es la hora de inicio del plan
            hora_text = f"H.Plan: {reg.hora_formateada}"
            seg_ciclo_text = f"Seg. Ciclo: {reg.segundos_ciclo}"
        else:
            plan_text = "Plan: --"
            ciclo_text = "Ciclo: --"
            fase_text = "Fase: --"
            hora_text = "H.Plan: --:--:--"
            seg_ciclo_text = "Seg. Ciclo: --"
        
        self.lbl_plan.config(text=plan_text)
        self.lbl_ciclo.config(text=ciclo_text)
        self.lbl_fase.config(text=fase_text)
        self.lbl_modo.config(text=f"Modo: {reg.estado_repr_texto}")
        self.lbl_hora.config(text=hora_text)
        self.lbl_seg_ciclo.config(text=seg_ciclo_text)
        
        # Actualizar modo de control (LOCAL/ORDENADOR)
        self._actualizar_modo_control_visual(reg)
        
        # Actualizar semáforos de grupos
        for i in range(self.num_grupos_actual):
            if i < len(reg.grupos):
                estado = reg.grupos[i].estado if hasattr(reg.grupos[i], 'estado') else str(reg.grupos[i])
                self._actualizar_semaforo_grupo(i, estado)
            else:
                self._actualizar_semaforo_grupo(i, 'APAGADO')
        
        # Actualizar alarmas
        self._actualizar_alarmas_visual(reg)
    
    def _actualizar_alarmas_visual(self, reg: EstadoRegulador):
        """Actualiza la visualización de alarmas"""
        # Colores para alarmas
        color_activa = '#ff4444'  # Rojo brillante
        color_inactiva = COLORES['texto_dim']  # Gris
        
        for key, info in self.alarmas_labels.items():
            lbl = info['label']
            texto_base = info['texto']
            attr = info['attr']
            
            # Obtener estado de la alarma
            alarma_activa = getattr(reg.alarmas, attr, False)
            
            if alarma_activa:
                texto = f"⚡{texto_base}"
                
                # Para fallo_rojo y lampara_fundida, mostrar grupos afectados
                if attr in ['fallo_rojo', 'lampara_fundida'] and reg.alarmas.grupos_con_fallo:
                    grupos_texto = ", ".join([f"G{g}" for g in reg.alarmas.grupos_con_fallo])
                    texto = f"⚡{texto_base} ({grupos_texto})"
                
                # Alarma activa - mostrar en rojo con indicador
                lbl.config(fg=color_activa, text=texto)
            else:
                # Alarma inactiva - mostrar en gris normal
                lbl.config(fg=color_inactiva, text=texto_base)
    
    def _actualizar_modo_control_visual(self, reg: EstadoRegulador):
        """Actualiza la visualización del modo de control (LOCAL/ORDENADOR)"""
        modo_texto = reg.modo_control_texto
        
        # Color según modo
        if reg.modo_control == ModoControl.LOCAL:
            color = COLORES['advertencia']  # Naranja - modo local
            aviso = "⚠️ La hora NO se sincronizará en modo LOCAL"
        elif reg.modo_control == ModoControl.ORDENADOR:
            color = COLORES['exito']  # Verde - modo ordenador (remoto)
            aviso = ""
        elif reg.modo_control == ModoControl.DESCONOCIDO:
            color = COLORES['texto_dim']  # Gris - desconocido
            aviso = ""
        else:
            color = COLORES['advertencia']  # Naranja - otros modos
            aviso = ""
        
        self.lbl_modo_control.config(text=f"Control: {modo_texto}", fg=color)
        self.lbl_aviso_local.config(text=aviso)
        
        # Actualizar texto del botón según modo actual
        if reg.modo_control == ModoControl.LOCAL:
            self.btn_cambiar_modo.config(text="📡 Pasar a ORDENADOR")
        elif reg.modo_control == ModoControl.ORDENADOR:
            self.btn_cambiar_modo.config(text="🏠 Pasar a LOCAL")
        else:
            self.btn_cambiar_modo.config(text="🔄 Cambiar Modo")
    
    def _agregar_regulador(self):
        """Agrega un nuevo regulador"""
        nuevo_id = self.gestor_reguladores.siguiente_id()
        nuevo_reg = EstadoRegulador(
            id=nuevo_id,
            nombre=f"Regulador {nuevo_id}",
            ip="127.0.0.1",
            puerto=5000
        )
        self.gestor_reguladores.agregar(nuevo_reg)
        self._actualizar_lista_reguladores()
        self._guardar_config()
        self._log(f"Regulador {nuevo_id} agregado", "INFO")
    
    def _eliminar_regulador(self):
        """Elimina el regulador seleccionado"""
        if not self.regulador_seleccionado:
            messagebox.showwarning("Aviso", "Seleccione un regulador para eliminar")
            return
        
        if messagebox.askyesno("Confirmar", f"¿Eliminar regulador {self.regulador_seleccionado.nombre}?"):
            reg_id = self.regulador_seleccionado.id
            self.gestor_reguladores.eliminar(reg_id)
            self.conexiones.eliminar(reg_id)
            self.regulador_seleccionado = None
            self._actualizar_lista_reguladores()
            self._guardar_config()
            self._log(f"Regulador {reg_id} eliminado", "INFO")
    
    def _guardar_config_regulador(self):
        """Guarda la configuración del regulador seleccionado"""
        if not self.regulador_seleccionado:
            return
        
        reg = self.regulador_seleccionado
        reg.nombre = self.entry_nombre.get()
        reg.tipo_conexion = self.var_tipo_conexion.get()
        reg.ip = self.entry_ip.get()
        
        try:
            reg.puerto = int(self.entry_puerto.get())
        except:
            reg.puerto = 5000
        
        reg.puerto_com = self.combo_com.get()
        
        try:
            reg.baudrate = int(self.combo_baud.get())
        except:
            reg.baudrate = 9600
        
        reg.modo = 'A' if 'A' in self.combo_modo.get() else 'B'
        
        try:
            reg.num_grupos = int(self.combo_num_grupos.get())
        except:
            reg.num_grupos = 8
        
        try:
            reg.polling_intervalo_ms = int(self.entry_polling.get())
        except:
            reg.polling_intervalo_ms = 5000
        
        reg.habilitado = self.var_habilitado.get()
        
        self._actualizar_lista_reguladores()
        self._guardar_config()
        self._log(f"Configuración de {reg.nombre} guardada", "INFO")
    
    # =========================================================================
    # CONEXIÓN
    # =========================================================================
    
    def _conectar_regulador(self):
        """Conecta el regulador seleccionado"""
        if not self.regulador_seleccionado:
            messagebox.showwarning("Aviso", "Seleccione un regulador")
            return
        
        reg = self.regulador_seleccionado
        
        # Crear conexión si no existe
        if reg.id not in self.conexiones.conexiones:
            if reg.tipo_conexion == 'tcp':
                self.conexiones.agregar_tcp(reg.id, reg.nombre, reg.ip, reg.puerto)
            else:
                self.conexiones.agregar_serial(reg.id, reg.nombre, reg.puerto_com, reg.baudrate)
        
        # Conectar
        self._log(f"[{reg.id:03d}] Conectando a {reg.direccion}...", "INFO")
        
        def conectar_thread():
            if self.conexiones.conectar(reg.id):
                reg.estado_conexion = EstadoConexion.CONECTADO
                self._log(f"[{reg.id:03d}] Conectado a {reg.direccion}", "INFO")
                # Iniciar polling
                self._iniciar_polling(reg)
            else:
                reg.estado_conexion = EstadoConexion.ERROR
                conexion = self.conexiones.obtener(reg.id)
                error = conexion.ultimo_error if conexion else "Error desconocido"
                self._log(f"[{reg.id:03d}] Error: {error}", "ERROR")
            
            self.root.after(0, lambda: self._actualizar_estado_visual(reg))
            self.root.after(0, self._actualizar_lista_reguladores)
        
        threading.Thread(target=conectar_thread, daemon=True).start()
    
    def _desconectar_regulador(self):
        """Desconecta el regulador seleccionado"""
        if not self.regulador_seleccionado:
            return
        
        reg = self.regulador_seleccionado
        self._detener_polling(reg.id)
        self.conexiones.desconectar(reg.id)
        reg.estado_conexion = EstadoConexion.DESCONECTADO
        self._actualizar_estado_visual(reg)
        self._actualizar_lista_reguladores()
        self._log(f"[{reg.id:03d}] Desconectado", "INFO")
    
    def _conectar_todos(self):
        """Conecta todos los reguladores habilitados"""
        for reg in self.gestor_reguladores.obtener_habilitados():
            self.regulador_seleccionado = reg
            self._conectar_regulador()
    
    def _desconectar_todos(self):
        """Desconecta todos los reguladores"""
        for reg_id in list(self.polling_threads.keys()):
            self._detener_polling(reg_id)
        
        self.conexiones.desconectar_todos()
        
        for reg in self.gestor_reguladores.listar():
            reg.estado_conexion = EstadoConexion.DESCONECTADO
        
        self._actualizar_lista_reguladores()
        self._log("Todos los reguladores desconectados", "INFO")
    
    # =========================================================================
    # POLLING
    # =========================================================================
    
    def _iniciar_polling(self, reg: EstadoRegulador):
        """Inicia el polling para un regulador"""
        if reg.id in self.polling_threads:
            return  # Ya existe
        
        self.polling_activo = True
        
        def polling_loop():
            poll_count = 0
            hora_sincronizada = False  # Flag para sincronizar hora
            modo_ordenador_solicitado = False  # Flag para solicitar modo ORDENADOR
            # Con polling de 5s: 36 polls = 3 min, 60 polls = 5 min, 360 polls = 30 min
            
            while self.polling_activo and reg.conectado:
                try:
                    poll_count += 1
                    
                    # Primer poll: consultar modo de control y solicitar cambio a ORDENADOR
                    if poll_count == 1:
                        # Consultar modo actual
                        self._enviar_comando(reg, self.protocolo.msg_consulta_modo_control())
                        time.sleep(0.3)
                        
                        # Automáticamente solicitar cambio a ORDENADOR
                        self._log(f"[{reg.id:03d}] 📡 Solicitando modo ORDENADOR automáticamente...", "INFO")
                        self._enviar_comando(reg, self.protocolo.msg_modo_ordenador())
                        time.sleep(0.3)
                        modo_ordenador_solicitado = True
                        
                        # Re-consultar modo para ver si cambió
                        self._enviar_comando(reg, self.protocolo.msg_consulta_modo_control())
                        time.sleep(0.3)
                    
                    # Sincronización de hora inteligente:
                    # - Primera conexión: inmediatamente (después de solicitar modo ORDENADOR)
                    # - Primeros 30 min (360 polls): cada 3 min (36 polls)
                    # - Después: cada 5 min (60 polls)
                    # NOTA: Solo sincroniza hora si está en modo ORDENADOR
                    if not hora_sincronizada:
                        # Verificar si está en modo ORDENADOR antes de sincronizar hora
                        if reg.modo_control == ModoControl.ORDENADOR or poll_count == 1:
                            now = datetime.now()
                            msg_hora = self.protocolo.msg_puesta_hora(now.hour, now.minute, now.second, now.day, now.month, now.year % 100)
                            self._enviar_comando(reg, msg_hora)
                            if reg.modo_control == ModoControl.ORDENADOR:
                                self._log(f"[{reg.id:03d}] 🕐 Hora sincronizada: {now.strftime('%H:%M:%S')}", "INFO")
                            else:
                                self._log(f"[{reg.id:03d}] ⚠️ Hora enviada pero regulador en modo {reg.modo_control_texto} - puede no aplicarse", "WARNING")
                            time.sleep(0.3)
                            hora_sincronizada = True
                        elif reg.modo_control == ModoControl.LOCAL:
                            # En modo LOCAL, no insistir con la hora
                            self._log(f"[{reg.id:03d}] ⚠️ Regulador en modo LOCAL - hora no sincronizada", "WARNING")
                            hora_sincronizada = True  # Marcar como "sincronizada" para no insistir
                    
                    # Siempre enviar sincronización (0x91) - obtiene hora, plan, ciclo
                    self._enviar_comando(reg, self.protocolo.msg_sincronizacion())
                    time.sleep(0.3)  # Pequeña pausa entre comandos
                    
                    # Cada 2 polls, solicitar datos de tráfico (0x94) - incluye estado repr
                    if poll_count % 2 == 0:
                        self._enviar_comando(reg, self.protocolo.msg_datos_trafico())
                        time.sleep(0.3)
                    
                    # Cada 3 polls, solicitar alarmas (0xB4)
                    if poll_count % 3 == 0:
                        self._enviar_comando(reg, self.protocolo.msg_estado_alarmas())
                        time.sleep(0.3)
                    
                    # Cada 4 polls, solicitar estado de grupos (0xB9) - COLORES
                    if poll_count % 4 == 0:
                        self._enviar_comando(reg, self.protocolo.msg_estado_grupos())
                        time.sleep(0.3)
                    
                    # Cada 5 polls, consultar modo de control (0xB3)
                    if poll_count % 5 == 0:
                        self._enviar_comando(reg, self.protocolo.msg_consulta_modo_control())
                        time.sleep(0.3)
                    
                    # Re-sincronizar hora según el tiempo transcurrido
                    if poll_count <= 360:  # Primeros 30 minutos
                        # Cada 3 minutos (36 polls)
                        if poll_count % 36 == 0:
                            hora_sincronizada = False
                    else:  # Después de 30 minutos
                        # Cada 5 minutos (60 polls)
                        if poll_count % 60 == 0:
                            hora_sincronizada = False
                    
                    time.sleep(reg.polling_intervalo_ms / 1000.0)
                except Exception as e:
                    logger.error(f"Error en polling {reg.id}: {e}")
                    break
        
        thread = threading.Thread(target=polling_loop, daemon=True)
        self.polling_threads[reg.id] = thread
        thread.start()
    
    def _detener_polling(self, reg_id: int):
        """Detiene el polling de un regulador"""
        if reg_id in self.polling_threads:
            del self.polling_threads[reg_id]
    
    # =========================================================================
    # COMANDOS
    # =========================================================================
    
    def _obtener_lock_regulador(self, reg_id: int) -> threading.Lock:
        """Obtiene o crea un lock para un regulador específico"""
        with self._reg_locks_lock:
            if reg_id not in self._reg_locks:
                self._reg_locks[reg_id] = threading.Lock()
            return self._reg_locks[reg_id]
    
    def _enviar_comando(self, reg: EstadoRegulador, mensaje: bytes):
        """Envía un comando a un regulador y procesa la respuesta (thread-safe)"""
        conexion = self.conexiones.obtener(reg.id)
        if not conexion or not conexion.conectado:
            self._log(f"[{reg.id:03d}] No conectado", "WARNING")
            logger.warning(f"[{reg.id:03d}] No conectado para enviar comando")
            return
        
        # Obtener lock para este regulador (serializa comandos)
        lock = self._obtener_lock_regulador(reg.id)
        
        with lock:  # Solo un comando a la vez por regulador
            # Log TX detallado
            tx_msg = f"[{reg.id:03d}] TX → {self.protocolo.formatear_mensaje(mensaje)} | Raw: {mensaje.hex()}"
            self._log(tx_msg, "TX")
            logger.info(tx_msg)
            
            # Enviar
            if conexion.enviar(mensaje):
                reg.mensajes_enviados += 1
                
                # Procesar TODOS los mensajes pendientes en la cola (incluyendo espontáneos B9)
                # Primera respuesta con timeout largo
                respuesta = conexion.recibir(timeout=2.0)
                while respuesta:
                    reg.mensajes_recibidos += 1
                    
                    # Decodificar
                    msg_dec = self.decodificador.decodificar(respuesta)
                    rx_msg = f"[{reg.id:03d}] RX ← {self.decodificador.formatear_mensaje(msg_dec)} | Raw: {respuesta.hex()}"
                    self._log(rx_msg, "RX")
                    logger.info(rx_msg)
                    
                    # Actualizar estado según tipo de mensaje
                    self._procesar_respuesta(reg, msg_dec)
                    
                    # Intentar recibir más mensajes con timeout corto (espontáneos)
                    respuesta = conexion.recibir(timeout=0.1)
            else:
                logger.error(f"[{reg.id:03d}] Error al enviar mensaje: {conexion.ultimo_error}")
    
    def _procesar_respuesta(self, reg: EstadoRegulador, msg):
        """Procesa una respuesta decodificada"""
        if not msg.valido:
            logger.warning(f"Mensaje inválido recibido: {msg.error}")
            return
        
        logger.debug(f"Procesando respuesta código=0x{msg.codigo:02X} datos={msg.datos}")
        
        if msg.codigo == 0x91:  # Sincronización
            logger.info(f"[{reg.id:03d}] 0x91 Sync: plan={msg.datos.get('plan')}, fase={msg.datos.get('fase_actual')}, ciclo={msg.datos.get('segundos_ciclo')}")
            reg.actualizar_desde_sincronizacion(msg.datos)
        
        elif msg.codigo == 0xB9:  # Estado de grupos
            if 'grupos' in msg.datos:
                logger.info(f"[{reg.id:03d}] 0xB9 Grupos: {len(msg.datos['grupos'])} grupos")
                reg.actualizar_grupos(msg.datos['grupos'])
        
        elif msg.codigo == 0xB4:  # Alarmas
            if 'alarmas' in msg.datos:
                reg.actualizar_alarmas(msg.datos['alarmas'])
                # Guardar grupos con fallo si vienen en el mensaje
                if 'grupos_con_fallo' in msg.datos:
                    reg.alarmas.grupos_con_fallo = msg.datos['grupos_con_fallo']
                    if msg.datos['grupos_con_fallo']:
                        logger.info(f"[{reg.id:03d}] 0xB4 Grupos con fallo: {msg.datos['grupos_con_fallo']}")
        
        elif msg.codigo == 0xB6:  # Grupos averiados (detalle)
            if 'grupos_averiados' in msg.datos:
                reg.alarmas.grupos_averiados = msg.datos['grupos_averiados']
                for ga in msg.datos['grupos_averiados']:
                    logger.info(f"[{reg.id:03d}] 0xB6 {ga['descripcion']}")
        
        elif msg.codigo == 0xB3:  # Cambio/consulta modo de control
            if 'modo_control' in msg.datos:
                modo_valor = msg.datos['modo_control']
                # Ignorar si hubo error de formato (respuesta inválida del regulador)
                if msg.datos.get('error_formato'):
                    logger.warning(f"[{reg.id:03d}] 0xB3 Respuesta con formato inválido - ignorada")
                elif modo_valor >= 0:
                    try:
                        reg.modo_control = ModoControl(modo_valor)
                    except ValueError:
                        reg.modo_control = ModoControl.DESCONOCIDO
                    logger.info(f"[{reg.id:03d}] 0xB3 Modo control: {reg.modo_control_texto}")
            if 'estado_repr' in msg.datos and not msg.datos.get('error_formato'):
                try:
                    reg.estado_repr = EstadoRepresentacion(msg.datos['estado_repr'])
                except ValueError:
                    pass
        
        elif msg.codigo == 0x94:  # Datos tráfico
            if 'estado_repr' in msg.datos:
                reg.estado_repr = EstadoRepresentacion(msg.datos['estado_repr'])
            # NOTA: El regulador NO envía grupos en 0x94, los envía en 0xB9
        
        # Actualizar GUI y lista de reguladores
        self.root.after(0, self._actualizar_lista_reguladores)
        if self.regulador_seleccionado and self.regulador_seleccionado.id == reg.id:
            self.root.after(0, lambda: self._actualizar_estado_visual(reg))
    
    def _cmd_cambiar_plan(self):
        """Comando: Cambiar plan"""
        if not self.regulador_seleccionado:
            return
        
        try:
            plan = int(self.combo_plan.get())
            msg = self.protocolo.msg_seleccion_plan(plan)
            self._enviar_comando(self.regulador_seleccionado, msg)
        except ValueError:
            messagebox.showerror("Error", "Plan inválido")
    
    def _cmd_intermitente(self):
        """Comando: Modo intermitente"""
        if not self.regulador_seleccionado:
            return
        msg = self.protocolo.msg_intermitente()
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_apagar(self):
        """Comando: Apagar"""
        if not self.regulador_seleccionado:
            return
        msg = self.protocolo.msg_apagar()
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_colores(self):
        """Comando: Modo colores (normal)"""
        if not self.regulador_seleccionado:
            return
        msg = self.protocolo.msg_colores()
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_puesta_hora(self):
        """Comando: Puesta en hora"""
        if not self.regulador_seleccionado:
            return
        now = datetime.now()
        msg = self.protocolo.msg_puesta_hora(now.hour, now.minute, now.second, now.day, now.month, now.year % 100)
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_solicitar_estado(self):
        """Comando: Solicitar estado"""
        if not self.regulador_seleccionado:
            return
        msg = self.protocolo.msg_estado_alarmas()
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_borrar_alarmas(self):
        """Comando: Borrar alarmas"""
        if not self.regulador_seleccionado:
            return
        msg = self.protocolo.msg_borrar_alarmas()
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_cambiar_modo(self):
        """Comando: Cambiar modo de control (LOCAL <-> ORDENADOR)"""
        if not self.regulador_seleccionado:
            messagebox.showwarning("Aviso", "Seleccione un regulador")
            return
        
        reg = self.regulador_seleccionado
        
        # Determinar el nuevo modo
        if reg.modo_control == ModoControl.LOCAL:
            # Cambiar a ORDENADOR
            msg = self.protocolo.msg_modo_ordenador()
            nuevo_modo = "ORDENADOR"
        else:
            # Cambiar a LOCAL (o si es desconocido, probar ORDENADOR)
            if reg.modo_control == ModoControl.DESCONOCIDO:
                msg = self.protocolo.msg_modo_ordenador()
                nuevo_modo = "ORDENADOR"
            else:
                msg = self.protocolo.msg_modo_local()
                nuevo_modo = "LOCAL"
        
        self._log(f"[{reg.id:03d}] 🔄 Solicitando cambio a modo {nuevo_modo}", "INFO")
        self._enviar_comando(reg, msg)
        
        # Consultar el modo actual después de un breve retardo
        def consultar_modo():
            time.sleep(0.5)
            self._enviar_comando(reg, self.protocolo.msg_consulta_modo_control())
        
        threading.Thread(target=consultar_modo, daemon=True).start()
    
    def _cmd_consultar_modo(self):
        """Comando: Consultar modo de control actual"""
        if not self.regulador_seleccionado:
            return
        msg = self.protocolo.msg_consulta_modo_control()
        self._enviar_comando(self.regulador_seleccionado, msg)
    
    def _cmd_bloque_plan(self):
        """Comando en bloque: Cambiar plan a todos"""
        try:
            plan = int(self.combo_plan.get())
        except:
            return
        
        for reg in self._obtener_reguladores_destino():
            msg = self.protocolo.msg_seleccion_plan(plan)
            threading.Thread(target=self._enviar_comando, args=(reg, msg), daemon=True).start()
    
    def _cmd_bloque_intermitente(self):
        """Comando en bloque: Intermitente a todos"""
        for reg in self._obtener_reguladores_destino():
            msg = self.protocolo.msg_intermitente()
            threading.Thread(target=self._enviar_comando, args=(reg, msg), daemon=True).start()
    
    def _cmd_bloque_apagar(self):
        """Comando en bloque: Apagar todos"""
        for reg in self._obtener_reguladores_destino():
            msg = self.protocolo.msg_apagar()
            threading.Thread(target=self._enviar_comando, args=(reg, msg), daemon=True).start()
    
    def _cmd_bloque_hora(self):
        """Comando en bloque: Puesta en hora global"""
        now = datetime.now()
        for reg in self._obtener_reguladores_destino():
            msg = self.protocolo.msg_puesta_hora(now.hour, now.minute, now.second, now.day, now.month, now.year % 100)
            threading.Thread(target=self._enviar_comando, args=(reg, msg), daemon=True).start()
    
    def _obtener_reguladores_destino(self):
        """Obtiene la lista de reguladores según el selector de destino"""
        destino = self.combo_destino.get()
        
        if destino == 'Solo conectados':
            return self.gestor_reguladores.obtener_conectados()
        elif destino == 'Seleccionados' and self.regulador_seleccionado:
            return [self.regulador_seleccionado]
        else:
            return self.gestor_reguladores.obtener_habilitados()
    
    # =========================================================================
    # LOG
    # =========================================================================
    
    def _log(self, mensaje: str, nivel: str = "INFO"):
        """Agrega un mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_queue.put((f"{timestamp} {mensaje}", nivel))
    
    def _actualizar_reloj_sistema(self):
        """Actualiza el reloj del sistema en la GUI"""
        try:
            hora_actual = datetime.now().strftime("%H:%M:%S")
            self.lbl_hora_sistema.config(text=f"🕐 Hora Sistema: {hora_actual}")
        except Exception:
            pass
        # Actualizar cada segundo
        self.root.after(1000, self._actualizar_reloj_sistema)
    
    def _procesar_logs(self):
        """Procesa la cola de logs y actualiza los widgets de log"""
        try:
            while True:
                mensaje, nivel = self.log_queue.get_nowait()
                
                # Log principal (compacto)
                self.log_text.configure(state='normal')
                self.log_text.insert('end', mensaje + '\n', nivel)
                
                # Limitar líneas
                max_lines = self.config.get('gui', {}).get('log_max_lines', 500)
                lines = int(self.log_text.index('end-1c').split('.')[0])
                if lines > max_lines:
                    self.log_text.delete('1.0', f'{lines - max_lines}.0')
                
                self.log_text.configure(state='disabled')
                
                if self.var_auto_scroll.get():
                    self.log_text.see('end')
                
                # Log externo (si existe)
                if self.log_window and self.log_window.winfo_exists():
                    if hasattr(self, 'log_text_ext'):
                        self.log_text_ext.configure(state='normal')
                        self.log_text_ext.insert('end', mensaje + '\n', nivel)
                        self.log_text_ext.configure(state='disabled')
                        
                        if hasattr(self, 'var_auto_scroll_ext') and self.var_auto_scroll_ext.get():
                            self.log_text_ext.see('end')
                        
                        # Actualizar contador
                        if hasattr(self, 'lbl_log_status'):
                            lines_ext = int(self.log_text_ext.index('end-1c').split('.')[0])
                            self.lbl_log_status.config(text=f"Líneas: {lines_ext}")
                
        except queue.Empty:
            pass
        
        self.root.after(100, self._procesar_logs)
    
    def _limpiar_log(self):
        """Limpia el log principal"""
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')


def main():
    """Función principal"""
    root = tk.Tk()
    app = CentralGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
