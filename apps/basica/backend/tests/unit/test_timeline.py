"""Testes unitários do módulo ``telemetry.application.timeline``.

Função testada:
  - amostrar_raia — redução uniforme de séries temporais para a tela Timeline
"""

from telemetry.application.timeline import amostrar_raia

# ── TU-BCK-14 — amostrar_raia ─────────────────────────────────────────────────


class TestAmostrarRaia:
    def test_deve_retornar_todos_pontos_quando_abaixo_do_limite(self):
        """Caso válido: série menor que o limite passa intacta, truncated=False."""
        pontos = [{"bucket_ts": i, "value": i * 10} for i in range(50)]
        resultado, truncado = amostrar_raia(pontos, limite=100)

        assert resultado == pontos
        assert truncado is False

    def test_deve_reduzir_preservando_primeiro_e_ultimo_ponto(self):
        """Caso válido: bordas da janela temporal sempre presentes na amostra."""
        pontos = [{"bucket_ts": i, "value": i} for i in range(500)]
        resultado, truncado = amostrar_raia(pontos, limite=10)

        assert truncado is True
        assert len(resultado) <= 10
        assert resultado[0] == pontos[0]  # primeiro ponto preservado
        assert resultado[-1] == pontos[-1]  # último ponto preservado

    def test_nao_deve_duplicar_pontos_na_amostragem(self):
        """Caso de erro previsto: arredondamento de índices não pode gerar duplicatas."""
        pontos = [{"bucket_ts": i, "value": i} for i in range(200)]
        resultado, _ = amostrar_raia(pontos, limite=50)

        bucket_ts_list = [p["bucket_ts"] for p in resultado]
        assert len(bucket_ts_list) == len(set(bucket_ts_list))

    def test_deve_retornar_lista_vazia_sem_erro(self):
        """Caso de limite: lista vazia → lista vazia, truncated=False."""
        resultado, truncado = amostrar_raia([], limite=100)
        assert resultado == []
        assert truncado is False

    def test_serie_exatamente_no_limite_nao_e_truncada(self):
        """Caso de limite: total == limite → sem redução."""
        pontos = [{"bucket_ts": i, "value": i} for i in range(100)]
        resultado, truncado = amostrar_raia(pontos, limite=100)

        assert resultado == pontos
        assert truncado is False

    def test_serie_um_acima_do_limite_e_truncada(self):
        """Caso de limite: total == limite + 1 → redução acontece."""
        pontos = [{"bucket_ts": i, "value": i} for i in range(101)]
        resultado, truncado = amostrar_raia(pontos, limite=100)

        assert truncado is True
        assert len(resultado) <= 100
        assert resultado[0] == pontos[0]
        assert resultado[-1] == pontos[-1]
