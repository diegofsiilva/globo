"""Testes locais da entrada HTTPS e da comutacao de destino."""

from __future__ import annotations

import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import handler  # noqa: E402


def evento(caminho: str, metodo: str = "GET") -> dict:
    """Monta uma requisicao HTTP API v2 com token ficticio."""
    return {
        "rawPath": caminho,
        "requestContext": {"http": {"method": metodo}},
        "headers": {"authorization": "Bearer " + "a" * 64},
    }


class EntradaTest(unittest.TestCase):
    """Verifica origem primaria, contingencia e protecao do token."""

    def setUp(self) -> None:
        """Configura endpoints ficticios sem contato com a AWS."""
        self.ambiente = patch.dict(
            os.environ,
            {
                "PRIMARY_HOST_PARAMETER": "/argus/edge/primary-alb-host",
                "FRONTEND_BUCKET": "site-exemplo",
                "READ_API_URL": "https://leitura.example.invalid",
            },
        )
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)
        handler._HOST_EXPIRA = 0

    def test_primario_saudavel(self) -> None:
        """Mantem a resposta do ALB e nao consulta a contingencia."""
        with patch.object(
            handler, "_host_primario", return_value="internal-a.elb.amazonaws.com"
        ):
            with patch.object(
                handler, "_requisitar", return_value={"statusCode": 200}
            ) as requisitar:
                self.assertEqual(
                    handler.lambda_handler(evento("/api/v1/clock"), None),
                    {"statusCode": 200},
                )
        self.assertEqual(requisitar.call_count, 1)
        self.assertTrue(requisitar.call_args.args[0].startswith("http://internal-a."))

    def test_api_comuta_apos_503(self) -> None:
        """Encaminha a mesma autorizacao para a API de leitura apos falha."""
        with patch.object(
            handler, "_host_primario", return_value="internal-a.elb.amazonaws.com"
        ):
            with patch.object(
                handler,
                "_requisitar",
                side_effect=[{"statusCode": 503}, {"statusCode": 200}],
            ) as requisitar:
                self.assertEqual(
                    handler.lambda_handler(evento("/api/v1/clock"), None)["statusCode"],
                    200,
                )
        self.assertEqual(requisitar.call_count, 2)
        self.assertEqual(
            requisitar.call_args.args[0], "https://leitura.example.invalid/api/v1/clock"
        )
        self.assertEqual(
            requisitar.call_args.args[3]["authorization"], "Bearer " + "a" * 64
        )

    def test_post_nao_repete_apos_falha_do_primario(self) -> None:
        """Evita duplicar uma escrita cujo resultado no ALB e incerto."""
        with patch.object(
            handler, "_host_primario", return_value="internal-a.elb.amazonaws.com"
        ):
            with patch.object(
                handler, "_requisitar", return_value={"statusCode": 503}
            ) as requisitar:
                resposta = handler.lambda_handler(
                    evento("/api/v1/hypotheses/1/feedback", "POST"), None
                )
        self.assertEqual(resposta["statusCode"], 503)
        self.assertEqual(requisitar.call_count, 1)

    def test_estatico_comuta_para_s3(self) -> None:
        """Le a pagina exportada quando o ALB nao responde."""

        class Corpo:
            """Corpo minimo do objeto S3."""

            def read(self) -> bytes:
                """Devolve o HTML de exemplo."""
                return b"<html>ok</html>"

        class S3:
            """Cliente S3 minimo para observar a chave solicitada."""

            def get_object(self, *, Bucket: str, Key: str) -> dict:
                """Confirma bucket e caminho do export estatico."""
                self_test.assertEqual((Bucket, Key), ("site-exemplo", "agora/index.html"))
                return {"Body": Corpo(), "ContentType": "text/html"}

        self_test = self
        with patch.object(handler, "_host_primario", return_value=""):
            with patch.object(handler, "_cliente", return_value=S3()):
                resposta = handler.lambda_handler(evento("/agora/"), None)
        self.assertEqual(resposta["statusCode"], 200)
        self.assertEqual(base64.b64decode(resposta["body"]), b"<html>ok</html>")

    def test_host_externo_e_rejeitado(self) -> None:
        """Nao envia o Bearer a um dominio arbitrario vindo do SSM."""

        class SSM:
            """Cliente SSM com valor hostil."""

            def get_parameter(self, *, Name: str) -> dict:
                """Devolve um host fora do ALB interno."""
                return {"Parameter": {"Value": "example.invalid"}}

        with patch.object(handler, "_cliente", return_value=SSM()):
            self.assertEqual(handler._host_primario(), "")


if __name__ == "__main__":
    unittest.main()
