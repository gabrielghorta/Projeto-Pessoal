"""Assistente, a IA conversacional (D-219 a D-224), com o MODELO SIMULADO: nenhum teste daqui usa a rede.

O que se troca é só o transporte (assistente.TRANSPORTE): o servidor, as rotas, as permissões, as consultas, o rascunho
e a gravação pela rota de sempre são os de verdade, sobre o banco das planilhas do repositório (tests/base_real.py). A
conversa com a API real da Groq é conferida à parte, por ferramentas/assistente/validar_api_real.py."""
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "ferramentas", "assistente"))
import assistente as IA  # noqa: E402
import relogio as RL  # noqa: E402
from base_real import BaseReal  # noqa: E402
from cenario import Tela  # noqa: E402
from test_acesso import SENHA  # noqa: E402

CHAVE = "gsk_chave_de_teste_que_nunca_pode_aparecer"


def chamada(nome, **args):
    return {"id": f"fc_{nome}", "type": "function", "function": {"name": nome, "arguments": json.dumps(args, ensure_ascii=False)}}


def resposta(*chamadas, texto=None, tokens=1300):
    msg = {"role": "assistant", "content": texto, "reasoning": "pensamento que não volta ao modelo"}
    if chamadas:
        msg["tool_calls"] = list(chamadas)
    return 200, {"X-Ratelimit-Remaining-Tokens": "6000", "X-Ratelimit-Remaining-Requests": "990"}, {
        "choices": [{"message": msg}], "usage": {"total_tokens": tokens}}


def recusa(tipo="tokens", espera="9", janela="tokens per minute (TPM): Limit 8000"):
    # o corpo é o que a Groq devolveu de verdade em 14/11/2026 (com a organização trocada)
    return 429, {"Retry-After": espera}, {"error": {
        "message": f"Rate limit reached for model `openai/gpt-oss-20b` in organization `org_x` service tier `on_demand` on {janela}, Used 7990, "
                   "Requested 2067. Please try again in 8.9s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing",
        "type": tipo, "code": "rate_limit_exceeded"}}


class Modelo:
    """O modelo simulado: devolve as respostas do roteiro, na ordem, e guarda o que o servidor mandou."""

    def __init__(self, *roteiro):
        self.roteiro, self.pedidos = list(roteiro), []

    def __call__(self, url, cabecalhos, corpo, tempo):
        self.pedidos.append({"url": url, "cabecalhos": cabecalhos, "corpo": json.loads(json.dumps(corpo))})
        if not self.roteiro:
            raise AssertionError("o servidor chamou o modelo mais vezes do que o roteiro previa")
        return self.roteiro.pop(0)

    def sistema(self, i=-1):
        return self.pedidos[i]["corpo"]["messages"][0]["content"]

    def funcoes(self, i=-1):
        return [f["function"]["name"] for f in self.pedidos[i]["corpo"].get("tools") or []]


class BaseAssistente(BaseReal):
    def setUp(self):
        super().setUp()
        self._antes = (IA.TRANSPORTE, IA.DORMIR, os.environ.get("GROQ_API_KEY"), os.environ.get("MC_SEGREDOS"))
        os.environ["GROQ_API_KEY"] = CHAVE
        os.environ["MC_SEGREDOS"] = os.path.join(self.tmp, "sem_segredos.env")
        self.dormiu = []
        IA.DORMIR = self.dormiu.append
        IA._RITMO.clear()
        self.modelo()

    def tearDown(self):
        IA.TRANSPORTE, IA.DORMIR = self._antes[:2]
        for nome, valor in (("GROQ_API_KEY", self._antes[2]), ("MC_SEGREDOS", self._antes[3])):
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor
        super().tearDown()

    def modelo(self, *roteiro):
        self.m = IA.TRANSPORTE = Modelo(*roteiro)
        return self.m

    def tela(self, login):
        return Tela(self.url, login, senha=SENHA)

    def um(self, sql, *args):
        r = self.c.execute(sql, args).fetchone()
        return tuple(r) if r else None


class TestAceitacao(BaseAssistente):
    def test_dois_conteineres_locacao_sanitario_tres(self):
        """O exemplo de aceitação: a busca no orçamento vira Instalação × Locação; a pessoa responde por toque e por
        texto, corrige a quantidade sem repetir o pedido e o rascunho mostra 6.1.3, Canteiro e 3 contêineres × 1 mês."""
        self.modelo(resposta(chamada("rascunho_apropriacao", item="contêiner", local="canteiro", fatores=[{"nome": "contêineres", "valor": 2}])),
                    resposta(chamada("rascunho_apropriacao", item="1.1_6.1.3", fatores=[{"nome": "mês", "valor": 1}])),
                    resposta(chamada("rascunho_apropriacao", item="1.1_6.1.3", fatores=[{"nome": "contêineres", "valor": 3}])))
        t = self.tela("eng1")
        r = t.dizer("Lança dois contêineres no canteiro")
        self.assertEqual([b["rotulo"] for b in t.botoes], ["Instalação", "Locação"])
        self.assertEqual(r["uso"]["chamadas"], 1)                 # os botões são do código: nenhuma chamada a mais
        self.assertFalse(t.rascunho["pronto"])
        self.assertEqual(t.linhas()["Anotado"], "2 contêineres")  # o que já foi dito fica guardado antes de saber o item
        t.tocar("Locação")                                        # grupo: abre os três itens sem chamar ninguém
        self.assertEqual(len(self.m.pedidos), 1)
        self.assertEqual([b["rotulo"][:5] for b in t.botoes], ["6.1.1", "6.1.2", "6.1.3"])
        t.dizer("sanitário por um mês")
        self.assertIn("Mais próxima do que foi dito: id 1.1_6.1.3 = LOCAÇÃO CONTAINER SANITÁRIO (unidade MES)", self.m.sistema())
        self.assertEqual(t.linhas()["Memória de cálculo"], "2 contêineres × 1 mês = 2 MES")
        t.dizer("na verdade, foram três")
        self.assertIn("anotado: 2 contêineres × 1 mês", self.m.sistema())   # o modelo recebe o rascunho atual para corrigir só um campo
        li = t.linhas()
        self.assertTrue(li["Item"].startswith("6.1.3 · LOCAÇÃO CONTAINER SANITÁRIO"))
        self.assertTrue(li["Grupo"].startswith("Canteiro"))
        self.assertEqual((li["Local"], li["Memória de cálculo"], li["Quantidade"]), ("Canteiro de obra", "3 contêineres × 1 mês = 3 MES", "3 MES"))
        self.assertTrue(t.rascunho["pronto"])
        self.assertIn("3 contêineres × 1 mês = 3 MES", t.conversa[-1]["texto"])
        self.assertEqual(self.um("SELECT COUNT(*) FROM apropriacoes"), (0,))  # nada é gravado antes do toque
        st, g = t.gravar()
        self.assertEqual(st, 200, g)
        self.assertEqual(self.um("SELECT item,quantidade,unidade,local_tipo,memoria_calculo,registrado_por,data FROM apropriacoes WHERE id=?", g["id"]),
                         ("1.1_6.1.3", 3.0, "MES", "CANTEIRO", "3 contêineres × 1 mês = 3 MES", "eng1", RL.hoje().isoformat()))
        # a gravação passou pela rota de sempre: está na auditoria como /api/apropriacao, com o login da sessão
        self.assertEqual(self.um("SELECT login,status FROM auditoria WHERE rota='/api/apropriacao' ORDER BY id DESC LIMIT 1"), ("eng1", 200))

    def test_o_que_foi_contado_serve_de_busca_quando_o_modelo_esquece_o_item(self):
        self.modelo(resposta(chamada("rascunho_apropriacao", local="canteiro", fatores=[{"nome": "contêineres", "valor": 2}])))
        t = self.tela("eng1")
        t.dizer("Lança dois contêineres no canteiro")
        self.assertEqual([b["rotulo"] for b in t.botoes], ["Instalação", "Locação"])

    def test_botao_e_campo_do_rascunho_nao_chamam_o_modelo(self):
        t = self.tela("adm")
        t.atalho("APROPRIACAO")
        self.assertEqual(t.rascunho["faltam"][0]["campo"], "item")
        t.editar("item", "5.1.1")                                   # instalação de contêiner, UN
        t.editar("fator.CONTAGEM", "2")
        t.editar("local", "zona 4")
        self.assertEqual((t.linhas()["Quantidade"], t.linhas()["Local"]), ("2 UN", "Zona 04"))
        self.assertTrue(t.rascunho["pronto"])
        self.assertEqual(self.m.pedidos, [])
        st, g = t.gravar()
        self.assertEqual(st, 200, g)
        self.assertEqual(self.um("SELECT item,quantidade,local_tipo,local_id FROM apropriacoes WHERE id=?", g["id"]), ("1.2_5.1.1", 2.0, "ZONA", "Zona04"))

    def test_item_ambiguo_vira_botoes_e_medidas_viram_conta(self):
        self.modelo(resposta(chamada("rascunho_apropriacao", item="placa de obra", data="ontem",
                                     fatores=[{"nome": "comprimento", "valor": 4}, {"nome": "altura", "valor": 2.5}])))
        t = self.tela("eng1")
        t.dizer("ontem terminamos a placa de obra, 4 metros por 2 e meio")
        self.assertGreaterEqual(len(t.botoes), 2)                   # o mesmo serviço em dois orçamentos parciais
        self.assertEqual(t.linhas()["Item"], "a definir")
        t.tocar("5.14.4")
        self.assertIn("Q = 4 × 2,5 = 10 m²", t.linhas()["Memória de cálculo"])
        self.assertEqual(t.rascunho["corpo"]["data"], (RL.hoje() - timedelta(days=1)).isoformat())
        t.editar("medida.0.largura", "abc")                         # a conta é do código: medida inválida não passa
        self.assertFalse(t.rascunho["pronto"])
        self.assertIn("Medida inválida", " ".join(t.rascunho["avisos"]))
        t.editar("medida.0.largura", "2,4")
        self.assertIn("9,6 m²", t.linhas()["Memória de cálculo"])
        st, g = t.gravar()
        self.assertEqual(st, 200, g)
        self.assertEqual(self.um("SELECT quantidade FROM apropriacoes WHERE id=?", g["id"]), (9.6,))

    def test_data_futura_e_item_inexistente_voltam_ao_modelo_como_erro(self):
        amanha = (RL.hoje() + timedelta(days=1)).isoformat()
        self.modelo(resposta(chamada("rascunho_apropriacao", item="foguete espacial", data=amanha)),
                    resposta(texto="Não achei esse serviço no orçamento. Qual é o serviço?"))
        t = self.tela("eng1")
        r = t.dizer("lança um foguete amanhã")
        erros = json.loads(self.m.pedidos[1]["corpo"]["messages"][-1]["content"])["erros"]
        self.assertTrue(any("futuro" in e for e in erros) and any("não encontrado" in e for e in erros), erros)
        self.assertEqual(r["resposta"], "Não achei esse serviço no orçamento. Qual é o serviço?")
        self.assertEqual(set(self.m.pedidos[1]["corpo"]["messages"][2]), {"role", "content", "tool_calls"})   # o pensamento do modelo não é reenviado


class TestPedidoEOcorrencia(BaseAssistente):
    def test_pedido_do_encarregado_com_correcao_e_frente_da_equipe(self):
        self.modelo(resposta(chamada("rascunho_pedido", itens=[{"material": "luva 110", "quantidade": 25}, {"material": "curva 90 63", "quantidade": 3}])),
                    resposta(chamada("rascunho_pedido", itens=[{"material": "luva 110", "quantidade": 40}])),
                    resposta(chamada("rascunho_pedido", frente="zona 7")))
        t = self.tela("enc3")
        t.dizer("tô sem luva de 110, manda 25, e 3 curvas de 90 de 63")
        qtd = lambda: {f["rotulo"]: f["valor"] for f in t.rascunho["form"] if f["id"].startswith("item.")}
        self.assertEqual(qtd(), {"Luva eletrofusão 110 mm": 25, "Curva 90° eletrofusão 63 mm": 3})
        self.assertEqual(t.rascunho["campos"]["frente_id"], "Zona03")       # a única frente do encarregado entra sozinha
        t.dizer("pensando bem, sobe as luvas pra 40")
        self.assertEqual(qtd(), {"Luva eletrofusão 110 mm": 40, "Curva 90° eletrofusão 63 mm": 3})
        r = t.dizer("manda pra zona 7")                                      # a regra da rotina vale também na conversa
        self.assertIn("Este login não pede para Zona 07: o pedido fica para Zona 03", r["resposta"])
        self.assertEqual(t.rascunho["campos"]["frente_id"], "Zona03")
        self.assertIn("material 'Luva eletrofusão 110 mm' quantidade 40", self.m.sistema())   # o rascunho que o modelo recebe
        self.assertEqual(len(self.m.pedidos), 3)                              # uma chamada por mensagem
        self.assertEqual(self.um("SELECT COUNT(*) FROM solicitacoes_compra"), (0,))
        st, g = t.gravar()
        self.assertEqual(st, 200, g)
        self.assertEqual(self.um("SELECT s.solicitante,d.frente_id FROM solicitacoes_compra s JOIN solicitacao_detalhes d ON d.solicitacao_id=s.id WHERE s.id=?", g["id"]),
                         ("enc3", "Zona03"))
        self.assertEqual(sorted(r[0] for r in self.c.execute("SELECT quantidade FROM solicitacao_itens WHERE solicitacao_id=?", (g["id"],))), [3.0, 40.0])

    def test_material_ambiguo_guarda_a_quantidade_no_botao(self):
        self.modelo(resposta(chamada("rascunho_pedido", frente="zona 5", itens=[{"material": "tubo 63", "quantidade": 12}])))
        t = self.tela("almox1")
        t.dizer("12 metros de tubo de 63 pra zona 5")
        self.assertEqual([b["rotulo"] for b in t.botoes], ["Tubo PEAD 63 mm", "Tubo PEAD 63 mm · tubo fornecido pela Caesb"])
        t.tocar("fornecido pela Caesb")
        self.assertEqual(t.rascunho["campos"]["itens"], [{"material_id": "CAESB-PEAD-DE63", "quantidade": 12.0}])
        self.assertTrue(t.rascunho["pronto"])
        self.assertEqual(len(self.m.pedidos), 1)

    def test_chuva_so_com_toques_e_as_travas_do_encarregado(self):
        t = self.tela("sup1")
        t.atalho("OCORRENCIA", chuva=True)
        self.assertEqual(t.rascunho["faltam"][0]["campo"], "equipe")
        t.tocar("EQUIPE ZONA 03")
        t.tocar("Tarde")
        t.tocar("Paralisou")
        self.assertTrue(t.rascunho["pronto"])
        self.assertEqual(self.m.pedidos, [])
        st, g = t.gravar()
        self.assertEqual(st, 200, g)
        self.assertEqual(self.um("SELECT o.equipe_id,o.aberta_por,c.turno,c.condicao FROM ocorrencias o JOIN ocorrencia_chuvas c ON c.ocorrencia_id=o.id WHERE o.id=?", g["id"]),
                         ("Zona03", "sup1", "TARDE", "PARALISADO_CHUVA"))
        # o encarregado: a equipe é a dele e "todas as equipes" não existe para ele, nem pedindo
        self.modelo(resposta(chamada("rascunho_ocorrencia", categoria="CHUVA", equipe="TODAS", turno="MANHA", efeito="VALA_ALAGADA_BOMBA")),
                    resposta(texto="Registro só para a sua equipe."))
        e = self.tela("enc3")
        e.dizer("choveu de manhã em todas as equipes, vala alagada")
        self.assertEqual(e.rascunho["campos"].get("equipe_id"), "Zona03")
        self.assertNotIn("todas_equipes", e.rascunho["campos"])
        self.assertFalse(e.rascunho["corpo"]["todas_equipes"])

    def test_interferencia_com_trecho_e_correcao(self):
        self.modelo(resposta(chamada("rascunho_ocorrencia", categoria="INTERFERENCIA", local="zona 3 pb06 tr014", descricao="cabo de fibra enterrado na vala")),
                    resposta(chamada("rascunho_ocorrencia", local="zona 3 pb06 tr015")))
        t = self.tela("enc3")
        t.dizer("achamos um cabo de fibra enterrado na vala, zona 3 pb06 tr014")
        self.assertEqual(t.linhas()["Onde"], "Zona 03 · PB06 · TR014")
        t.dizer("opa, foi no tr015")
        self.assertEqual(t.linhas()["Onde"], "Zona 03 · PB06 · TR015")
        self.assertEqual(t.rascunho["campos"]["descricao"], "cabo de fibra enterrado na vala")
        st, g = t.gravar()
        self.assertEqual(st, 200, g)
        self.assertEqual(self.um("SELECT categoria,equipe_id,aberta_por FROM ocorrencias WHERE id=?", g["id"]), ("INTERFERENCIA", "Zona03", "enc3"))


class TestPerfisEConsultas(BaseAssistente):
    def test_todo_login_conversa_mas_so_lanca_o_que_ja_podia(self):
        for login, tem in (("rh1", set()), ("topo1", set()), ("cad1", set()), ("sup1", {"rascunho_pedido", "rascunho_ocorrencia"}),
                           ("almox1", {"rascunho_pedido", "rascunho_ocorrencia"}), ("eng1", {"rascunho_pedido", "rascunho_ocorrencia", "rascunho_apropriacao"})):
            self.modelo(resposta(texto="Posso tirar dúvidas de uso."))
            IA._RITMO.clear()
            t = self.tela(login)
            st, estado = t.req("/api/assistente")
            self.assertEqual(st, 200, login)
            self.assertEqual({u["tipo"] for u in estado["usos"]}, {IA._RASCUNHOS[f] for f in tem}, login)
            r = t.dizer("oi, o que você faz?")
            self.assertEqual(r["situacao"], "OK", login)
            # D-225: o modelo recebe só as funções de lançamento do perfil; o que ele não lança vira a função mínima
            # sem_permissao, e o código continua conferindo a permissão em cada função
            enviadas = set(self.m.funcoes())
            self.assertEqual({f for f in enviadas if f.startswith("rascunho_")}, tem, login)
            self.assertEqual("sem_permissao" in enviadas, len(tem) < 3, login)
            self.assertEqual("consultar_orcamento" in enviadas, "rascunho_apropriacao" in tem, login)
            self.assertTrue({"consultar_ajuda", "consultar_trecho"} <= enviadas, login)
            self.assertNotIn("descartar_rascunho", enviadas, login)               # sem rascunho aberto, não há o que descartar
            for funcao, tipo in IA._RASCUNHOS.items():
                turno = IA._Turno()
                r, _ = IA.executar(self.srv_conn, IA.config(), t.usuario, turno, funcao, {"item": "tapume", "categoria": "CHUVA"})
                self.assertEqual("erro" in r, funcao not in tem, (login, funcao))
                self.assertEqual(turno.rascunho is None, funcao not in tem, (login, funcao))

    def test_modelo_nao_passa_por_cima_da_permissao(self):
        # o modelo encaminha o pedido para a função do assunto; o código recusa pela permissão e explica, numa chamada só
        self.modelo(resposta(chamada("rascunho_apropriacao", item="tapume", fatores=[{"nome": "metros", "valor": 40}])))
        t = self.tela("almox1")
        r = t.dizer("lança 40 metros de tapume")
        self.assertIsNone(t.rascunho)
        self.assertEqual(r["resposta"], IA.SEM_PERMISSAO["APROPRIACAO"])
        st, r = t.req("/api/assistente/rascunho", {"rascunho": {"tipo": "APROPRIACAO", "campos": {"item_ref": "BM:359"}}, "mudar": {"fator.CONTAGEM": 5}})
        self.assertEqual((st, r), (422, {"erro": "Não há rascunho aberto."}))
        st, r = t.req("/api/apropriacao", {"item_ref": "BM:359", "data": RL.hoje().isoformat(), "parcelas": [{"comprimento": "40", "largura": "2"}]})
        self.assertEqual(st, 403)                                   # e a rota de sempre continua sendo a última palavra
        self.assertEqual(self.um("SELECT COUNT(*) FROM apropriacoes"), (0,))

    def test_consultas_especificas_respeitam_o_login(self):
        self.modelo(resposta(chamada("consultar_catalogo", busca="luva 110"), chamada("consultar_frentes"), chamada("consultar_pedidos", quais="TODOS")),
                    resposta(texto="Tem luva de 110 no catálogo."))
        e = self.tela("enc3")
        e.dizer("tem luva de 110? pra onde eu posso pedir?")
        r1, r2, r3 = [json.loads(m["content"]) for m in self.m.pedidos[1]["corpo"]["messages"] if m["role"] == "tool"]
        self.assertEqual([m["nome"] for m in r1["materiais"]], ["Luva eletrofusão 110 mm"])
        self.assertEqual((r2["frentes_para_pedir"], r2["equipes"]), (["Zona 03"], ["EQUIPE ZONA 03"]))
        self.assertEqual(r3["pedidos"], [])
        # um pedido do almoxarifado: o encarregado continua não vendo; o almoxarifado (que abre Compras) vê
        a = self.tela("almox1")
        a.atalho("PEDIDO")
        a.editar("itens", [{"material": "cimento", "quantidade": 4}])
        a.tocar("Zona 02")
        self.assertEqual(a.gravar()[0], 200)
        for login, visto in (("enc3", 0), ("almox1", 1)):
            self.modelo(resposta(chamada("consultar_pedidos", quais="ABERTOS")), resposta(texto="ok"))
            IA._RITMO.clear()
            self.tela(login).dizer("quais pedidos estão abertos?")
            self.assertEqual(len(json.loads(self.m.pedidos[1]["corpo"]["messages"][-1]["content"])["pedidos"]), visto, login)
        # o orçamento é só de quem lança apropriação
        self.modelo(resposta(chamada("consultar_orcamento", busca="tapume")), resposta(texto="ok"))
        self.tela("sup1").dizer("quanto tem de tapume no orçamento?")
        self.assertIn("erro", json.loads(self.m.pedidos[1]["corpo"]["messages"][-1]["content"]))

    def test_acao_fora_do_escopo_nao_abre_rascunho_e_explica_onde_se_faz(self):
        """“Quero dar o OK nos trechos” é o OK interno, não apropriação: mesmo que o modelo tente o rascunho, o código não
        abre rascunho vazio e manda consultar o guia; a resposta leva à tela certa, com um botão só."""
        self.modelo(resposta(chamada("rascunho_apropriacao", item="TR confeccionados")),
                    resposta(chamada("consultar_ajuda", assunto="dar OK ou liberar trecho para a fiscalização")),
                    resposta(texto="O OK interno é dado na ficha do trecho, no Mapa iluminado."))
        t = self.tela("eng1")
        r = t.dizer("eu quero dar o ok em TR confeccionados, pra liberá-los pra fiscalização")
        self.assertIsNone(t.rascunho)
        self.assertEqual(r["resposta"], "O OK interno é dado na ficha do trecho, no Mapa iluminado.")
        self.assertEqual(t.botoes, [{"rotulo": "Abrir Mapa iluminado", "tela": "iluminado"}])
        recusa_, guia = [json.loads(m["content"]) for m in self.m.pedidos[2]["corpo"]["messages"] if m["role"] == "tool"]
        self.assertIn("isso não é apropriação: use consultar_ajuda", recusa_["erro"])
        self.assertEqual(guia["ajuda"][0]["titulo"], "OK interno (liberar o trecho para a medição)")
        self.assertIn("O OK é um toque da pessoa, trecho a trecho, não do assistente", guia["ajuda"][0]["texto"])
        self.assertEqual(self.um("SELECT COUNT(*) FROM apropriacoes"), (0,))
        # o rascunho que já existia não é mexido por uma tentativa vazia de outro assunto
        t.atalho("PEDIDO")
        self.modelo(resposta(chamada("rascunho_apropriacao", item="coisa que não existe")), resposta(texto="Qual serviço?"))
        t.dizer("outra coisa")
        self.assertEqual(t.rascunho["tipo"], "PEDIDO")

    def test_duvida_de_uso_consulta_o_guia_e_oferece_a_tela_que_o_perfil_abre(self):
        self.modelo(resposta(chamada("consultar_ajuda", assunto="dar entrada em nota fiscal")), resposta(texto="A nota sobe em Compras › Notas fiscais."))
        t = self.tela("almox1")
        r = t.dizer("onde dou entrada numa nota fiscal?")
        self.assertEqual(r["resposta"], "A nota sobe em Compras › Notas fiscais.")
        self.assertIn({"rotulo": "Abrir Notas fiscais", "tela": "compras/notas"}, t.botoes)
        self.assertIsNone(t.rascunho)
        self.modelo(resposta(chamada("consultar_ajuda", assunto="nota fiscal")), resposta(texto="Quem cuida disso é o almoxarifado."))
        s = self.tela("rh1")
        s.dizer("onde dou entrada numa nota fiscal?")
        self.assertEqual(s.botoes, [])                               # o RH não abre Compras: sem botão para lá
        self.assertFalse(json.loads(self.m.pedidos[1]["corpo"]["messages"][-1]["content"])["ajuda"][0]["este_login_abre_a_tela"])


class TestCotaEChave(BaseAssistente):
    def test_cota_excedida_avisa_guarda_o_rascunho_e_o_formulario_segue(self):
        t = self.tela("eng1")
        t.atalho("APROPRIACAO")
        t.editar("item", "5.1.1")
        self.modelo(recusa("tokens", "9"))
        r = t.dizer("foram quatro")
        self.assertEqual((r["situacao"], r["cota"]), ("COTA", {"tipo": "tokens", "janela": "minuto", "espera_s": 9}))
        self.assertIn("limite gratuito", r["aviso"])
        self.assertIn("formulário", r["aviso"])
        self.assertNotIn("Upgrade", json.dumps(r))                  # a propaganda do plano pago não chega à tela
        self.assertEqual(r["rascunho"]["campos"]["item_ref"], t.rascunho["campos"]["item_ref"])
        self.assertEqual(len(self.m.pedidos), 1)                    # sem segunda tentativa em outro lugar
        t.editar("fator.CONTAGEM", "4")                             # sem a IA, o rascunho segue pelo formulário
        self.assertTrue(t.rascunho["pronto"])
        self.assertEqual(t.gravar()[0], 200)

    def test_cota_do_dia_e_espera_curta(self):
        # o teto diário de tokens (200 mil no plano gratuito) não aparece nos cabeçalhos: vem só na mensagem do 429
        self.modelo(recusa("tokens", "619", "tokens per day (TPD): Limit 200000"))
        r = self.tela("eng1").dizer("oi")
        self.assertEqual((r["situacao"], r["cota"]), ("COTA", {"tipo": "tokens", "janela": "dia", "espera_s": 619}))
        self.assertIn("cota gratuita de hoje da IA acabou", r["aviso"])
        self.assertIn("cerca de 11 minutos", r["aviso"])
        self.modelo(recusa("requests", "30000", "requests per day (RPD): Limit 1000"))
        IA._RITMO.clear()
        r = self.tela("adm").dizer("oi")
        self.assertEqual((r["cota"]["tipo"], r["cota"]["janela"]), ("requests", "dia"))
        self.assertNotIn("minutos", r["aviso"])
        # espera curta (até espera_maxima_s): o servidor aguarda e tenta de novo uma vez, no mesmo serviço
        self.modelo(recusa("tokens", "1"), resposta(texto="Oi!"))
        IA._RITMO.clear()
        r = self.tela("eng2").dizer("oi")
        self.assertEqual((r["situacao"], r["resposta"], self.dormiu), ("OK", "Oi!", [1.3]))
        self.assertEqual({p["url"] for p in self.m.pedidos}, {"https://api.groq.com/openai/v1/chat/completions"})

    def test_chamada_de_funcao_invalida_do_modelo_termina_em_texto(self):
        invalida = (400, {}, {"error": {"message": "Tool call validation failed", "type": "invalid_request_error", "code": "tool_use_failed"}})
        self.modelo(invalida, invalida, resposta(texto="Este perfil não pede material: fale com o almoxarifado."))
        r = self.tela("rh1").dizer("queria pedir 10 tubos")
        self.assertEqual((r["situacao"], r["resposta"]), ("OK", "Este perfil não pede material: fale com o almoxarifado."))
        self.assertEqual([p["corpo"]["tool_choice"] for p in self.m.pedidos], ["auto", "auto", "none"])

    def test_modelo_e_endereco_configuraveis_e_freio_por_login(self):
        cfg = IA.config()
        self.assertEqual((cfg["modelo"], cfg["base_url"]), ("openai/gpt-oss-20b", "https://api.groq.com/openai/v1"))
        os.environ["MC_IA_MODELO"] = "outro/modelo"
        try:
            self.modelo(resposta(texto="ok"))
            self.tela("eng1").dizer("oi")
            self.assertEqual(self.m.pedidos[0]["corpo"]["model"], "outro/modelo")
        finally:
            del os.environ["MC_IA_MODELO"]
        self.modelo(*[resposta(texto="ok")] * 20)
        t = self.tela("eng2")
        limite = cfg["mensagens_por_minuto"]
        situacoes = [t.dizer(f"oi {i}")["situacao"] for i in range(limite + 1)]
        self.assertEqual(situacoes, ["OK"] * limite + ["COTA"])
        self.assertEqual(t.ultima["cota"]["tipo"], "ritmo")
        self.assertEqual(len(self.m.pedidos), limite)

    def test_sem_chave_a_tela_avisa_e_os_atalhos_funcionam(self):
        del os.environ["GROQ_API_KEY"]
        t = self.tela("eng1")
        self.assertEqual(t.req("/api/assistente")[1]["disponivel"], False)
        r = t.dizer("lança dois contêineres")
        self.assertEqual(r["situacao"], "INDISPONIVEL")
        self.assertEqual(self.m.pedidos, [])
        t.atalho("PEDIDO")
        self.assertEqual(t.rascunho["tipo"], "PEDIDO")
        # a chave também pode vir do segredos.env da pasta do programa (fora do Git)
        with open(os.environ["MC_SEGREDOS"], "w", encoding="utf-8") as f:
            f.write("# chave gratuita da Groq\nGROQ_API_KEY='gsk_do_arquivo'\n")
        self.assertEqual(IA.chave(), "gsk_do_arquivo")
        self.assertTrue(t.req("/api/assistente")[1]["disponivel"])

    def test_a_chave_so_vai_no_cabecalho_e_a_conversa_fica_na_auditoria(self):
        self.modelo(resposta(chamada("consultar_ajuda", assunto="estoque")), resposta(texto="O saldo fica em Almoxarifado › Estoque."))
        t = self.tela("almox1")
        r = t.dizer("onde vejo o saldo?")
        self.assertEqual(self.m.pedidos[0]["cabecalhos"]["Authorization"], "Bearer " + CHAVE)
        self.assertNotIn(CHAVE, json.dumps(self.m.pedidos[0]["corpo"]) + json.dumps(r) + json.dumps(t.req("/api/assistente")[1]))
        linha = self.um("SELECT login,status,resultado,corpo FROM auditoria WHERE rota='/api/assistente/mensagem' ORDER BY id DESC LIMIT 1")
        self.assertEqual(linha[:2], ("almox1", 200))
        self.assertIn("2 chamada(s), 2600 tokens; consultar_ajuda", linha[2])
        self.assertEqual(json.loads(linha[3]), {"texto": "onde vejo o saldo?"})
        self.assertFalse(self.c.execute("SELECT 1 FROM auditoria WHERE corpo LIKE ? OR resultado LIKE ?", (f"%{CHAVE}%",) * 2).fetchone())
        # dados pessoais do usuário não vão para o serviço: só o perfil
        self.assertNotIn("ALMOX1", self.m.sistema().upper().replace("PERFIL DE QUEM FALA: ALMOXARIFADO", ""))

    def test_erro_do_servico_o_motivo_vai_para_o_historico_e_nao_para_a_tela(self):
        recusado = (400, {}, {"error": {"message": "Organization `org_abc123` has been restricted. Need more tokens? Upgrade at https://x",
                                        "type": "invalid_request_error", "code": "organization_restricted"}})
        self.modelo(recusado)
        t = self.tela("eng1")
        r = t.dizer("oi")
        self.assertEqual((r["situacao"], r["aviso"]), ("INDISPONIVEL", "O serviço da IA respondeu com erro (400)."))
        self.assertNotIn("motivo", r["uso"])
        self.assertNotIn("organization_restricted", json.dumps(r))
        resultado = self.um("SELECT resultado FROM auditoria WHERE rota='/api/assistente/mensagem' ORDER BY id DESC LIMIT 1")[0]
        self.assertIn("HTTP 400 · organization_restricted: Organization `org_***` has been restricted.", resultado)
        self.assertNotIn("Upgrade", resultado)
        self.assertNotIn("org_abc123", resultado)
        # resposta que não é da API (página de erro da borda do serviço, como quando o cabeçalho da chave vai inválido)
        self.assertEqual(IA._motivo(400, {"nao_json": "400 Bad Request cloudflare"}),
                         "HTTP 400 · a resposta não veio da API, e sim da borda do serviço: 400 Bad Request cloudflare")

    def test_chave_colada_com_caracteres_invisiveis(self):
        del os.environ["GROQ_API_KEY"]
        with open(os.environ["MC_SEGREDOS"], "w", encoding="utf-8", newline="") as f:
            f.write("GROQ_API_KEY=\x1b[200~gsk_abcDEF123\x1b[201~\r\n")       # marcas de colagem do terminal e fim de linha do Windows
        self.assertEqual(IA.chave(), "gsk_abcDEF123")
        tamanho, problemas = IA.forma_da_chave()
        self.assertEqual(tamanho, 13)
        self.assertEqual(len(problemas), 1)
        self.assertIn("invisível", problemas[0])
        self.modelo(resposta(texto="ok"))
        self.tela("eng1").dizer("oi")
        self.assertEqual(self.m.pedidos[0]["cabecalhos"]["Authorization"], "Bearer gsk_abcDEF123")
        os.environ["GROQ_API_KEY"] = "sk-outra coisa gsk_a gsk_b"
        self.assertEqual(IA.forma_da_chave()[1], ["vieram 3 caractere(s) invisível(is) ou espaço(s) junto com ela (foram ignorados)",
                                                  "não começa com gsk_, como as chaves da Groq", "parece ter sido colada mais de uma vez"])

    def test_rota_exige_sessao_e_cabecalho_da_aplicacao(self):
        import urllib.error
        import urllib.request
        for cab, esperado in (({"X-MC": "1"}, 401), ({}, 403)):
            req = urllib.request.Request(self.url + "/api/assistente/mensagem", data=b'{"texto":"oi"}', method="POST",
                                         headers={"Content-Type": "application/json", **cab})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10)
            self.assertEqual(e.exception.code, esperado)
        self.assertEqual(self.m.pedidos, [])


class TestHistoricoEConhecimento(BaseAssistente):
    def test_historico_quase_zero(self):
        """D-225: vão ao modelo só a mensagem atual e, se houver, a última pergunta da IA sem resposta. O que a tela antiga
        mandava como conversa é ignorado; o rascunho e as opções vão nas instruções."""
        self.modelo(resposta(texto="Qual serviço?"), resposta(chamada("rascunho_apropriacao", item="tapume")),
                    resposta(texto="Oi!"))
        t = self.tela("eng1")
        r = t.dizer("quero lançar um serviço")
        self.assertEqual(r["pergunta"], "Qual serviço?")
        self.assertEqual([m["role"] for m in self.m.pedidos[0]["corpo"]["messages"]], ["system", "user"])
        t.dizer("tapume")
        self.assertEqual([(m["role"], m["content"]) for m in self.m.pedidos[1]["corpo"]["messages"][1:]],
                         [("assistant", "Qual serviço?"), ("user", "tapume")])
        self.assertTrue(t.linhas()["Item"].startswith("5.1.2"))
        self.assertIsNone(t.pergunta and None)
        # a conversa velha, se vier, não vai ao modelo; e sem pergunta pendente vai só a mensagem
        st, r = t.req("/api/assistente/mensagem", {"texto": "oi", "rascunho": None, "pergunta": None,
                                                   "conversa": [{"de": "u", "texto": "SEGREDO_DA_CONVERSA_ANTIGA"}]})
        self.assertEqual(st, 200, r)
        enviado = json.dumps(self.m.pedidos[2]["corpo"], ensure_ascii=False)
        self.assertNotIn("SEGREDO_DA_CONVERSA_ANTIGA", enviado)
        self.assertEqual([m["role"] for m in self.m.pedidos[2]["corpo"]["messages"]], ["system", "user"])
        self.assertIsNone(r["pergunta"])                                       # "Oi!" não é pergunta

    def test_funcoes_mudam_com_o_rascunho_aberto(self):
        eng = self.tela("eng1").usuario
        sem = {f["function"]["name"] for f in IA.ferramentas_do_login(eng)}
        com = {f["function"]["name"] for f in IA.ferramentas_do_login(eng, {"tipo": "APROPRIACAO", "campos": {}})}
        self.assertIn("consultar_catalogo", sem)
        self.assertNotIn("consultar_catalogo", com)                            # consulta de outro tipo sai
        self.assertIn("rascunho_pedido", com)                                  # a troca de assunto continua possível
        self.assertIn("descartar_rascunho", com)
        self.assertNotIn("descartar_rascunho", sem)
        self.assertNotIn("oferecer_opcoes", com)                               # no rascunho, os botões vêm do código

    def test_conhecimento_por_secao(self):
        secoes = IA.conhecimento()
        self.assertGreaterEqual(len(secoes), 20)
        for sec in secoes:                                                     # toda seção com tela diz quem a abre
            self.assertTrue(not sec["tela"] or sec["telas_perfil"], sec["titulo"])
            self.assertLess(len(sec["texto"]), 1100, sec["titulo"])            # curta: é ela que vai ao modelo
        cfg = IA.config()
        u = self.tela("eng1").usuario
        for pergunta, titulo in (("eu quero dar o ok em TR confecionados, pra liberalos pra fiscalização", "OK interno"),
                                 ("dar OK em TR", "OK interno"), ("onde dou entrada numa nota fiscal", "Notas fiscais"),
                                 ("choveu de tarde", "Registrar chuva"), ("o que é MND", "Glossário"),
                                 ("como verifico um trecho executado", "Verificar")):
            achadas = IA.ajuda(cfg, u, pergunta)
            self.assertTrue(achadas and achadas[0]["titulo"].startswith(titulo), (pergunta, [a["titulo"] for a in achadas]))
        self.assertEqual(IA.ajuda(cfg, u, "receita de bolo de cenoura"), [])
        with open(IA.arquivo_conhecimento(), encoding="utf-8") as f:
            bruto = f.read()
        for proibido in ("drive.google.com", "docs.google.com", "@gmail", "@ankara"):     # arquivo público e enviado ao serviço
            self.assertNotIn(proibido, bruto.lower())

    def test_ok_interno_no_conhecimento_segue_a_regra_do_servidor(self):
        """O guia não pode exigir o que o servidor não exige: o OK interno não depende do cadastro de campo."""
        import inspect
        import regras as R
        import servicos as S
        ok = next(s for s in IA.conhecimento() if s["titulo"].startswith("OK interno"))
        self.assertIn("O cadastro de campo não é exigido para o OK", ok["texto"])
        for frase in ("execução 100 %", "verificados pelo supervisor", "fotos obrigatórias", "avanço antigo sem posição"):
            self.assertIn(frase, ok["texto"])
        regra = inspect.getsource(S.ok_fiscalizacao) + inspect.getsource(R.validar_ok_fiscal)
        self.assertNotIn("CADASTRO_CAMPO", regra)                              # se mudar no servidor, mude o guia
        self.assertIn("sem_verificacao", regra)
        self.assertIn("fotos_faltando", regra)
        self.assertIn("_exigir_sem_legado", regra)

    def test_consultar_trecho(self):
        u = self.tela("eng1").usuario
        r = IA.situacao_trecho(self.srv_conn, u, "Zona 03 PB08 TR020")
        self.assertEqual(r["trecho"], "Zona 03 · PB08 · TR020")
        self.assertFalse(r["pronto_para_ok"])
        self.assertTrue(any(f.startswith("Executado 100 %") for f in r["falta"]), r)
        self.assertEqual(r["lembrete"], "o OK interno não exige o cadastro de campo")
        sem_numero = IA.situacao_trecho(self.srv_conn, u, "TR confeccionados", "quero dar o ok nos trechos")
        self.assertTrue(sem_numero["ajuda"][0]["titulo"].startswith("OK interno"))
        self.assertIn("Peça o nome", IA.situacao_trecho(self.srv_conn, u, "TR999 da zona 99")["erro"])

    def test_medida_com_unidade_escrita(self):
        t = self.tela("eng1")
        t.atalho("APROPRIACAO")
        turno = IA._Turno(IA.normalizar(self.srv_conn, t.usuario, {"tipo": "APROPRIACAO", "campos": {}}))
        IA.aplicar_campos(self.srv_conn, t.usuario, turno, "APROPRIACAO", {"item": "5.1.2", "medidas": [{"comprimento": "4m", "largura": "2,5 m"}]})
        v = IA.vista(self.srv_conn, t.usuario, turno.rascunho)
        self.assertIn("Q = 4 × 2,5 = 10 m²", dict(v["linhas"])["Memória de cálculo"])


class TestRegrasPuras(unittest.TestCase):
    OPCOES = ["id 1.1_6.1.1 = LOCAÇÃO CONTAINER ESCRITÓRIO C/ 01 SANITÁRIO", "id 1.1_6.1.2 = LOCAÇÃO CONTAINER ESCRITÓRIO S/ SANITÁRIO",
              "id 1.1_6.1.3 = LOCAÇÃO CONTAINER SANITÁRIO"]

    def test_opcao_mais_proxima_so_quando_ganha_com_folga(self):
        self.assertEqual(IA.mais_proxima("sanitário por um mês", self.OPCOES), self.OPCOES[2])
        for texto in ("escritório com sanitário", "o segundo", "escritório", ""):
            self.assertIsNone(IA.mais_proxima(texto, self.OPCOES), texto)

    def test_plural_papel_data_e_numero(self):
        self.assertEqual([IA._plural(n, v) for n, v in (("contêineres", 1), ("contêiner", 3), ("mês", 2), ("meses", 1), ("hora", 2))],
                         ["contêiner", "contêineres", "meses", "mês", "horas"])
        self.assertEqual([IA._papel(n) for n in ("mês", "contêineres", "horas", "km", "altura", "metros", "metros cúbicos")],
                         ["MES", "CONTAGEM", "HORA", "KM", "LARGURA", "COMPRIMENTO", "VOLUME"])
        hoje = RL.hoje()
        self.assertEqual(IA._data("ontem", hoje), (hoje - timedelta(days=1)).isoformat())
        self.assertEqual(IA._data("05/11/2026", hoje), "2026-11-05")
        self.assertIsNone(IA._data("31/02/2026", hoje))
        self.assertEqual([IA._numero(v) for v in ("2,5", "1.234,5", 3, "abc", -1, True, None)], [2.5, 1234.5, 3.0, None, None, None, None])
        self.assertEqual([IA._segundos(t) for t in ("9", "8.93", "2m52.8s", "1h2m3s", "")], [9.0, 8.93, 172.8, 3723.0, None])

    def test_configuracao_sem_segredo_e_arquivos_da_tela(self):
        raiz = os.path.dirname(AQUI)
        with open(os.path.join(raiz, "config", "assistente.json"), encoding="utf-8") as f:
            bruto = f.read()
        self.assertNotIn("gsk_", bruto)
        cfg = json.loads(bruto)
        self.assertEqual(cfg["base_url"], "https://api.groq.com/openai/v1")
        self.assertNotIn("ajuda", cfg)                               # o guia mudou para docs/CONHECIMENTO_IA.md (D-225)
        with open(os.path.join(raiz, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("segredos.env", f.read())
        with open(os.path.join(raiz, "web", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('<h1>O que você quer fazer?</h1>', html)
        self.assertIn('data-tela="assistente"', html)
        self.assertIn('<script src="/apropriacao.js"></script>\n<script src="/assistente.js"></script>', html)
        with open(os.path.join(raiz, "web", "assistente.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("api(v.rota, corpo)", js)                      # o toque grava pela rota de sempre (X-MC, X-Idem)
        self.assertNotIn("groq", js.lower())                         # a tela não fala com o serviço nem conhece a chave
        self.assertNotIn("localStorage.setItem(iaChave(), JSON.stringify({ conversa", js)   # a conversa não é guardada (D-225)
        self.assertIn("pergunta: IA.pergunta", js)
        self.assertNotIn("conversa:", js.split("/api/assistente/mensagem")[1].split("\n")[0])
        # o tamanho das funções enviadas a cada chamada é o que mais pesa nos 8.000 tokens por minuto
        todas = {"permissoes": ["apropriacao", "compras_solicitar", "campo"], "telas": ["solicitar", "compras"]}
        self.assertLess(len(json.dumps(IA.ferramentas_do_login(todas), ensure_ascii=False)), 4600)          # no #39: 4.953 para todos
        self.assertLess(len(json.dumps(IA.ferramentas_do_login(todas, {"tipo": "APROPRIACAO"}), ensure_ascii=False)), 3700)
        self.assertLess(len(json.dumps(IA.ferramentas_do_login({"permissoes": [], "telas": ["iluminado"]}), ensure_ascii=False)), 1500)


if __name__ == "__main__":
    unittest.main()
