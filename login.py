import logging

import flet as ft
import pyodbc

import conexion


REPORTE_FORMULARIO_19 = "mante_condensados"
REPORTE_FORMULARIO_20 = "mante_aguas_caldera"
REPORTE_FORMULARIO_3 = "mante_control_caldera"
CONSULTA_USUARIO = """
SELECT usuario, nombre, reporte
FROM dbo.Maestro_Permisos_Reportes
WHERE usuario = ? AND [contraseña] = ? AND reporte IN (?, ?, ?)
ORDER BY id_maestro
"""


def autenticar_usuario(
    usuario: str, contraseña: str
) -> tuple[str, str, frozenset[str]] | None:
    usuario = usuario.strip()
    if not usuario or not contraseña or len(contraseña) > 20:
        return None

    conn = conexion.obtener_conexion_usuarios()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(
                CONSULTA_USUARIO,
                usuario,
                contraseña,
                REPORTE_FORMULARIO_19,
                REPORTE_FORMULARIO_20,
                REPORTE_FORMULARIO_3,
            )
            filas = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    if not filas:
        return None

    fila = filas[0]
    usuario_validado = str(fila[0])
    nombre = str(fila[1]).strip() if fila[1] else usuario_validado
    reportes = frozenset(str(registro[2]) for registro in filas)
    return usuario_validado, nombre, reportes


def crear_login(page: ft.Page, al_autenticar):
    page.controls.clear()
    page.title = "Ingreso - Formularios de Mantenimiento"
    page.bgcolor = "#F1F5F9"

    campo_usuario = ft.TextField(
        label="Usuario",
        prefix_icon=ft.Icons.PERSON_OUTLINE,
        max_length=20,
        autofocus=True,
        on_submit=lambda _: iniciar_sesion(),
    )
    campo_contraseña = ft.TextField(
        label="Contraseña",
        prefix_icon=ft.Icons.LOCK_OUTLINE,
        password=True,
        can_reveal_password=True,
        max_length=20,
        on_submit=lambda _: iniciar_sesion(),
    )
    texto_error = ft.Text(color="#B91C1C", size=13, visible=False)
    boton_ingresar = ft.ElevatedButton(
        "Iniciar sesión",
        icon=ft.Icons.LOGIN_ROUNDED,
        bgcolor="#1E3A8A",
        color="white",
        width=340,
    )

    def iniciar_sesion(_=None):
        usuario = campo_usuario.value or ""
        contraseña = campo_contraseña.value or ""
        if not usuario.strip() or not contraseña:
            texto_error.value = "Ingresa tu usuario y contraseña."
            texto_error.visible = True
            page.update()
            return

        boton_ingresar.disabled = True
        texto_error.visible = False
        page.update()
        try:
            identidad = autenticar_usuario(usuario, contraseña)
        except pyodbc.Error:
            logging.exception("Error de SQL Server durante el inicio de sesión.")
            texto_error.value = (
                "No fue posible consultar los permisos. Verifica la conexión "
                "a SQL Server e inténtalo de nuevo."
            )
            texto_error.visible = True
        except (RuntimeError, ValueError):
            logging.exception("La configuración de SQL Server no es válida.")
            texto_error.value = (
                "La conexión a SQL Server no está configurada correctamente."
            )
            texto_error.visible = True
        else:
            if identidad is None:
                texto_error.value = (
                    "Usuario, contraseña o permiso incorrectos para este formulario."
                )
                texto_error.visible = True
            else:
                campo_contraseña.value = ""
                al_autenticar(*identidad)
                return
        boton_ingresar.disabled = False
        page.update()

    boton_ingresar.on_click = iniciar_sesion
    tarjeta_login = ft.Container(
        width=410,
        padding=32,
        bgcolor="white",
        border_radius=16,
        border=ft.Border.all(1, "#E2E8F0"),
        content=ft.Column(
            [
                ft.Icon(ft.Icons.WATER_DROP_ROUNDED, size=42, color="#1E3A8A"),
                ft.Text(
                    "Formularios de Mantenimiento",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color="#0F172A",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Inicia sesión con tu cuenta autorizada.",
                    size=14,
                    color="#64748B",
                    text_align=ft.TextAlign.CENTER,
                ),
                campo_usuario,
                campo_contraseña,
                texto_error,
                boton_ingresar,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            tight=True,
        ),
    )
    page.add(
        ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            padding=20,
            content=tarjeta_login,
        )
    )
    page.update()
