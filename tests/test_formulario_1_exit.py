import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft
from flet.controls.base_control import BaseControl

import form_monitoreo_control_aguas_condensado as formulario


class PaginaPrueba:
    def __init__(self):
        self.controls = []
        self.window = SimpleNamespace(maximized=False, resizable=False)
        self.opened_dialog = None

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def open(self, dialog):
        self.opened_dialog = dialog

    def close(self, _dialog):
        del _dialog
        self.opened_dialog = None


class SalidaFormulario1Tests(unittest.TestCase):
    def test_volver_al_menu_conserva_el_callback_de_sesion(self):
        pagina = PaginaPrueba()
        volver_al_menu = Mock()

        with (
            patch.object(formulario.threading, "Thread"),
            patch.object(formulario, "obtener_ultimos_registros_bd", return_value={}),
            patch.object(BaseControl, "update"),
        ):
            formulario.abrir_ventana(
                pagina, "usuario", "Operador", volver_al_menu
            )

        controles = pagina.controls[0].content.controls
        encabezado = controles[0]
        boton_volver = encabezado.content.controls[0].controls[0]
        boton_volver.on_click(SimpleNamespace(control=boton_volver))

        boton_confirmar_salida = next(
            accion
            for accion in pagina.opened_dialog.actions
            if isinstance(accion, ft.ElevatedButton)
        )
        boton_confirmar_salida.on_click(
            SimpleNamespace(control=boton_confirmar_salida)
        )

        volver_al_menu.assert_called_once_with()
        self.assertIsNone(pagina.opened_dialog)
