"""
Módulo de Estado del Regulador
Gestiona el estado interno del regulador virtual
"""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EstadoRegulador:
    """Clase que mantiene el estado completo del regulador"""
    
    def __init__(self, config_path=None):
        """Inicializa el estado desde archivo de configuración"""
        self.config = self._cargar_config(config_path)
        self._inicializar_estado()
    
    def _cargar_config(self, config_path):
        """Carga la configuración desde archivo JSON"""
        if config_path is None:
            # Buscar archivo de configuración por defecto
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_path, 'config', 'regulador_config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Configuración cargada desde: {config_path}")
                return config
        except FileNotFoundError:
            logger.warning(f"Archivo de configuración no encontrado: {config_path}")
            return self._config_por_defecto()
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear configuración: {e}")
            return self._config_por_defecto()
    
    def _config_por_defecto(self):
        """Retorna configuración por defecto"""
        return {
            "regulador": {
                "modo_operacion": "A",
                "puerto_escucha": 19000
            },
            "subreguladores": {
                "cpu_estado": 128,
                "planes_sync": 129
            },
            "grupos": {"cantidad": 6},
            "detectores": {"cantidad": 4},
            "planes": {
                "plan_activo": 130,
                "lista": [
                    {"id": 130, "ciclo": 130, "fase1": 65, "fase2": 60, "estructura": 1, "transitorio": 5}
                ]
            },
            "estado_inicial": {
                "modo_control": 1,
                "estado_representacion": 2
            }
        }
    
    def _inicializar_estado(self):
        """Inicializa todas las variables de estado"""
        # Callback para notificar cambios de plan
        self._on_plan_change_callback = None
        
        # Secuencia de arranque
        self.en_secuencia_arranque = False
        self.fase_arranque = 0  # 0=ninguna, 1=ámbar inter, 2=ámbar, 3=todo rojo
        self.tiempo_fase_arranque = 0
        self.arranque_completado = False
        
        # Configuración básica
        cfg = self.config
        
        # Planes
        planes_cfg = cfg.get('planes', {})
        self.planes = {p['id'] for p in planes_cfg.get('lista', [])}
        self.plan_actual = planes_cfg.get('plan_activo', 130)
        self.planes_config = {p['id']: p for p in planes_cfg.get('lista', [])}
        
        # Estado
        estado_cfg = cfg.get('estado_inicial', {})
        # Modo ORDENADOR: El regulador inicia en modo ordenador para que la central pueda
        # enviar comandos D1 (selección de plan) y D4 (cambio de modo)
        self.modo_control = 2  # 2 = ORDENADOR (para que la central pueda forzar planes)
        self.estado_representacion = estado_cfg.get('estado_representacion', 2)
        
        logger.info("Modo de control inicial: ORDENADOR (2) - La central puede forzar planes via 0xD1")
        
        # Fases - nuevo formato con 'lista' en lugar de 'configuracion'
        fases_cfg = cfg.get('fases', {})
        fases_lista = fases_cfg.get('lista', fases_cfg.get('configuracion', []))
        self.fases_config = {}
        for f in fases_lista:
            fase_id = f.get('id', f.get('fase', 1))
            self.fases_config[fase_id] = f
        self.fase_actual = 1
        
        # Estructuras (nuevo)
        estructuras_cfg = cfg.get('estructuras', {})
        self.estructuras = {e['id']: e for e in estructuras_cfg.get('lista', [])}
        
        # Ciclo
        plan_config = self.get_plan_config()
        self.ciclo_actual = 0
        self.tiempo_ciclo = plan_config.get('ciclo', 130)
        
        # Posición en la estructura (para seguir la secuencia)
        self.posicion_estructura = 0
        self.en_transitorio = False
        self.tiempo_en_paso = 0
        
        # Grupos
        grupos_cfg = cfg.get('grupos', {})
        self.num_grupos = grupos_cfg.get('cantidad', 6)
        self.grupos = list(range(1, self.num_grupos + 1))
        self.grupos_descripcion = {g['id']: g for g in grupos_cfg.get('descripcion', [])}
        self.estado_grupos = [0] * self.num_grupos
        
        # Grupos que siempre están en ámbar
        self.grupos_siempre_ambar = []
        for g in grupos_cfg.get('descripcion', []):
            if g.get('siempre_ambar', False):
                self.grupos_siempre_ambar.append(g['id'])
        
        # Detectores
        det_cfg = cfg.get('detectores', {})
        self.num_detectores = det_cfg.get('cantidad', 4)
        self.detectores = [False] * self.num_detectores
        self.contador_detectores = [0] * self.num_detectores
        self.tiempo_real_detectores = det_cfg.get('tiempo_real', False)
        
        # Alarmas
        alarmas_cfg = cfg.get('alarmas', {})
        self.alarma_roja = alarmas_cfg.get('alarma_roja', False)
        self.alarma_lampara = alarmas_cfg.get('alarma_lampara', False)
        self.alarma_conflicto = alarmas_cfg.get('alarma_conflicto', False)
        
        logger.info(f"Estado inicializado: Plan={self.plan_actual}, Modo={self.modo_control}, "
                    f"Estado repr={self.estado_representacion}, Grupos={self.num_grupos}, "
                    f"Fases={len(self.fases_config)}, Estructuras={len(self.estructuras)}")
        
        # Selección automática de plan según horario (forzar al inicio)
        planes_cfg = self.config.get('planes', {})
        if planes_cfg.get('seleccion_automatica', True):
            self.seleccionar_plan_por_horario(forzar_inicial=True)
            logger.info(f"Plan inicial seleccionado por horario: {self.plan_actual}")
    
    def get_plan_config(self, plan_id=None):
        """Obtiene la configuración de un plan específico o el actual"""
        if plan_id is None:
            plan_id = self.plan_actual
        
        if plan_id in self.planes_config:
            return self.planes_config[plan_id]
        
        # Plan por defecto si no existe
        return {
            'id': plan_id,
            'ciclo': 130,
            'fase1': 65,
            'fase2': 60,
            'estructura': 1,
            'transitorio': 5,
            'desfase': 0,
            'minimo': 20,
            'maximo': 50
        }
    
    def seleccionar_plan_por_horario(self, forzar_inicial=False):
        """
        Selecciona automáticamente el plan según la hora actual.
        
        Args:
            forzar_inicial: Si es True, selecciona el plan aunque esté en modo ORDENADOR.
                           Útil para establecer el plan inicial al arrancar.
        
        En operación normal (no inicial), solo funciona en modo LOCAL.
        En modo ORDENADOR, la central decide el plan mediante comandos.
        
        Los planes solo tienen hora de inicio. El plan activo es el último
        cuya hora de inicio ya pasó.
        """
        from datetime import datetime
        
        # Solo selección automática en modo LOCAL (excepto al inicio)
        if not forzar_inicial and self.modo_control != 1:  # 1 = LOCAL
            logger.debug(f"Modo {self.modo_control} (no LOCAL), la central controla el plan")
            return self.plan_actual
        
        ahora = datetime.now()
        hora_actual = ahora.strftime("%H:%M")
        
        # Construir lista de (hora_inicio, plan_id) ordenada
        planes_horarios = []
        for plan_id, plan_config in self.planes_config.items():
            horarios = plan_config.get('horarios', [])
            for horario in horarios:
                # Solo usar hora de inicio
                inicio = horario.get('inicio', horario.get('hora_inicio', '00:00'))
                planes_horarios.append((inicio, plan_id))
        
        # Ordenar por hora de inicio
        planes_horarios.sort(key=lambda x: x[0])
        
        if not planes_horarios:
            logger.warning(f"No hay planes con horarios definidos. Plan actual: {self.plan_actual}")
            return self.plan_actual
        
        logger.debug(f"Evaluando horarios - Hora actual: {hora_actual}")
        logger.debug(f"Planes con horario: {planes_horarios}")
        
        # Encontrar el plan cuya hora de inicio ya pasó (el más reciente)
        plan_seleccionado = planes_horarios[0][1]  # Por defecto el primero
        
        for hora_inicio, plan_id in planes_horarios:
            if hora_inicio <= hora_actual:
                plan_seleccionado = plan_id
                logger.debug(f"  Hora {hora_inicio} <= {hora_actual} → Candidato: Plan {plan_id}")
            else:
                logger.debug(f"  Hora {hora_inicio} > {hora_actual} → Descartado: Plan {plan_id}")
                break  # Ya pasamos la hora actual
        
        # Si ninguno coincide (hora actual < primera hora), usar el último del día anterior
        if hora_actual < planes_horarios[0][0]:
            plan_seleccionado = planes_horarios[-1][1]
            logger.debug(f"  Hora actual antes del primer horario, usando último plan del día: {plan_seleccionado}")
        
        if plan_seleccionado != self.plan_actual:
            logger.info(f"")
            logger.info(f"{'!'*70}")
            logger.info(f"[CAMBIO AUTOMÁTICO DE PLAN POR HORARIO]")
            logger.info(f"Hora actual: {hora_actual}")
            logger.info(f"Plan anterior: {self.plan_actual}")
            logger.info(f"Plan nuevo: {plan_seleccionado}")
            logger.info(f"{'!'*70}")
            self.cambiar_plan(plan_seleccionado)
        else:
            logger.debug(f"Plan {plan_seleccionado} ya está activo, no hay cambio")
        
        return plan_seleccionado
    
    def iniciar_secuencia_arranque(self):
        """Inicia la secuencia de arranque del regulador"""
        logger.info("")
        logger.info("="*70)
        logger.info("🚦 INICIANDO SECUENCIA DE ARRANQUE DEL REGULADOR")
        logger.info("  Fase 1 (5s): Grupos verticales Ámbar intermitente, peatonales Apagados")
        logger.info("  Fase 2 (4s): Grupos verticales Ámbar, peatonales Apagados")
        logger.info("  Fase 3 (3s): Todos los grupos en Rojo")
        logger.info("="*70)
        
        self.en_secuencia_arranque = True
        self.fase_arranque = 1
        self.tiempo_fase_arranque = 0
        self.arranque_completado = False
        
        # Aplicar fase 1: Ámbar intermitente en grupos verticales
        self._aplicar_fase_arranque()
    
    def _aplicar_fase_arranque(self):
        """Aplica el estado de grupos según la fase de arranque actual"""
        if self.fase_arranque == 1:
            # Fase 1: Grupos verticales en Ámbar intermitente (6), peatonales Apagados (0)
            logger.info("🔶 ARRANQUE FASE 1: Ámbar intermitente en grupos verticales")
            for i in range(self.num_grupos):
                grupo_id = i + 1
                # Verificar si es grupo vertical o peatonal
                es_peatonal = False
                if grupo_id in self.grupos_descripcion:
                    tipo = self.grupos_descripcion[grupo_id].get('tipo', 'vehicular')
                    es_peatonal = tipo == 'peatonal'
                
                if es_peatonal:
                    self.estado_grupos[i] = 0  # Apagado
                else:
                    self.estado_grupos[i] = 6  # Ámbar intermitente
        
        elif self.fase_arranque == 2:
            # Fase 2: Grupos verticales en Ámbar (2), peatonales Apagados (0)
            logger.info("🟡 ARRANQUE FASE 2: Ámbar en grupos verticales")
            for i in range(self.num_grupos):
                grupo_id = i + 1
                es_peatonal = False
                if grupo_id in self.grupos_descripcion:
                    tipo = self.grupos_descripcion[grupo_id].get('tipo', 'vehicular')
                    es_peatonal = tipo == 'peatonal'
                
                if es_peatonal:
                    self.estado_grupos[i] = 0  # Apagado
                else:
                    self.estado_grupos[i] = 2  # Ámbar
        
        elif self.fase_arranque == 3:
            # Fase 3: Todos en Rojo (3)
            logger.info("🔴 ARRANQUE FASE 3: Todos los grupos en Rojo")
            for i in range(self.num_grupos):
                self.estado_grupos[i] = 3  # Rojo
    
    def actualizar_arranque(self):
        """Actualiza el estado de la secuencia de arranque. Retorna True si hay cambio de fase"""
        if not self.en_secuencia_arranque:
            return False
        
        self.tiempo_fase_arranque += 1
        cambio = False
        
        # Fase 1: 5 segundos
        if self.fase_arranque == 1 and self.tiempo_fase_arranque >= 5:
            logger.info(f"✅ Fase 1 completada ({self.tiempo_fase_arranque}s)")
            self.fase_arranque = 2
            self.tiempo_fase_arranque = 0
            self._aplicar_fase_arranque()
            cambio = True
        
        # Fase 2: 4 segundos
        elif self.fase_arranque == 2 and self.tiempo_fase_arranque >= 4:
            logger.info(f"✅ Fase 2 completada ({self.tiempo_fase_arranque}s)")
            self.fase_arranque = 3
            self.tiempo_fase_arranque = 0
            self._aplicar_fase_arranque()
            cambio = True
        
        # Fase 3: 3 segundos
        elif self.fase_arranque == 3 and self.tiempo_fase_arranque >= 3:
            logger.info(f"✅ Fase 3 completada ({self.tiempo_fase_arranque}s)")
            logger.info("")
            logger.info("="*70)
            logger.info("🎉 SECUENCIA DE ARRANQUE COMPLETADA")
            logger.info(f"   Iniciando operación normal con Plan {self.plan_actual}")
            logger.info("="*70)
            self.en_secuencia_arranque = False
            self.arranque_completado = True
            self.fase_arranque = 0
            self.tiempo_fase_arranque = 0
            # No devolver cambio aquí, dejar que el ciclo normal tome control
            return False
        
        return cambio
    
    def get_parametros_plan(self):
        """Obtiene los parámetros del plan actual"""
        return self.get_plan_config(self.plan_actual)
    
    def set_on_plan_change_callback(self, callback):
        """
        Registra un callback que se invocará cuando cambie el plan.
        El callback recibe: (plan_anterior, nuevo_plan)
        """
        self._on_plan_change_callback = callback
    
    def cambiar_plan(self, nuevo_plan):
        """Cambia al plan especificado"""
        if nuevo_plan in self.planes:
            plan_anterior = self.plan_actual
            self.plan_actual = nuevo_plan
            logger.info(f"[EstadoRegulador.cambiar_plan] Plan cambiado: {plan_anterior} → {nuevo_plan}")
            logger.info(f"   self.plan_actual ahora es: {self.plan_actual}")
            
            plan_config = self.get_plan_config()
            self.tiempo_ciclo = plan_config.get('ciclo', 130)
            logger.info(f"Plan cambiado: {plan_anterior} → {nuevo_plan}")
            
            # Notificar el cambio de plan via callback
            if self._on_plan_change_callback and plan_anterior != nuevo_plan:
                try:
                    logger.info(f"   Invocando callback _on_plan_change_callback...")
                    self._on_plan_change_callback(plan_anterior, nuevo_plan)
                except Exception as e:
                    logger.error(f"Error en callback de cambio de plan: {e}")
            
            return True
        else:
            logger.warning(f"Plan {nuevo_plan} no existe")
            return False
    
    def cambiar_modo(self, nuevo_modo, nuevo_estado_repr=None):
        """Cambia el modo de control y/o estado de representación"""
        modo_anterior = self.modo_control
        estado_repr_anterior = self.estado_representacion
        
        self.modo_control = nuevo_modo
        logger.info(f"[EstadoRegulador.cambiar_modo] self.modo_control cambiado a: {nuevo_modo}")
        
        if nuevo_estado_repr is not None:
            self.estado_representacion = nuevo_estado_repr
            logger.info(f"[EstadoRegulador.cambiar_modo] self.estado_representacion cambiado a: {nuevo_estado_repr}")
        
        MODOS = {1: "LOCAL", 2: "ORDENADOR", 3: "MANUAL"}
        ESTADOS = {0: "APAGADO", 1: "INTERMITENTE", 2: "COLORES"}
        
        logger.info(f"Modo cambiado: {MODOS.get(modo_anterior, '?')} → {MODOS.get(nuevo_modo, '?')}")
        if nuevo_estado_repr is not None:
            logger.info(f"Estado repr cambiado: {ESTADOS.get(estado_repr_anterior, '?')} → {ESTADOS.get(nuevo_estado_repr, '?')}")
        
        return modo_anterior, estado_repr_anterior
    
    def get_estado_grupos(self):
        """Obtiene el estado de los grupos según la fase actual"""
        # Estados UNE: 0=Apagado, 1=Verde, 2=Ámbar, 3=Rojo, 4=Rojo Int, 5=Verde Int, 6=Ámbar Int
        
        if self.estado_representacion == 0:  # Apagado
            return [0] * self.num_grupos
        
        if self.estado_representacion == 1:  # Intermitente
            return [6] * self.num_grupos  # Todos en ámbar intermitente
        
        # Si estamos en transitorio, aplicar la lógica de transitorio
        if self.en_transitorio:
            return self._get_estado_transitorio()
        
        # Estado Colores - calcular según fase actual
        estados = [3] * self.num_grupos  # Por defecto rojo
        
        # Obtener configuración de la fase actual
        fase_config = self.fases_config.get(self.fase_actual, {})
        
        # Nuevo formato: fase tiene 'grupos' como dict con colores
        grupos_colores = fase_config.get('grupos', {})
        
        if grupos_colores:
            # Nuevo formato: {'1': 1, '2': 3, ...} donde valor es el código de color
            for g_str, color in grupos_colores.items():
                g = int(g_str)
                if 1 <= g <= self.num_grupos:
                    estados[g - 1] = color
        else:
            # Formato antiguo: grupos_verde y grupos_rojo
            grupos_verde = fase_config.get('grupos_verde', [1, 5, 6] if self.fase_actual == 1 else [2, 3, 4])
            for g in grupos_verde:
                if 1 <= g <= self.num_grupos:
                    estados[g - 1] = 1  # Verde
        
        # Grupos que siempre están en ámbar
        for g in self.grupos_siempre_ambar:
            if 1 <= g <= self.num_grupos:
                estados[g - 1] = 2  # Ámbar
        
        return estados
    
    def _get_estado_transitorio(self):
        """Obtiene el estado de los grupos durante un transitorio"""
        # Obtener tiempos de transitorio del plan
        plan_config = self.get_plan_config()
        transitorios = plan_config.get('transitorios', {})
        trans_veh = transitorios.get('vehicular', {})
        tiempo_ambar = trans_veh.get('tiempo_ambar', 3)
        tiempo_rojo_seg = trans_veh.get('tiempo_rojo_seguridad', 2)
        
        # Obtener la fase que acaba de terminar (fase_actual contiene la fase anterior durante el transitorio)
        fase_config = self.fases_config.get(self.fase_actual, {})
        grupos_colores = fase_config.get('grupos', {})
        
        estados = [3] * self.num_grupos  # Por defecto rojo
        
        if self.tiempo_en_paso <= tiempo_ambar:
            # Fase ámbar: grupos que estaban en verde pasan a ámbar
            for g_str, color in grupos_colores.items():
                g = int(g_str)
                if 1 <= g <= self.num_grupos:
                    if color == 1:  # Era verde -> pasa a ámbar
                        estados[g - 1] = 2  # Ámbar
                    else:
                        estados[g - 1] = 3  # Rojo
        else:
            # Fase rojo de seguridad: todos en rojo
            for g in range(self.num_grupos):
                estados[g] = 3  # Rojo
        
        return estados
    
    def get_estructura_actual(self):
        """Obtiene la estructura del plan actual"""
        plan_config = self.get_plan_config()
        estructura_id = plan_config.get('estructura_id', plan_config.get('estructura', 1))
        return self.estructuras.get(estructura_id, {'secuencia': []})
    
    def get_duracion_fase(self, fase_id):
        """Obtiene la duración de una fase según el plan actual"""
        plan_config = self.get_plan_config()
        duraciones = plan_config.get('duraciones_fases', {})
        
        # Intentar obtener del nuevo formato
        duracion = duraciones.get(str(fase_id), duraciones.get(fase_id, None))
        
        if duracion is not None:
            return duracion
        
        # Fallback al formato antiguo (fase1, fase2)
        if fase_id == 1:
            return plan_config.get('fase1', 30)
        elif fase_id == 2:
            return plan_config.get('fase2', 30)
        
        return 30  # Default
    
    def actualizar_ciclo(self):
        """Actualiza el tiempo de ciclo y detecta cambios de fase"""
        self.ciclo_actual += 1
        
        plan_config = self.get_plan_config()
        ciclo_total = plan_config.get('ciclo', 130)
        
        # Reset ciclo si llega al final
        if self.ciclo_actual >= ciclo_total:
            self.ciclo_actual = 0
            self.posicion_estructura = 0
            self.tiempo_en_paso = 0
        
        # Obtener estructura actual
        estructura = self.get_estructura_actual()
        secuencia = estructura.get('secuencia', [])
        
        if not secuencia:
            # Fallback al formato antiguo (fase1, fase2)
            fase1_duracion = plan_config.get('fase1', 65)
            fase_anterior = self.fase_actual
            self.fase_actual = 1 if self.ciclo_actual < fase1_duracion else 2
            return self.fase_actual != fase_anterior
        
        # Usar secuencia de estructura
        self.tiempo_en_paso += 1
        fase_anterior = self.fase_actual
        
        # Obtener paso actual de la secuencia
        if self.posicion_estructura < len(secuencia):
            paso = secuencia[self.posicion_estructura]
            
            if paso.get('tipo') == 'estable':
                # Es una fase estable
                fase_id = paso.get('fase', 1)
                duracion = self.get_duracion_fase(fase_id)
                
                self.fase_actual = fase_id
                self.en_transitorio = False
                
                # Si pasó el tiempo, avanzar al siguiente paso
                if self.tiempo_en_paso >= duracion:
                    self._avanzar_paso(secuencia)
            
            elif paso.get('tipo') == 'transitorio':
                # Es un transitorio entre fases
                self.en_transitorio = True
                
                # Obtener tiempos de transitorio del plan
                transitorios = plan_config.get('transitorios', {})
                trans_veh = transitorios.get('vehicular', {})
                trans_pea = transitorios.get('peatonal', {})
                
                t_veh = trans_veh.get('tiempo_ambar', 3) + trans_veh.get('tiempo_rojo_seguridad', 2)
                t_pea = trans_pea.get('tiempo_verde_intermitente', 5) + trans_pea.get('tiempo_rojo', 2)
                duracion_trans = max(t_veh, t_pea)
                
                if self.tiempo_en_paso >= duracion_trans:
                    self._avanzar_paso(secuencia)
        
        return self.fase_actual != fase_anterior
    
    def _avanzar_paso(self, secuencia):
        """Avanza al siguiente paso de la secuencia"""
        self.posicion_estructura += 1
        self.tiempo_en_paso = 0
        
        # Si llegamos al final, volver al inicio
        if self.posicion_estructura >= len(secuencia):
            self.posicion_estructura = 0
    
    def to_dict(self):
        """Exporta el estado actual como diccionario"""
        return {
            'plan_actual': self.plan_actual,
            'modo_control': self.modo_control,
            'estado_representacion': self.estado_representacion,
            'fase_actual': self.fase_actual,
            'ciclo_actual': self.ciclo_actual,
            'estado_grupos': self.get_estado_grupos(),
            'alarmas': {
                'roja': self.alarma_roja,
                'lampara': self.alarma_lampara,
                'conflicto': self.alarma_conflicto
            }
        }
