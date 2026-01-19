#!/usr/bin/env python3
"""
INTERFAZ GRÁFICA DEL REGULADOR VIRTUAL UNE
Permite configurar, iniciar y monitorear el regulador virtual
Versión 1.11.0 - Modo intermitente completo con reporte a central
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

# Configuración global de logging con archivo único por sesión
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Crear nombre de archivo con timestamp único
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(log_dir, f'regulador_{timestamp}.log')

# Cola para enviar logs a la GUI
log_queue = queue.Queue()

# Handler personalizado que envía logs a la GUI
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(('log_detallado', msg))
        except Exception:
            self.handleError(record)

# Crear logger principal
logger = logging.getLogger('ReguladorUNE')
logger.setLevel(logging.DEBUG)

# Handler para archivo con formato detallado
file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# Handler para consola con formato más simple
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
console_handler.setFormatter(console_formatter)

# Handler para enviar a GUI
gui_handler = QueueHandler(log_queue)
gui_handler.setLevel(logging.INFO)
gui_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
gui_handler.setFormatter(gui_formatter)

# Agregar handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.addHandler(gui_handler)

# Configurar logging para otros módulos
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[file_handler, console_handler, gui_handler]
)

logger.info("="*80)
logger.info("REGULADOR VIRTUAL UNE 135401-4 - INICIANDO")
logger.info(f"Log guardado en: {log_file}")
logger.info("="*80)

# Agregar directorio al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ============================================================================
# CÓDIGOS DE COLOR UNE
# ============================================================================
COLORES_UNE = {
    0: ("Apagado", "#333333"),
    1: ("Verde", "#00ff00"),
    2: ("Ámbar", "#ffaa00"),
    3: ("Rojo", "#ff0000"),
    4: ("Rojo Int.", "#ff0000"),
    5: ("Verde Int.", "#00ff00"),
    6: ("Ámbar Int.", "#ffaa00"),
    7: ("Rojo+Ámbar", "#ff5500"),
    8: ("Verde+Ámbar", "#88ff00")
}


class FasesFrame(ttk.LabelFrame):
    """Frame para configurar las fases (asignación de colores a grupos)"""
    
    def __init__(self, parent, config, on_config_change):
        super().__init__(parent, text="🎨 Fases (Colores por Grupo)", padding=10)
        self.config = config
        self.on_config_change = on_config_change
        self._crear_widgets()
    
    def _crear_widgets(self):
        # Información
        info_frame = ttk.Frame(self)
        info_frame.pack(fill='x', pady=5)
        
        ttk.Label(info_frame, text="Las FASES definen qué color muestra cada grupo en un momento dado.",
                  font=('Arial', 9, 'italic')).pack(anchor='w')
        ttk.Label(info_frame, text="Máximo 32 fases según UNE 135401-4. Colores: 0=Apagado, 1=Verde, 2=Ámbar, 3=Rojo, etc.",
                  font=('Arial', 8), foreground='gray').pack(anchor='w')
        
        # Treeview para mostrar fases
        columns = ('ID', 'Nombre', 'Grupos Verde', 'Grupos Rojo', 'Otros')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=8)
        
        self.tree.heading('ID', text='ID')
        self.tree.heading('Nombre', text='Nombre')
        self.tree.heading('Grupos Verde', text='Grupos Verde')
        self.tree.heading('Grupos Rojo', text='Grupos Rojo')
        self.tree.heading('Otros', text='Otros Estados')
        
        self.tree.column('ID', width=50, anchor='center')
        self.tree.column('Nombre', width=200)
        self.tree.column('Grupos Verde', width=120, anchor='center')
        self.tree.column('Grupos Rojo', width=120, anchor='center')
        self.tree.column('Otros', width=150, anchor='center')
        
        self.tree.pack(fill='both', expand=True, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self._cargar_fases()
        
        # Botones
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(btn_frame, text="➕ Nueva Fase", command=self._agregar_fase).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Editar Fase", command=self._editar_fase).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Eliminar Fase", command=self._eliminar_fase).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📋 Duplicar Fase", command=self._duplicar_fase).pack(side='left', padx=5)
    
    def _cargar_fases(self):
        """Carga las fases en el treeview"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        fases = self.config.get('fases', {}).get('lista', [])
        for fase in fases:
            grupos = fase.get('grupos', {})
            
            # Agrupar por color
            verdes = [g for g, c in grupos.items() if c == 1]
            rojos = [g for g, c in grupos.items() if c == 3]
            otros = [f"G{g}={c}" for g, c in grupos.items() if c not in [0, 1, 3]]
            
            self.tree.insert('', 'end', values=(
                fase['id'],
                fase.get('nombre', f"Fase {fase['id']}"),
                ', '.join(verdes) if verdes else '-',
                ', '.join(rojos) if rojos else '-',
                ', '.join(otros) if otros else '-'
            ))
    
    def _agregar_fase(self):
        """Agrega una nueva fase"""
        self._mostrar_dialogo_fase(None)
    
    def _editar_fase(self):
        """Edita la fase seleccionada"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona una fase para editar")
            return
        
        item = self.tree.item(selection[0])
        fase_id = item['values'][0]
        
        fases = self.config.get('fases', {}).get('lista', [])
        fase = next((f for f in fases if f['id'] == fase_id), None)
        
        if fase:
            self._mostrar_dialogo_fase(fase)
    
    def _eliminar_fase(self):
        """Elimina la fase seleccionada"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona una fase para eliminar")
            return
        
        if messagebox.askyesno("Confirmar", "¿Eliminar la fase seleccionada?\nAsegúrate de que no esté en uso por ninguna estructura."):
            item = self.tree.item(selection[0])
            fase_id = item['values'][0]
            
            fases = self.config.get('fases', {}).get('lista', [])
            self.config['fases']['lista'] = [f for f in fases if f['id'] != fase_id]
            self._cargar_fases()
            self.on_config_change()
    
    def _duplicar_fase(self):
        """Duplica la fase seleccionada"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona una fase para duplicar")
            return
        
        item = self.tree.item(selection[0])
        fase_id = item['values'][0]
        
        fases = self.config.get('fases', {}).get('lista', [])
        fase_orig = next((f for f in fases if f['id'] == fase_id), None)
        
        if fase_orig:
            # Calcular nuevo ID
            max_id = max(f['id'] for f in fases) if fases else 0
            nueva_fase = fase_orig.copy()
            nueva_fase['id'] = max_id + 1
            nueva_fase['nombre'] = f"{fase_orig.get('nombre', '')} (copia)"
            nueva_fase['grupos'] = fase_orig.get('grupos', {}).copy()
            
            fases.append(nueva_fase)
            self._cargar_fases()
            self.on_config_change()
    
    def _mostrar_dialogo_fase(self, fase):
        """Muestra diálogo para editar/crear fase"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Editar Fase" if fase else "Nueva Fase")
        dialogo.geometry("600x500")
        dialogo.transient(self)
        dialogo.grab_set()
        
        # Calcular siguiente ID
        fases = self.config.get('fases', {}).get('lista', [])
        if not fase:
            siguiente_id = max((f['id'] for f in fases), default=0) + 1
        else:
            siguiente_id = fase['id']
        
        # Frame superior
        top_frame = ttk.Frame(dialogo, padding=10)
        top_frame.pack(fill='x')
        
        ttk.Label(top_frame, text="ID:").grid(row=0, column=0, sticky='w', padx=5)
        entry_id = ttk.Entry(top_frame, width=10)
        entry_id.insert(0, str(siguiente_id))
        entry_id.grid(row=0, column=1, sticky='w', padx=5)
        
        ttk.Label(top_frame, text="Nombre:").grid(row=0, column=2, sticky='w', padx=5)
        entry_nombre = ttk.Entry(top_frame, width=30)
        entry_nombre.insert(0, fase.get('nombre', '') if fase else '')
        entry_nombre.grid(row=0, column=3, sticky='w', padx=5)
        
        # Leyenda de colores
        leyenda_frame = ttk.LabelFrame(dialogo, text="Códigos de Color UNE", padding=5)
        leyenda_frame.pack(fill='x', padx=10, pady=5)
        
        for i, (codigo, (nombre, color)) in enumerate(COLORES_UNE.items()):
            lbl = ttk.Label(leyenda_frame, text=f"{codigo}={nombre}", font=('Arial', 8))
            lbl.grid(row=0, column=i, padx=5)
        
        # Frame para grupos con scroll
        grupos_outer = ttk.LabelFrame(dialogo, text="Asignación de Colores por Grupo", padding=10)
        grupos_outer.pack(fill='both', expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(grupos_outer)
        scrollbar = ttk.Scrollbar(grupos_outer, orient="vertical", command=canvas.yview)
        grupos_frame = ttk.Frame(canvas)
        
        grupos_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=grupos_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Obtener grupos de config
        num_grupos = self.config.get('grupos', {}).get('cantidad', 6)
        grupos_desc = self.config.get('grupos', {}).get('descripcion', [])
        grupos_fase = fase.get('grupos', {}) if fase else {}
        
        grupo_combos = {}
        colores_valores = list(COLORES_UNE.keys())
        colores_nombres = [f"{k} - {v[0]}" for k, v in COLORES_UNE.items()]
        
        # Cabecera
        ttk.Label(grupos_frame, text="Grupo", font=('Arial', 9, 'bold'), width=25).grid(row=0, column=0, padx=5, pady=2)
        ttk.Label(grupos_frame, text="Tipo", font=('Arial', 9, 'bold'), width=10).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(grupos_frame, text="Color", font=('Arial', 9, 'bold'), width=15).grid(row=0, column=2, padx=5, pady=2)
        ttk.Label(grupos_frame, text="Vista", font=('Arial', 9, 'bold'), width=5).grid(row=0, column=3, padx=5, pady=2)
        
        preview_labels = {}
        
        for i in range(num_grupos):
            g_id = i + 1
            g_info = next((g for g in grupos_desc if g['id'] == g_id), {})
            g_nombre = g_info.get('nombre', f'Grupo {g_id}')
            g_tipo = g_info.get('tipo', 'vehicular')
            
            # Color actual (de string a int)
            color_actual = grupos_fase.get(str(g_id), 0)
            if isinstance(color_actual, str):
                color_actual = int(color_actual)
            
            row = i + 1
            
            # Nombre grupo
            icono = "🚗" if g_tipo == 'vehicular' else "🚶" if g_tipo == 'peatonal' else "🚴"
            ttk.Label(grupos_frame, text=f"{icono} G{g_id}: {g_nombre}").grid(row=row, column=0, sticky='w', padx=5, pady=2)
            
            # Tipo
            ttk.Label(grupos_frame, text=g_tipo).grid(row=row, column=1, padx=5, pady=2)
            
            # Combo color
            combo = ttk.Combobox(grupos_frame, values=colores_nombres, width=15, state='readonly')
            combo.current(color_actual if color_actual < len(colores_valores) else 0)
            combo.grid(row=row, column=2, padx=5, pady=2)
            grupo_combos[g_id] = combo
            
            # Preview
            preview = tk.Label(grupos_frame, text="  ●  ", font=('Arial', 12), 
                              bg=COLORES_UNE.get(color_actual, ("#333333", "#333333"))[1])
            preview.grid(row=row, column=3, padx=5, pady=2)
            preview_labels[g_id] = preview
            
            # Actualizar preview al cambiar color
            def hacer_update(combo_ref, label_ref):
                def update(*args):
                    try:
                        idx = combo_ref.current()
                        color_hex = COLORES_UNE.get(idx, ("#333333", "#333333"))[1]
                        label_ref.configure(bg=color_hex)
                    except:
                        pass
                return update
            
            combo.bind('<<ComboboxSelected>>', hacer_update(combo, preview))
        
        # Botones
        btn_frame = ttk.Frame(dialogo)
        btn_frame.pack(fill='x', pady=10, padx=10)
        
        def guardar():
            try:
                nueva_fase = {
                    'id': int(entry_id.get()),
                    'nombre': entry_nombre.get(),
                    'grupos': {}
                }
                
                for g_id, combo in grupo_combos.items():
                    color_idx = combo.current()
                    nueva_fase['grupos'][str(g_id)] = color_idx
                
                # Agregar o actualizar
                fases = self.config.get('fases', {}).get('lista', [])
                if 'fases' not in self.config:
                    self.config['fases'] = {'lista': []}
                
                if fase:
                    # Actualizar existente
                    for i, f in enumerate(fases):
                        if f['id'] == fase['id']:
                            fases[i] = nueva_fase
                            break
                else:
                    # Agregar nueva
                    fases.append(nueva_fase)
                
                self.config['fases']['lista'] = fases
                self._cargar_fases()
                self.on_config_change()
                dialogo.destroy()
                
            except ValueError as e:
                messagebox.showerror("Error", f"Valor inválido: {e}")
        
        ttk.Button(btn_frame, text="💾 Guardar", command=guardar).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="❌ Cancelar", command=dialogo.destroy).pack(side='left', padx=10)
    
    def get_config(self):
        return self.config


class EstructurasFrame(ttk.LabelFrame):
    """Frame para configurar las estructuras (secuencias de fases)"""
    
    def __init__(self, parent, config, on_config_change):
        super().__init__(parent, text="🔄 Estructuras (Secuencias de Fases)", padding=10)
        self.config = config
        self.on_config_change = on_config_change
        self._crear_widgets()
    
    def _crear_widgets(self):
        # Información
        info_frame = ttk.Frame(self)
        info_frame.pack(fill='x', pady=5)
        
        ttk.Label(info_frame, text="Las ESTRUCTURAS definen el orden de las fases y los transitorios entre ellas.",
                  font=('Arial', 9, 'italic')).pack(anchor='w')
        ttk.Label(info_frame, text="Los PLANES referencian estructuras. Varias planes pueden usar la misma estructura.",
                  font=('Arial', 8), foreground='gray').pack(anchor='w')
        
        # Treeview para mostrar estructuras
        columns = ('ID', 'Nombre', 'Secuencia', 'Descripción')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=6)
        
        self.tree.heading('ID', text='ID')
        self.tree.heading('Nombre', text='Nombre')
        self.tree.heading('Secuencia', text='Secuencia de Fases')
        self.tree.heading('Descripción', text='Descripción')
        
        self.tree.column('ID', width=50, anchor='center')
        self.tree.column('Nombre', width=180)
        self.tree.column('Secuencia', width=200)
        self.tree.column('Descripción', width=250)
        
        self.tree.pack(fill='both', expand=True, pady=5)
        
        self._cargar_estructuras()
        
        # Botones
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(btn_frame, text="➕ Nueva Estructura", command=self._agregar_estructura).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Editar Estructura", command=self._editar_estructura).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Eliminar Estructura", command=self._eliminar_estructura).pack(side='left', padx=5)
    
    def _cargar_estructuras(self):
        """Carga las estructuras en el treeview"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        estructuras = self.config.get('estructuras', {}).get('lista', [])
        for est in estructuras:
            secuencia = est.get('secuencia', [])
            
            # Formatear secuencia
            sec_str = []
            for paso in secuencia:
                if paso.get('tipo') == 'estable':
                    sec_str.append(f"F{paso.get('fase', '?')}")
                elif paso.get('tipo') == 'transitorio':
                    sec_str.append(f"→T{paso.get('transitorio', '?')}→")
            
            self.tree.insert('', 'end', values=(
                est['id'],
                est.get('nombre', f"Estructura {est['id']}"),
                ' '.join(sec_str),
                est.get('descripcion', '')[:50]
            ))
    
    def _agregar_estructura(self):
        self._mostrar_dialogo_estructura(None)
    
    def _editar_estructura(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona una estructura para editar")
            return
        
        item = self.tree.item(selection[0])
        est_id = item['values'][0]
        
        estructuras = self.config.get('estructuras', {}).get('lista', [])
        est = next((e for e in estructuras if e['id'] == est_id), None)
        
        if est:
            self._mostrar_dialogo_estructura(est)
    
    def _eliminar_estructura(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona una estructura para eliminar")
            return
        
        if messagebox.askyesno("Confirmar", "¿Eliminar la estructura seleccionada?\nAsegúrate de que ningún plan la esté usando."):
            item = self.tree.item(selection[0])
            est_id = item['values'][0]
            
            estructuras = self.config.get('estructuras', {}).get('lista', [])
            self.config['estructuras']['lista'] = [e for e in estructuras if e['id'] != est_id]
            self._cargar_estructuras()
            self.on_config_change()
    
    def _mostrar_dialogo_estructura(self, estructura):
        """Muestra diálogo para editar/crear estructura"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Editar Estructura" if estructura else "Nueva Estructura")
        dialogo.geometry("700x550")
        dialogo.transient(self)
        dialogo.grab_set()
        
        # Calcular siguiente ID
        estructuras = self.config.get('estructuras', {}).get('lista', [])
        if not estructura:
            siguiente_id = max((e['id'] for e in estructuras), default=0) + 1
        else:
            siguiente_id = estructura['id']
        
        # Info superior
        top_frame = ttk.Frame(dialogo, padding=10)
        top_frame.pack(fill='x')
        
        ttk.Label(top_frame, text="ID:").grid(row=0, column=0, sticky='w', padx=5)
        entry_id = ttk.Entry(top_frame, width=10)
        entry_id.insert(0, str(siguiente_id))
        entry_id.grid(row=0, column=1, sticky='w', padx=5)
        
        ttk.Label(top_frame, text="Nombre:").grid(row=0, column=2, sticky='w', padx=5)
        entry_nombre = ttk.Entry(top_frame, width=30)
        entry_nombre.insert(0, estructura.get('nombre', '') if estructura else '')
        entry_nombre.grid(row=0, column=3, sticky='w', padx=5)
        
        ttk.Label(top_frame, text="Descripción:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        entry_desc = ttk.Entry(top_frame, width=60)
        entry_desc.insert(0, estructura.get('descripcion', '') if estructura else '')
        entry_desc.grid(row=1, column=1, columnspan=3, sticky='ew', padx=5, pady=5)
        
        # Frame para secuencia
        sec_frame = ttk.LabelFrame(dialogo, text="Secuencia de Fases y Transitorios", padding=10)
        sec_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Lista de pasos
        columns = ('Orden', 'Tipo', 'Fase/Trans', 'Descripción')
        tree_sec = ttk.Treeview(sec_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            tree_sec.heading(col, text=col)
            tree_sec.column(col, width=120 if col != 'Descripción' else 200)
        
        tree_sec.pack(fill='both', expand=True, pady=5)
        
        # Cargar secuencia existente
        secuencia_actual = estructura.get('secuencia', []) if estructura else []
        
        def cargar_secuencia():
            for item in tree_sec.get_children():
                tree_sec.delete(item)
            for i, paso in enumerate(secuencia_actual):
                tipo = paso.get('tipo', 'estable')
                if tipo == 'estable':
                    ref = f"Fase {paso.get('fase', '?')}"
                else:
                    ref = f"Transitorio {paso.get('transitorio', '?')}"
                
                tree_sec.insert('', 'end', values=(i+1, tipo.capitalize(), ref, ''))
        
        cargar_secuencia()
        
        # Botones de edición de secuencia
        btn_sec_frame = ttk.Frame(sec_frame)
        btn_sec_frame.pack(fill='x', pady=5)
        
        # Obtener fases disponibles
        fases_disponibles = self.config.get('fases', {}).get('lista', [])
        fases_ids = [f"Fase {f['id']}" for f in fases_disponibles]
        
        ttk.Label(btn_sec_frame, text="Agregar:").pack(side='left', padx=5)
        
        combo_fase = ttk.Combobox(btn_sec_frame, values=fases_ids, width=15, state='readonly')
        if fases_ids:
            combo_fase.current(0)
        combo_fase.pack(side='left', padx=5)
        
        def agregar_fase():
            if not combo_fase.get():
                return
            fase_id = int(combo_fase.get().replace("Fase ", ""))
            secuencia_actual.append({'tipo': 'estable', 'fase': fase_id})
            cargar_secuencia()
        
        ttk.Button(btn_sec_frame, text="+ Fase", command=agregar_fase).pack(side='left', padx=5)
        
        def agregar_transitorio():
            # El transitorio toma el número según su posición
            num_trans = sum(1 for p in secuencia_actual if p.get('tipo') == 'transitorio') + 1
            secuencia_actual.append({'tipo': 'transitorio', 'transitorio': num_trans})
            cargar_secuencia()
        
        ttk.Button(btn_sec_frame, text="+ Transitorio", command=agregar_transitorio).pack(side='left', padx=5)
        
        def eliminar_paso():
            selection = tree_sec.selection()
            if selection:
                idx = tree_sec.index(selection[0])
                del secuencia_actual[idx]
                cargar_secuencia()
        
        ttk.Button(btn_sec_frame, text="🗑️ Eliminar", command=eliminar_paso).pack(side='left', padx=5)
        
        def mover_arriba():
            selection = tree_sec.selection()
            if selection:
                idx = tree_sec.index(selection[0])
                if idx > 0:
                    secuencia_actual[idx], secuencia_actual[idx-1] = secuencia_actual[idx-1], secuencia_actual[idx]
                    cargar_secuencia()
        
        def mover_abajo():
            selection = tree_sec.selection()
            if selection:
                idx = tree_sec.index(selection[0])
                if idx < len(secuencia_actual) - 1:
                    secuencia_actual[idx], secuencia_actual[idx+1] = secuencia_actual[idx+1], secuencia_actual[idx]
                    cargar_secuencia()
        
        ttk.Button(btn_sec_frame, text="⬆️", command=mover_arriba).pack(side='left', padx=2)
        ttk.Button(btn_sec_frame, text="⬇️", command=mover_abajo).pack(side='left', padx=2)
        
        # Botones principales
        btn_frame = ttk.Frame(dialogo)
        btn_frame.pack(fill='x', pady=10, padx=10)
        
        def guardar():
            try:
                nueva_estructura = {
                    'id': int(entry_id.get()),
                    'nombre': entry_nombre.get(),
                    'descripcion': entry_desc.get(),
                    'secuencia': secuencia_actual
                }
                
                if 'estructuras' not in self.config:
                    self.config['estructuras'] = {'lista': []}
                
                estructuras = self.config.get('estructuras', {}).get('lista', [])
                
                if estructura:
                    for i, e in enumerate(estructuras):
                        if e['id'] == estructura['id']:
                            estructuras[i] = nueva_estructura
                            break
                else:
                    estructuras.append(nueva_estructura)
                
                self.config['estructuras']['lista'] = estructuras
                self._cargar_estructuras()
                self.on_config_change()
                dialogo.destroy()
                
            except ValueError as e:
                messagebox.showerror("Error", f"Valor inválido: {e}")
        
        ttk.Button(btn_frame, text="💾 Guardar", command=guardar).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="❌ Cancelar", command=dialogo.destroy).pack(side='left', padx=10)
    
    def get_config(self):
        return self.config


class ConfiguracionFrame(ttk.LabelFrame):
    """Frame para mostrar y editar la configuración del regulador"""
    
    def __init__(self, parent, config, on_config_change):
        super().__init__(parent, text="⚙️ Configuración del Regulador", padding=10)
        self.config = config
        self.on_config_change = on_config_change
        self.entries = {}
        self._crear_widgets()
    
    def _crear_widgets(self):
        # Configuración general
        general_frame = ttk.LabelFrame(self, text="General", padding=5)
        general_frame.pack(fill='x', pady=5)
        
        reg_config = self.config.get('regulador', {})
        
        row = 0
        ttk.Label(general_frame, text="Puerto:").grid(row=row, column=0, sticky='w', padx=5)
        self.entries['puerto'] = ttk.Entry(general_frame, width=10)
        self.entries['puerto'].insert(0, str(reg_config.get('puerto_escucha', 19000)))
        self.entries['puerto'].grid(row=row, column=1, sticky='w', padx=5)
        
        ttk.Label(general_frame, text="Modo:").grid(row=row, column=2, sticky='w', padx=5)
        self.entries['modo'] = ttk.Combobox(general_frame, values=['A', 'B'], width=5, state='readonly')
        self.entries['modo'].set(reg_config.get('modo_operacion', 'A'))
        self.entries['modo'].grid(row=row, column=3, sticky='w', padx=5)
        
        row += 1
        ttk.Label(general_frame, text="Subregulador CPU:").grid(row=row, column=0, sticky='w', padx=5)
        sub_config = self.config.get('subreguladores', {})
        self.entries['sub_cpu'] = ttk.Entry(general_frame, width=10)
        self.entries['sub_cpu'].insert(0, str(sub_config.get('cpu_estado', 128)))
        self.entries['sub_cpu'].grid(row=row, column=1, sticky='w', padx=5)
        
        ttk.Label(general_frame, text="Subregulador Planes:").grid(row=row, column=2, sticky='w', padx=5)
        self.entries['sub_planes'] = ttk.Entry(general_frame, width=10)
        self.entries['sub_planes'].insert(0, str(sub_config.get('planes_sync', 129)))
        self.entries['sub_planes'].grid(row=row, column=3, sticky='w', padx=5)
        
        # Estado inicial
        estado_frame = ttk.LabelFrame(self, text="Estado Inicial", padding=5)
        estado_frame.pack(fill='x', pady=5)
        
        estado_config = self.config.get('estado_inicial', {})
        
        # Nota: Modo Control eliminado - El regulador siempre inicia en modo LOCAL
        # Solo cambia de modo cuando la central lo solicita mediante comando 0xD4
        
        ttk.Label(estado_frame, text="Estado Repr:").grid(row=0, column=0, sticky='w', padx=5)
        # Nota: Modo Control eliminado - El regulador siempre inicia en modo LOCAL
        # Solo cambia de modo cuando la central lo solicita mediante comando 0xD4
        
        self.entries['estado_repr'] = ttk.Combobox(estado_frame,
            values=['0 - Apagado', '1 - Intermitente', '2 - Colores'], width=15, state='readonly')
        estado_repr = estado_config.get('estado_representacion', 2)
        self.entries['estado_repr'].set(f"{estado_repr} - {'Apagado' if estado_repr == 0 else 'Intermitente' if estado_repr == 1 else 'Colores'}")
        self.entries['estado_repr'].grid(row=0, column=1, sticky='w', padx=5)
        
        ttk.Label(estado_frame, text="(Modo inicial: LOCAL)", font=('Arial', 8, 'italic'), 
                  foreground='gray').grid(row=0, column=2, sticky='w', padx=20)
        
        # Grupos
        grupos_frame = ttk.LabelFrame(self, text="Grupos", padding=5)
        grupos_frame.pack(fill='x', pady=5)
        
        grupos_config = self.config.get('grupos', {})
        
        ttk.Label(grupos_frame, text="Cantidad:").grid(row=0, column=0, sticky='w', padx=5)
        self.entries['num_grupos'] = ttk.Spinbox(grupos_frame, from_=1, to=32, width=5, state='normal')
        self.entries['num_grupos'].delete(0, 'end')
        self.entries['num_grupos'].insert(0, str(grupos_config.get('cantidad', 6)))
        self.entries['num_grupos'].grid(row=0, column=1, sticky='w', padx=5)
        
        # Grupos siempre en ámbar
        ttk.Label(grupos_frame, text="Grupos siempre ámbar:").grid(row=0, column=2, sticky='w', padx=5)
        grupos_ambar = [str(g['id']) for g in grupos_config.get('descripcion', []) if g.get('siempre_ambar', False)]
        self.entries['grupos_ambar'] = ttk.Entry(grupos_frame, width=15)
        self.entries['grupos_ambar'].insert(0, ', '.join(grupos_ambar))
        self.entries['grupos_ambar'].grid(row=0, column=3, sticky='w', padx=5)
        
        # Botón para editar grupos
        ttk.Button(grupos_frame, text="✏️ Editar Grupos", 
                   command=self._editar_grupos).grid(row=0, column=4, padx=10)
    
    def _editar_grupos(self):
        """Abre diálogo para editar la configuración de grupos"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Configuración de Grupos")
        dialogo.geometry("500x400")
        dialogo.transient(self)
        dialogo.grab_set()
        
        # Frame con scroll
        canvas = tk.Canvas(dialogo)
        scrollbar = ttk.Scrollbar(dialogo, orient="vertical", command=canvas.yview)
        frame_scroll = ttk.Frame(canvas)
        
        frame_scroll.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=frame_scroll, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Cabecera
        ttk.Label(frame_scroll, text="ID", width=5, font=('Arial', 9, 'bold')).grid(row=0, column=0, padx=2, pady=5)
        ttk.Label(frame_scroll, text="Nombre", width=25, font=('Arial', 9, 'bold')).grid(row=0, column=1, padx=2, pady=5)
        ttk.Label(frame_scroll, text="Tipo", width=12, font=('Arial', 9, 'bold')).grid(row=0, column=2, padx=2, pady=5)
        ttk.Label(frame_scroll, text="Siempre Ámbar", font=('Arial', 9, 'bold')).grid(row=0, column=3, padx=2, pady=5)
        
        grupos_config = self.config.get('grupos', {})
        num_grupos = grupos_config.get('cantidad', 6)
        descripcion = grupos_config.get('descripcion', [])
        
        # Asegurar que hay suficientes grupos
        while len(descripcion) < num_grupos:
            descripcion.append({
                'id': len(descripcion) + 1,
                'tipo': 'vehicular',
                'nombre': f'Grupo {len(descripcion) + 1}',
                'siempre_ambar': False
            })
        
        grupo_entries = []
        
        for i, grupo in enumerate(descripcion[:num_grupos]):
            row = i + 1
            
            # ID (solo lectura)
            ttk.Label(frame_scroll, text=str(grupo['id']), width=5).grid(row=row, column=0, padx=2, pady=2)
            
            # Nombre
            entry_nombre = ttk.Entry(frame_scroll, width=25)
            entry_nombre.insert(0, grupo.get('nombre', f"Grupo {grupo['id']}"))
            entry_nombre.grid(row=row, column=1, padx=2, pady=2)
            
            # Tipo
            combo_tipo = ttk.Combobox(frame_scroll, values=['vehicular', 'peatonal'], width=10, state='readonly')
            combo_tipo.set(grupo.get('tipo', 'vehicular'))
            combo_tipo.grid(row=row, column=2, padx=2, pady=2)
            
            # Siempre ámbar
            var_ambar = tk.BooleanVar(value=grupo.get('siempre_ambar', False))
            check_ambar = ttk.Checkbutton(frame_scroll, variable=var_ambar)
            check_ambar.grid(row=row, column=3, padx=2, pady=2)
            
            grupo_entries.append({
                'id': grupo['id'],
                'nombre': entry_nombre,
                'tipo': combo_tipo,
                'ambar': var_ambar
            })
        
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)
        
        def guardar_grupos():
            nueva_descripcion = []
            for entry in grupo_entries:
                nueva_descripcion.append({
                    'id': entry['id'],
                    'nombre': entry['nombre'].get(),
                    'tipo': entry['tipo'].get(),
                    'siempre_ambar': entry['ambar'].get()
                })
            
            self.config['grupos']['descripcion'] = nueva_descripcion
            
            # Actualizar el campo de grupos ámbar
            grupos_ambar = [str(g['id']) for g in nueva_descripcion if g['siempre_ambar']]
            self.entries['grupos_ambar'].delete(0, tk.END)
            self.entries['grupos_ambar'].insert(0, ', '.join(grupos_ambar))
            
            self.on_config_change()
            dialogo.destroy()
            messagebox.showinfo("Éxito", "Grupos actualizados")
        
        # Botones
        btn_frame = ttk.Frame(dialogo)
        btn_frame.pack(fill='x', pady=10)
        ttk.Button(btn_frame, text="Guardar", command=guardar_grupos).pack(side='left', padx=20)
        ttk.Button(btn_frame, text="Cancelar", command=dialogo.destroy).pack(side='left', padx=10)
    
    def get_config(self):
        """Obtiene la configuración actual de los widgets"""
        try:
            self.config['regulador']['puerto_escucha'] = int(self.entries['puerto'].get())
            self.config['regulador']['modo_operacion'] = self.entries['modo'].get()
            self.config['subreguladores']['cpu_estado'] = int(self.entries['sub_cpu'].get())
            self.config['subreguladores']['planes_sync'] = int(self.entries['sub_planes'].get())
            # Modo control eliminado - siempre inicia en LOCAL
            self.config['estado_inicial']['estado_representacion'] = int(self.entries['estado_repr'].get().split(' - ')[0])
            self.config['grupos']['cantidad'] = int(self.entries['num_grupos'].get())
            
            # Actualizar grupos siempre en ámbar
            grupos_ambar_str = self.entries['grupos_ambar'].get().strip()
            grupos_ambar_ids = []
            if grupos_ambar_str:
                grupos_ambar_ids = [int(x.strip()) for x in grupos_ambar_str.split(',') if x.strip()]
            
            # Actualizar la descripción de grupos
            num_grupos = int(self.entries['num_grupos'].get())
            descripcion_actual = self.config.get('grupos', {}).get('descripcion', [])
            
            # Ajustar cantidad de grupos si es necesario
            while len(descripcion_actual) < num_grupos:
                nuevo_id = len(descripcion_actual) + 1
                descripcion_actual.append({
                    "id": nuevo_id,
                    "tipo": "vehicular",
                    "nombre": f"Grupo {nuevo_id}",
                    "siempre_ambar": False
                })
            descripcion_actual = descripcion_actual[:num_grupos]
            
            # Actualizar flag siempre_ambar según el input
            for grupo in descripcion_actual:
                grupo['siempre_ambar'] = grupo['id'] in grupos_ambar_ids
            
            self.config['grupos']['descripcion'] = descripcion_actual
            
            return self.config
        except ValueError as e:
            messagebox.showerror("Error", f"Valor inválido: {e}")
            return None


class PlanesFrame(ttk.LabelFrame):
    """Frame para mostrar y editar los planes (nuevo modelo con estructuras)"""
    
    def __init__(self, parent, config, on_config_change):
        super().__init__(parent, text="📋 Planes (Referencian Estructuras)", padding=10)
        self.config = config
        self.on_config_change = on_config_change
        self._crear_widgets()
    
    def _crear_widgets(self):
        # Información
        info_frame = ttk.Frame(self)
        info_frame.pack(fill='x', pady=5)
        
        ttk.Label(info_frame, text="Los PLANES definen tiempos de ciclo y referencian una ESTRUCTURA.",
                  font=('Arial', 9, 'italic')).pack(anchor='w')
        ttk.Label(info_frame, text="IDs de planes: 130-255 según UNE 135401-4. Cada plan define la duración de cada fase.",
                  font=('Arial', 8), foreground='gray').pack(anchor='w')
        
        # Treeview para mostrar planes
        columns = ('ID', 'Nombre', 'Estructura', 'Ciclo', 'Duraciones', 'Horarios', 'Activo')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=8)
        
        self.tree.heading('ID', text='ID')
        self.tree.heading('Nombre', text='Nombre')
        self.tree.heading('Estructura', text='Estructura')
        self.tree.heading('Ciclo', text='Ciclo')
        self.tree.heading('Duraciones', text='Duraciones Fases')
        self.tree.heading('Horarios', text='Horarios')
        self.tree.heading('Activo', text='Act.')
        
        self.tree.column('ID', width=50, anchor='center')
        self.tree.column('Nombre', width=150)
        self.tree.column('Estructura', width=80, anchor='center')
        self.tree.column('Ciclo', width=60, anchor='center')
        self.tree.column('Duraciones', width=120, anchor='center')
        self.tree.column('Horarios', width=150)
        self.tree.column('Activo', width=40, anchor='center')
        
        self.tree.pack(fill='both', expand=True, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Cargar datos
        self._cargar_planes()
        
        # Botones
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(btn_frame, text="➕ Agregar Plan", command=self._agregar_plan).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✏️ Editar Plan", command=self._editar_plan).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🗑️ Eliminar Plan", command=self._eliminar_plan).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📋 Duplicar Plan", command=self._duplicar_plan).pack(side='left', padx=5)
        
        # Plan activo
        ttk.Label(btn_frame, text="Plan Activo:").pack(side='left', padx=(20, 5))
        planes_ids = [str(p['id']) for p in self.config.get('planes', {}).get('lista', [])]
        self.plan_activo_combo = ttk.Combobox(btn_frame, values=planes_ids, width=10, state='readonly')
        self.plan_activo_combo.set(str(self.config.get('planes', {}).get('plan_activo', 130)))
        self.plan_activo_combo.pack(side='left', padx=5)
        
        # Selección automática
        self.auto_var = tk.BooleanVar(value=self.config.get('planes', {}).get('seleccion_automatica', True))
        ttk.Checkbutton(btn_frame, text="Auto por horario", 
                       variable=self.auto_var).pack(side='left', padx=10)
    
    def _cargar_planes(self):
        """Carga los planes en el treeview"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        planes = self.config.get('planes', {}).get('lista', [])
        estructuras = self.config.get('estructuras', {}).get('lista', [])
        
        for plan in planes:
            horarios = plan.get('horarios', [])
            # Solo mostrar hora de inicio
            horarios_str = ', '.join([h.get('inicio', h.get('hora_inicio', '?')) for h in horarios])
            
            # Buscar nombre de estructura
            est_id = plan.get('estructura_id', plan.get('estructura', 1))
            est_nombre = next((e['nombre'] for e in estructuras if e['id'] == est_id), f"Est. {est_id}")
            
            # Formatear duraciones
            duraciones = plan.get('duraciones_fases', {})
            dur_str = ', '.join([f"F{k}:{v}s" for k, v in duraciones.items()])
            
            self.tree.insert('', 'end', values=(
                plan['id'],
                plan.get('nombre', ''),
                est_nombre[:15],
                plan.get('ciclo', 0),
                dur_str if dur_str else '-',
                horarios_str,
                '✓' if plan.get('activo', True) else '✗'
            ))
    
    def _agregar_plan(self):
        """Abre diálogo para agregar un plan"""
        self._mostrar_dialogo_plan(None)
    
    def _editar_plan(self):
        """Edita el plan seleccionado"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona un plan para editar")
            return
        
        item = self.tree.item(selection[0])
        plan_id = item['values'][0]
        
        planes = self.config.get('planes', {}).get('lista', [])
        plan = next((p for p in planes if p['id'] == plan_id), None)
        
        if plan:
            self._mostrar_dialogo_plan(plan)
    
    def _eliminar_plan(self):
        """Elimina el plan seleccionado"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona un plan para eliminar")
            return
        
        if messagebox.askyesno("Confirmar", "¿Eliminar el plan seleccionado?"):
            item = self.tree.item(selection[0])
            plan_id = item['values'][0]
            
            planes = self.config.get('planes', {}).get('lista', [])
            self.config['planes']['lista'] = [p for p in planes if p['id'] != plan_id]
            self._cargar_planes()
            self.on_config_change()
    
    def _duplicar_plan(self):
        """Duplica el plan seleccionado"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Aviso", "Selecciona un plan para duplicar")
            return
        
        item = self.tree.item(selection[0])
        plan_id = item['values'][0]
        
        planes = self.config.get('planes', {}).get('lista', [])
        plan_orig = next((p for p in planes if p['id'] == plan_id), None)
        
        if plan_orig:
            import copy
            nuevo_plan = copy.deepcopy(plan_orig)
            max_id = max(p['id'] for p in planes) if planes else 129
            nuevo_plan['id'] = max_id + 1
            nuevo_plan['nombre'] = f"{plan_orig.get('nombre', '')} (copia)"
            
            planes.append(nuevo_plan)
            self._cargar_planes()
            self.on_config_change()
    
    def _mostrar_dialogo_plan(self, plan):
        """Muestra diálogo para editar/crear plan con nuevo modelo"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Editar Plan" if plan else "Nuevo Plan")
        dialogo.geometry("650x700")
        dialogo.transient(self)
        dialogo.grab_set()
        
        entries = {}
        
        # Calcular siguiente ID automático para planes nuevos
        if not plan:
            planes_existentes = self.config.get('planes', {}).get('lista', [])
            if planes_existentes:
                max_id = max(p['id'] for p in planes_existentes)
                siguiente_id = max_id + 1
            else:
                siguiente_id = 130  # ID inicial por defecto
        else:
            siguiente_id = plan.get('id', 130)
        
        # Notebook con pestañas
        notebook = ttk.Notebook(dialogo)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # ========== PESTAÑA 1: GENERAL ==========
        tab_general = ttk.Frame(notebook, padding=10)
        notebook.add(tab_general, text="📋 General")
        
        # Campos básicos
        ttk.Label(tab_general, text="ID (130-255):").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        entries['id'] = ttk.Entry(tab_general, width=15)
        entries['id'].insert(0, str(siguiente_id))
        entries['id'].grid(row=0, column=1, sticky='w', padx=5, pady=3)
        
        ttk.Label(tab_general, text="Nombre:").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        entries['nombre'] = ttk.Entry(tab_general, width=30)
        entries['nombre'].insert(0, plan.get('nombre', '') if plan else '')
        entries['nombre'].grid(row=1, column=1, sticky='w', padx=5, pady=3)
        
        # Estructura (combo)
        ttk.Label(tab_general, text="Estructura:").grid(row=2, column=0, sticky='w', padx=5, pady=3)
        estructuras = self.config.get('estructuras', {}).get('lista', [])
        est_nombres = [f"{e['id']} - {e['nombre']}" for e in estructuras]
        entries['estructura'] = ttk.Combobox(tab_general, values=est_nombres, width=30, state='readonly')
        
        est_actual = plan.get('estructura_id', plan.get('estructura', 1)) if plan else 1
        for i, e in enumerate(estructuras):
            if e['id'] == est_actual:
                entries['estructura'].current(i)
                break
        entries['estructura'].grid(row=2, column=1, sticky='w', padx=5, pady=3)
        
        ttk.Label(tab_general, text="Ciclo total (seg):").grid(row=3, column=0, sticky='w', padx=5, pady=3)
        entries['ciclo'] = ttk.Spinbox(tab_general, from_=30, to=300, width=10)
        entries['ciclo'].set(plan.get('ciclo', 90) if plan else 90)
        entries['ciclo'].grid(row=3, column=1, sticky='w', padx=5, pady=3)
        
        ttk.Label(tab_general, text="Desfase (seg):").grid(row=4, column=0, sticky='w', padx=5, pady=3)
        entries['desfase'] = ttk.Spinbox(tab_general, from_=0, to=120, width=10)
        entries['desfase'].set(plan.get('desfase', 0) if plan else 0)
        entries['desfase'].grid(row=4, column=1, sticky='w', padx=5, pady=3)
        
        # Horarios (solo hora de inicio)
        ttk.Label(tab_general, text="Horas de inicio (HH:MM):").grid(
            row=5, column=0, columnspan=2, sticky='w', padx=5, pady=(15, 3))
        ttk.Label(tab_general, text="(Una por línea. Solo aplica en modo LOCAL)",
                  font=('Arial', 8), foreground='gray').grid(
            row=5, column=1, sticky='e', padx=5)
        
        horarios_text = tk.Text(tab_general, width=20, height=4)
        horarios_text.grid(row=6, column=0, columnspan=2, padx=5, pady=3, sticky='w')
        
        if plan and 'horarios' in plan:
            for h in plan['horarios']:
                # Mostrar solo hora de inicio
                hora = h.get('inicio', h.get('hora_inicio', ''))
                if hora:
                    horarios_text.insert('end', f"{hora}\n")
        
        # Activo
        activo_var = tk.BooleanVar(value=plan.get('activo', True) if plan else True)
        ttk.Checkbutton(tab_general, text="Plan Activo", variable=activo_var).grid(
            row=7, column=0, columnspan=2, padx=5, pady=10, sticky='w')
        
        # ========== PESTAÑA 2: DURACIONES DE FASES ==========
        tab_duraciones = ttk.Frame(notebook, padding=10)
        notebook.add(tab_duraciones, text="⏱️ Duraciones Fases")
        
        ttk.Label(tab_duraciones, text="Define la duración de cada fase de la estructura seleccionada:",
                  font=('Arial', 9)).pack(anchor='w', pady=(0, 10))
        
        # Frame para duraciones (se actualiza según estructura)
        duraciones_frame = ttk.LabelFrame(tab_duraciones, text="Duraciones por Fase", padding=10)
        duraciones_frame.pack(fill='both', expand=True)
        
        duracion_entries = {}
        duraciones_actuales = plan.get('duraciones_fases', {}) if plan else {}
        
        def actualizar_duraciones(*args):
            """Actualiza los campos de duración según la estructura seleccionada"""
            for widget in duraciones_frame.winfo_children():
                widget.destroy()
            
            duracion_entries.clear()
            
            # Obtener estructura seleccionada
            sel = entries['estructura'].get()
            if not sel:
                return
            
            est_id = int(sel.split(' - ')[0])
            est = next((e for e in estructuras if e['id'] == est_id), None)
            
            if not est:
                return
            
            # Obtener fases de la estructura
            fases_en_estructura = set()
            for paso in est.get('secuencia', []):
                if paso.get('tipo') == 'estable':
                    fases_en_estructura.add(paso.get('fase'))
            
            fases_lista = self.config.get('fases', {}).get('lista', [])
            
            row = 0
            for fase_id in sorted(fases_en_estructura):
                fase_info = next((f for f in fases_lista if f['id'] == fase_id), None)
                fase_nombre = fase_info.get('nombre', f'Fase {fase_id}') if fase_info else f'Fase {fase_id}'
                
                ttk.Label(duraciones_frame, text=f"Fase {fase_id}:").grid(
                    row=row, column=0, sticky='w', padx=5, pady=3)
                ttk.Label(duraciones_frame, text=fase_nombre, foreground='gray').grid(
                    row=row, column=1, sticky='w', padx=5, pady=3)
                
                spin = ttk.Spinbox(duraciones_frame, from_=5, to=120, width=8)
                dur_val = duraciones_actuales.get(str(fase_id), 30)
                spin.set(dur_val)
                spin.grid(row=row, column=2, sticky='w', padx=5, pady=3)
                ttk.Label(duraciones_frame, text="seg").grid(row=row, column=3, sticky='w', padx=2, pady=3)
                
                duracion_entries[fase_id] = spin
                row += 1
            
            if not fases_en_estructura:
                ttk.Label(duraciones_frame, text="Selecciona una estructura para ver sus fases").pack()
        
        entries['estructura'].bind('<<ComboboxSelected>>', actualizar_duraciones)
        actualizar_duraciones()  # Cargar inicial
        
        # ========== PESTAÑA 3: TRANSITORIOS ==========
        tab_trans = ttk.Frame(notebook, padding=10)
        notebook.add(tab_trans, text="🚦 Transitorios")
        
        # Cargar transitorios del plan o usar defaults
        trans_plan = plan.get('transitorios', {}) if plan else {}
        trans_veh = trans_plan.get('vehicular', {'tiempo_ambar': 3, 'tiempo_rojo_seguridad': 2})
        trans_pea = trans_plan.get('peatonal', {'tiempo_verde_intermitente': 5, 'tiempo_rojo': 2})
        trans_cic = trans_plan.get('ciclista', {'tiempo_ambar': 3, 'tiempo_rojo_seguridad': 2})
        
        # Frame vehicular
        frame_veh = ttk.LabelFrame(tab_trans, text="🚗 Grupos Vehiculares", padding=10)
        frame_veh.pack(fill='x', pady=5)
        
        ttk.Label(frame_veh, text="Tiempo ámbar:").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        entries['trans_veh_ambar'] = ttk.Spinbox(frame_veh, from_=1, to=10, width=8)
        entries['trans_veh_ambar'].set(trans_veh.get('tiempo_ambar', 3))
        entries['trans_veh_ambar'].grid(row=0, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(frame_veh, text="seg").grid(row=0, column=2, sticky='w')
        
        ttk.Label(frame_veh, text="Rojo seguridad:").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        entries['trans_veh_rojo'] = ttk.Spinbox(frame_veh, from_=1, to=10, width=8)
        entries['trans_veh_rojo'].set(trans_veh.get('tiempo_rojo_seguridad', 2))
        entries['trans_veh_rojo'].grid(row=1, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(frame_veh, text="seg").grid(row=1, column=2, sticky='w')
        
        # Frame peatonal
        frame_pea = ttk.LabelFrame(tab_trans, text="🚶 Grupos Peatonales", padding=10)
        frame_pea.pack(fill='x', pady=5)
        
        ttk.Label(frame_pea, text="Verde intermitente:").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        entries['trans_pea_verde'] = ttk.Spinbox(frame_pea, from_=1, to=15, width=8)
        entries['trans_pea_verde'].set(trans_pea.get('tiempo_verde_intermitente', 5))
        entries['trans_pea_verde'].grid(row=0, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(frame_pea, text="seg").grid(row=0, column=2, sticky='w')
        
        ttk.Label(frame_pea, text="Tiempo rojo:").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        entries['trans_pea_rojo'] = ttk.Spinbox(frame_pea, from_=1, to=10, width=8)
        entries['trans_pea_rojo'].set(trans_pea.get('tiempo_rojo', 2))
        entries['trans_pea_rojo'].grid(row=1, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(frame_pea, text="seg").grid(row=1, column=2, sticky='w')
        
        # Frame ciclista
        frame_cic = ttk.LabelFrame(tab_trans, text="🚴 Grupos Ciclistas", padding=10)
        frame_cic.pack(fill='x', pady=5)
        
        ttk.Label(frame_cic, text="Tiempo ámbar:").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        entries['trans_cic_ambar'] = ttk.Spinbox(frame_cic, from_=1, to=10, width=8)
        entries['trans_cic_ambar'].set(trans_cic.get('tiempo_ambar', 3))
        entries['trans_cic_ambar'].grid(row=0, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(frame_cic, text="seg").grid(row=0, column=2, sticky='w')
        
        ttk.Label(frame_cic, text="Rojo seguridad:").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        entries['trans_cic_rojo'] = ttk.Spinbox(frame_cic, from_=1, to=10, width=8)
        entries['trans_cic_rojo'].set(trans_cic.get('tiempo_rojo_seguridad', 2))
        entries['trans_cic_rojo'].grid(row=1, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(frame_cic, text="seg").grid(row=1, column=2, sticky='w')
        
        # ========== PESTAÑA 4: TIMELINE VISUAL ==========
        tab_timeline = ttk.Frame(notebook, padding=10)
        notebook.add(tab_timeline, text="📊 Timeline")
        
        ttk.Label(tab_timeline, text="Vista del ciclo completo - Una barra por grupo:",
                  font=('Arial', 9, 'bold')).pack(anchor='w', pady=(0, 5))
        
        # Canvas para el timeline unificado (más alto para incluir todos los grupos)
        timeline_canvas = tk.Canvas(tab_timeline, height=280, bg='white', relief='sunken', bd=1)
        timeline_canvas.pack(fill='both', expand=True, pady=5)
        
        def dibujar_timeline(*args):
            """Dibuja el timeline visual del plan con una barra por grupo"""
            timeline_canvas.delete("all")
            
            # Obtener estructura seleccionada
            sel = entries['estructura'].get()
            if not sel:
                return
            
            est_id = int(sel.split(' - ')[0])
            est = next((e for e in estructuras if e['id'] == est_id), None)
            if not est:
                return
            
            secuencia = est.get('secuencia', [])
            fases_lista = self.config.get('fases', {}).get('lista', [])
            num_grupos = self.config.get('grupos', {}).get('cantidad', 4)
            grupos_desc = self.config.get('grupos', {}).get('descripcion', [])
            
            # Calcular tiempos de transitorios
            try:
                t_ambar = int(entries['trans_veh_ambar'].get())
                t_rojo = int(entries['trans_veh_rojo'].get())
            except:
                t_ambar, t_rojo = 3, 2
            tiempo_trans = t_ambar + t_rojo
            
            # Calcular segmentos y tiempo total
            total_tiempo = 0
            segmentos = []
            
            for paso in secuencia:
                if paso.get('tipo') == 'estable':
                    fase_id = paso.get('fase', 1)
                    try:
                        duracion = int(duracion_entries.get(fase_id, tk.StringVar()).get()) if fase_id in duracion_entries else 30
                    except:
                        duracion = 30
                    segmentos.append({
                        'tipo': 'fase',
                        'id': fase_id,
                        'duracion': duracion,
                        'inicio': total_tiempo
                    })
                    total_tiempo += duracion
                elif paso.get('tipo') == 'transitorio':
                    segmentos.append({
                        'tipo': 'transitorio',
                        'id': paso.get('transitorio', 1),
                        'duracion': tiempo_trans,
                        'inicio': total_tiempo,
                        't_ambar': t_ambar,
                        't_rojo': t_rojo
                    })
                    total_tiempo += tiempo_trans
            
            if total_tiempo == 0:
                total_tiempo = 120
            
            # Dimensiones
            canvas_width = timeline_canvas.winfo_width() or 600
            margin_left = 80  # Espacio para etiquetas de grupo
            margin_right = 20
            margin_top = 50
            bar_width = canvas_width - margin_left - margin_right
            bar_height = 30
            bar_spacing = 8
            
            # Colores para estados
            COLORES = {
                0: '#333333',   # Apagado
                1: '#00CC00',   # Verde
                2: '#FFCC00',   # Ámbar  
                3: '#CC0000',   # Rojo
                4: '#CC0000',   # Rojo Int
                5: '#00CC00',   # Verde Int
                6: '#FFCC00',   # Ámbar Int
            }
            
            # Título
            timeline_canvas.create_text(canvas_width/2, 15, 
                                       text=f"Ciclo: {total_tiempo} seg",
                                       font=('Arial', 11, 'bold'))
            
            # Dibujar escala de tiempo en la parte superior
            timeline_canvas.create_line(margin_left, margin_top - 5, 
                                        canvas_width - margin_right, margin_top - 5, 
                                        fill='gray')
            
            # Marcas de tiempo cada fase/transitorio
            x = margin_left
            tiempo_acum = 0
            for seg in segmentos:
                ancho = (seg['duracion'] / total_tiempo) * bar_width
                
                # Marca de inicio
                timeline_canvas.create_line(x, margin_top - 10, x, margin_top - 2, fill='gray')
                timeline_canvas.create_text(x, margin_top - 15, text=f"{tiempo_acum}s", 
                                           font=('Arial', 7), anchor='s')
                
                # Etiqueta del segmento
                if seg['tipo'] == 'fase':
                    timeline_canvas.create_text(x + ancho/2, margin_top - 15, 
                                               text=f"F{seg['id']} ({seg['duracion']}s)",
                                               font=('Arial', 8, 'bold'), fill='#2196F3')
                else:
                    timeline_canvas.create_text(x + ancho/2, margin_top - 15, 
                                               text=f"T{seg['id']}",
                                               font=('Arial', 7), fill='#FF9800')
                
                tiempo_acum += seg['duracion']
                x += ancho
            
            # Marca final
            timeline_canvas.create_line(x, margin_top - 10, x, margin_top - 2, fill='gray')
            timeline_canvas.create_text(x, margin_top - 15, text=f"{tiempo_acum}s", 
                                       font=('Arial', 7), anchor='s')
            
            # Dibujar barra por cada grupo
            for g_idx in range(num_grupos):
                g_id = g_idx + 1
                g_info = next((g for g in grupos_desc if g['id'] == g_id), {})
                g_nombre = g_info.get('nombre', f'Grupo {g_id}')
                g_tipo = g_info.get('tipo', 'vehicular')
                icono = "🚗" if g_tipo == 'vehicular' else "🚶" if g_tipo == 'peatonal' else "🚴"
                
                y = margin_top + g_idx * (bar_height + bar_spacing)
                
                # Etiqueta del grupo
                timeline_canvas.create_text(margin_left - 5, y + bar_height/2,
                                           text=f"{icono} G{g_id}",
                                           font=('Arial', 9, 'bold'), anchor='e')
                
                # Dibujar segmentos para este grupo
                x = margin_left
                estado_anterior = 3  # Por defecto rojo
                
                for seg in segmentos:
                    ancho = (seg['duracion'] / total_tiempo) * bar_width
                    
                    if seg['tipo'] == 'fase':
                        # Obtener estado del grupo en esta fase
                        fase_info = next((f for f in fases_lista if f['id'] == seg['id']), {})
                        grupos_fase = fase_info.get('grupos', {})
                        estado = grupos_fase.get(str(g_id), 3)  # Default rojo
                        
                        color = COLORES.get(estado, '#333333')
                        timeline_canvas.create_rectangle(x, y, x + ancho, y + bar_height,
                                                        fill=color, outline='black', width=1)
                        
                        estado_anterior = estado
                    else:
                        # Transitorio: mostrar ámbar luego rojo si estaba en verde
                        ancho_ambar = (seg['t_ambar'] / seg['duracion']) * ancho
                        ancho_rojo = (seg['t_rojo'] / seg['duracion']) * ancho
                        
                        if estado_anterior == 1:  # Estaba en verde -> ámbar -> rojo
                            timeline_canvas.create_rectangle(x, y, x + ancho_ambar, y + bar_height,
                                                            fill='#FFCC00', outline='black', width=1)
                            timeline_canvas.create_rectangle(x + ancho_ambar, y, x + ancho, y + bar_height,
                                                            fill='#CC0000', outline='black', width=1)
                        else:  # Estaba en rojo -> sigue rojo
                            timeline_canvas.create_rectangle(x, y, x + ancho, y + bar_height,
                                                            fill='#CC0000', outline='black', width=1)
                    
                    x += ancho
            
            # Leyenda de colores
            leyenda_y = margin_top + num_grupos * (bar_height + bar_spacing) + 15
            timeline_canvas.create_text(margin_left, leyenda_y, text="Leyenda:", 
                                       font=('Arial', 8, 'bold'), anchor='w')
            
            leyenda_items = [
                ('#00CC00', 'Verde'),
                ('#FFCC00', 'Ámbar'),
                ('#CC0000', 'Rojo'),
            ]
            
            x_ley = margin_left + 60
            for color, texto in leyenda_items:
                timeline_canvas.create_rectangle(x_ley, leyenda_y - 6, x_ley + 20, leyenda_y + 6,
                                                fill=color, outline='black')
                timeline_canvas.create_text(x_ley + 25, leyenda_y, text=texto,
                                           font=('Arial', 8), anchor='w')
                x_ley += 80
        
        # Vincular actualizaciones
        entries['estructura'].bind('<<ComboboxSelected>>', dibujar_timeline)
        entries['ciclo'].bind('<KeyRelease>', dibujar_timeline)
        entries['trans_veh_ambar'].bind('<KeyRelease>', dibujar_timeline)
        entries['trans_veh_rojo'].bind('<KeyRelease>', dibujar_timeline)
        
        # Dibujar al cambiar pestaña
        def on_tab_change(event):
            if notebook.index(notebook.select()) == 3:  # Pestaña Timeline
                dialogo.after(100, dibujar_timeline)
        notebook.bind('<<NotebookTabChanged>>', on_tab_change)
        
        # También vincular cambios en duraciones
        def vincular_duraciones(*args):
            for fase_id, spin in duracion_entries.items():
                spin.bind('<KeyRelease>', dibujar_timeline)
                spin.bind('<<Increment>>', dibujar_timeline)
                spin.bind('<<Decrement>>', dibujar_timeline)
        
        entries['estructura'].bind('<<ComboboxSelected>>', 
                                   lambda e: dialogo.after(200, vincular_duraciones))
        
        # ========== BOTONES ==========
        def guardar():
            try:
                # Obtener estructura seleccionada
                est_sel = entries['estructura'].get()
                est_id = int(est_sel.split(' - ')[0]) if est_sel else 1
                
                # Construir duraciones
                duraciones = {}
                for fase_id, spin in duracion_entries.items():
                    duraciones[str(fase_id)] = int(spin.get())
                
                nuevo_plan = {
                    'id': int(entries['id'].get()),
                    'nombre': entries['nombre'].get(),
                    'estructura_id': est_id,
                    'ciclo': int(entries['ciclo'].get()),
                    'desfase': int(entries['desfase'].get()),
                    'activo': activo_var.get(),
                    'duraciones_fases': duraciones,
                    'horarios': [],
                    'transitorios': {
                        'vehicular': {
                            'tiempo_ambar': int(entries['trans_veh_ambar'].get()),
                            'tiempo_rojo_seguridad': int(entries['trans_veh_rojo'].get())
                        },
                        'peatonal': {
                            'tiempo_verde_intermitente': int(entries['trans_pea_verde'].get()),
                            'tiempo_rojo': int(entries['trans_pea_rojo'].get())
                        },
                        'ciclista': {
                            'tiempo_ambar': int(entries['trans_cic_ambar'].get()),
                            'tiempo_rojo_seguridad': int(entries['trans_cic_rojo'].get())
                        }
                    }
                }
                
                # Parsear horarios (solo hora de inicio)
                horarios_raw = horarios_text.get('1.0', 'end').strip().split('\n')
                for h in horarios_raw:
                    hora = h.strip().replace('-', '').strip()  # Limpiar guiones si los hay
                    if hora and ':' in hora:
                        # Validar formato HH:MM
                        try:
                            hh, mm = hora.split(':')
                            if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
                                nuevo_plan['horarios'].append({
                                    'inicio': hora
                                })
                        except:
                            pass  # Ignorar formato inválido
                
                # Agregar o actualizar
                planes = self.config.get('planes', {}).get('lista', [])
                if plan:
                    for i, p in enumerate(planes):
                        if p['id'] == plan['id']:
                            planes[i] = nuevo_plan
                            break
                else:
                    planes.append(nuevo_plan)
                
                self.config['planes']['lista'] = planes
                self._cargar_planes()
                self.on_config_change()
                dialogo.destroy()
                
            except ValueError as e:
                messagebox.showerror("Error", f"Valor inválido: {e}")
        
        # Botones (fuera del notebook)
        btn_frame = ttk.Frame(dialogo)
        btn_frame.pack(fill='x', pady=10, padx=10)
        ttk.Button(btn_frame, text="💾 Guardar", command=guardar).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="❌ Cancelar", command=dialogo.destroy).pack(side='left', padx=10)
    
    def get_config(self):
        """Obtiene la configuración actualizada"""
        self.config['planes']['plan_activo'] = int(self.plan_activo_combo.get())
        self.config['planes']['seleccion_automatica'] = self.auto_var.get()
        return self.config


class MonitorFrame(ttk.LabelFrame):
    """Frame para monitorear el estado del regulador"""
    
    def __init__(self, parent, config=None):
        super().__init__(parent, text="📊 Monitor de Estado", padding=10)
        self.config = config or {}
        self.semaforos = {}  # Diccionario de canvas de semáforos
        self.luces = {}  # Diccionario de IDs de óvalos por grupo
        self._planes_dict = {}  # Diccionario id -> nombre de planes
        
        # Sistema de parpadeo para estados intermitentes
        self._estados_intermitentes = {}  # grupo_id -> color ('rojo', 'ambar', 'verde')
        self._parpadeo_visible = True  # Alterna entre True/False
        self._parpadeo_timer = None  # ID del timer de parpadeo
        
        self._cargar_planes_config()
        self._crear_widgets()
        
        # Iniciar timer de parpadeo (500ms = 2 Hz típico de intermitente)
        self._iniciar_parpadeo()
    
    def _cargar_planes_config(self):
        """Carga el diccionario de planes desde la configuración"""
        planes_cfg = self.config.get('planes', {})
        for plan in planes_cfg.get('lista', []):
            plan_id = plan.get('id')
            plan_nombre = plan.get('nombre', f'Plan {plan_id}')
            self._planes_dict[plan_id] = plan_nombre
    
    def _crear_widgets(self):
        # Estado actual
        estado_frame = ttk.Frame(self)
        estado_frame.pack(fill='x', pady=5)
        
        # Indicadores
        self.lbl_estado = ttk.Label(estado_frame, text="⚪ DETENIDO", font=('Arial', 14, 'bold'))
        self.lbl_estado.pack(side='left', padx=10)
        
        self.lbl_conexion = ttk.Label(estado_frame, text="Sin conexión")
        self.lbl_conexion.pack(side='left', padx=20)
        
        self.lbl_plan = ttk.Label(estado_frame, text="Plan: --")
        self.lbl_plan.pack(side='left', padx=20)
        
        self.lbl_fase = ttk.Label(estado_frame, text="Fase: --")
        self.lbl_fase.pack(side='left', padx=20)
        
        self.lbl_modo = ttk.Label(estado_frame, text="Modo: --")
        self.lbl_modo.pack(side='left', padx=20)
        
        # Variable para guardar el estado de conexión
        self._conexion_actual = None
        
        # ========== SEMÁFOROS GRÁFICOS ==========
        semaforos_frame = ttk.LabelFrame(self, text="🚦 Estado de Grupos", padding=10)
        semaforos_frame.pack(fill='x', pady=10)
        
        # Obtener configuración de grupos
        grupos_config = self.config.get('grupos', {})
        num_grupos = grupos_config.get('cantidad', 6)
        grupos_desc = grupos_config.get('descripcion', [])
        
        # Crear semáforos para cada grupo
        for g_idx in range(num_grupos):
            g_id = g_idx + 1
            g_info = next((g for g in grupos_desc if g['id'] == g_id), {})
            g_tipo = g_info.get('tipo', 'vehicular')
            g_nombre = g_info.get('nombre', f'Grupo {g_id}')
            
            # Frame para cada semáforo
            sem_frame = ttk.Frame(semaforos_frame)
            sem_frame.pack(side='left', padx=10, pady=5)
            
            # Icono de tipo
            icono = "🚗" if g_tipo == 'vehicular' else "🚶"
            ttk.Label(sem_frame, text=f"{icono} G{g_id}", font=('Arial', 10, 'bold')).pack()
            
            # Canvas para el semáforo
            if g_tipo == 'vehicular':
                # Semáforo vehicular: 3 luces verticales
                canvas = tk.Canvas(sem_frame, width=40, height=100, bg='#333333', 
                                   highlightthickness=2, highlightbackground='#666666')
                canvas.pack(pady=5)
                
                # Crear las 3 luces (apagadas inicialmente)
                luz_rojo = canvas.create_oval(8, 5, 32, 29, fill='#4a0000', outline='#222222')
                luz_ambar = canvas.create_oval(8, 35, 32, 59, fill='#4a4a00', outline='#222222')
                luz_verde = canvas.create_oval(8, 65, 32, 89, fill='#004a00', outline='#222222')
                
                self.luces[g_id] = {
                    'tipo': 'vehicular',
                    'canvas': canvas,
                    'rojo': luz_rojo,
                    'ambar': luz_ambar,
                    'verde': luz_verde
                }
            else:
                # Semáforo peatonal: 2 luces verticales
                canvas = tk.Canvas(sem_frame, width=40, height=70, bg='#333333',
                                   highlightthickness=2, highlightbackground='#666666')
                canvas.pack(pady=5)
                
                # Crear las 2 luces
                luz_rojo = canvas.create_oval(8, 5, 32, 29, fill='#4a0000', outline='#222222')
                luz_verde = canvas.create_oval(8, 35, 32, 59, fill='#004a00', outline='#222222')
                
                self.luces[g_id] = {
                    'tipo': 'peatonal',
                    'canvas': canvas,
                    'rojo': luz_rojo,
                    'verde': luz_verde
                }
            
            # Etiqueta de estado
            lbl_estado = ttk.Label(sem_frame, text="--", font=('Arial', 8))
            lbl_estado.pack()
            self.luces[g_id]['label'] = lbl_estado
        
        # Contador de ciclo
        ciclo_frame = ttk.Frame(semaforos_frame)
        ciclo_frame.pack(side='left', padx=30)
        
        ttk.Label(ciclo_frame, text="Ciclo:", font=('Arial', 10)).pack()
        self.lbl_ciclo = ttk.Label(ciclo_frame, text="0s", font=('Arial', 20, 'bold'))
        self.lbl_ciclo.pack()
        
        # Log de mensajes
        log_frame = ttk.LabelFrame(self, text="📝 Log de Comunicaciones", padding=5)
        log_frame.pack(fill='both', expand=True, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap='word', 
                                                   font=('Consolas', 9))
        self.log_text.pack(fill='both', expand=True)
        self.log_text.configure(state='disabled')
        
        # Configurar tags para colores
        self.log_text.tag_configure('enviado', foreground='blue')
        self.log_text.tag_configure('recibido', foreground='green')
        self.log_text.tag_configure('error', foreground='red')
        self.log_text.tag_configure('info', foreground='gray')
        self.log_text.tag_configure('debug', foreground='#666666', font=('Consolas', 8))
    
    def actualizar_semaforo(self, grupo_id, estado):
        """
        Actualiza el color de un semáforo
        estado: 'rojo', 'ambar', 'verde', 'apagado', 'ambar_intermitente', 'verde_intermitente'
        """
        if grupo_id not in self.luces:
            return
        
        luz = self.luces[grupo_id]
        canvas = luz['canvas']
        
        # Colores apagados
        COLOR_OFF_ROJO = '#4a0000'
        COLOR_OFF_AMBAR = '#4a4a00'
        COLOR_OFF_VERDE = '#004a00'
        
        # Colores encendidos
        COLOR_ON_ROJO = '#ff0000'
        
        # Registrar si es estado intermitente
        es_intermitente = False
        color_intermitente = None
        COLOR_ON_AMBAR = '#ffaa00'
        COLOR_ON_VERDE = '#00ff00'
        
        # Apagar todas las luces primero
        canvas.itemconfig(luz['rojo'], fill=COLOR_OFF_ROJO)
        if luz['tipo'] == 'vehicular':
            canvas.itemconfig(luz['ambar'], fill=COLOR_OFF_AMBAR)
        canvas.itemconfig(luz['verde'], fill=COLOR_OFF_VERDE)
        
        # Encender según estado
        # Estados UNE internos: 0=Off, 1=Verde, 2=Ámbar, 3=Rojo, 4=Rojo Int, 5=Verde Int, 6=Ámbar Int
        texto_estado = "--"
        if estado == 'rojo' or estado == 3:
            canvas.itemconfig(luz['rojo'], fill=COLOR_ON_ROJO)
            texto_estado = "ROJO"
        elif estado == 'ambar' or estado == 2:
            if luz['tipo'] == 'vehicular':
                canvas.itemconfig(luz['ambar'], fill=COLOR_ON_AMBAR)
            else:
                # Peatonal no tiene ámbar, mostrar rojo
                canvas.itemconfig(luz['rojo'], fill=COLOR_ON_ROJO)
            texto_estado = "ÁMBAR"
        elif estado == 'verde' or estado == 1:
            canvas.itemconfig(luz['verde'], fill=COLOR_ON_VERDE)
            texto_estado = "VERDE"
        elif estado == 'apagado' or estado == 0:
            texto_estado = "OFF"
        elif estado == 'rojo_intermitente' or estado == 4:
            es_intermitente = True
            color_intermitente = 'rojo'
            # El color se maneja en el timer de parpadeo
            if self._parpadeo_visible:
                canvas.itemconfig(luz['rojo'], fill=COLOR_ON_ROJO)
            texto_estado = "ROJO ⚡"
        elif estado == 'verde_intermitente' or estado == 5:
            es_intermitente = True
            color_intermitente = 'verde'
            if self._parpadeo_visible:
                canvas.itemconfig(luz['verde'], fill=COLOR_ON_VERDE)
            texto_estado = "VERDE ⚡"
        elif estado == 'ambar_intermitente' or estado == 6:
            es_intermitente = True
            color_intermitente = 'ambar'
            if luz['tipo'] == 'vehicular' and self._parpadeo_visible:
                canvas.itemconfig(luz['ambar'], fill=COLOR_ON_AMBAR)
            texto_estado = "ÁMBAR ⚡"
        
        # Actualizar registro de estados intermitentes
        if es_intermitente:
            self._estados_intermitentes[grupo_id] = color_intermitente
        elif grupo_id in self._estados_intermitentes:
            del self._estados_intermitentes[grupo_id]
        
        luz['label'].configure(text=texto_estado)
    
    def actualizar_todos_semaforos(self, estados):
        """Actualiza todos los semáforos con una lista de estados"""
        for i, estado in enumerate(estados):
            self.actualizar_semaforo(i + 1, estado)
    
    def _iniciar_parpadeo(self):
        """Inicia el timer de parpadeo para estados intermitentes"""
        self._tick_parpadeo()
    
    def _tick_parpadeo(self):
        """Ejecuta un tick del parpadeo y programa el siguiente"""
        # Alternar visibilidad
        self._parpadeo_visible = not self._parpadeo_visible
        
        # Colores
        COLOR_OFF_ROJO = '#4a0000'
        COLOR_OFF_AMBAR = '#4a4a00'
        COLOR_OFF_VERDE = '#004a00'
        COLOR_ON_ROJO = '#ff0000'
        COLOR_ON_AMBAR = '#ffaa00'
        COLOR_ON_VERDE = '#00ff00'
        
        # Actualizar todos los grupos en estado intermitente
        for grupo_id, color in self._estados_intermitentes.items():
            if grupo_id not in self.luces:
                continue
            
            luz = self.luces[grupo_id]
            canvas = luz['canvas']
            
            if color == 'rojo':
                if self._parpadeo_visible:
                    canvas.itemconfig(luz['rojo'], fill=COLOR_ON_ROJO)
                else:
                    canvas.itemconfig(luz['rojo'], fill=COLOR_OFF_ROJO)
            elif color == 'ambar' and luz['tipo'] == 'vehicular':
                if self._parpadeo_visible:
                    canvas.itemconfig(luz['ambar'], fill=COLOR_ON_AMBAR)
                else:
                    canvas.itemconfig(luz['ambar'], fill=COLOR_OFF_AMBAR)
            elif color == 'verde':
                if self._parpadeo_visible:
                    canvas.itemconfig(luz['verde'], fill=COLOR_ON_VERDE)
                else:
                    canvas.itemconfig(luz['verde'], fill=COLOR_OFF_VERDE)
        
        # Programar siguiente tick (500ms = parpadeo de 1Hz, típico de intermitente)
        self._parpadeo_timer = self.after(500, self._tick_parpadeo)
    
    def detener_parpadeo(self):
        """Detiene el timer de parpadeo"""
        if self._parpadeo_timer:
            self.after_cancel(self._parpadeo_timer)
            self._parpadeo_timer = None
    
    def actualizar_ciclo(self, segundos):
        """Actualiza el contador de ciclo"""
        self.lbl_ciclo.configure(text=f"{segundos}s")
    
    def actualizar_estado(self, ejecutando, conexion=None, plan=None, fase=None, modo=None, esperando=False):
        """Actualiza los indicadores de estado"""
        if ejecutando:
            self.lbl_estado.configure(text="🟢 EJECUTANDO", foreground='green')
        else:
            self.lbl_estado.configure(text="⚪ DETENIDO", foreground='gray')
            self._conexion_actual = None  # Reset al detener
        
        # Guardar conexión si se proporciona
        if conexion:
            self._conexion_actual = conexion
        
        # Mostrar estado de conexión
        if self._conexion_actual:
            self.lbl_conexion.configure(text=f"Conectado: {self._conexion_actual}", foreground='green')
        elif esperando:
            self.lbl_conexion.configure(text="⏳ Esperando conexión...", foreground='orange')
        elif not ejecutando:
            self.lbl_conexion.configure(text="Sin conexión", foreground='gray')
        
        if plan is not None:
            logger.info(f"[MonitorFrame.actualizar_estado] Actualizando GUI: plan={plan}")
            # Obtener nombre del plan desde el diccionario
            plan_nombre = self._planes_dict.get(plan, f"Plan {plan}")
            self.lbl_plan.configure(text=f"Plan actual: {plan_nombre}")
        
        if fase is not None:
            self.lbl_fase.configure(text=f"Fase: {fase}")
        
        if modo is not None:
            logger.info(f"[MonitorFrame.actualizar_estado] Actualizando GUI: modo={modo}")
            MODOS = {1: "LOCAL", 2: "ORDENADOR", 3: "MANUAL"}
            modo_texto = MODOS.get(modo, '?')
            self.lbl_modo.configure(text=f"Modo: {modo_texto}")
    
    def agregar_log(self, mensaje, tipo='info'):
        """Agrega un mensaje al log"""
        self.log_text.configure(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert('end', f"[{timestamp}] {mensaje}\n", tipo)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')
    
    def limpiar_log(self):
        """Limpia el log"""
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')


class ReguladorGUI:
    """Ventana principal de la aplicación"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🚦 Regulador Virtual UNE 135401-4")
        self.root.geometry("900x700")
        
        # Estado
        self.regulador = None
        self.regulador_thread = None
        self.ejecutando = False
        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'config', 'regulador_config.json'
        )
        
        # Cola para mensajes del regulador
        self.message_queue = queue.Queue()
        
        # Cargar configuración
        self.config = self._cargar_config()
        
        # Crear interfaz
        self._crear_menu()
        self._crear_widgets()
        
        # Iniciar procesamiento de mensajes
        self._procesar_mensajes()
    
    def _cargar_config(self):
        """Carga la configuración desde archivo"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar la configuración: {e}")
            return {}
    
    def _guardar_config(self):
        """Guarda la configuración en archivo"""
        try:
            # Obtener configuración actualizada de los frames
            self.config = self.config_frame.get_config()
            if self.config is None:
                return False
            
            self.config = self.planes_frame.get_config()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            messagebox.showinfo("Éxito", "Configuración guardada correctamente")
            return True
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la configuración: {e}")
            return False
    
    def _crear_menu(self):
        """Crea el menú de la aplicación"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Menú Archivo
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Guardar configuración", command=self._guardar_config)
        file_menu.add_command(label="Recargar configuración", command=self._recargar_config)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self._salir)
        
        # Menú Control
        control_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Control", menu=control_menu)
        control_menu.add_command(label="▶️ Iniciar", command=self._iniciar_regulador)
        control_menu.add_command(label="⏹️ Detener", command=self._detener_regulador)
        
        # Menú Ayuda
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ayuda", menu=help_menu)
        help_menu.add_command(label="Acerca de", command=self._mostrar_acerca)
    
    def _crear_widgets(self):
        """Crea los widgets de la interfaz"""
        # Frame principal con scroll
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        # Botones de control
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill='x', pady=5)
        
        self.btn_iniciar = ttk.Button(control_frame, text="▶️ Iniciar Regulador", 
                                       command=self._iniciar_regulador, style='Accent.TButton')
        self.btn_iniciar.pack(side='left', padx=5)
        
        self.btn_detener = ttk.Button(control_frame, text="⏹️ Detener Regulador",
                                       command=self._detener_regulador, state='disabled')
        self.btn_detener.pack(side='left', padx=5)
        
        ttk.Button(control_frame, text="💾 Guardar Config", 
                   command=self._guardar_config).pack(side='left', padx=5)
        
        ttk.Button(control_frame, text="🔄 Recargar Config",
                   command=self._recargar_config).pack(side='left', padx=5)
        
        # Notebook con pestañas
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True, pady=10)
        
        # Pestaña Monitor (pasamos config para crear semáforos)
        self.monitor_frame = MonitorFrame(notebook, self.config)
        notebook.add(self.monitor_frame, text="📊 Monitor")
        
        # Pestaña Configuración General
        config_tab = ttk.Frame(notebook, padding=10)
        notebook.add(config_tab, text="⚙️ Configuración")
        
        self.config_frame = ConfiguracionFrame(config_tab, self.config, self._on_config_change)
        self.config_frame.pack(fill='x', pady=5)
        
        # Pestaña Fases (nueva)
        fases_tab = ttk.Frame(notebook, padding=10)
        notebook.add(fases_tab, text="🎨 Fases")
        
        self.fases_frame = FasesFrame(fases_tab, self.config, self._on_config_change)
        self.fases_frame.pack(fill='both', expand=True)
        
        # Pestaña Estructuras (nueva)
        estructuras_tab = ttk.Frame(notebook, padding=10)
        notebook.add(estructuras_tab, text="🔄 Estructuras")
        
        self.estructuras_frame = EstructurasFrame(estructuras_tab, self.config, self._on_config_change)
        self.estructuras_frame.pack(fill='both', expand=True)
        
        # Pestaña Planes
        planes_tab = ttk.Frame(notebook, padding=10)
        notebook.add(planes_tab, text="📋 Planes")
        
        self.planes_frame = PlanesFrame(planes_tab, self.config, self._on_config_change)
        self.planes_frame.pack(fill='both', expand=True)
    
    def _on_config_change(self):
        """Callback cuando cambia la configuración"""
        pass  # Se puede usar para marcar cambios no guardados
    
    def _recargar_config(self):
        """Recarga la configuración desde el archivo"""
        if self.ejecutando:
            messagebox.showwarning("Aviso", "Detén el regulador antes de recargar la configuración")
            return
        
        self.config = self._cargar_config()
        # Recrear frames de configuración
        messagebox.showinfo("Info", "Configuración recargada. Reinicia la aplicación para ver los cambios.")
    
    def _iniciar_regulador(self):
        """Inicia el regulador virtual"""
        if self.ejecutando:
            return
        
        # Guardar configuración antes de iniciar
        if not self._guardar_config():
            return
        
        try:
            self.ejecutando = True
            self.btn_iniciar.configure(state='disabled')
            self.btn_detener.configure(state='normal')
            
            self.monitor_frame.actualizar_estado(True, esperando=True)
            self.monitor_frame.agregar_log("Iniciando regulador...", 'info')
            
            # Crear y ejecutar regulador en hilo separado
            def run_regulador():
                try:
                    self.regulador = ReguladorVirtualGUI(self.config_path, self.message_queue)
                    self.regulador.ejecutar()
                except Exception as e:
                    self.message_queue.put(('error', f"Error: {e}"))
                finally:
                    self.message_queue.put(('stopped', None))
            
            self.regulador_thread = threading.Thread(target=run_regulador, daemon=True)
            self.regulador_thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo iniciar el regulador: {e}")
            self.ejecutando = False
            self.btn_iniciar.configure(state='normal')
            self.btn_detener.configure(state='disabled')
    
    def _detener_regulador(self):
        """Detiene el regulador virtual"""
        if not self.ejecutando:
            return
        
        if self.regulador:
            self.regulador.detener()
        
        self.ejecutando = False
        self.btn_iniciar.configure(state='normal')
        self.btn_detener.configure(state='disabled')
        self.monitor_frame.actualizar_estado(False)
        self.monitor_frame.agregar_log("Regulador detenido", 'info')
    
    def _procesar_mensajes(self):
        """Procesa mensajes de la cola del regulador y de los logs"""
        try:
            # Procesar mensajes del regulador
            while True:
                tipo, mensaje = self.message_queue.get_nowait()
                
                if tipo == 'log':
                    self.monitor_frame.agregar_log(mensaje, 'info')
                elif tipo == 'log_detallado':
                    # Logs del sistema de logging (consola)
                    self.monitor_frame.agregar_log(mensaje, 'debug')
                elif tipo == 'enviado':
                    self.monitor_frame.agregar_log(f"📤 {mensaje}", 'enviado')
                elif tipo == 'recibido':
                    self.monitor_frame.agregar_log(f"📥 {mensaje}", 'recibido')
                elif tipo == 'error':
                    self.monitor_frame.agregar_log(mensaje, 'error')
                elif tipo == 'estado':
                    self.monitor_frame.actualizar_estado(True, **mensaje)
                elif tipo == 'stopped':
                    self._detener_regulador()
                elif tipo == 'conexion':
                    self.monitor_frame.actualizar_estado(True, conexion=mensaje)
                    self.monitor_frame.agregar_log(f"✅ Conectado: {mensaje}", 'info')
                elif tipo == 'esperando':
                    self.monitor_frame.actualizar_estado(True, esperando=True)
                    self.monitor_frame.agregar_log(f"⏳ {mensaje}", 'info')
                elif tipo == 'semaforos':
                    # Actualizar todos los semáforos gráficos
                    self.monitor_frame.actualizar_todos_semaforos(mensaje)
                elif tipo == 'ciclo':
                    # Actualizar contador de ciclo
                    self.monitor_frame.actualizar_ciclo(mensaje)
                    
        except queue.Empty:
            pass
        
        # Procesar logs del sistema
        try:
            while True:
                tipo, mensaje = log_queue.get_nowait()
                if tipo == 'log_detallado':
                    self.monitor_frame.agregar_log(mensaje, 'debug')
        except queue.Empty:
            pass
        
        # Programar siguiente revisión
        self.root.after(100, self._procesar_mensajes)
    
    def _mostrar_acerca(self):
        """Muestra diálogo Acerca de"""
        version = self.config.get('regulador', {}).get('version', '?.?.?')
        nombre = self.config.get('regulador', {}).get('nombre', 'Regulador Virtual UNE')
        
        messagebox.showinfo("Acerca de",
            f"{nombre}\n\n"
            f"Versión: {version}\n\n"
            "Simula un regulador de tráfico según\n"
            "el protocolo UNE 135401-4:2003")
    
    def _salir(self):
        """Cierra la aplicación"""
        if self.ejecutando:
            self._detener_regulador()
        self.root.quit()
    
    def ejecutar(self):
        """Ejecuta la aplicación"""
        self.root.protocol("WM_DELETE_WINDOW", self._salir)
        self.root.mainloop()


class ReguladorVirtualGUI:
    """Versión del regulador adaptada para la GUI"""
    
    def __init__(self, config_path, message_queue):
        self.message_queue = message_queue
        
        # Importar módulos
        from modules import (
            ProtocoloUNE,
            codificar_byte_une,
            decodificar_byte_une,
            calcular_checksum,
            verificar_checksum,
            construir_mensaje,
            separar_mensajes,
            EstadoRegulador,
            GeneradorRespuestas
        )
        
        self.ProtocoloUNE = ProtocoloUNE
        self.codificar_byte_une = codificar_byte_une
        self.decodificar_byte_une = decodificar_byte_une
        self.verificar_checksum = verificar_checksum
        self.separar_mensajes = separar_mensajes
        self.GeneradorRespuestas = GeneradorRespuestas
        
        # Cargar configuración
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Estado del regulador
        self.estado = EstadoRegulador(config_path)
        
        # Suscribir al callback de cambio de plan
        self.estado.set_on_plan_change_callback(self._on_plan_changed)
        
        # Configuración de red
        reg_config = self.config.get('regulador', {})
        self.puerto = reg_config.get('puerto_escucha', 19000)
        self.ip = reg_config.get('ip_escucha', '0.0.0.0')
        
        # Subreguladores
        sub_config = self.config.get('subreguladores', {})
        self.sub_cpu = sub_config.get('cpu_estado', 128)
        self.sub_planes = sub_config.get('planes_sync', 129)
        
        # Sockets
        self.server_socket = None
        self.client_socket = None
        self.conectado = False
        
        logger.info(f"Regulador inicializado - Puerto {self.puerto}, IP {self.ip}")
        logger.info(f"Subreguladores: CPU={self.sub_cpu}, Planes={self.sub_planes}")
        logger.info(f"Estado inicial: Modo={self.estado.modo_control}, Plan={self.estado.plan_actual}")
    
    def _log(self, mensaje, tipo='log'):
        """Envía mensaje a la GUI"""
        self.message_queue.put((tipo, mensaje))
    
    def _log_mensaje_detallado(self, mensaje, direccion):
        """Log detallado de un mensaje del protocolo para comparar con sniffer"""
        if len(mensaje) < 5:
            logger.warning(f"{direccion}: Mensaje demasiado corto ({len(mensaje)} bytes): {mensaje.hex().upper()}")
            return
        
        # Decodificar estructura del mensaje
        stx = mensaje[0]
        subregulador = mensaje[1]
        codigo_raw = mensaje[2]
        datos = mensaje[3:-2] if len(mensaje) > 5 else b''
        checksum = mensaje[-2] if len(mensaje) >= 2 else 0
        etx = mensaje[-1] if len(mensaje) >= 1 else 0
        
        # Decodificar código
        codigo = self.decodificar_byte_une(codigo_raw)
        
        # Nombres de códigos
        CODIGOS = {
            0x11: 'SINCRONIZACIÓN (0x91)',
            0x12: 'SELECCIÓN PLAN (0x92)',
            0x14: 'DATOS TRÁFICO (0x94)',
            0x33: 'DETECTORES/MODO (0xB3)',
            0x34: 'ALARMAS (0xB4)',
            0x35: 'CONFIGURACIÓN (0xB5)',
            0x36: 'TABLAS PROG (0xB6)',
            0x37: 'INCOMPATIBILIDADES (0xB7)',
            0x39: 'ESTADO GRUPOS (0xB9)',
            0x51: 'SELECCIÓN PLAN (0xD1)',
            0x54: 'ESTADOS (0xD4)',
            0x55: 'CAMBIO FASE (0xD5)',
            0x5B: 'MANDO DIRECTO (0xDB)',
        }
        
        codigo_nombre = CODIGOS.get(codigo, f'DESCONOCIDO (0x{codigo:02X})')
        
        logger.info(f"")
        logger.info(f"{'='*70}")
        logger.info(f"{direccion}: {codigo_nombre}")
        logger.info(f"  Mensaje completo: {mensaje.hex().upper()}")
        logger.info(f"  STX={stx:02X}, Subreg={subregulador:02X}, Código={codigo_raw:02X}→{codigo:02X}, Checksum={checksum:02X}, ETX={etx:02X}")
        logger.info(f"  Longitud total: {len(mensaje)} bytes, Datos: {len(datos)} bytes")
        
        if datos:
            logger.info(f"  Datos (hex): {datos.hex().upper()}")
            logger.info(f"  Datos (bytes): {' '.join(f'{b:02X}' for b in datos)}")
            
            # Decodificar datos según el código
            self._decodificar_datos(codigo, datos)
        else:
            logger.info(f"  Sin datos adicionales")
        
        logger.info(f"{'='*70}")
    
    def _decodificar_datos(self, codigo, datos):
        """Decodifica e imprime los datos según el tipo de mensaje"""
        if codigo == 0x11:  # Sincronización
            if len(datos) >= 8:
                plan = datos[0]
                hora = self.decodificar_byte_une(datos[1])
                minuto = self.decodificar_byte_une(datos[2])
                segundo = self.decodificar_byte_une(datos[3])
                fase = self.decodificar_byte_une(datos[4])
                ciclo_msb = self.decodificar_byte_une(datos[5])
                ciclo_lsb = self.decodificar_byte_une(datos[6])
                resta = self.decodificar_byte_une(datos[7])
                ciclo = (ciclo_msb << 7) | ciclo_lsb
                logger.info(f"  → Plan={plan}, Hora={hora:02d}:{minuto:02d}:{segundo:02d}, Fase={fase}, Ciclo={ciclo}s, Resta={resta}s")
        
        elif codigo == 0x12 or codigo == 0x51:  # Selección de plan (0x92 o 0xD1)
            if len(datos) >= 1:
                plan_solicitado = self.decodificar_byte_une(datos[0])
                logger.info(f"  → PLAN SOLICITADO: {plan_solicitado}")
            else:
                logger.warning(f"  → Mensaje de selección de plan sin datos")
        
        elif codigo == 0x34:  # Alarmas
            if len(datos) >= 4:
                byte1 = datos[0]
                byte2 = datos[1]
                byte3 = datos[2]
                byte4 = datos[3]
                logger.info(f"  → Alarmas: B1={byte1:02X}, B2={byte2:02X}, B3={byte3:02X}, B4={byte4:02X}")
                # Decodificar bits de alarmas
                b1 = self.decodificar_byte_une(byte1)
                logger.info(f"  → Byte1 decodificado: {b1:02X} (bits: {bin(b1)})")
                if b1 & 0x01: logger.info(f"    - Incompatibilidad")
                if b1 & 0x10: logger.info(f"    - Lámpara fundida")
        
        elif codigo == 0x35:  # Configuración
            if len(datos) >= 11:
                sel_planes = self.decodificar_byte_une(datos[0])
                coord = self.decodificar_byte_une(datos[1])
                metodo = self.decodificar_byte_une(datos[2])
                plan = self.decodificar_byte_une(datos[3])
                ciclo = self.decodificar_byte_une(datos[4])
                estructura = self.decodificar_byte_une(datos[5])
                
                logger.info(f"  → Sel_Planes={sel_planes:02X}, Coord={coord:02X}, Método={metodo}")
                logger.info(f"  → Plan={plan}, Ciclo={ciclo}s, Estructura={estructura}")
                
                # Interpretar modos
                if sel_planes & 0x04:
                    logger.info(f"    * Plan seleccionado por ORDENADOR")
                else:
                    logger.info(f"    * Control LOCAL de planes")
                
                if coord & 0x04:
                    logger.info(f"    * Control CENTRALIZADO")
                elif coord & 0x08:
                    logger.info(f"    * Control MANUAL")
                else:
                    logger.info(f"    * Control LOCAL")
        
        elif codigo == 0x39:  # Estado grupos (0xB9)
            logger.info(f"  → Estados de grupos:")
            for i, byte_val in enumerate(datos):
                grupo_id = i + 1
                val_decodificado = self.decodificar_byte_une(byte_val)
                # Mapeo de valores
                estado_nombre = "?"
                if val_decodificado == 0:
                    estado_nombre = "APAGADO"
                elif val_decodificado == 1:
                    estado_nombre = "ROJO"
                elif val_decodificado == 4:
                    estado_nombre = "ÁMBAR"
                elif val_decodificado == 16:
                    estado_nombre = "VERDE"
                
                logger.info(f"    G{grupo_id}: {byte_val:02X} → {val_decodificado:02X} ({val_decodificado}) = {estado_nombre}")
        
        elif codigo == 0x54:  # Estados (0xD4)
            if len(datos) >= 4:
                repr_byte = self.decodificar_byte_une(datos[0])
                planes_byte = self.decodificar_byte_une(datos[1])
                coord_byte = self.decodificar_byte_une(datos[2])
                metodo_byte = self.decodificar_byte_une(datos[3])
                
                logger.info(f"  → BYTE1 (Repr): {datos[0]:02X} → {repr_byte:02X}")
                estados_repr = ["APAGADO", "INTERMITENTE", "COLORES"]
                logger.info(f"    * Estado representación: {estados_repr[repr_byte] if repr_byte < 3 else 'DESCONOCIDO'}")
                
                logger.info(f"  → BYTE2 (Planes): {datos[1]:02X} → {planes_byte:02X}")
                if planes_byte & 0x04:
                    logger.info(f"    * Plan seleccionado por ORDENADOR")
                elif planes_byte & 0x01:
                    logger.info(f"    * Control externo seleccionado")
                else:
                    logger.info(f"    * Control LOCAL de planes")
                
                logger.info(f"  → BYTE3 (Coordinación): {datos[2]:02X} → {coord_byte:02X}")
                if coord_byte & 0x04:
                    logger.info(f"    * Control CENTRALIZADO")
                elif coord_byte & 0x08:
                    logger.info(f"    * Control MANUAL")
                elif coord_byte & 0x01:
                    logger.info(f"    * Coordinado con reloj interno (LOCAL)")
                else:
                    logger.info(f"    * Coordinado con señal externa")
                
                logger.info(f"  → BYTE4 (Método): {datos[3]:02X} → {metodo_byte:02X}")
                metodos = ["TIEMPOS FIJOS", "SEMIACTUADO", "ACTUADO TOTAL"]
                logger.info(f"    * {metodos[metodo_byte] if metodo_byte < 3 else 'DESCONOCIDO'}")
        
        elif codigo == 0x55:  # Cambio de fase
            if len(datos) >= 1:
                fase = self.decodificar_byte_une(datos[0])
                logger.info(f"  → Nueva fase: {fase}")
    
    def _actualizar_estado(self, **kwargs):
        """Actualiza estado en la GUI"""
        self.message_queue.put(('estado', kwargs))
    
    def enviar_mensaje(self, mensaje):
        """Envía un mensaje a la central"""
        if self.client_socket and self.conectado:
            try:
                self.client_socket.send(mensaje)
                # Log detallado del mensaje enviado
                hex_str = mensaje.hex().upper()
                self._log_mensaje_detallado(mensaje, 'ENVIADO')
                self._log(f"📤 ENVIADO: {hex_str}", 'enviado')
            except Exception as e:
                self._log(f"Error al enviar: {e}", 'error')
    
    def enviar_estado_completo(self):
        """
        Envía el estado completo del regulador a la central.
        Igual que al inicio de conexión: alarmas, modo y estado de grupos.
        """
        if not self.conectado:
            return
        
        logger.info(f"📤 ENVIANDO ESTADO COMPLETO:")
        logger.info(f"   estado.modo_control={self.estado.modo_control}")
        logger.info(f"   estado.plan_actual={self.estado.plan_actual}")
        logger.info(f"   estado.fase_actual={self.estado.fase_actual}")
        self._log("Enviando estado completo...")
        
        import time
        
        # 1. Enviar alarmas/estado general
        respuesta = self.GeneradorRespuestas.respuesta_alarmas(self.estado, self.sub_cpu)
        logger.info(f"   1) Enviando 0xB4 (alarmas)")
        self.enviar_mensaje(respuesta)
        
        time.sleep(0.1)
        
        # 2. Enviar estados del regulador (0xD4) - modo, coordinación, etc.
        logger.info(f"   2) Generando 0xD4 (estados) con modo_control={self.estado.modo_control}")
        msg_modo = self.GeneradorRespuestas.mensaje_estados(self.estado, self.sub_cpu)
        self.enviar_mensaje(msg_modo)
        
        time.sleep(0.1)
        
        # 3. Enviar estado de grupos (0xB9)
        logger.info(f"   3) Enviando 0xB9 (estado grupos)")
        msg_grupos = self.GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
        self.enviar_mensaje(msg_grupos)
    
    def _on_plan_changed(self, plan_anterior, nuevo_plan):
        """
        Callback invocado cuando cambia el plan (por horario o por orden de central).
        Solo actualiza la GUI, NO envía mensajes automáticamente.
        """
        logger.info(f"🔔 CALLBACK _on_plan_changed: {plan_anterior} → {nuevo_plan}")
        logger.info(f"   Estado actual en callback: modo_control={self.estado.modo_control}, plan_actual={self.estado.plan_actual}")
        self._log(f"CAMBIO DE PLAN: {plan_anterior} → {nuevo_plan}")
        self._actualizar_estado(plan=nuevo_plan)
        
        # NO enviar estado completo automáticamente
        # El regulador real solo envía mensajes cuando la central los solicita
    
    def ejecutar(self):
        """Ejecuta el regulador"""
        import socket
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.ip, self.puerto))
            self.server_socket.listen(1)
            
            self._log(f"Servidor iniciado en puerto {self.puerto}")
            self.message_queue.put(('esperando', f"Servidor escuchando en puerto {self.puerto}"))
            
            self.client_socket, addr = self.server_socket.accept()
            self.client_socket.settimeout(1.0)
            self.conectado = True
            
            self.message_queue.put(('conexion', f"{addr[0]}:{addr[1]}"))
            self._actualizar_estado(
                plan=self.estado.plan_actual,
                fase=self.estado.fase_actual,
                modo=self.estado.modo_control
            )
            
            # INICIAR SECUENCIA DE ARRANQUE (como regulador real)
            logger.info("🚦 Iniciando secuencia de arranque del regulador...")
            self._log("🚦 Iniciando secuencia de arranque (12 segundos)...")
            self.estado.iniciar_secuencia_arranque()
            
            # Enviar estado inicial - 0xB4 (alarmas)
            respuesta = self.GeneradorRespuestas.respuesta_alarmas(self.estado, self.sub_cpu)
            self.enviar_mensaje(respuesta)
            time.sleep(0.1)
            
            # ENVIAR MENSAJE 0xB3 ESPONTÁNEO (como regulador real)
            # NOTA: Según captura del regulador real, SIEMPRE envía byte 0x80
            # (decodificado 0x00) independientemente del estado o modo.
            logger.info("📤 Enviando mensaje 0xB3 espontáneo (modo de control)")
            MODOS_STR = {1: "LOCAL", 2: "ORDENADOR", 3: "MANUAL"}
            self._log(f"📤 Informando estado a la central (0xB3)")
            from modules.protocolo_une import construir_mensaje
            
            # Byte de modo: SIEMPRE 0x00 como el regulador real
            byte_modo = 0x00
            byte_modo_codificado = byte_modo | 0x80
            
            # 48 bytes: primer byte con modo (0x80), resto 0x80 (como regulador real)
            datos_b3 = bytes([byte_modo_codificado] + [0x80] * 47)
            msg_b3 = construir_mensaje(self.sub_cpu, 0xB3, datos_b3)
            
            logger.info(f"   Byte modo: 0x{byte_modo:02X} → codificado: 0x{byte_modo_codificado:02X} (igual que regulador real)")
            self.enviar_mensaje(msg_b3)
            
            # Bucle principal
            ultimo_ciclo = time.time()
            ultimo_estado_grupos = time.time()
            ultimo_check_horario = time.time()
            
            # Verificar plan por horario al inicio si está en modo LOCAL
            if self.estado.modo_control == 1:
                logger.info("Verificando plan por horario al inicio de conexión...")
                self.estado.seleccionar_plan_por_horario()
            
            while self.conectado:
                try:
                    data = self.client_socket.recv(1024)
                    if data:
                        hex_str = data.hex().upper()
                        self._log(f"📥 RECIBIDO: {hex_str}", 'recibido')
                        logger.info(f"RECIBIDO {len(data)} bytes: {hex_str}")
                        self._procesar_mensaje(data)
                except socket.timeout:
                    pass
                except Exception as e:
                    if self.conectado:
                        self._log(f"Error: {e}", 'error')
                    break
                
                ahora = time.time()
                
                # Verificar cambio de plan por horario cada minuto (solo en modo LOCAL)
                if ahora - ultimo_check_horario >= 60:  # Cada 60 segundos
                    ultimo_check_horario = ahora
                    if self.estado.modo_control == 1:  # Solo en modo LOCAL
                        from datetime import datetime
                        hora_actual = datetime.now().strftime("%H:%M")
                        logger.debug(f"Verificación periódica de horarios - Hora actual: {hora_actual}")
                        plan_anterior = self.estado.plan_actual
                        self.estado.seleccionar_plan_por_horario()
                        # El callback _on_plan_changed se encargará de notificar si hubo cambio
                    else:
                        logger.debug(f"Modo {self.estado.modo_control} - La central controla el plan")
                
                # Enviar estado de grupos periódicamente (cada 2 segundos)
                if ahora - ultimo_estado_grupos >= 2:
                    ultimo_estado_grupos = ahora
                    # Actualizar semáforos gráficos
                    estados = self.estado.get_estado_grupos()
                    self.message_queue.put(('semaforos', estados))
                    logger.debug(f"Envío periódico de estados - Grupos: {estados}")
                    # Enviar a central (usar sub_cpu = 128, no sub_planes)
                    msg = self.GeneradorRespuestas.mensaje_estado_grupos(
                        self.estado, self.sub_cpu)
                    self.enviar_mensaje(msg)
                
                # Actualizar ciclo cada segundo
                if ahora - ultimo_ciclo >= 1:
                    ultimo_ciclo = ahora
                    
                    # Si estamos en secuencia de arranque, procesarla primero
                    if self.estado.en_secuencia_arranque:
                        cambio_arranque = self.estado.actualizar_arranque()
                        if cambio_arranque:
                            self._log(f"🔄 Arranque Fase {self.estado.fase_arranque} ({self.estado.tiempo_fase_arranque}s)")
                            # Actualizar semáforos inmediatamente
                            estados = self.estado.get_estado_grupos()
                            self.message_queue.put(('semaforos', estados))
                            # Enviar estado de grupos
                            msg = self.GeneradorRespuestas.mensaje_estado_grupos(
                                self.estado, self.sub_cpu)
                            self.enviar_mensaje(msg)
                        continue  # No procesar ciclo normal durante arranque
                    
                    # Si acabamos de completar el arranque, notificar
                    if self.estado.arranque_completado and not hasattr(self, '_arranque_notificado'):
                        self._log("✅ Secuencia de arranque completada - Iniciando operación normal")
                        self._arranque_notificado = True
                    
                    # Enviar contador de ciclo a la GUI
                    self.message_queue.put(('ciclo', self.estado.ciclo_actual))
                    
                    cambio = self.estado.actualizar_ciclo()
                    if cambio:
                        logger.info(f"")
                        logger.info(f"{'*'*70}")
                        logger.info(f"CAMBIO DE FASE: Fase actual = {self.estado.fase_actual}")
                        logger.info(f"Estados de grupos: {self.estado.get_estado_grupos()}")
                        logger.info(f"{'*'*70}")
                        self._log(f"🔄 Cambio de fase → Fase {self.estado.fase_actual}")
                        self._actualizar_estado(fase=self.estado.fase_actual)
                        # Actualizar semáforos inmediatamente
                        estados = self.estado.get_estado_grupos()
                        self.message_queue.put(('semaforos', estados))
                        # Enviar mensajes de cambio
                        logger.info("Enviando mensaje CAMBIO DE FASE (0xD5)")
                        msg = self.GeneradorRespuestas.mensaje_cambio_fase(
                            self.estado.fase_actual, self.sub_planes)
                        self.enviar_mensaje(msg)
                        time.sleep(0.1)
                        logger.info("Enviando ESTADO GRUPOS tras cambio de fase")
                        msg = self.GeneradorRespuestas.mensaje_estado_grupos(
                            self.estado, self.sub_cpu)
                        self.enviar_mensaje(msg)
            
        except Exception as e:
            self._log(f"Error: {e}", 'error')
        finally:
            self.detener()
    
    def _procesar_mensaje(self, data):
        """Procesa mensajes recibidos"""
        # LOG COMPLETO DE BYTES RECIBIDOS
        logger.info(f"")
        logger.info(f"{'#'*70}")
        logger.info(f"BUFFER RECIBIDO: {len(data)} bytes")
        logger.info(f"  HEX: {data.hex().upper()}")
        logger.info(f"  BYTES: {' '.join(f'{b:02X}' for b in data)}")
        logger.info(f"  ASCII: {' '.join(chr(b) if 32 <= b < 127 else '.' for b in data)}")
        logger.info(f"{'#'*70}")
        
        # =========================================================================
        # MANEJO DE BYTES ESPECIALES SIN FORMATO UNE
        # Algunos mensajes de la central se envían como bytes sueltos:
        # - 0x20 (DET): Petición de estado/detectores → Responder con 0xB3
        # - 0x06 (ACK): Confirmación
        # El byte 0x20 puede venir:
        #   a) Como único byte en el buffer: data = [0x20]
        #   b) Antes de un mensaje UNE: data = [0x20, 0x02, ...msg..., 0x03]
        # =========================================================================
        
        # Detectar si hay byte 0x20 FUERA de mensajes UNE
        # Esto ocurre cuando 0x20 aparece antes de un STX (0x02) o es el único byte
        procesar_0x20 = False
        
        if len(data) == 1 and data[0] == 0x20:
            # Caso: byte único
            procesar_0x20 = True
        elif len(data) > 1 and data[0] == 0x20 and data[1] != 0x80:
            # Caso: 0x20 seguido de algo que NO es un subregulador codificado (0x80+)
            # O seguido de STX (0x02)
            procesar_0x20 = True
        elif 0x20 in data:
            # Buscar si 0x20 aparece fuera de un mensaje UNE
            stx_pos = data.find(b'\x02')
            pos_20 = data.find(b'\x20')
            if pos_20 != -1 and (stx_pos == -1 or pos_20 < stx_pos):
                # 0x20 aparece antes del primer STX
                procesar_0x20 = True
        
        if procesar_0x20:
            logger.info(f"")
            logger.info(f"🔔 BYTE ESPECIAL DETECTADO: 0x20 (DET - Petición estado)")
            self._log(f"📥 Central solicita estado (0x20 suelto) - enviando 0xB3")
            self._responder_peticion_estado()
        
        mensajes = self.separar_mensajes(data)
        
        logger.info(f"Procesando {len(mensajes)} mensaje(s) del buffer")
        
        for idx, mensaje in enumerate(mensajes):
            if len(mensaje) < 5:
                logger.warning(f"Mensaje #{idx+1} demasiado corto ({len(mensaje)} bytes), ignorando")
                continue
            
            if mensaje[0] != self.ProtocoloUNE.STX[0]:
                logger.warning(f"Mensaje #{idx+1} sin STX válido, ignorando")
                continue
            
            # Log detallado del mensaje recibido
            self._log_mensaje_detallado(mensaje, 'RECIBIDO')
            
            subregulador = mensaje[1]
            codigo = mensaje[2]
            datos = mensaje[3:-2] if len(mensaje) > 5 else b''
            
            # Log del código recibido para debug
            codigo_decodificado = self.decodificar_byte_une(codigo)
            
            # Obtener información del código según norma UNE
            info_codigo = self.ProtocoloUNE.obtener_nombre_codigo(codigo_decodificado)
            
            logger.info(f"")
            logger.info(f"{'='*70}")
            logger.info(f"CÓDIGO RECIBIDO: 0x{codigo:02X} → DECODIFICADO: 0x{codigo_decodificado:02X}")
            logger.info(f"  Implementado: {'✅ SÍ' if info_codigo['implementado'] else '❌ NO'}")
            logger.info(f"  Nombre: {info_codigo['nombre']}")
            logger.info(f"  En norma UNE: {'✅ SÍ' if info_codigo['en_norma'] else '❌ NO'}")
            logger.info(f"  Descripción UNE: {info_codigo['nombre_norma']}")
            logger.info(f"{'='*70}")
            
            if not info_codigo['implementado']:
                if info_codigo['en_norma']:
                    logger.warning(f"⚠️ CÓDIGO EN NORMA PERO NO IMPLEMENTADO")
                    logger.warning(f"   Código: 0x{codigo_decodificado:02X}")
                    logger.warning(f"   Según UNE: {info_codigo['nombre_norma']}")
                    self._log(f"⚠️ Código 0x{codigo_decodificado:02X} en norma pero NO implementado: {info_codigo['nombre_norma']}", 'error')
                else:
                    logger.error(f"❌ CÓDIGO DESCONOCIDO - NO ESTÁ EN NORMA UNE")
                    logger.error(f"   Código codificado: 0x{codigo:02X}")
                    logger.error(f"   Código decodificado: 0x{codigo_decodificado:02X}")
                    self._log(f"❌ Código 0x{codigo_decodificado:02X} DESCONOCIDO - No está en norma UNE", 'error')
            
            # Procesar según código (usar código decodificado)
            if codigo_decodificado == 0x11:  # 0x91 decodificado → Sincronización
                # El regulador real responde ACK + mensaje con datos de sincronización
                logger.info("→ Respondiendo SINCRONIZACIÓN (0x91) - ACK + datos")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                resp = self.GeneradorRespuestas.respuesta_sincronizacion(self.estado, subregulador)
                self.enviar_mensaje(resp)
            
            elif codigo_decodificado == 0x12 or codigo_decodificado == 0x51:  # 0x92 o 0xD1 → Selección de plan
                logger.info("→ Procesando SELECCIÓN DE PLAN (0x92/0xD1)")
                self._procesar_cambio_plan(datos, subregulador)
            
            elif codigo_decodificado == 0x34:  # 0xB4 decodificado → Alarmas
                # El regulador real responde ACK + mensaje con datos
                logger.info("→ Respondiendo ALARMAS (0xB4) - ACK + datos")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                resp = self.GeneradorRespuestas.respuesta_alarmas(self.estado, subregulador)
                self.enviar_mensaje(resp)
            
            elif codigo_decodificado == 0x35:  # 0xB5 decodificado → Configuración
                # El regulador real responde ACK + eco vacío
                logger.info("→ Respondiendo CONFIGURACIÓN (0xB5) - ACK + eco")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                resp = self.GeneradorRespuestas.respuesta_configuracion(self.estado, subregulador)
                self.enviar_mensaje(resp)
            
            elif codigo_decodificado == 0x36:  # 0xB6 decodificado → Tablas programación
                # El regulador real responde ACK + eco vacío
                logger.info("→ Respondiendo TABLAS PROGRAMACIÓN (0xB6) - ACK + eco")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                resp = self.GeneradorRespuestas.respuesta_tablas_programacion(self.estado, subregulador)
                self.enviar_mensaje(resp)
            
            elif codigo_decodificado == 0x37:  # 0xB7 decodificado → Incompatibilidades
                # El regulador real responde ACK + eco vacío
                logger.info("→ Respondiendo INCOMPATIBILIDADES (0xB7) - ACK + eco")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                resp = self.GeneradorRespuestas.respuesta_incompatibilidades(self.estado, subregulador)
                self.enviar_mensaje(resp)
            
            elif codigo_decodificado == 0x14:  # 0x94 decodificado → Datos tráfico
                # El regulador real responde ACK + mensaje 0x94 con datos
                # IMPORTANTE: El byte 1 indica el estado de representación:
                #   0x01 = INTERMITENTE, 0x02 = COLORES
                # La central usa este byte para mostrar el "Estado de Luces"
                # Ejemplo captura real INTERMITENTE: 028194818183809603 (byte1=0x81→0x01)
                # Ejemplo captura real COLORES:      028194828183809503 (byte1=0x82→0x02)
                logger.info("→ Respondiendo DATOS TRÁFICO (0x94) - ACK + datos")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                # Construir respuesta con datos como regulador real
                from modules.protocolo_une import construir_mensaje, codificar_byte_une
                # Byte 1: Estado de representación (1=INTERMIT, 2=COLORES)
                # Byte 2: Control de planes (0=LOCAL, 1=ORDENADOR)
                # Byte 3: Coordinación (1=LOCAL, 3=ORDENADOR)
                # Byte 4: Método (0=tiempos fijos)
                estado_repr = self.estado.estado_representacion  # 1=INTERMIT, 2=COLORES
                control_planes = 1 if self.estado.modo_control == 2 else 0  # 1=ORDENADOR, 0=LOCAL
                coordinacion = 3 if self.estado.modo_control == 2 else 1  # 3=ORDENADOR, 1=LOCAL
                logger.info(f"   0x94: estado_repr={estado_repr}, control={control_planes}, coord={coordinacion}")
                datos_trafico = bytes([
                    codificar_byte_une(estado_repr),    # Estado representación
                    codificar_byte_une(control_planes), # Control de planes
                    codificar_byte_une(coordinacion),   # Coordinación
                    codificar_byte_une(0),              # Método (tiempos fijos)
                ])
                resp_94 = construir_mensaje(subregulador, 0x94, datos_trafico)
                self.enviar_mensaje(resp_94)
            
            elif codigo_decodificado == 0x52:  # 0xD2 decodificado → Puesta en hora
                # El regulador real responde ACK + eco 0xD2 sin datos
                # Ejemplo: C→R: 0280D28189A18193819AF203 → R→C: 06 + 0280D2D203
                logger.info("→ Respondiendo PUESTA EN HORA (0xD2) - ACK + eco")
                self._log("📥 Recibida puesta en hora de la central")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                # Eco sin datos (como regulador real)
                from modules.protocolo_une import construir_mensaje
                resp_d2 = construir_mensaje(subregulador, 0xD2, b'')
                self.enviar_mensaje(resp_d2)
            
            elif codigo_decodificado == 0x33:  # 0xB3 decodificado → Detectores
                # 0xB3 es solo para REPORTE del regulador a la central
                # La central NO usa 0xB3 para cambiar modos
                logger.info("→ Código 0xB3 recibido (normalmente solo lo envía el regulador)")
                logger.info("   Enviando ACK simple - Este código no cambia el modo")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
            
            elif codigo_decodificado == 0x54:  # 0xD4 decodificado → Estados
                logger.info("→ Procesando ESTADOS (0xD4) - PUEDE CAMBIAR MODO")
                self._log(f"🔔 CÓDIGO 0xD4 DETECTADO (Estados) en Sub:{subregulador}")
                self._procesar_cambio_modo(datos, subregulador)
            
            elif codigo_decodificado == 0x5D:  # 0xDD decodificado → Código propietario Ecotrafix
                # El regulador real responde ACK + eco
                # Ejemplo: C→R: 0280DDDD03 → R→C: 06 + 0280DDDD03
                logger.info("→ Respondiendo código propietario (0xDD) - ACK + eco")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
                time.sleep(0.02)
                from modules.protocolo_une import construir_mensaje
                resp_dd = construir_mensaje(subregulador, 0xDD, b'')
                self.enviar_mensaje(resp_dd)
            
            elif codigo_decodificado == 0x20:  # Petición estado/detectores
                logger.info("→ Procesando PETICIÓN ESTADO (0x20)")
                self._log(f"📥 Central solicita estado (0x20) - enviando 0xB3")
                self._responder_peticion_estado()
            
            else:
                # Código no implementado - ya se registró arriba con comparación UNE
                # Enviar ACK para confirmar recepción aunque no se procese
                logger.warning(f"→ ENVIANDO ACK (código no procesado)")
                self.enviar_mensaje(self.ProtocoloUNE.ACK)
    
    def _responder_peticion_estado(self):
        """Responde a petición 0x20 con mensaje 0xB3 informando modo de control
        
        NOTA IMPORTANTE: Según la captura del regulador real, SIEMPRE envía byte 0x80
        (decodificado 0x00) independientemente del estado de representación o modo.
        La central Ecotrafix no usa B3 para determinar el estado de luces.
        """
        MODOS_STR = {1: "LOCAL", 2: "ORDENADOR", 3: "MANUAL"}
        
        logger.info("")
        logger.info("="*70)
        logger.info("RESPUESTA A PETICIÓN 0x20 (Estado)")
        logger.info(f"  Modo actual: {MODOS_STR.get(self.estado.modo_control, '?')} ({self.estado.modo_control})")
        logger.info(f"  Estado representación: {self.estado.estado_representacion}")
        logger.info("="*70)
        
        # SEGÚN CAPTURA DEL REGULADOR REAL:
        # El regulador SIEMPRE envía 0x80 (= 0x00 decodificado) en el byte de modo
        # sin importar el estado de representación ni el modo de control.
        # La central NO usa B3 para determinar COLORES/INTERMITENTE.
        #
        # Ejemplo de captura (regulador en INTERMITENTE):
        #   R→C | 0280B380808080... | Byte modo: 0x00, Estado repr: APAGADO, MODO: LOCAL
        #
        # Construimos exactamente igual que el regulador real
        
        # Byte de modo: SIEMPRE 0x00 como el regulador real
        byte_modo = 0x00
        byte_modo_codificado = byte_modo | 0x80
        
        # Construir datos: 48 bytes, primero con modo (0x80), resto 0x80
        datos_b3 = bytes([byte_modo_codificado] + [0x80] * 47)
        
        from modules.protocolo_une import construir_mensaje
        msg_b3 = construir_mensaje(self.sub_cpu, 0xB3, datos_b3)
        
        logger.info(f"📤 Enviando 0xB3: Modo={MODOS_STR.get(self.estado.modo_control, '?')}, Estado repr={self.estado.estado_representacion}")
        logger.info(f"   Byte modo: 0x{byte_modo:02X} → codificado: 0x{byte_modo_codificado:02X} (igual que regulador real)")
        self._log(f"📤 Informando estado a la central (0xB3)")
        
        self.enviar_mensaje(msg_b3)
    
    def _procesar_cambio_modo(self, datos, subregulador):
        """Procesa cambio de modo desde 0xD4 (Estados)
        
        Formato del mensaje 0xD4 según capturas reales:
        ORDENADOR: 0281D482818380D503 → Bytes: 82 81 83 80 → Decodif: 02 01 03 00
        LOCAL:     0281D482808180D603 → Bytes: 82 80 81 80 → Decodif: 02 00 01 00
        INTERMIT:  0281D481818380D603 → Bytes: 81 81 83 80 → Decodif: 01 01 03 00
        
        Byte1: Estado representación (01=INTERMITENTE, 02=COLORES)
        Byte2: Control planes (00=LOCAL, 01=ORDENADOR)
        Byte3: Coordinación (01=LOCAL, 03=ORDENADOR)
        Byte4: Método (00=tiempos fijos)
        """
        MODOS = {1: "LOCAL", 2: "ORDENADOR", 3: "MANUAL"}
        ESTADOS_REPR = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES", 3: "MANUAL"}
        
        if len(datos) < 3:
            self._log(f"⚠️ Petición 0xD4 con datos insuficientes ({len(datos)} bytes) - enviando ACK", 'error')
            self.enviar_mensaje(self.ProtocoloUNE.ACK)
            return
        
        # Extraer y decodificar bytes
        byte1 = self.decodificar_byte_une(datos[0])  # Estado representación
        byte2 = self.decodificar_byte_une(datos[1])  # Control planes
        byte3 = self.decodificar_byte_une(datos[2])  # Coordinación
        byte4 = self.decodificar_byte_une(datos[3]) if len(datos) > 3 else 0  # Método
        
        # Log detallado de los bytes recibidos
        logger.info(f"")
        logger.info(f"{'='*70}")
        logger.info(f"COMANDO 0xD4 (ESTADOS) RECIBIDO")
        logger.info(f"  Byte 1 (Estado repr): 0x{datos[0]:02X} → 0x{byte1:02X} = {ESTADOS_REPR.get(byte1, '?')}")
        logger.info(f"  Byte 2 (Control):     0x{datos[1]:02X} → 0x{byte2:02X} = {'ORDENADOR' if byte2 == 0x01 else 'LOCAL'}")
        logger.info(f"  Byte 3 (Coord):       0x{datos[2]:02X} → 0x{byte3:02X} = {'ORDENADOR' if byte3 == 0x03 else 'LOCAL'}")
        if len(datos) > 3:
            logger.info(f"  Byte 4 (Método):      0x{datos[3]:02X} → 0x{byte4:02X}")
        logger.info(f"{'='*70}")
        
        # Determinar modo de control basado en Byte2 y Byte3
        # Según capturas reales:
        # ORDENADOR: byte2=0x01, byte3=0x03
        # LOCAL:     byte2=0x00, byte3=0x01
        
        modo_anterior = self.estado.modo_control
        estado_repr_anterior = self.estado.estado_representacion
        
        # Byte2 indica el control de planes
        if byte2 == 0x01 or byte3 == 0x03:
            modo_nuevo = 2  # ORDENADOR
        else:
            modo_nuevo = 1  # LOCAL
        
        # Byte1 indica estado de representación
        estado_repr_nuevo = byte1 & 0x03  # 01=INTERMITENTE, 02=COLORES
        
        # Log detallado de la petición
        self._log("="*70)
        self._log("🔔 COMANDO 0xD4 (ESTADOS) RECIBIDO", 'importante')
        self._log(f"   Estado repr: {ESTADOS_REPR.get(estado_repr_nuevo, '?')}")
        self._log(f"   Control: {'ORDENADOR' if byte2 == 0x01 else 'LOCAL'}")
        
        if modo_anterior != modo_nuevo:
            self._log(f"🔄 CAMBIO DE MODO: {MODOS.get(modo_anterior, '?')} → {MODOS.get(modo_nuevo, '?')}", 'importante')
            logger.info(f"🔄 CAMBIO DE MODO: {MODOS.get(modo_anterior, '?')} → {MODOS.get(modo_nuevo, '?')}")
        
        if estado_repr_anterior != estado_repr_nuevo:
            self._log(f"🔄 CAMBIO ESTADO REPR: {ESTADOS_REPR.get(estado_repr_anterior, '?')} → {ESTADOS_REPR.get(estado_repr_nuevo, '?')}", 'importante')
            logger.info(f"🔄 CAMBIO ESTADO REPR: {ESTADOS_REPR.get(estado_repr_anterior, '?')} → {ESTADOS_REPR.get(estado_repr_nuevo, '?')}")
        
        self._log("="*70)
        
        # Aplicar cambios
        self.estado.cambiar_modo(modo_nuevo, estado_repr_nuevo)
        
        # VERIFICACIÓN: Confirmar que el estado interno se actualizó
        logger.info(f"Estado interno verificado: modo_control={self.estado.modo_control}, estado_repr={self.estado.estado_representacion}")
        
        self._actualizar_estado(modo=modo_nuevo)
        
        # Responder con ACK
        logger.info("✅ Enviando ACK de confirmación")
        self._log(f"✅ Enviando ACK de confirmación")
        self.enviar_mensaje(self.ProtocoloUNE.ACK)
        time.sleep(0.1)
        
        # Según el log del sniffer, el regulador real responde 0xD4 con ACK simple (sin datos)
        # Ejemplo del log: C→R: 0281D482818380D503  →  R→C: 0281D4D503
        # Solo devuelve: STX + SUB + CÓDIGO + BCC + ETX
        from modules.protocolo_une import construir_mensaje
        resp_ack = construir_mensaje(subregulador, 0xD4, b'')
        logger.info(f"📤 RESPONDIENDO 0xD4 (ACK sin datos) en Sub:{subregulador}")
        self._log(f"📤 RESPONDIENDO 0xD4 - Modo {MODOS.get(modo_nuevo, '?')}")
        self.enviar_mensaje(resp_ack)
        time.sleep(0.1)
        
        # Según la captura del regulador real, después del D4 envía B9 con el estado de grupos
        # Especialmente importante para INTERMITENTE donde los grupos deben mostrar ámbar intermitente (0x8C)
        logger.info(f"📤 ENVIANDO B9 (estado grupos) después de cambio de modo/estado")
        msg_grupos = self.GeneradorRespuestas.mensaje_estado_grupos(self.estado, self.sub_cpu)
        self.enviar_mensaje(msg_grupos)
        self._log(f"📤 Enviado B9 - Estado grupos: {self.estado.get_estado_grupos()}")
    
    def _procesar_cambio_plan(self, datos, subregulador):
        """Procesa un mensaje de cambio de plan desde la central"""
        if len(datos) < 1:
            logger.warning("Mensaje de selección de plan sin datos")
            self._log("⚠️ Petición de cambio de plan sin datos", 'error')
            self.enviar_mensaje(self.ProtocoloUNE.ACK)
            return
        
        plan_recibido = self.decodificar_byte_une(datos[0])
        
        # El plan recibido de la central viene en formato 3, 4, 5...
        # Pero nuestra configuración usa IDs 129, 131, 132, 133...
        # Necesitamos mapear el plan de la central al ID interno
        # Opción 1: Sumar 128 (3 → 131, 4 → 132, 5 → 133)
        # Opción 2: Usar un mapeo configurable
        nuevo_plan = plan_recibido + 128
        
        logger.info(f"  → PLAN RECIBIDO DE CENTRAL: {plan_recibido}")
        logger.info(f"  → PLAN CONVERTIDO (+ 128): {nuevo_plan}")
        
        plan_anterior = self.estado.plan_actual
        
        # Logs detallados para archivo
        logger.info(f"")
        logger.info(f"{'#'*70}")
        logger.info(f"CAMBIO DE PLAN SOLICITADO POR LA CENTRAL")
        logger.info(f"Plan anterior: {plan_anterior}")
        logger.info(f"Plan solicitado: {nuevo_plan}")
        logger.info(f"{'#'*70}")
        
        # Logs detallados también en la GUI
        self._log("="*70)
        self._log("🔔 CAMBIO DE PLAN SOLICITADO POR LA CENTRAL", 'importante')
        self._log(f"   Plan anterior: {plan_anterior}")
        self._log(f"   Plan solicitado: {nuevo_plan}")
        self._log("="*70)
        
        # Intentar cambiar el plan
        if self.estado.cambiar_plan(nuevo_plan):
            logger.info(f"✅ Plan cambiado exitosamente a {nuevo_plan}")
            self._log(f"✅ Plan cambiado exitosamente a: {nuevo_plan}", 'importante')
            self._actualizar_estado(plan=nuevo_plan)
            
            # Enviar ACK
            self._log("📤 Enviando ACK de confirmación")
            self.enviar_mensaje(self.ProtocoloUNE.ACK)
            time.sleep(0.05)
            
            # Según log del sniffer, el regulador real responde 0xD1 con ACK simple (sin datos adicionales)
            # Ejemplo: C→R: 0281D1868DBBBBDB03  →  R→C: 0281D1D003
            from modules.protocolo_une import construir_mensaje
            resp_ack = construir_mensaje(subregulador, 0xD1, b'')
            logger.info(f"📤 RESPONDIENDO 0xD1 (ACK sin datos) en Sub:{subregulador}")
            self._log(f"📤 RESPONDIENDO 0xD1 - Plan {nuevo_plan}")
            self.enviar_mensaje(resp_ack)
            
            # El callback _on_plan_changed NO debe enviar estado completo aquí
            # La sincronización se enviará cuando la central la solicite con 0x91
        else:
            logger.error(f"❌ Plan {nuevo_plan} no existe en la configuración")
            self._log(f"❌ Plan {nuevo_plan} no existe en la configuración", 'error')
            self._log("📤 Enviando NAK (rechazo)")
            self.enviar_mensaje(self.ProtocoloUNE.NAK)
    
    def detener(self):
        """Detiene el regulador"""
        self.conectado = False
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self._log("Regulador detenido")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    app = ReguladorGUI()
    app.ejecutar()
