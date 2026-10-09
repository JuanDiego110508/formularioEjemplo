import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft
from flet.controls.base_control import BaseControl
import form_monitoreo_control_aguas_caldera as formulario
from form_monitoreo_control_aguas_caldera import (
    SECCIONES,
    evaluar_criterio,
    obtener_desviaciones,
    parsear_valor,
    validar_lecturas,
    validar_lecturas_seccion,
    validar_lecturas_seleccionadas,
)


class PaginaPrueba:
    def __init__(self):
        self.controls = []
        self.window = SimpleNamespace(maximized=False, resizable=False)
        self.dialog = None

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def open(self, dialog):
        self.dialog = dialog

    def close(self, dialog):
        del dialog
        self.dialog = None


class CriteriosFormulario2Tests(unittest.TestCase):
    @staticmethod
    def recorrer_controles(valor):
        if isinstance(valor, (list, tuple)):
            for item in valor:
                yield from CriteriosFormulario2Tests.recorrer_controles(item)
        elif isinstance(valor, ft.Control):
            yield valor
            for atributo in ("controls", "content"):
                hijo = getattr(valor, atributo, None)
                if hijo is not None:
                    yield from CriteriosFormulario2Tests.recorrer_controles(hijo)

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

    def test_rangos_incluyen_los_limites(self):
        regla = {"tipo": "rango", "min": "8.0", "max": "10.0"}

        self.assertTrue(evaluar_criterio(Decimal("8.0"), regla))
        self.assertTrue(evaluar_criterio(Decimal("10.0"), regla))
        self.assertFalse(evaluar_criterio(Decimal("10.01"), regla))

    def test_igualdad_y_limites_estrictos(self):
        self.assertTrue(
            evaluar_criterio(Decimal("0"), {"tipo": "igual", "valor": "0"})
        )
        self.assertFalse(
            evaluar_criterio(Decimal("0.01"), {"tipo": "igual", "valor": "0"})
        )
        self.assertFalse(
            evaluar_criterio(Decimal("120"), {"tipo": "menor", "max": "120"})
        )
        self.assertFalse(
            evaluar_criterio(Decimal("100"), {"tipo": "mayor", "min": "100"})
        )

    def test_acepta_coma_decimal_y_rechaza_no_finitos(self):
        self.assertEqual(parsear_valor("10,5"), Decimal("10.5"))
        with self.assertRaises(ValueError):
            parsear_valor("NaN")
        self.assertEqual(parsear_valor("1.2300"), Decimal("1.2300"))
        with self.assertRaisesRegex(ValueError, "dos decimales"):
            parsear_valor("0,001")
        self.assertEqual(parsear_valor("99999999.99"), Decimal("99999999.99"))
        with self.assertRaisesRegex(ValueError, "ocho dígitos enteros"):
            parsear_valor("100000000")
        with self.assertRaisesRegex(ValueError, "ocho dígitos enteros"):
            parsear_valor("-100000000")

    def test_criterio_no_definido_no_se_califica(self):
        self.assertIsNone(evaluar_criterio(Decimal("4"), None))

    def test_validacion_exige_las_36_lecturas(self):
        campos = {
            (seccion["id"], parametro["id"]): "0"
            for seccion in SECCIONES
            for parametro in seccion["parametros"]
        }

        lecturas = validar_lecturas(campos)
        self.assertEqual(len(lecturas), 36)
        del campos[("PURGA_CALDERA_3", "ph")]
        with self.assertRaisesRegex(ValueError, "Completa todas las lecturas"):
            validar_lecturas(campos)

    def test_validacion_de_borrador_cubre_solo_la_seccion_seleccionada(self):
        campos = {
            ("ALIMENTACION_CALDERA", parametro["id"]): "1"
            for parametro in SECCIONES[0]["parametros"]
        }

        self.assertEqual(
            len(validar_lecturas_seccion("ALIMENTACION_CALDERA", campos)),
            6,
        )
        with self.assertRaisesRegex(ValueError, "Completa las lecturas"):
            validar_lecturas_seccion("PURGA_CALDERA_1", campos)

    def test_validacion_de_envio_acepta_secciones_completas_seleccionadas(self):
        campos = {
            ("ALIMENTACION_CALDERA", parametro["id"]): "1"
            for parametro in SECCIONES[0]["parametros"]
        }
        lecturas = validar_lecturas_seccion("ALIMENTACION_CALDERA", campos)

        self.assertEqual(
            validar_lecturas_seleccionadas(lecturas, {"ALIMENTACION_CALDERA"}),
            lecturas,
        )
        with self.assertRaisesRegex(ValueError, "no corresponden"):
            validar_lecturas_seleccionadas(lecturas, {"PURGA_CALDERA_1"})

    def test_criterios_coinciden_con_los_limites_del_excel(self):
        parametros = {
            (seccion["id"], parametro["id"]): parametro
            for seccion in SECCIONES
            for parametro in seccion["parametros"]
        }
        self.assertEqual(
            parametros[("ALIMENTACION_CALDERA", "dureza")]["regla"],
            {"tipo": "igual", "valor": "0"},
        )
        self.assertEqual(
            parametros[("ALIMENTACION_CALDERA", "temperatura")]["regla"],
            {"tipo": "mayor", "min": "60"},
        )
        self.assertEqual(
            parametros[("PURGA_CALDERA_1", "sulfitos")]["regla"],
            {"tipo": "rango", "min": "30", "max": "60"},
        )
        self.assertEqual(
            parametros[("PURGA_CALDERA_3", "alcalinidad_oh")]["regla"],
            {"tipo": "mayor", "min": "100"},
        )

    def test_desviaciones_se_reportan_incluyendo_igualdades(self):
        campos = {
            (seccion["id"], parametro["id"]): "0"
            for seccion in SECCIONES
            for parametro in seccion["parametros"]
        }
        campos[("ALIMENTACION_CALDERA", "dureza")] = "0,1"
        lecturas = validar_lecturas(campos)

        desviaciones = obtener_desviaciones(lecturas)
        dureza = next(
            item
            for item in desviaciones
            if item["seccion"] == "Alimentación caldera"
            and item["parametro"] == "Dureza"
        )
        self.assertEqual(dureza["valor"], "0.1")
        self.assertEqual(dureza["control"], "= 0")

    def test_guardado_inserta_36_lecturas_en_una_fila(self):
        campos = {
            (seccion["id"], parametro["id"]): "1"
            for seccion in SECCIONES
            for parametro in seccion["parametros"]
        }
        lecturas = validar_lecturas(campos)
        conexion = Mock()
        cursor = Mock()
        conexion.cursor.return_value = cursor
        cursor.fetchone.side_effect = [None, (42,)]

        with patch.object(
            formulario.conexionform,
            "obtener_conexion_formulario",
            return_value=conexion,
        ):
            id_registro = formulario.insertar_registro_bd(
                "2026-10-08",
                "15:30:00",
                "Operador",
                "usuario",
                "",
                lecturas,
            )

        self.assertEqual(id_registro, 42)
        conexion.commit.assert_called_once()
        conexion.rollback.assert_not_called()
        insercion = next(
            llamada
            for llamada in cursor.execute.call_args_list
            if "INSERT INTO" in llamada.args[0]
        )
        self.assertIn("OUTPUT INSERTED.id_registro", insercion.args[0])
        self.assertEqual(insercion.args[1], "2026-10-08")
        self.assertEqual(insercion.args[2], "15:30:00")
        self.assertEqual(
            sum(valor is not None for valor in insercion.args[1:][-36:]),
            36,
        )

    def test_guardado_parcial_inserta_una_fila_con_solo_su_seccion(self):
        seccion = SECCIONES[0]
        campos = {
            (seccion["id"], parametro["id"]): "1"
            for parametro in seccion["parametros"]
        }
        lecturas = validar_lecturas_seccion(seccion["id"], campos)
        conexion = Mock()
        cursor = Mock()
        conexion.cursor.return_value = cursor
        cursor.fetchone.side_effect = [None, (42,)]

        with patch.object(
            formulario.conexionform,
            "obtener_conexion_formulario",
            return_value=conexion,
        ):
            formulario.insertar_registro_bd(
                "2026-10-08",
                "15:30:00",
                "Operador",
                "usuario",
                "",
                lecturas,
                {seccion["id"]},
            )

        insercion = next(
            llamada
            for llamada in cursor.execute.call_args_list
            if "INSERT INTO" in llamada.args[0]
        )
        self.assertEqual(
            sum(valor is not None for valor in insercion.args[1:][-36:]),
            len(seccion["parametros"]),
        )
        conexion.commit.assert_called_once()

    def test_guardado_parcial_completa_la_misma_fila_de_fecha(self):
        seccion = SECCIONES[1]
        campos = {
            (seccion["id"], parametro["id"]): "1"
            for parametro in seccion["parametros"]
        }
        lecturas = validar_lecturas_seccion(seccion["id"], campos)
        conexion = Mock()
        cursor = Mock()
        conexion.cursor.return_value = cursor
        columnas_seleccionadas = formulario.PARAMETROS_REGISTRO[seccion["id"]]
        cursor.fetchone.side_effect = [
            (42, *(None for _ in columnas_seleccionadas))
        ]

        with patch.object(
            formulario.conexionform,
            "obtener_conexion_formulario",
            return_value=conexion,
        ):
            id_registro = formulario.insertar_registro_bd(
                "2026-10-08",
                "15:30:00",
                "Operador",
                "usuario",
                "",
                lecturas,
                {seccion["id"]},
            )

        self.assertEqual(id_registro, 42)
        actualizacion = next(
            llamada
            for llamada in cursor.execute.call_args_list
            if "UPDATE" in llamada.args[0]
        )
        self.assertEqual(
            actualizacion.args[1:-1],
            tuple(Decimal("1") for _ in seccion["parametros"]),
        )
        self.assertEqual(actualizacion.args[-1], 42)
        conexion.commit.assert_called_once()

    def test_no_permite_reenviar_una_seccion_ya_guardada_para_la_fecha(self):
        seccion = SECCIONES[0]
        campos = {
            (seccion["id"], parametro["id"]): "1"
            for parametro in seccion["parametros"]
        }
        lecturas = validar_lecturas_seccion(seccion["id"], campos)
        conexion = Mock()
        cursor = Mock()
        conexion.cursor.return_value = cursor
        cursor.fetchone.return_value = (
            42,
            *(Decimal("1") for _ in formulario.PARAMETROS_REGISTRO[seccion["id"]]),
        )

        with patch.object(
            formulario.conexionform,
            "obtener_conexion_formulario",
            return_value=conexion,
        ):
            with self.assertRaisesRegex(ValueError, "Ya se habían enviado"):
                formulario.insertar_registro_bd(
                    "2026-10-08",
                    "15:30:00",
                    "Operador",
                    "usuario",
                    "",
                    lecturas,
                    {seccion["id"]},
                )

        conexion.rollback.assert_called_once()
        conexion.commit.assert_not_called()

    def test_secciones_se_guardan_como_borradores_y_solo_se_envian_las_marcadas(self):
        pagina = PaginaPrueba()
        valores = {
            "ph": "9",
            "std": "10",
            "conductividad": "100",
            "dureza": "0",
            "temperatura": "70",
            "alcalinidad_m": "120",
            "hierro": "1",
            "silice": "1",
            "sulfitos": "40",
            "alcalinidad_p": "100",
            "alcalinidad_oh": "150",
        }

        with (
            patch.object(formulario.threading, "Thread"),
            patch.object(BaseControl, "update"),
        ):
            formulario.abrir_ventana(pagina, "usuario", "Operador")

        lista_principal = pagina.controls[0].content
        self.assertIsInstance(lista_principal, ft.Column)
        self.assertEqual(lista_principal.scroll, ft.ScrollMode.AUTO)
        self.assertTrue(lista_principal.tight)
        self.assertEqual(len(lista_principal.controls), 9)
        barra_fecha_hora = lista_principal.controls[1]
        self.assertIsInstance(barra_fecha_hora.content, ft.Column)
        fila_fecha_hora = barra_fecha_hora.content.controls[0]
        self.assertIsInstance(fila_fecha_hora, ft.Row)
        self.assertFalse(fila_fecha_hora.wrap)
        self.assertEqual(len(fila_fecha_hora.controls), 2)
        self.assertTrue(fila_fecha_hora.controls[0].expand)
        self.assertTrue(fila_fecha_hora.controls[1].expand)
        for tarjeta_seccion in lista_principal.controls[3:7]:
            self.assertIsInstance(
                tarjeta_seccion.content.controls[2], ft.Column
            )
        self.assertIsInstance(
            lista_principal.controls[8].content.controls[1], ft.Column
        )
        controles = list(self.recorrer_controles(pagina.controls))
        campos = [
            control
            for control in controles
            if isinstance(control, ft.TextField)
            and str(control.label).startswith("Lectura")
        ]
        self.assertEqual(len(campos), 36)
        titulos_seccion = {seccion["titulo"] for seccion in SECCIONES}
        titulos_renderizados = {
            control.value
            for control in controles
            if isinstance(control, ft.Text) and control.value in titulos_seccion
        }
        self.assertEqual(titulos_renderizados, titulos_seccion)
        textos_renderizados = {
            control.value
            for control in controles
            if isinstance(control, ft.Text)
        }
        self.assertIn("MONITOREO DE AGUAS DE CALDERA", textos_renderizados)
        self.assertIn("Hora de Medición (Operación):", textos_renderizados)
        self.assertIn("Fecha de Medición (Operación):", textos_renderizados)
        indice_campo = 0
        for seccion in SECCIONES[:2]:
            for parametro in seccion["parametros"]:
                valor = valores[parametro["id"]]
                if seccion["id"] == "PURGA_CALDERA_1" and parametro["id"] == "ph":
                    valor = "11"
                campos[indice_campo].value = valor
                indice_campo += 1

        botones_borrador = [
            control
            for control in controles
            if isinstance(control, ft.OutlinedButton)
            and self.texto_control(control.content)
            == "Guardar sección como borrador"
        ]
        self.assertEqual(len(botones_borrador), 4)
        botones_borrador[0].on_click(SimpleNamespace(control=botones_borrador[0]))
        botones_borrador[1].on_click(SimpleNamespace(control=botones_borrador[1]))

        controles = list(self.recorrer_controles(pagina.controls))
        seleccion = [
            control
            for control in controles
            if isinstance(control, ft.Checkbox)
            and control.label == "Incluir"
        ]
        self.assertEqual(len(seleccion), 2)
        seleccion[0].value = False

        boton_enviar = next(
            control
            for control in controles
            if isinstance(control, ft.ElevatedButton)
            and self.texto_control(control.content)
            == "Enviar borradores seleccionados"
        )
        with patch.object(
            formulario,
            "insertar_registro_bd",
            return_value=42,
        ) as insertar:
            boton_enviar.on_click(SimpleNamespace(control=boton_enviar))

        insertar.assert_called_once()
        self.assertEqual(insertar.call_args.args[-1], {"PURGA_CALDERA_1"})


if __name__ == "__main__":
    unittest.main()
