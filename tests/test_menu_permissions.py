import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft
import login
import menu
from menu import tiene_permiso_formulario_2, tiene_permiso_formulario_3


class PaginaMenuPrueba:
    def __init__(self):
        self.controls = []
        self.dialog = None

    def add(self, *controls):
        self.controls.extend(controls)

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None

    def update(self):
        pass


class PermisosMenuTests(unittest.TestCase):
    @classmethod
    def recorrer_controles(cls, value):
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from cls.recorrer_controles(item)
        elif isinstance(value, ft.Control):
            yield value
            for attribute in ("controls", "content"):
                child = getattr(value, attribute, None)
                if child is not None:
                    yield from cls.recorrer_controles(child)

    def test_formulario_2_requiere_su_permiso_dedicado(self):
        self.assertFalse(tiene_permiso_formulario_2(frozenset()))
        self.assertFalse(
            tiene_permiso_formulario_2(
                frozenset({login.REPORTE_FORMULARIO_19})
            )
        )
        self.assertTrue(
            tiene_permiso_formulario_2(
                frozenset({login.REPORTE_FORMULARIO_20})
            )
        )

    def test_formulario_1_no_otorga_acceso_al_formulario_2(self):
        permisos_formulario_1 = frozenset({login.REPORTE_FORMULARIO_19})

        self.assertIn(login.REPORTE_FORMULARIO_19, permisos_formulario_1)
        self.assertNotIn(login.REPORTE_FORMULARIO_20, permisos_formulario_1)
        self.assertFalse(tiene_permiso_formulario_2(permisos_formulario_1))

    def test_formulario_3_requiere_su_permiso_dedicado(self):
        self.assertFalse(tiene_permiso_formulario_3(frozenset()))
        self.assertFalse(
            tiene_permiso_formulario_3(
                frozenset({login.REPORTE_FORMULARIO_20})
            )
        )
        self.assertTrue(
            tiene_permiso_formulario_3(
                frozenset({login.REPORTE_FORMULARIO_3})
            )
        )

    def test_menu_abre_formulario_3_con_el_permiso_correcto(self):
        pagina = PaginaMenuPrueba()
        permiso = frozenset({login.REPORTE_FORMULARIO_3})
        menu.crear_menu(pagina, "usuario", "Operador", Mock(), permiso)
        botones_disponibles = [
            control
            for control in self.recorrer_controles(pagina.controls)
            if isinstance(control, ft.ElevatedButton)
            and control.content == "Abrir formulario"
        ]
        self.assertEqual(len(botones_disponibles), 1)

        modulo = SimpleNamespace(abrir_ventana=Mock())
        with patch.dict(sys.modules, {"form_control_purgas_caldera": modulo}):
            botones_disponibles[0].on_click(
                SimpleNamespace(control=botones_disponibles[0])
            )

        modulo.abrir_ventana.assert_called_once()
        argumentos = modulo.abrir_ventana.call_args.args
        self.assertIs(argumentos[0], pagina)
        self.assertEqual(argumentos[1:3], ("usuario", "Operador"))
        self.assertTrue(callable(argumentos[3]))

    def test_autenticacion_consulta_solo_codigos_nuevos(self):
        class CursorPrueba:
            def execute(self, _consulta, *parametros):
                del _consulta
                self.parametros = parametros

            def fetchall(self):
                return [
                    ("usuario", "Operador", "mante_condensados"),
                    ("usuario", "Operador", "mante_aguas_caldera"),
                    ("usuario", "Operador", "mante_control_caldera"),
                ]

            def close(self):
                pass

        class ConexionPrueba:
            def __init__(self):
                self.cursor_prueba = CursorPrueba()

            def cursor(self):
                return self.cursor_prueba

            def close(self):
                pass

        conexion = ConexionPrueba()
        with patch.object(login.conexion, "obtener_conexion_usuarios", return_value=conexion):
            identidad = login.autenticar_usuario("usuario", "secreto")

        self.assertEqual(
            identidad,
            (
                "usuario",
                "Operador",
                frozenset(
                    {
                        login.REPORTE_FORMULARIO_19,
                        login.REPORTE_FORMULARIO_20,
                        login.REPORTE_FORMULARIO_3,
                    }
                ),
            ),
        )
        self.assertEqual(
            conexion.cursor_prueba.parametros,
            (
                "usuario",
                "secreto",
                login.REPORTE_FORMULARIO_19,
                login.REPORTE_FORMULARIO_20,
                login.REPORTE_FORMULARIO_3,
            ),
        )

    def test_retorno_de_formulario_1_conserva_los_permisos_de_sesion(self):
        pagina = PaginaMenuPrueba()
        cerrar_sesion = Mock()
        permisos = frozenset({login.REPORTE_FORMULARIO_19})
        menu.crear_menu(pagina, "usuario", "Operador", cerrar_sesion, permisos)

        boton_formulario_1 = next(
            control
            for control in self.recorrer_controles(pagina.controls)
            if isinstance(control, ft.ElevatedButton)
            and control.content == "Abrir formulario"
        )
        with patch(
            "form_monitoreo_control_aguas_condensado.abrir_ventana"
        ) as abrir_formulario:
            boton_formulario_1.on_click(
                SimpleNamespace(control=boton_formulario_1)
            )
            volver_al_menu = abrir_formulario.call_args.args[3]

        with patch.object(menu, "crear_menu", wraps=menu.crear_menu) as mostrar_menu:
            volver_al_menu()

        mostrar_menu.assert_called_once_with(
            pagina, "usuario", "Operador", cerrar_sesion, permisos
        )

    def test_cerrar_sesion_requiere_confirmacion(self):
        pagina = PaginaMenuPrueba()
        cerrar_sesion = Mock()
        menu.crear_menu(pagina, "usuario", "Operador", cerrar_sesion)
        boton_cerrar_sesion = next(
            control
            for control in self.recorrer_controles(pagina.controls)
            if isinstance(control, ft.OutlinedButton)
            and control.content == "Cerrar sesión"
        )

        boton_cerrar_sesion.on_click(SimpleNamespace(control=boton_cerrar_sesion))

        dialogo = pagina.dialog
        self.assertIsInstance(dialogo, ft.AlertDialog)
        cerrar_sesion.assert_not_called()
        boton_cancelar = next(
            accion
            for accion in dialogo.actions
            if isinstance(accion, ft.OutlinedButton)
        )
        boton_cancelar.on_click(SimpleNamespace(control=boton_cancelar))
        cerrar_sesion.assert_not_called()
        self.assertIsNone(pagina.dialog)

        boton_cerrar_sesion.on_click(SimpleNamespace(control=boton_cerrar_sesion))
        dialogo = pagina.dialog
        boton_confirmar = next(
            accion
            for accion in dialogo.actions
            if isinstance(accion, ft.ElevatedButton)
        )
        boton_confirmar.on_click(SimpleNamespace(control=boton_confirmar))

        cerrar_sesion.assert_called_once_with()
