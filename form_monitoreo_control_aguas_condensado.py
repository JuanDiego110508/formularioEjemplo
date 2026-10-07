import flet as ft
import datetime
import threading
import time
import os
import sys
import unicodedata

# 🟢 Conexión a SQL Server
try:
    import conexion
except ImportError:
    conexion = None


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


def limpiar_texto(texto):
    if not texto:
        return ""
    texto_str = str(texto).strip().upper()
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto_str)
        if unicodedata.category(c) != "Mn"
    )


# ==================================================
# CONSULTA DE ÚLTIMOS REGISTROS DESDE BD
# ==================================================
def obtener_ultimos_registros_bd():
    if not conexion:
        return {}

    query = """
    WITH UltimosRegistros AS (
        SELECT 
            id_registro, fecha, hora, seccion, analizo, usuario_registro,
            ph, std, conductividad, dureza, co2, alcalinidad_m, cloruros,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(seccion, 'Á', 'A'), 'É', 'E'), 'Í', 'I'), 'Ó', 'O'), 'Ú', 'U'))
                ORDER BY fecha DESC, hora DESC, id_registro DESC
            ) as rn
        FROM Registro_Monitoreo_Condensados_FMAN46
    )
    SELECT seccion, fecha, hora, analizo, ph, std, conductividad, dureza, co2, alcalinidad_m, cloruros
    FROM UltimosRegistros
    WHERE rn = 1
    """

    conn = None
    resultados = {}
    try:
        conn = conexion.obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(query)
        filas = cursor.fetchall()

        for f in filas:
            sec_limpia = limpiar_texto(f[0])
            f_fecha = str(f[1]) if f[1] else ""
            f_hora = str(f[2])[:8] if f[2] else ""
            f_analizo = str(f[3]) if f[3] else "Desconocido"

            def formatear(val):
                if val is None:
                    return "--"
                try:
                    num = float(val)
                    return f"{int(num)}" if num.is_integer() else f"{num:.2f}"
                except ValueError:
                    return str(val)

            resultados[sec_limpia] = {
                "fecha": f_fecha,
                "hora": f_hora,
                "analizo": f_analizo,
                "valores": {
                    "pH": formatear(f[4]),
                    "STD": formatear(f[5]),
                    "Conductividad": formatear(f[6]),
                    "Dureza": formatear(f[7]),
                    "CO₂": formatear(f[8]),
                    "Alcalino M": formatear(f[9]),
                    "Cloruros": formatear(f[10]),
                },
            }
        cursor.close()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    return resultados


# ==================================================
# INSERCIÓN EN BASE DE DATOS
# ==================================================
def insertar_registros_bd(
    secciones_a_enviar, datos_sistema, usuario_logueado, texto_observaciones=""
):
    if not conexion:
        return False, "No se encontró el módulo conexion.py en la carpeta."

    query = """
    INSERT INTO Registro_Monitoreo_Condensados_FMAN46 (
        fecha, hora, seccion, analizo, usuario_registro,
        ph, std, conductividad, dureza, co2, alcalinidad_m, cloruros, observaciones
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn = None
    try:
        conn = conexion.obtener_conexion()
        cursor = conn.cursor()

        def parse_float(val):
            if not val or str(val).strip() == "" or str(val).strip() == "--":
                return None
            try:
                return float(str(val).replace(",", ".").strip())
            except ValueError:
                return None

        obs_a_guardar = (
            texto_observaciones.strip()
            if texto_observaciones and texto_observaciones.strip()
            else None
        )

        for sec in secciones_a_enviar:
            reg = datos_sistema[sec]
            vals = reg["valores"]

            v_ph = parse_float(vals.get("pH"))
            v_std = parse_float(vals.get("STD"))
            v_conductividad = parse_float(vals.get("Conductividad"))
            v_dureza = parse_float(vals.get("Dureza"))
            v_co2 = parse_float(vals.get("CO₂"))
            v_alcalinidad = parse_float(vals.get("Alcalino M"))
            v_cloruros = parse_float(vals.get("Cloruros"))

            cursor.execute(
                query,
                reg["fecha"],
                reg["hora"],
                sec,
                reg["analizo"],
                usuario_logueado,
                v_ph,
                v_std,
                v_conductividad,
                v_dureza,
                v_co2,
                v_alcalinidad,
                v_cloruros,
                obs_a_guardar,
            )

        conn.commit()
        cursor.close()
        return True, "Datos guardados exitosamente en la base de datos."
    except Exception as ex:
        if conn:
            conn.rollback()
        return False, f"Error en BD: {str(ex)}"
    finally:
        if conn:
            conn.close()


def abrir_ventana(
    page: ft.Page,
    usuario_logueado="Invitado",
    nombre_completo="Invitado",
):
    page.controls.clear()

    reloj_activo = True
    page_lista = False
    observaciones_generales = ""

    def on_disconnect(e):
        nonlocal reloj_activo
        reloj_activo = False

    page.on_disconnect = on_disconnect

    # ==================================================
    # PALETA DE COLORES
    # ==================================================
    COLOR_PRIMARIO = "#1E3A8A"
    COLOR_TITULO_BARRA = "#0F172A"
    COLOR_FONDO = "#F8FAFC"
    COLOR_BORDE_DEFAULT = "#E2E8F0"

    page.title = "Formulario 19 - Monitoreo de Condensados (FMAN-46)"
    page.bgcolor = COLOR_FONDO
    page.window.maximized = True
    page.window.resizable = True

    # ==================================================
    # CONFIGURACIÓN Y REGLAS (FMAN-46)
    # ==================================================
    campos_base = [
        {
            "campo": "pH",
            "unidad": "UN",
            "tipo": "numero",
            "regla": {"tipo": "rango", "min": 8.5, "max": 9.5},
        },
        {
            "campo": "STD",
            "unidad": "ppm",
            "tipo": "numero",
            "regla": {"tipo": "menor", "max": 10.0},
        },
        {
            "campo": "Conductividad",
            "unidad": "µS/cm",
            "tipo": "numero",
            "regla": None,
        },
        {
            "campo": "Dureza",
            "unidad": "ppm",
            "tipo": "numero",
            "regla": {"tipo": "igual", "val": 0.0},
        },
        {
            "campo": "CO₂",
            "unidad": "ppm",
            "tipo": "numero",
            "regla": {"tipo": "igual", "val": 0.0},
        },
        {
            "campo": "Alcalino M",
            "unidad": "ppm",
            "tipo": "numero",
            "regla": {"tipo": "menor", "max": 100.0},
        },
        {
            "campo": "Cloruros",
            "unidad": "ppm",
            "tipo": "numero",
            "regla": None,
        },
    ]

    configuracion_secciones = {
        "CONDENSADO TINTORERÍA": {
            "subtitulo": "Monitoreo Retorno Área Tintorería",
            "icono": ft.Icons.COLOR_LENS_ROUNDED,
            "color": "#0284C7",
            "color_soft": "#E0F2FE",
            "archivo_imagen": "form_control_monitoreo_images/tintoreria.jpg",
            "campos": [dict(c) for c in campos_base],
        },
        "CONDENSADO RETORNO CALDERA": {
            "subtitulo": "Monitoreo Retorno de Condensado a Calderas",
            "icono": ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
            "color": "#EA580C",
            "color_soft": "#FFEDD5",
            "archivo_imagen": "form_control_monitoreo_images/caldera.jpg",
            "campos": [dict(c) for c in campos_base],
        },
    }

    datos_sistema = {
        sec: {
            "estado": "SIN_REGISTROS",
            "hora": "",
            "fecha": "",
            "analizo": usuario_logueado,
            "valores": {},
        }
        for sec in configuracion_secciones
    }

    widgets_tarjetas = {}

    def abrir_dialogo(dlg):
        if hasattr(page, "open"):
            page.open(dlg)
        else:
            page.dialog = dlg
            dlg.open = True
            page.update()

    def cerrar_dialogo(dlg=None):
        if hasattr(page, "close") and dlg:
            page.close(dlg)
        elif page.dialog:
            page.dialog.open = False
            page.update()

    # ==================================================
    # SELECTOR DE FECHA Y HORA
    # ==================================================
    ahora_actual = datetime.datetime.now()
    fecha_limite_minima = ahora_actual - datetime.timedelta(days=4)
    fecha_fijada = None
    hora_fijada = None

    txt_input_fecha = ft.TextField(
        value=ahora_actual.strftime("%Y-%m-%d"),
        read_only=True,
        width=150,
        height=40,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        border_color="#CBD5E1",
        text_size=13,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
    )

    txt_input_hora = ft.TextField(
        value=ahora_actual.strftime("%H:%M:%S"),
        read_only=True,
        width=130,
        height=40,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        border_color="#CBD5E1",
        text_size=13,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
    )

    def on_date_change(e):
        nonlocal fecha_fijada
        if date_picker.value:
            fecha_fijada = date_picker.value.strftime("%Y-%m-%d")
            txt_input_fecha.value = fecha_fijada
            btn_actualizar_ahora.visible = True
            if page_lista:
                page.update()

    def on_time_change(e):
        nonlocal hora_fijada
        if time_picker.value:
            hora_fijada = time_picker.value.strftime("%H:%M:%S")
            txt_input_hora.value = hora_fijada
            btn_actualizar_ahora.visible = True
            if page_lista:
                page.update()

    date_picker = ft.DatePicker(
        value=ahora_actual,
        first_date=fecha_limite_minima,
        last_date=ahora_actual,
        current_date=ahora_actual,
        on_change=on_date_change,
    )

    time_picker = ft.TimePicker(
        value=ahora_actual.time(),
        on_change=on_time_change,
    )

    def lanzar_calendario(e):
        abrir_dialogo(date_picker)

    def lanzar_reloj(e):
        abrir_dialogo(time_picker)

    def poner_ahora(e):
        nonlocal fecha_fijada, hora_fijada
        fecha_fijada = None
        hora_fijada = None
        ahora_loop = datetime.datetime.now()
        txt_input_fecha.value = ahora_loop.strftime("%Y-%m-%d")
        txt_input_hora.value = ahora_loop.strftime("%H:%M:%S")
        btn_actualizar_ahora.visible = False
        if page_lista:
            page.update()

    btn_actualizar_ahora = ft.TextButton(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.UPDATE_ROUNDED, size=16, color=COLOR_PRIMARIO),
                ft.Text(
                    "Poner Hora Actual",
                    size=12,
                    color=COLOR_PRIMARIO,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=4,
        ),
        visible=False,
        on_click=poner_ahora,
    )

    def obtener_fecha_registro():
        if fecha_fijada:
            return fecha_fijada
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def obtener_hora_registro():
        if hora_fijada:
            return hora_fijada
        return datetime.datetime.now().strftime("%H:%M:%S")

    bar_fecha_hora = ft.Container(
        bgcolor="white",
        border_radius=12,
        padding=ft.padding.symmetric(horizontal=24, vertical=16),
        border=ft.border.all(1, COLOR_BORDE_DEFAULT),
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.CALENDAR_MONTH_ROUNDED,
                                    size=16,
                                    color="#0F172A",
                                ),
                                ft.Text(
                                    "Fecha de Medición (Operación):",
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color="#0F172A",
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Row(
                            [
                                txt_input_fecha,
                                ft.IconButton(
                                    icon=ft.Icons.CALENDAR_TODAY_ROUNDED,
                                    icon_color=COLOR_PRIMARIO,
                                    icon_size=20,
                                    tooltip="Abrir calendario (máx. 4 días atrás)",
                                    on_click=lanzar_calendario,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=6,
                ),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.ACCESS_TIME_ROUNDED,
                                    size=16,
                                    color="#0F172A",
                                ),
                                ft.Text(
                                    "Hora de Medición (Operación):",
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color="#0F172A",
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Row(
                            [
                                txt_input_hora,
                                ft.IconButton(
                                    icon=ft.Icons.ACCESS_TIME_FILLED_ROUNDED,
                                    icon_color=COLOR_PRIMARIO,
                                    icon_size=20,
                                    tooltip="Abrir reloj",
                                    on_click=lanzar_reloj,
                                ),
                                btn_actualizar_ahora,
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=6,
                ),
            ],
            spacing=40,
            alignment=ft.MainAxisAlignment.START,
        ),
    )

    # ==================================================
    # RELOJ EN VIVO
    # ==================================================
    txt_reloj = ft.Text(
        datetime.datetime.now().strftime("%H:%M:%S"),
        size=15,
        weight=ft.FontWeight.BOLD,
        color=COLOR_PRIMARIO,
    )

    def actualizar_reloj():
        while reloj_activo:
            if page_lista:
                try:
                    ahora_loop = datetime.datetime.now()
                    txt_reloj.value = ahora_loop.strftime("%H:%M:%S")

                    if not fecha_fijada:
                        txt_input_fecha.value = ahora_loop.strftime("%Y-%m-%d")
                    if not hora_fijada:
                        txt_input_hora.value = ahora_loop.strftime("%H:%M:%S")

                    txt_reloj.update()
                    if not fecha_fijada:
                        txt_input_fecha.update()
                    if not hora_fijada:
                        txt_input_hora.update()
                except Exception:
                    pass
            time.sleep(1)

    threading.Thread(target=actualizar_reloj, daemon=True).start()

    # ==================================================
    # MARQUEE
    # ==================================================
    txt_marquee = ft.Text(
        "",
        size=16,
        color="#F8FAFC",
        weight=ft.FontWeight.BOLD,
        no_wrap=True,
    )

    def animar_marquee():
        texto = (
            f"💧 FMAN-46 MONITOREO DE CONDENSADOS • "
            f"          ✦                    "
            f"🎨 CONDENSADO TINTORERÍA • "
            f"          ✦                    "
            f"🔥 CONDENSADO RETORNO CALDERA • "
            f"          ✦                    "
            f"👤 RESPONSABLE: {nombre_completo} • "
            f"          ✦                    "
            f"🔑 USUARIO: {usuario_logueado} • "
            f"          ✦                    "
            f"🏭 CRYSTAL S.A.S • "
            f"          ✦                    "
        ) * 8

        while reloj_activo:
            if page_lista:
                try:
                    texto = texto[1:] + texto[0]
                    txt_marquee.value = texto
                    txt_marquee.update()
                except Exception:
                    pass
            time.sleep(0.08)

    threading.Thread(target=animar_marquee, daemon=True).start()

    # ==================================================
    # LOGO
    # ==================================================
    nombre_logo = "LOGO CRYSTAL PNG 1.png"
    ruta_logo = resource_path(nombre_logo)

    if os.path.exists(ruta_logo):
        img_logo = ft.Image(
            src=f"/{nombre_logo}",
            width=180,
            height=60,
            fit=ft.ImageFit.CONTAIN,
        )
    else:
        img_logo = ft.Text("LOGO CRYSTAL", color="red", weight=ft.FontWeight.BOLD)

    # ==================================================
    # MODAL ADVERTENCIA AL SALIR
    # ==================================================
    def confirmar_salida(e):
        modal_salir = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="#DC2626", size=28),
                    ft.Text(
                        "¿Seguro que deseas salir?",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color="#DC2626",
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=450,
                content=ft.Text(
                    "Todos los datos ingresados que no hayan sido enviados a la base de datos se perderán definitivamente.",
                    size=13,
                    color="#4A5568",
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda ev: cerrar_dialogo(modal_salir),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
                ft.ElevatedButton(
                    "Sí, Continuar y Salir",
                    bgcolor="#DC2626",
                    color="white",
                    on_click=lambda ev: ejecutar_salida(modal_salir),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        def ejecutar_salida(dlg):
            nonlocal reloj_activo
            cerrar_dialogo(dlg)
            reloj_activo = False
            try:
                import menu

                page.controls.clear()
                menu.crear_menu(page, usuario_logueado, nombre_completo)
            except Exception:
                page.window.close()

        abrir_dialogo(modal_salir)

    # ==================================================
    # HEADER
    # ==================================================
    header = ft.Container(
        bgcolor="white",
        border_radius=15,
        padding=20,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_ROUNDED,
                            icon_color="white",
                            bgcolor=COLOR_PRIMARIO,
                            tooltip="Volver al Menú",
                            on_click=confirmar_salida,
                        ),
                    ]
                ),
                ft.Row(
                    [
                        img_logo,
                        ft.Container(width=15),
                        ft.Container(
                            expand=True,
                            height=70,
                            bgcolor=COLOR_TITULO_BARRA,
                            border_radius=10,
                            padding=12,
                            alignment=ft.alignment.center_left,
                            content=txt_marquee,
                        ),
                    ]
                ),
                ft.Divider(),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "CONTROL DE CONDENSADOS",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_PRIMARIO,
                                ),
                                ft.Text(
                                    "Monitoreo de Calidad de Condensados Tintorería y Calderas",
                                    color="#64748B",
                                ),
                                ft.Text(
                                    f"{nombre_completo} ({usuario_logueado})",
                                    color="#64748B",
                                    size=12,
                                ),
                            ],
                            spacing=4,
                        ),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ACCESS_TIME, color=COLOR_PRIMARIO
                                        ),
                                        txt_reloj,
                                    ]
                                ),
                                ft.Container(
                                    padding=10,
                                    border_radius=8,
                                    border=ft.border.all(1.5, COLOR_PRIMARIO),
                                    content=ft.Text(
                                        "FMAN-46",
                                        color=COLOR_PRIMARIO,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ]
        ),
    )

    # ==================================================
    # WIZARD DE REGISTRO / EDICIÓN TIPO SLIDE
    # ==================================================
    def abrir_wizard_seccion(seccion_nombre, color_tema):
        campos = configuracion_secciones[seccion_nombre]["campos"]
        total_campos = len(campos)
        indice_actual = 0
        valores_temporales = datos_sistema[seccion_nombre]["valores"].copy()

        txt_num_paso = ft.Text("1", size=13, weight=ft.FontWeight.BOLD, color="white")
        badge_paso = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ANALYTICS_OUTLINED, color="white", size=14),
                    txt_num_paso,
                    ft.Text(f"/ {total_campos}", size=13, color="#CBD5E0"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            ),
            bgcolor=COLOR_TITULO_BARRA,
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
        )

        barra_progreso = ft.ProgressBar(
            value=1 / total_campos,
            color=color_tema,
            bgcolor="#E2E8F0",
            height=6,
        )

        txt_nombre_campo = ft.Text(
            "",
            size=24,
            weight=ft.FontWeight.BOLD,
            color=COLOR_PRIMARIO,
            text_align=ft.TextAlign.CENTER,
        )

        txt_unidad_campo = ft.Container(
            content=ft.Text(
                "", size=12, weight=ft.FontWeight.BOLD, color=COLOR_PRIMARIO
            ),
            bgcolor="white",
            border=ft.border.all(1, "#CBD5E0"),
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
        )

        txt_error_validacion = ft.Text(
            "",
            size=12,
            color="#DC2626",
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            visible=False,
        )

        input_valor = ft.TextField(
            hint_text="Ingresa el valor numérico...",
            text_align=ft.TextAlign.CENTER,
            border_radius=10,
            text_size=20,
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            border_color="#CBD5E0",
            focused_border_color=color_tema,
            content_padding=ft.padding.symmetric(horizontal=18, vertical=16),
            on_submit=lambda e: on_siguiente(None),
        )

        def es_numero_valido(texto):
            if not texto:
                return True
            texto_limpio = texto.replace(",", ".").strip()
            try:
                val = float(texto_limpio)
                return val >= 0
            except ValueError:
                return False

        def aplicar_estado_paso(idx):
            nonlocal indice_actual
            indice_actual = idx
            cfg = campos[idx]

            txt_num_paso.value = str(idx + 1)
            barra_progreso.value = (idx + 1) / total_campos
            txt_nombre_campo.value = cfg["campo"]
            txt_unidad_campo.content.value = cfg["unidad"]
            txt_error_validacion.visible = False

            val_guardado = valores_temporales.get(cfg["campo"], "")
            input_valor.value = "" if val_guardado == "--" else str(val_guardado)

            btn_anterior.disabled = idx == 0
            if idx == total_campos - 1:
                btn_siguiente.text = "Fin"
                btn_siguiente.icon = ft.Icons.CHECK_ROUNDED
            else:
                btn_siguiente.text = "Siguiente"
                btn_siguiente.icon = ft.Icons.ARROW_FORWARD_ROUNDED

            vista_formulario.visible = True
            vista_alertas.visible = False

        def cargar_paso(idx):
            aplicar_estado_paso(idx)
            dialog_modal.update()

        def guardar_valor_actual():
            cfg = campos[indice_actual]
            val = input_valor.value.strip()
            if val and not es_numero_valido(val):
                txt_error_validacion.value = (
                    "❌ No se permiten letras, símbolos ni números negativos."
                )
                txt_error_validacion.visible = True
                dialog_modal.update()
                return False
            txt_error_validacion.visible = False
            valores_temporales[cfg["campo"]] = val.replace(",", ".")
            return True

        def on_anterior(e):
            if guardar_valor_actual():
                if indice_actual > 0:
                    cargar_paso(indice_actual - 1)

        def on_siguiente(e):
            if guardar_valor_actual():
                if indice_actual < total_campos - 1:
                    cargar_paso(indice_actual + 1)
                else:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(
                            "Llegaste al final. Puedes guardar los datos registrados."
                        ),
                        bgcolor=COLOR_PRIMARIO,
                    )
                    page.snack_bar.open = True
                    page.update()

        def on_cancelar(e):
            cerrar_dialogo(dialog_modal)

        def registrar_definitivamente():
            datos_sistema[seccion_nombre]["estado"] = "PENDIENTE"
            datos_sistema[seccion_nombre]["hora"] = obtener_hora_registro()
            datos_sistema[seccion_nombre]["fecha"] = obtener_fecha_registro()
            datos_sistema[seccion_nombre]["analizo"] = usuario_logueado
            datos_sistema[seccion_nombre]["valores"] = valores_temporales.copy()

            actualizar_panel_datos(seccion_nombre)
            actualizar_tabla_automatica()

            cerrar_dialogo(dialog_modal)
            page.snack_bar = ft.SnackBar(
                ft.Text(
                    f"✓ Datos de {seccion_nombre} guardados en la tabla (Pendiente por Enviar)."
                ),
                bgcolor="#D97706",
            )
            page.snack_bar.open = True
            page.update()

        columna_tarjetas_desviacion = ft.Column(spacing=8)

        def mostrar_vista_desviacion(desviaciones):
            columna_tarjetas_desviacion.controls.clear()
            for d in desviaciones:
                columna_tarjetas_desviacion.controls.append(
                    ft.Container(
                        padding=12,
                        border_radius=10,
                        bgcolor="#FEF2F2",
                        border=ft.border.all(1.5, "#FECACA"),
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.REPORT_PROBLEM_ROUNDED,
                                                    color="#DC2626",
                                                    size=18,
                                                ),
                                                ft.Text(
                                                    d["campo"],
                                                    weight=ft.FontWeight.BOLD,
                                                    size=15,
                                                    color="#991B1B",
                                                ),
                                            ],
                                            spacing=6,
                                        ),
                                        ft.Container(
                                            content=ft.Text(
                                                f"{d['valor']} {d['unidad']}",
                                                size=12,
                                                weight=ft.FontWeight.BOLD,
                                                color="white",
                                            ),
                                            bgcolor="#DC2626",
                                            border_radius=6,
                                            padding=ft.padding.symmetric(
                                                horizontal=8, vertical=3
                                            ),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Divider(height=6, color="#FEE2E2"),
                                ft.Row(
                                    [
                                        ft.Text(
                                            "Límite Operativo:",
                                            size=12,
                                            color="#64748B",
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            d["esperado"],
                                            size=12,
                                            color="#1E293B",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Row(
                                    [
                                        ft.Text(
                                            "Desviación Detectada:",
                                            size=12,
                                            color="#64748B",
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            d["desviacion"],
                                            size=12,
                                            color="#DC2626",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                            ],
                            spacing=4,
                        ),
                    )
                )

            primer_indice_fallido = desviaciones[0]["indice"]
            btn_editar_desvio.on_click = lambda ev: cargar_paso(primer_indice_fallido)
            vista_formulario.visible = False
            vista_alertas.visible = True
            dialog_modal.update()

        def on_guardar(e):
            if not guardar_valor_actual():
                return

            desviaciones = []
            for idx_c, cfg in enumerate(campos):
                campo_nombre = cfg["campo"]
                regla = cfg["regla"]
                val_str = valores_temporales.get(campo_nombre, "")

                if regla and val_str and val_str != "--":
                    try:
                        v = float(val_str)
                        if regla["tipo"] == "rango":
                            min_val = regla["min"]
                            max_val = regla["max"]
                            if v < min_val:
                                diff = round(min_val - v, 2)
                                desviaciones.append(
                                    {
                                        "indice": idx_c,
                                        "campo": campo_nombre,
                                        "valor": v,
                                        "unidad": cfg["unidad"],
                                        "esperado": f"Entre {min_val} y {max_val} {cfg['unidad']}",
                                        "desviacion": f"Bajo por {diff} {cfg['unidad']}",
                                    }
                                )
                            elif v > max_val:
                                diff = round(v - max_val, 2)
                                desviaciones.append(
                                    {
                                        "indice": idx_c,
                                        "campo": campo_nombre,
                                        "valor": v,
                                        "unidad": cfg["unidad"],
                                        "esperado": f"Entre {min_val} y {max_val} {cfg['unidad']}",
                                        "desviacion": f"Excedido por {diff} {cfg['unidad']}",
                                    }
                                )
                        elif regla["tipo"] == "menor":
                            max_val = regla["max"]
                            if v >= max_val:
                                diff = round(v - max_val, 2)
                                desviaciones.append(
                                    {
                                        "indice": idx_c,
                                        "campo": campo_nombre,
                                        "valor": v,
                                        "unidad": cfg["unidad"],
                                        "esperado": f"< {max_val} {cfg['unidad']}",
                                        "desviacion": f"Excedido por {diff} {cfg['unidad']}",
                                    }
                                )
                        elif regla["tipo"] == "igual":
                            val_esp = regla["val"]
                            if v != val_esp:
                                diff = round(abs(v - val_esp), 2)
                                desviaciones.append(
                                    {
                                        "indice": idx_c,
                                        "campo": campo_nombre,
                                        "valor": v,
                                        "unidad": cfg["unidad"],
                                        "esperado": f"= {val_esp} {cfg['unidad']}",
                                        "desviacion": f"Diferencia de {diff} {cfg['unidad']}",
                                    }
                                )
                    except ValueError:
                        pass

            if desviaciones:
                mostrar_vista_desviacion(desviaciones)
            else:
                registrar_definitivamente()

        btn_anterior = ft.ElevatedButton(
            "Anterior",
            icon=ft.Icons.ARROW_BACK_ROUNDED,
            on_click=on_anterior,
            bgcolor="#F1F5F9",
            color=COLOR_PRIMARIO,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=16),
        )
        btn_siguiente = ft.ElevatedButton(
            "Siguiente",
            icon=ft.Icons.ARROW_FORWARD_ROUNDED,
            on_click=on_siguiente,
            bgcolor=COLOR_PRIMARIO,
            color="white",
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=16),
        )
        btn_cancelar = ft.TextButton(
            "Descartar",
            icon=ft.Icons.CLOSE,
            style=ft.ButtonStyle(color="#DC2626"),
            on_click=on_cancelar,
        )
        btn_guardar = ft.ElevatedButton(
            "Guardar Datos",
            icon=ft.Icons.SAVE_ROUNDED,
            bgcolor="#16A34A",
            color="white",
            on_click=on_guardar,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=16),
        )

        btn_editar_desvio = ft.OutlinedButton(
            "Editar",
            icon=ft.Icons.EDIT_ROUNDED,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=16,
                side=ft.BorderSide(1.5, COLOR_PRIMARIO),
            ),
        )
        btn_continuar_desvio = ft.ElevatedButton(
            "Sí, Continuar y Guardar",
            icon=ft.Icons.CHECK_CIRCLE_ROUNDED,
            bgcolor="#16A34A",
            color="white",
            on_click=lambda ev: registrar_definitivamente(),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=16),
        )

        vista_formulario = ft.Container(
            padding=25,
            content=ft.Column(
                [
                    ft.Container(
                        padding=22,
                        border_radius=12,
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1.5, "#E2E8F0"),
                        content=ft.Column(
                            [
                                ft.Row(
                                    [txt_nombre_campo, txt_unidad_campo],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=10,
                                ),
                                ft.Container(height=12),
                                input_valor,
                                txt_error_validacion,
                                ft.Container(
                                    width=float("inf"),
                                    alignment=ft.alignment.center,
                                    content=ft.Text(
                                        "💡 Presiona Enter para avanzar de parámetro rápidamente",
                                        size=11,
                                        color="#64748B",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=6,
                        ),
                    ),
                    ft.Container(height=15),
                    ft.Row(
                        [btn_anterior, btn_siguiente],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=20,
                    ),
                    ft.Divider(height=25, color="#F1F5F9"),
                    ft.Row(
                        [btn_cancelar, btn_guardar],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=0,
            ),
        )

        vista_alertas = ft.Container(
            padding=22,
            visible=False,
            content=ft.Column(
                [
                    ft.Container(
                        padding=12,
                        border_radius=10,
                        bgcolor="#FEF2F2",
                        border=ft.border.all(1, "#FECACA"),
                        content=ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.WARNING_ROUNDED, color="#DC2626", size=26
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            "Desviación de Restricciones Operativas",
                                            weight=ft.FontWeight.BOLD,
                                            color="#991B1B",
                                            size=14,
                                        ),
                                        ft.Text(
                                            "Revisa los parámetros fuera de rango antes de continuar.",
                                            size=12,
                                            color="#64748B",
                                        ),
                                    ],
                                    spacing=1,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                        ),
                    ),
                    ft.Container(height=10),
                    ft.Container(
                        height=250,
                        content=ft.ListView(
                            controls=[columna_tarjetas_desviacion], spacing=6
                        ),
                    ),
                    ft.Divider(height=20, color="#F1F5F9"),
                    ft.Row(
                        [btn_editar_desvio, btn_continuar_desvio],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=12,
                    ),
                ],
                spacing=0,
            ),
        )

        slide_card = ft.Container(
            width=540,
            bgcolor="white",
            border_radius=14,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(
                [
                    ft.Container(
                        bgcolor=COLOR_PRIMARIO,
                        padding=ft.padding.symmetric(horizontal=20, vertical=16),
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.WATER_DROP_ROUNDED,
                                            color=color_tema,
                                            size=24,
                                        ),
                                        ft.Text(
                                            seccion_nombre,
                                            size=16,
                                            weight=ft.FontWeight.BOLD,
                                            color="white",
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                badge_paso,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ),
                    barra_progreso,
                    vista_formulario,
                    vista_alertas,
                ],
                tight=True,
                spacing=0,
            ),
        )

        dialog_modal = ft.AlertDialog(
            modal=True,
            content=slide_card,
            content_padding=0,
            shape=ft.RoundedRectangleBorder(radius=14),
        )

        aplicar_estado_paso(0)
        abrir_dialogo(dialog_modal)

    # ==================================================
    # MODAL: VER DATOS
    # ==================================================
    def modal_ver_datos(seccion_nombre):
        registro = datos_sistema[seccion_nombre]
        cfg_sec = configuracion_secciones[seccion_nombre]
        campos = cfg_sec["campos"]
        color_sec = cfg_sec["color"]

        chips_lecturas = []
        for c in campos:
            val = registro["valores"].get(c["campo"], "")
            hay_val = bool(val and val != "--")

            chips_lecturas.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=14, vertical=10),
                    border_radius=10,
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1.5, color_sec if hay_val else "#CBD5E1"),
                    content=ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(
                                        (
                                            ft.Icons.CHECK_CIRCLE_ROUNDED
                                            if hay_val
                                            else ft.Icons.RADIO_BUTTON_UNCHECKED
                                        ),
                                        size=18,
                                        color=color_sec if hay_val else "#94A3B8",
                                    ),
                                    ft.Text(
                                        c["campo"],
                                        size=13,
                                        weight=(
                                            ft.FontWeight.BOLD
                                            if hay_val
                                            else ft.FontWeight.W_500
                                        ),
                                        color="#0F172A" if hay_val else "#64748B",
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                border_radius=6,
                                bgcolor=color_sec if hay_val else "#F1F5F9",
                                content=ft.Row(
                                    [
                                        ft.Text(
                                            str(val) if hay_val else "--",
                                            size=13,
                                            weight=ft.FontWeight.BOLD,
                                            color="white" if hay_val else "#64748B",
                                        ),
                                        ft.Text(
                                            c["unidad"],
                                            size=10,
                                            weight=(
                                                ft.FontWeight.BOLD
                                                if hay_val
                                                else ft.FontWeight.W_500
                                            ),
                                            color="#E2E8F0" if hay_val else "#94A3B8",
                                        ),
                                    ],
                                    spacing=4,
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                )
            )

        modal_contenido = ft.Container(
            width=520,
            content=ft.Column(
                [
                    ft.Container(
                        bgcolor=color_sec,
                        padding=ft.padding.symmetric(horizontal=20, vertical=16),
                        border_radius=ft.border_radius.only(top_left=14, top_right=14),
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(
                                                cfg_sec["icono"],
                                                color=color_sec,
                                                size=22,
                                            ),
                                            bgcolor="white",
                                            border_radius=8,
                                            padding=6,
                                        ),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    seccion_nombre,
                                                    size=16,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="white",
                                                ),
                                                ft.Text(
                                                    cfg_sec["subtitulo"],
                                                    size=11,
                                                    color="#F8FAFC",
                                                ),
                                            ],
                                            spacing=1,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                ft.Container(
                                    content=ft.Text(
                                        registro["estado"],
                                        size=10,
                                        weight=ft.FontWeight.BOLD,
                                        color="white",
                                    ),
                                    bgcolor=(
                                        "#16A34A"
                                        if registro["estado"] == "ÚLTIMO REGISTRO"
                                        else "#B45309"
                                    ),
                                    border_radius=6,
                                    padding=ft.padding.symmetric(
                                        horizontal=8, vertical=4
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ),
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=20, vertical=10),
                        bgcolor="#F1F5F9",
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.CALENDAR_TODAY_ROUNDED,
                                            size=14,
                                            color="#475569",
                                        ),
                                        ft.Text(
                                            f"{registro['fecha']} • {registro['hora']}",
                                            size=11,
                                            color="#334155",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    spacing=5,
                                ),
                                ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.ACCOUNT_CIRCLE_ROUNDED,
                                            size=15,
                                            color="#475569",
                                        ),
                                        ft.Text(
                                            f"Analista: {registro['analizo']}",
                                            size=11,
                                            color="#334155",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    spacing=5,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ),
                    ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Container(
                                    height=280,
                                    content=ft.ListView(
                                        controls=chips_lecturas, spacing=8
                                    ),
                                ),
                                ft.Divider(height=15, color="#E2E8F0"),
                                ft.Row(
                                    [
                                        ft.ElevatedButton(
                                            "Cerrar",
                                            icon=ft.Icons.CHECK,
                                            bgcolor=color_sec,
                                            color="white",
                                            style=ft.ButtonStyle(
                                                shape=ft.RoundedRectangleBorder(
                                                    radius=8
                                                ),
                                                padding=ft.padding.symmetric(
                                                    horizontal=22, vertical=12
                                                ),
                                            ),
                                            on_click=lambda ev: cerrar_dialogo(
                                                modal_detalle
                                            ),
                                        )
                                    ],
                                    alignment=ft.MainAxisAlignment.END,
                                ),
                            ],
                            spacing=0,
                        ),
                    ),
                ],
                tight=True,
                spacing=0,
            ),
        )

        modal_detalle = ft.AlertDialog(
            modal=True,
            content=modal_contenido,
            content_padding=0,
            shape=ft.RoundedRectangleBorder(radius=14),
        )

        abrir_dialogo(modal_detalle)

    # ==================================================
    # ELIMINAR REGISTRO TEMPORAL
    # ==================================================
    def eliminar_registro(seccion_nombre):
        datos_sistema[seccion_nombre]["estado"] = "SIN_REGISTROS"
        datos_sistema[seccion_nombre]["hora"] = ""
        datos_sistema[seccion_nombre]["fecha"] = ""
        datos_sistema[seccion_nombre]["valores"] = {}

        ultimos = obtener_ultimos_registros_bd()
        sec_limpia = limpiar_texto(seccion_nombre)
        if sec_limpia in ultimos:
            u = ultimos[sec_limpia]
            datos_sistema[seccion_nombre]["estado"] = "ÚLTIMO REGISTRO"
            datos_sistema[seccion_nombre]["hora"] = u["hora"]
            datos_sistema[seccion_nombre]["fecha"] = u["fecha"]
            datos_sistema[seccion_nombre]["analizo"] = u["analizo"]
            datos_sistema[seccion_nombre]["valores"] = u["valores"].copy()

        actualizar_panel_datos(seccion_nombre)
        actualizar_tabla_automatica()

        page.snack_bar = ft.SnackBar(
            ft.Text(f"🗑️ Registro pendiente de {seccion_nombre} eliminado."),
            bgcolor="#DC2626",
        )
        page.snack_bar.open = True
        page.update()

    # ==================================================
    # RENDER DE DATOS EN LA TARJETA
    # ==================================================
    def actualizar_panel_datos(seccion_nombre):
        registro = datos_sistema[seccion_nombre]
        campos = configuracion_secciones[seccion_nombre]["campos"]
        w = widgets_tarjetas[seccion_nombre]

        for c in campos:
            nombre = c["campo"]
            val = registro["valores"].get(nombre, "")
            hay_dato = bool(val and val != "--")

            nodo_txt = w["campos_txt"][nombre]
            nodo_txt.value = str(val) if hay_dato else "--"
            nodo_txt.color = COLOR_PRIMARIO if hay_dato else "#A0AEC0"

        if registro["estado"] == "SIN_REGISTROS":
            w["icono_estado"].name = ft.Icons.RADIO_BUTTON_UNCHECKED
            w["icono_estado"].color = "#94A3B8"
            w["txt_estado"].value = "SIN REGISTROS"
            w["txt_estado"].color = "#94A3B8"
            w["txt_tiempo"].value = "Pendiente hoy"
        elif registro["estado"] == "PENDIENTE":
            w["icono_estado"].name = ft.Icons.PENDING_ACTIONS_ROUNDED
            w["icono_estado"].color = "#D97706"
            w["txt_estado"].value = "PENDIENTE POR ENVIAR"
            w["txt_estado"].color = "#D97706"
            w["txt_tiempo"].value = f"{registro['hora']} ({registro['analizo']})"
        else:
            w["icono_estado"].name = ft.Icons.CHECK_CIRCLE_ROUNDED
            w["icono_estado"].color = "#16A34A"
            w["txt_estado"].value = "ÚLTIMO REGISTRO"
            w["txt_estado"].color = "#16A34A"
            w["txt_tiempo"].value = f"{registro['hora']} ({registro['analizo']})"

        if page_lista:
            try:
                w["contenedor_raiz"].update()
            except Exception:
                pass

    # ==================================================
    # TABLA AUTOMÁTICA DE REGISTROS
    # ==================================================
    contenedor_filas_tabla = ft.Column(spacing=6)

    box_tabla_vacia = ft.Container(
        padding=30,
        alignment=ft.alignment.center,
        content=ft.Row(
            [
                ft.Icon(ft.Icons.INFO_OUTLINE, color="#94A3B8", size=22),
                ft.Text(
                    "Aún no has ingresado lecturas hoy. Haz clic en 'Ingresar Lecturas' en cualquiera de las 2 secciones.",
                    size=13,
                    color="#64748B",
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
    )

    header_tabla = ft.Container(
        bgcolor="#F8FAFC",
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        border=ft.border.all(1, "#E2E8F0"),
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        "DÍA / HORA",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                        size=12,
                    ),
                    expand=2,
                ),
                ft.Container(
                    content=ft.Text(
                        "SECCIÓN / EQUIPO",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                        size=12,
                    ),
                    expand=3,
                ),
                ft.Container(
                    content=ft.Text(
                        "ANALIZÓ",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                        size=12,
                    ),
                    expand=2,
                ),
                ft.Container(
                    content=ft.Text(
                        "ESTADO",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                        size=12,
                    ),
                    expand=2,
                ),
                ft.Container(
                    content=ft.Text(
                        "ACCIONES",
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                        size=12,
                    ),
                    expand=2,
                    alignment=ft.alignment.center_right,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
    )

    def actualizar_tabla_automatica():
        contenedor_filas_tabla.controls.clear()
        hay_pendientes = False
        registros_visibles = 0

        for sec, reg in datos_sistema.items():
            if reg["estado"] == "PENDIENTE":
                registros_visibles += 1
                color_sec = configuracion_secciones[sec]["color"]
                hay_pendientes = True

                chip_estado = ft.Container(
                    content=ft.Text(
                        "Pendiente por Enviar",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="#B45309",
                    ),
                    bgcolor="#FEF3C7",
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                )

                btn_ver = ft.IconButton(
                    icon=ft.Icons.VISIBILITY_ROUNDED,
                    icon_color=color_sec,
                    tooltip="Ver datos digitados",
                    on_click=lambda ev, s=sec: modal_ver_datos(s),
                )
                btn_editar = ft.IconButton(
                    icon=ft.Icons.EDIT_ROUNDED,
                    icon_color="#2563EB",
                    tooltip="Editar en el slide",
                    on_click=lambda ev, s=sec: abrir_wizard_seccion(
                        s, configuracion_secciones[s]["color"]
                    ),
                )
                btn_eliminar = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    icon_color="#DC2626",
                    tooltip="Eliminar registro",
                    on_click=lambda ev, s=sec: eliminar_registro(s),
                )

                acciones = ft.Row(
                    [btn_ver, btn_editar, btn_eliminar],
                    spacing=2,
                    alignment=ft.MainAxisAlignment.END,
                )

                fila_card = ft.Container(
                    bgcolor="white",
                    border_radius=8,
                    padding=ft.padding.symmetric(horizontal=16, vertical=10),
                    border=ft.border.all(1, "#E2E8F0"),
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    f"{reg['fecha']} {reg['hora']}",
                                    size=12,
                                    color="#2D3748",
                                ),
                                expand=2,
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Container(
                                            width=4,
                                            height=18,
                                            bgcolor=color_sec,
                                            border_radius=2,
                                        ),
                                        ft.Text(
                                            sec,
                                            size=13,
                                            weight=ft.FontWeight.BOLD,
                                            color="#0F172A",
                                        ),
                                    ],
                                    spacing=6,
                                ),
                                expand=3,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    reg["analizo"], size=12, color="#4A5568"
                                ),
                                expand=2,
                            ),
                            ft.Container(content=chip_estado, expand=2),
                            ft.Container(
                                content=acciones,
                                expand=2,
                                alignment=ft.alignment.center_right,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
                contenedor_filas_tabla.controls.append(fila_card)

        if registros_visibles == 0:
            contenedor_filas_tabla.controls.append(box_tabla_vacia)

        btn_enviar_bd.disabled = not hay_pendientes
        if page_lista:
            try:
                contenedor_tabla.update()
            except Exception:
                pass

    # ==================================================
    # MODAL DE OBSERVACIONES
    # ==================================================
    txt_observaciones_field = ft.TextField(
        multiline=True,
        min_lines=5,
        max_lines=7,
        hint_text="Escribe aquí observaciones, novedades o anomalías operativas presentadas durante el turno...",
        border_color="#CBD5E1",
        focused_border_color=COLOR_PRIMARIO,
        border_radius=10,
        text_size=13,
        autofocus=True,
    )

    def abrir_modal_observaciones(e):
        txt_observaciones_field.value = observaciones_generales

        def guardar_obs(ev):
            nonlocal observaciones_generales
            observaciones_generales = txt_observaciones_field.value.strip()
            cerrar_dialogo(modal_obs)

            if observaciones_generales:
                btn_observaciones.style.bgcolor = "#E0E7FF"
                btn_observaciones.style.side = ft.BorderSide(1.5, COLOR_PRIMARIO)
                txt_label_btn_obs.value = "Observaciones (Con Nota)"
                icono_btn_obs.color = COLOR_PRIMARIO
                icono_btn_obs.name = ft.Icons.COMMENT_ROUNDED
            else:
                btn_observaciones.style.bgcolor = "white"
                btn_observaciones.style.side = ft.BorderSide(1.5, "#CBD5E1")
                txt_label_btn_obs.value = "Observaciones"
                icono_btn_obs.color = "#475569"
                icono_btn_obs.name = ft.Icons.ADD_COMMENT_ROUNDED

            btn_observaciones.update()
            page.snack_bar = ft.SnackBar(
                ft.Text("✓ Observación actualizada."),
                bgcolor=COLOR_PRIMARIO,
            )
            page.snack_bar.open = True
            page.update()

        modal_obs = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.NOTES_ROUNDED, color=COLOR_PRIMARIO, size=24),
                    ft.Text(
                        "Observaciones Generales de la Jornada",
                        size=17,
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    [
                        ft.Text(
                            "Estas notas se guardarán en SQL Server asociadas a los registros de este envío.",
                            size=12,
                            color="#64748B",
                        ),
                        ft.Container(height=6),
                        txt_observaciones_field,
                    ],
                    tight=True,
                    spacing=6,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cerrar",
                    on_click=lambda ev: cerrar_dialogo(modal_obs),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8), padding=14
                    ),
                ),
                ft.ElevatedButton(
                    "Guardar Observación",
                    icon=ft.Icons.CHECK_ROUNDED,
                    bgcolor=COLOR_PRIMARIO,
                    color="white",
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8), padding=14
                    ),
                    on_click=guardar_obs,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        abrir_dialogo(modal_obs)

    # ==================================================
    # MODAL DE ENVÍO FINAL
    # ==================================================
    def abrir_modal_envio_final():
        secciones_a_enviar = [
            sec for sec, reg in datos_sistema.items() if reg["estado"] == "PENDIENTE"
        ]

        if not secciones_a_enviar:
            return

        tarjetas_desglose = []
        for sec in secciones_a_enviar:
            reg = datos_sistema[sec]
            cfg_sec = configuracion_secciones[sec]
            campos_sec = cfg_sec["campos"]
            color_sec = cfg_sec["color"]

            chips_valores = []
            for c in campos_sec:
                nombre_p = c["campo"]
                unidad_p = c["unidad"]
                val_p = reg["valores"].get(nombre_p, "")

                if val_p and val_p != "--":
                    chips_valores.append(
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            border_radius=7,
                            bgcolor="#FFFFFF",
                            border=ft.border.all(1.2, color_sec),
                            content=ft.Row(
                                [
                                    ft.Text(
                                        nombre_p,
                                        size=11,
                                        color="#334155",
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Container(
                                        padding=ft.padding.symmetric(
                                            horizontal=6, vertical=2
                                        ),
                                        bgcolor=color_sec,
                                        border_radius=4,
                                        content=ft.Text(
                                            f"{val_p} {unidad_p}",
                                            size=10,
                                            weight=ft.FontWeight.BOLD,
                                            color="white",
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                        )
                    )

            mitad = (len(chips_valores) + 1) // 2
            col1 = chips_valores[:mitad]
            col2 = chips_valores[mitad:]

            tarjetas_desglose.append(
                ft.Container(
                    padding=10,
                    border_radius=10,
                    bgcolor="#FFFFFF",
                    border=ft.border.all(1.5, color_sec),
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Row(
                                        [
                                            ft.Container(
                                                content=ft.Icon(
                                                    cfg_sec["icono"],
                                                    color="white",
                                                    size=16,
                                                ),
                                                bgcolor=color_sec,
                                                border_radius=6,
                                                padding=4,
                                            ),
                                            ft.Text(
                                                sec,
                                                size=13,
                                                weight=ft.FontWeight.BOLD,
                                                color=color_sec,
                                            ),
                                        ],
                                        spacing=6,
                                    ),
                                    ft.Container(
                                        content=ft.Text(
                                            f"{reg['fecha']} {reg['hora']}",
                                            size=10,
                                            color="#334155",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        bgcolor="#F1F5F9",
                                        border_radius=5,
                                        padding=ft.padding.symmetric(
                                            horizontal=6, vertical=2
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Divider(height=6, color=f"{color_sec}33"),
                            (
                                ft.Row(
                                    [
                                        ft.Column(col1, spacing=3, expand=True),
                                        ft.Column(col2, spacing=3, expand=True),
                                    ],
                                    spacing=6,
                                    vertical_alignment=ft.CrossAxisAlignment.START,
                                )
                                if chips_valores
                                else ft.Text(
                                    "Sin lecturas digitadas",
                                    size=10,
                                    color="#94A3B8",
                                    italic=True,
                                )
                            ),
                        ],
                        spacing=4,
                    ),
                )
            )

        tarjeta_resumen_obs = ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=8,
            bgcolor="#F8FAFC",
            border=ft.border.all(1, "#CBD5E1"),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.NOTES_ROUNDED, size=15, color=COLOR_PRIMARIO
                            ),
                            ft.Text(
                                "Observaciones Generales a Guardar:",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_PRIMARIO,
                            ),
                        ],
                        spacing=5,
                    ),
                    ft.Text(
                        (
                            observaciones_generales
                            if observaciones_generales
                            else "Ninguna especificada."
                        ),
                        size=11,
                        color="#334155" if observaciones_generales else "#94A3B8",
                        italic=not bool(observaciones_generales),
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=2,
            ),
        )

        modal_confirmar = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CLOUD_UPLOAD_ROUNDED, color=COLOR_PRIMARIO, size=26
                    ),
                    ft.Text(
                        "Confirmar Envío a Base de Datos",
                        size=17,
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                width=580,
                content=ft.Column(
                    [
                        ft.Container(
                            padding=10,
                            border_radius=8,
                            bgcolor="#FEF3C7",
                            border=ft.border.all(1, "#FCD34D"),
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.INFO_OUTLINE_ROUNDED,
                                        color="#B45309",
                                        size=20,
                                    ),
                                    ft.Text(
                                        "Al darle enviar estos datos se guardarán definitivamente en la base de datos:",
                                        size=11,
                                        color="#78350F",
                                        weight=ft.FontWeight.W_500,
                                        expand=True,
                                    ),
                                ],
                                spacing=8,
                            ),
                        ),
                        ft.Container(
                            height=190,
                            content=ft.ListView(controls=tarjetas_desglose, spacing=8),
                        ),
                        tarjeta_resumen_obs,
                    ],
                    tight=True,
                    spacing=8,
                ),
            ),
            actions=[
                ft.OutlinedButton(
                    "Cancelar",
                    on_click=lambda ev: cerrar_dialogo(modal_confirmar),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8), padding=14
                    ),
                ),
                ft.ElevatedButton(
                    "Enviar a Base de Datos",
                    icon=ft.Icons.SEND_ROUNDED,
                    bgcolor="#16A34A",
                    color="white",
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8), padding=14
                    ),
                    on_click=lambda ev: procesar_envio_base_datos(modal_confirmar),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        def procesar_envio_base_datos(dlg):
            nonlocal observaciones_generales
            cerrar_dialogo(dlg)

            exito, mensaje = insertar_registros_bd(
                secciones_a_enviar,
                datos_sistema,
                usuario_logueado,
                observaciones_generales,
            )

            if exito:
                for sec in secciones_a_enviar:
                    datos_sistema[sec]["estado"] = "ÚLTIMO REGISTRO"
                    actualizar_panel_datos(sec)

                actualizar_tabla_automatica()

                observaciones_generales = ""
                btn_observaciones.style.bgcolor = "white"
                btn_observaciones.style.side = ft.BorderSide(1.5, "#CBD5E1")
                txt_label_btn_obs.value = "Observaciones"
                icono_btn_obs.color = "#475569"
                icono_btn_obs.name = ft.Icons.ADD_COMMENT_ROUNDED
                btn_observaciones.update()

                page.snack_bar = ft.SnackBar(
                    ft.Text("✓ ¡Datos guardados exitosamente en SQL Server!"),
                    bgcolor="#16A34A",
                )
            else:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"❌ {mensaje}"),
                    bgcolor="#DC2626",
                )

            page.snack_bar.open = True
            page.update()

        abrir_dialogo(modal_confirmar)

    # ==================================================
    # CREACIÓN DE TARJETAS SIMÉTRICAS
    # ==================================================
    def crear_tarjeta_seccion(titulo):
        cfg = configuracion_secciones[titulo]
        color_icono = cfg["color"]
        archivo_img = cfg["archivo_imagen"]
        ruta_img = resource_path(archivo_img)
        ruta_web = f"/{archivo_img.replace(os.sep, '/')}"

        if os.path.exists(ruta_img):
            box_imagen = ft.Container(
                height=160,
                border_radius=10,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Image(
                    src=ruta_web,
                    fit=ft.ImageFit.COVER,
                    width=float("inf"),
                    height=160,
                ),
            )
        else:
            box_imagen = ft.Container(
                height=160,
                border_radius=10,
                bgcolor=cfg["color_soft"],
                border=ft.border.all(1, "#CBD5E1"),
                content=ft.Column(
                    [
                        ft.Icon(cfg["icono"], size=46, color=color_icono),
                        ft.Text(
                            f"{titulo}",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color="#1E293B",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                alignment=ft.alignment.center,
            )

        btn_ingresar = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Text(
                        "Ingresar Lecturas", weight=ft.FontWeight.BOLD, color="white"
                    ),
                    ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, size=16, color="white"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            style=ft.ButtonStyle(
                bgcolor=COLOR_PRIMARIO,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(vertical=13),
            ),
            on_click=lambda e: abrir_wizard_seccion(titulo, color_icono),
        )

        header_textos = ft.Container(
            width=float("inf"),
            height=46,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Text(
                        titulo,
                        size=15,
                        weight=ft.FontWeight.BOLD,
                        color=COLOR_PRIMARIO,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        cfg["subtitulo"],
                        size=11,
                        color="#64748B",
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )

        nodo_icono_estado = ft.Icon(
            ft.Icons.RADIO_BUTTON_UNCHECKED, size=13, color="#94A3B8"
        )
        nodo_txt_estado = ft.Text(
            "SIN REGISTROS", size=10, weight=ft.FontWeight.BOLD, color="#94A3B8"
        )
        nodo_txt_tiempo = ft.Text(
            "Pendiente hoy", size=10, color="#64748B", weight=ft.FontWeight.W_500
        )

        header_estado = ft.Row(
            [
                ft.Row([nodo_icono_estado, nodo_txt_estado], spacing=4),
                nodo_txt_tiempo,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        mapa_textos_campos = {}
        widgets_campos_todos = []

        for c in cfg["campos"]:
            txt_v = ft.Text("--", size=11, weight=ft.FontWeight.BOLD, color="#94A3B8")
            mapa_textos_campos[c["campo"]] = txt_v

            box_campo = ft.Container(
                height=32,
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                border_radius=7,
                bgcolor="#F8FAFC",
                border=ft.border.all(1, "#EDF2F7"),
                content=ft.Row(
                    [
                        ft.Text(
                            c["campo"],
                            size=11,
                            color="#334155",
                            weight=ft.FontWeight.W_500,
                            no_wrap=True,
                        ),
                        ft.Row(
                            [
                                txt_v,
                                ft.Text(
                                    c["unidad"],
                                    size=9,
                                    color="#64748B",
                                    weight=ft.FontWeight.W_500,
                                ),
                            ],
                            spacing=2,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            )
            widgets_campos_todos.append(box_campo)

        col1 = widgets_campos_todos[:4]
        col2 = widgets_campos_todos[4:]

        contenedor_matriz_datos = ft.Container(
            height=165,
            content=ft.Column(
                [
                    header_estado,
                    ft.Row(
                        [
                            ft.Column(col1, spacing=4, expand=True),
                            ft.Column(col2, spacing=4, expand=True),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=6,
            ),
        )

        widgets_tarjetas[titulo] = {
            "contenedor_raiz": contenedor_matriz_datos,
            "icono_estado": nodo_icono_estado,
            "txt_estado": nodo_txt_estado,
            "txt_tiempo": nodo_txt_tiempo,
            "campos_txt": mapa_textos_campos,
        }

        card_content = ft.Column(
            [
                box_imagen,
                header_textos,
                ft.Divider(height=1, color="#EDF2F5"),
                contenedor_matriz_datos,
                btn_ingresar,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            spacing=8,
        )

        card_container = ft.Container(
            content=card_content,
            expand=True,
            height=505,
            bgcolor="white",
            border_radius=14,
            padding=18,
            border=ft.border.all(1.5, COLOR_BORDE_DEFAULT),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

        def on_hover(e):
            if e.data == "true":
                card_container.border = ft.border.all(1.5, color_icono)
                card_container.bgcolor = "#FAFCFF"
            else:
                card_container.border = ft.border.all(1.5, COLOR_BORDE_DEFAULT)
                card_container.bgcolor = "white"
            card_container.update()

        card_container.on_hover = on_hover
        return card_container

    # ==================================================
    # SECCIONES: 2 TARJETAS SIMÉTRICAS
    # ==================================================
    tarjeta_tintoreria = crear_tarjeta_seccion("CONDENSADO TINTORERÍA")
    tarjeta_caldera = crear_tarjeta_seccion("CONDENSADO RETORNO CALDERA")

    secciones = ft.Container(
        bgcolor="white",
        border_radius=15,
        padding=25,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.DASHBOARD_CUSTOMIZE_ROUNDED, color=COLOR_PRIMARIO
                        ),
                        ft.Text(
                            "SECCIONES DE REGISTRO DIARIO (1 VEZ POR DÍA)",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_PRIMARIO,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                ft.Text(
                    "Selecciona una de las dos secciones de condensado para registrar parámetros paso a paso.",
                    color="#64748B",
                    size=13,
                ),
                ft.Container(height=10),
                ft.Row(
                    [tarjeta_tintoreria, tarjeta_caldera],
                    spacing=24,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=18,
        ),
    )

    # ==================================================
    # SECCIÓN INFERIOR: BOTÓN OBSERVACIONES Y BOTÓN ENVIAR
    # ==================================================
    icono_btn_obs = ft.Icon(ft.Icons.ADD_COMMENT_ROUNDED, size=18, color="#475569")
    txt_label_btn_obs = ft.Text(
        "Observaciones", weight=ft.FontWeight.BOLD, color="#334155"
    )

    btn_observaciones = ft.OutlinedButton(
        content=ft.Row([icono_btn_obs, txt_label_btn_obs], spacing=6),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            side=ft.BorderSide(1.5, "#CBD5E1"),
            padding=ft.padding.symmetric(horizontal=18, vertical=16),
            bgcolor="white",
        ),
        tooltip="Añadir observaciones o notas sobre el turno antes de enviar",
        on_click=abrir_modal_observaciones,
    )

    btn_enviar_bd = ft.ElevatedButton(
        "Enviar Formulario Completo",
        icon=ft.Icons.SEND_ROUNDED,
        bgcolor=COLOR_PRIMARIO,
        color="white",
        disabled=True,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=24, vertical=16),
        ),
        on_click=lambda e: abrir_modal_envio_final(),
    )

    contenedor_tabla = ft.Container(
        bgcolor="white",
        border_radius=15,
        padding=25,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.TABLE_CHART_ROUNDED, color=COLOR_PRIMARIO
                                ),
                                ft.Text(
                                    "TABLA AUTOMÁTICA DE REGISTROS DEL DÍA",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=COLOR_PRIMARIO,
                                ),
                            ],
                            spacing=8,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(
                    "Aquí se listan automáticamente las secciones completadas pendientes por enviar a la base de datos.",
                    color="#64748B",
                    size=13,
                ),
                ft.Container(height=10),
                header_tabla,
                contenedor_filas_tabla,
                ft.Divider(height=25, color="#F1F5F9"),
                ft.Row(
                    [btn_observaciones, btn_enviar_bd],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
        ),
    )

    # ==================================================
    # CARGAR PÁGINA Y CARGA INICIAL DE ÚLTIMOS DATOS DE BD
    # ==================================================
    page.add(
        ft.Container(
            expand=True,
            padding=10,
            content=ft.Column(
                [
                    header,
                    bar_fecha_hora,
                    secciones,
                    contenedor_tabla,
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=15,
            ),
        )
    )

    page_lista = True

    # 🟢 Carga directa comprobando variaciones ortográficas
    ultimos_historicos = obtener_ultimos_registros_bd()
    for sec_nom in configuracion_secciones:
        sec_normalizada = limpiar_texto(sec_nom)
        if sec_normalizada in ultimos_historicos:
            h = ultimos_historicos[sec_normalizada]
            datos_sistema[sec_nom]["estado"] = "ÚLTIMO REGISTRO"
            datos_sistema[sec_nom]["hora"] = h["hora"]
            datos_sistema[sec_nom]["fecha"] = h["fecha"]
            datos_sistema[sec_nom]["analizo"] = h["analizo"]
            datos_sistema[sec_nom]["valores"] = h["valores"].copy()
        actualizar_panel_datos(sec_nom)

    actualizar_tabla_automatica()
    page.update()
