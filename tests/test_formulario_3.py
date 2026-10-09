import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import flet as ft
from flet.controls.base_control import BaseControl

import form_control_purgas_caldera as formulario


class PaginaPrueba:
    def __init__(self):
        self.controls = []
        self.dialog = None

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None

    def run_task(self, handler, *args):
        return asyncio.run(handler(*args))


class Formulario3Tests(unittest.TestCase):
    @classmethod
    def recorrer_controles(cls, valor):
        if isinstance(valor, (list, tuple)):
            for elemento in valor:
                yield from cls.recorrer_controles(elemento)
        elif isinstance(valor, ft.Control):
            yield valor
            for atributo in ("controls", "content"):
                hijo = getattr(valor, atributo, None)
                if hijo is not None:
                    yield from cls.recorrer_controles(hijo)

    @classmethod
    def texto_control(cls, control):
        if isinstance(control, ft.Text):
            return control.value or ""
        if isinstance(control, str):
            return control
        if isinstance(control, (list, tuple)):
            return " ".join(cls.texto_control(item) for item in control)
        if isinstance(control, ft.Control):
            return " ".join(
                cls.texto_control(getattr(control, atributo, None))
                for atributo in ("controls", "content")
                if getattr(control, atributo, None) is not None
            )
        return ""

    @staticmethod
    def campos_validos():
        return {
            "purga_1_ph": "11",
            "purga_1_alcalinidad_m": "500",
            "purga_1_color": "Claro",
            "purga_1_soda_g": "2,25",
            "purga_2_ph": "10,5",
            "purga_2_alcalinidad_m": "499.99",
            "purga_2_color": "Transparente",
            "purga_2_soda_g": "0",
            "entrega": "Operador saliente",
            "recibe": "Operador entrante",
        }

    def test_validacion_y_limites_del_excel(self):
        valores = formulario.validar_turno(1, self.campos_validos())
        self.assertEqual(valores["purga_1_soda_g"], Decimal("2.25"))
        self.assertEqual(formulario.obtener_desviaciones(valores), [])

        valores["purga_2_ph"] = Decimal("11.51")
        valores["purga_1_alcalinidad_m"] = Decimal("500.01")
        self.assertEqual(
            len(formulario.obtener_desviaciones(valores)),
            2,
        )

    def test_validacion_rechaza_valores_incompletos_y_precision_excesiva(self):
        campos = self.campos_validos()
        campos["purga_1_color"] = ""
        with self.assertRaisesRegex(ValueError, "Color de caldera #1"):
            formulario.validar_turno(1, campos)

        campos = self.campos_validos()
        campos["purga_1_soda_g"] = "1.234"
        with self.assertRaisesRegex(ValueError, "dos decimales"):
            formulario.validar_turno(1, campos)

    def test_guardado_inserta_cada_turno_en_una_fila(self):
        conexion = Mock()
        cursor = Mock()
        conexion.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        cursor.fetchone.side_effect = [(31,), (32,)]
        borradores = [
            {
                "turno": turno,
                "fecha": "2026-10-08",
                "hora": "15:30:00",
                "valores": formulario.validar_turno(turno, self.campos_validos()),
            }
            for turno in (1, 2)
        ]

        with patch.object(
            formulario.conexionform,
            "obtener_conexion_formulario",
            return_value=conexion,
        ):
            ids = formulario.insertar_borradores_bd(
                "2026-10-08",
                "usuario",
                borradores,
            )

        self.assertEqual(ids, [31, 32])
        inserciones = [
            llamada
            for llamada in cursor.execute.call_args_list
            if "INSERT INTO" in llamada.args[0]
        ]
        self.assertEqual(len(inserciones), 2)
        self.assertEqual(inserciones[0].args[1], "2026-10-08")
        self.assertEqual(inserciones[0].args[2], "15:30:00")
        self.assertEqual(inserciones[0].args[3], 1)
        self.assertEqual(inserciones[0].args[-1], "usuario")
        conexion.commit.assert_called_once()
        conexion.rollback.assert_not_called()

    def test_no_envia_turno_que_ya_existe_en_la_fecha(self):
        conexion = Mock()
        cursor = Mock()
        conexion.cursor.return_value = cursor
        cursor.fetchall.return_value = [(1,)]
        borrador = {
            "turno": 1,
            "fecha": "2026-10-08",
            "hora": "15:30:00",
            "valores": formulario.validar_turno(1, self.campos_validos()),
        }

        with patch.object(
            formulario.conexionform,
            "obtener_conexion_formulario",
            return_value=conexion,
        ):
            with self.assertRaisesRegex(ValueError, "Ya existe un registro"):
                formulario.insertar_borradores_bd(
                    "2026-10-08",
                    "usuario",
                    [borrador],
                )

        conexion.rollback.assert_called_once()
        conexion.commit.assert_not_called()

    def test_interfaz_muestra_tres_turnos_con_scroll_y_borradores(self):
        pagina = PaginaPrueba()
        with (
            patch.object(formulario.threading, "Thread"),
            patch.object(BaseControl, "update"),
        ):
            formulario.abrir_ventana(pagina, "usuario", "Operador")

        contenido = pagina.controls[0].content
        self.assertIsInstance(contenido, ft.Column)
        self.assertEqual(contenido.scroll, ft.ScrollMode.AUTO)
        barra_fecha_hora = contenido.controls[1].content
        self.assertIsInstance(barra_fecha_hora, ft.Row)
        campos_en_barra = [
            control
            for control in barra_fecha_hora.controls
            if isinstance(control, ft.TextField)
        ]
        self.assertEqual(len(campos_en_barra), 2)
        self.assertEqual(
            {len(campo.value) for campo in campos_en_barra},
            {8, 10},
        )
        controles = list(self.recorrer_controles(pagina.controls))
        campos_fecha_hora = [
            control
            for control in controles
            if isinstance(control, ft.TextField)
            and control.value
            and (
                (len(control.value) == 10 and control.value[4] == "-")
                or (len(control.value) == 8 and control.value[2] == ":")
            )
        ]
        self.assertEqual(len(campos_fecha_hora), 2)
        botones_guardar = [
            control
            for control in controles
            if isinstance(control, ft.OutlinedButton)
            and self.texto_control(control.content).startswith("Guardar Turno")
        ]
        self.assertEqual(len(botones_guardar), 3)
        campos = [
            control
            for control in controles
            if isinstance(control, ft.TextField)
            and control.label in {
                "pH (UN)",
                "Alcalinidad M (ppm)",
                "Color",
                "Soda adicionada (g)",
                "Entrega",
                "Recibe",
            }
        ]
        self.assertEqual(len(campos), 30)

        for campo in campos[:10]:
            etiqueta = campo.label
            campo.value = {
                "pH (UN)": "11",
                "Alcalinidad M (ppm)": "450",
                "Color": "Claro",
                "Soda adicionada (g)": "1.5",
                "Entrega": "Operador saliente",
                "Recibe": "Operador entrante",
            }[etiqueta]
        botones_guardar[0].on_click(
            SimpleNamespace(control=botones_guardar[0])
        )
        controles = list(self.recorrer_controles(pagina.controls))
        textos_estado = [
            control.value or ""
            for control in controles
            if isinstance(control, ft.Text)
        ]
        self.assertTrue(
            any("campos limpiados" in texto for texto in textos_estado)
        )
        self.assertTrue(all(not campo.value for campo in campos[:10]))

        boton_cargar = next(
            control
            for control in controles
            if isinstance(control, ft.OutlinedButton)
            and self.texto_control(control.content) == "Cargar / editar"
        )
        with patch.object(
            ft.Column,
            "scroll_to",
            new_callable=AsyncMock,
        ) as desplazar:
            boton_cargar.on_click(SimpleNamespace(control=boton_cargar))

        desplazar.assert_awaited_once_with(
            scroll_key="turno-1",
            duration=500,
        )
        self.assertEqual(
            [campo.value for campo in campos[:10]],
            [
                "11",
                "450",
                "Claro",
                "1.5",
                "11",
                "450",
                "Claro",
                "1.5",
                "Operador saliente",
                "Operador entrante",
            ],
        )
        self.assertTrue(
            any(
                isinstance(control, ft.Text)
                and "Borrador cargado" in (control.value or "")
                for control in self.recorrer_controles(pagina.controls)
            )
        )

        controles = list(self.recorrer_controles(pagina.controls))
        boton_enviar = next(
            control
            for control in controles
            if isinstance(control, ft.ElevatedButton)
            and self.texto_control(control.content)
            == "Enviar turnos seleccionados"
        )
        with patch.object(
            formulario,
            "insertar_borradores_bd",
            return_value=[51],
        ) as insertar:
            boton_enviar.on_click(SimpleNamespace(control=boton_enviar))

        insertar.assert_called_once()
        self.assertEqual(insertar.call_args.args[1], "usuario")
        self.assertEqual(insertar.call_args.args[2][0]["turno"], 1)
        textos = [
            control.value or ""
            for control in self.recorrer_controles(pagina.controls)
            if isinstance(control, ft.Text)
        ]
        self.assertTrue(
            any("Se enviaron 1 turno(s)" in texto for texto in textos)
        )


if __name__ == "__main__":
    unittest.main()
