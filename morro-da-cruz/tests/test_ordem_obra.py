"""Ordem obrigatória topografia → serviço → cadastro (D-20 DECIDIDA em 23/10/2026: bloqueio). A NS de serviço só sobre
trecho liberado pela topografia até a data da nota; a NS do dia não grava execução sobre o que não está liberado; o
cadastro de campo recusado volta só à mão ("Aplicar de novo"). A mensagem diz exatamente o que falta."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import ns_sintetica as NSS  # noqa: E402
import servicos as S  # noqa: E402
from base_real import TR006, TR020, BaseReal, b64, pdf_ns  # noqa: E402
from test_ns_dia import BaseDia, grupo, pdf_dia  # noqa: E402


class TestNsDeServico(BaseReal):
    def test_so_sobre_trecho_liberado_e_nada_gravado_quando_falta(self):
        pdf, croqui = pdf_ns(numero="020"), b64(NSS.pdf_de_texto(["CROQUI NS 020"]))
        st, r = self.registrar("eng1", "SERVICO", pdf, croqui_b64=croqui, croqui_nome="croqui.pdf")
        self.assertEqual(st, 422, r)
        self.assertIn("NS de serviço só sobre trecho liberado pela topografia", r["erro"])
        self.assertIn("Zona 03 · PB08 · TR020, de 0,0 m a 278,0 m: falta a liberação topográfica (registre a NS de topografia antes)",
                      r["erro"])
        self.assertEqual((self.n("notas_servico"), self.n("documentos", "tipo LIKE 'NS_%'")), (0, 0))       # nada gravado
        self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf_ns(numero="012")))                                   # a ordem certa
        self.ok(self.registrar("eng1", "SERVICO", pdf, croqui_b64=croqui, croqui_nome="croqui.pdf"))


class TestNumeroParaCasarNoLote(BaseReal):
    """O envio em lote casa o croqui e a planilha com cada NS pelo número escrito neles (e, na falta, pelo nome)."""

    def test_numero_da_nota_do_croqui_e_da_foto(self):
        cli = self.cli("enc3")
        num = lambda dados: cli.post("/api/ns/numero", {"arquivo_b64": b64(dados)})
        self.assertEqual(num(pdf_ns(numero="013")), (200, {"numeros": [13]}))                       # cabeçalho da própria NS
        self.assertEqual(num(NSS.pdf_de_texto(["CROQUI DA N.S. 012 - REDE ZONA 03"])), (200, {"numeros": [12]}))
        self.assertEqual(num(b"\xff\xd8\xff\xe0 foto"), (200, {"numeros": []}))                   # foto: casa pelo nome
        self.assertEqual(self.cli("topo1").post("/api/ns/numero", {"arquivo_b64": b64(b"x")})[0], 403)


class TestNsDoDiaSemLiberacao(BaseDia):
    LIBERAR_TUDO = False

    def test_execucao_sobre_o_nao_liberado_nao_e_gravada(self):
        st, r = self.enviar("enc3", pdf_dia([grupo(["NÓ9.1 - TÊ 160x160", "CH_VRP-15 (CAIXA DA VRP)"], [295.98], obs=["ASSENTAMENTO", None])]))
        texto = str(r)
        self.assertIn("falta a liberação topográfica", texto)
        self.assertEqual(self.gravado(), [])                                   # nada de execução fora de ordem
        self.assertEqual(S.fora_de_ordem(self.c), [])


if __name__ == "__main__":
    unittest.main()
