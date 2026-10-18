"""Servidor local (privado) do Sistema Morro da Cruz — só biblioteca padrão + openpyxl.

Uso:  python server.py [--porta 8765] [--db dados/morro_da_cruz.db] [--host 127.0.0.1]
Abra http://127.0.0.1:8765
"""
import argparse
import json
import logging
import logging.handlers
import mimetypes
import os
import signal
import sys
import threading
from http.cookies import SimpleCookie
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import acesso as A
import caminhos
import backup
import compras as C
import medicao as M
import planejamento as P
import relatorios as RL
import exportar
import link
import regras as R
import servicos as S

BASE = caminhos.PASTA
WEB = os.path.join(caminhos.RECURSOS, "web")
LOCK = threading.Lock()
CONN = None
DB_PATH = S.DB_PADRAO
DEMONSTRACAO = False                  # banco de demonstração (dados_demo/): a interface mostra a faixa de aviso
LINK = False                          # link para a equipe (túnel), ligado pelo programa do escritório (iniciar.py)
PORTA = 8765
DIR_FOTOS = S.DIR_FOTOS                 # sempre <pasta do banco>/fotos (é o que o backup copia e confere)
COOKIE = "mc_sessao"
COOKIE_SEGURO = False                   # True só atrás de HTTPS (decisão D-60); em 127.0.0.1 é HTTP
LOG = logging.getLogger("morro_da_cruz.servidor")
LOG.addHandler(logging.NullHandler())


def _cfg():
    with open(os.path.join(BASE, "config", "fontes.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ rotas
def r_resumo(q, c):
    """Totais da obra ou de uma frente (?frente=Zona01 … ADUTORA, CH)."""
    fr = q.get("frente") or None
    one = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    ft = " AND frente_id=?" if fr else ""
    fa = (fr,) if fr else ()
    ultima = c.execute("SELECT id, concluida_em, status FROM importacoes WHERE modo='APLICACAO' ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "contrato": S.contrato(c),
        "obra": _cfg()["obra"],
        "frente": fr,
        "frentes": R.FRENTES,
        "valor_contrato": float(S.parametro(c, "valor_contrato", 0)),
        "p0_bm": float(S.parametro(c, "p0_bm", 0)),
        "trechos": one("SELECT COUNT(*) FROM trechos WHERE vigente=1" + ft, *fa),
        "extensao_m": one("SELECT ROUND(COALESCE(SUM(extensao_m),0),2) FROM trechos WHERE vigente=1" + ft, *fa),
        "elementos": one("SELECT COUNT(DISTINCT elemento_id) FROM atividades WHERE vigente=1" + ft, *fa) if fr
        else one("SELECT COUNT(*) FROM elementos WHERE vigente=1"),
        "atividades": one("SELECT COUNT(*) FROM atividades WHERE vigente=1" + ft, *fa),
        "itens_pendentes": one("""SELECT COUNT(*) FROM itens_projeto i JOIN atividades a ON a.id=i.atividade_id
                                  WHERE i.vigente=1 AND (i.quantidade IS NULL OR i.unidade IS NULL)""" + (" AND a.frente_id=?" if fr else ""), *fa),
        "executado_m": one("""SELECT ROUND(COALESCE(SUM(e.metros_reaterrados),0),2) FROM execucao e JOIN trechos t ON t.id=e.alvo_id
                              WHERE e.alvo_tipo='TRECHO' AND t.vigente=1""" + (" AND t.frente_id=?" if fr else ""), *fa),
        "ok_fiscal": one("""SELECT COUNT(*) FROM execucao e LEFT JOIN trechos t ON e.alvo_tipo='TRECHO' AND t.id=e.alvo_id
                            LEFT JOIN atividades a ON e.alvo_tipo='ATIVIDADE' AND a.id=e.alvo_id
                            WHERE e.ok_fiscal_em IS NOT NULL""" + (" AND COALESCE(t.frente_id, a.frente_id)=?" if fr else ""), *fa),
        "medicao_oficial_liberada": S.medicao_oficial_liberada(c),
        "ultima_importacao": dict(ultima) if ultima else None,
        "mapa_disponivel": os.path.exists(_mapa_path()),
        "equipes": [dict(r) for r in c.execute("SELECT * FROM equipes")],
        "clima": R.CONDICOES_CLIMA,
        "contingencias": R.CONTINGENCIAS,
        "etapas": R.ETAPAS,
        "checklist_conferencia": R.CHECKLIST_CONFERENCIA_CADASTRO,
        "categorias_ocorrencia": S.CATEGORIAS_OCORRENCIA,
        "perfis": {k: {"nome": v["nome"]} for k, v in A.carregar_perfis()["perfis"].items()},
        "servicos_programacao": P.SERVICOS,
    }


def r_buscar(q, c):
    return S.buscar(c, q.get("q", ""))


def r_detalhe(q, c):
    d = S.detalhe(c, q["tipo"], q["id"])
    d["programacoes"] = [dict(r) for r in c.execute(
        "SELECT * FROM programacoes WHERE alvo_tipo=? AND alvo_id=? ORDER BY data DESC, id DESC LIMIT 15", (d["alvo_tipo"], d["id"]))]
    return d


def r_previsto(q, c):
    return S.previsto(c, q["tipo"], q["id"], float(q.get("metros") or 0))


def r_mapa_estado(q, c):
    med = q.get("medicao")
    out = S.estado_mapa(c, int(med) if med else None, q.get("data"))
    out["camadas"] = P.camadas_mapa(c, q.get("data"))
    return out


# ------------------------------------------------------------------ planejamento (módulo D)
def r_programacoes(q, c):
    ini, fim = q.get("ini") or date.today().isoformat(), q.get("fim") or date.today().isoformat()
    return {"programacoes": P.programacoes(c, ini, fim, q.get("frente"), q.get("equipe")),
            "resumo": P.resumo(c, ini, fim, q.get("frente"), q.get("equipe")),
            "faltantes": P.faltantes(c, ini, fim, q.get("frente"))}


def p_programacao(b, c):
    return {"id": P.programar(c, b.get("data"), b.get("equipe_id"), b.get("alvo_tipo"), b.get("alvo_id"), b.get("servico"), b["por"],
                              b.get("ini_m"), b.get("fim_m"), b.get("materiais") or [], b.get("obs"))}


def p_programacao_encerrar(b, c):
    P.encerrar(c, int(b["programacao_id"]), b.get("status"), b.get("motivo"), b["por"])
    return {"ok": True}


def r_equipe(q, c):
    eid = q["id"]
    return {"funcionarios": [dict(r) for r in c.execute("SELECT * FROM funcionarios WHERE equipe_id=? ORDER BY nome", (eid,))],
            "maquinas": [dict(r) for r in c.execute("SELECT * FROM maquinas WHERE equipe_id=? ORDER BY descricao", (eid,))]}


def p_funcionario(b, c):
    return {"id": c.execute("INSERT INTO funcionarios(nome,funcao,equipe_id) VALUES (?,?,?)",
                            (b["nome"], b.get("funcao"), b["equipe_id"])).lastrowid}


def p_maquina(b, c):
    return {"id": c.execute("INSERT INTO maquinas(descricao,equipe_id) VALUES (?,?)", (b["descricao"], b["equipe_id"])).lastrowid}


def r_estoque(q, c):
    return S.estoque(c)


def r_compat(q, c):
    return S.compatibilizacao_caesb(c)


def p_movimento(b, c):
    S.entrada_material(c, b["data"], b["material_id"], float(b["quantidade"]), b["tipo"], b.get("documento"),
                       b.get("responsavel"), b.get("autorizacao"))
    return {"ok": True}


def r_movimentos(q, c):
    return S.movimentos(c, int(q.get("limite", 100)), q.get("material_id"))


def p_estorno(b, c):
    S.estornar(c, int(b["movimento_id"]), b.get("motivo"), b.get("responsavel"), bool(b.get("ajustar_reservas")))
    return {"ok": True}


def p_retificar(b, c):
    return {"id": S.retificar_fechamento(c, int(b["movimento_id"]), b.get("destino") or {}, b.get("motivo"),
                                         b.get("responsavel"), bool(b.get("ajustar_reservas")))}


def r_reservas(q, c):
    return S.reservas_ativas(c, q.get("data"))


def p_reserva(b, c):
    return {"id": S.reservar(c, b["data"], b["equipe_id"], b["material_id"], float(b["quantidade"]), b.get("alvo_tipo"),
                             b.get("alvo_id"), b.get("responsavel"))}


def p_reserva_cancelar(b, c):
    S.cancelar_reserva(c, int(b["reserva_id"]), b.get("motivo"))
    return {"ok": True}


def r_consumo(q, c):
    return S.consumo_previsto_x_confirmado(c)


def r_nfs(q, c):
    """Notas registradas diretamente antes da v11 (o fluxo novo está em /api/compras)."""
    out = [dict(r) for r in c.execute("SELECT * FROM notas_fiscais WHERE origem='DIRETA' ORDER BY id DESC")]
    for n in out:
        n["itens"] = [dict(r) for r in c.execute("SELECT * FROM nf_itens WHERE nf_id=?", (n["id"],))]
    return out


def p_nf_aceitar(b, c):
    S.aceitar_nf(c, int(b["nf_id"]), b.get("laudo_arquivo"))
    return {"ok": True}


def r_checkins(q, c):
    return S.checkins_abertos(c, q.get("data"))


def p_checkin(b, c):
    return {"id": S.checkin(c, b["data"], b["equipe_id"], b.get("alvo_tipo"), b.get("alvo_id"), b.get("funcionarios", []),
                            b.get("maquinas", []), b.get("materiais", []), b.get("contingencia"))}


def p_checkout(b, c):
    S.checkout(c, int(b["checkin_id"]), b["itens"])
    return {"ok": True}


def r_histograma(q, c):
    return S.histograma(c, q["ini"], q["fim"])


def p_clima(b, c):
    for turno in ("MANHA", "TARDE"):
        if b.get(turno):
            S.registrar_clima(c, b["data"], b["equipe_id"], turno, b[turno])
    return {"ok": True}


def p_apontamento(b, c):
    return {"id": S.apontar(c, b["data"], b["equipe_id"], b["alvo_tipo"], b["alvo_id"], float(b.get("metros_executados") or 0),
                            float(b.get("metros_reaterrados") or 0), bool(b.get("concluido_100")), b.get("estaca_ini"),
                            b.get("estaca_fim"), b.get("quantidades"), b.get("intervalos") or None, b.get("informado_por"))}


def p_legado_conciliar(b, c):
    return {"id": S.conciliar_legado(c, b["trecho_id"], b.get("intervalos") or [], b.get("motivo"), b.get("responsavel"))}


def p_intervalos_retificar(b, c):
    """Retificação de intervalos; com "simular": true devolve a prévia (antes × depois) sem gravar."""
    return S.retificar_intervalos(c, b.get("ref_tipo"), int(b["ref_id"]), b.get("intervalos") or [], b.get("motivo"),
                                  b.get("responsavel"), b.get("data") or None, b.get("quantidades"), bool(b.get("simular")))


def p_intervalo_verificar(b, c):
    S.verificar_intervalo(c, int(b["intervalo_id"]), b.get("verificado_por"))
    return {"ok": True}


def p_solda(b, c):
    return {"id": S.registrar_soldas(c, b["data"], b.get("equipe_id"), b["alvo_tipo"], b["alvo_id"], b.get("tipo"),
                                     b.get("quantidade"), b.get("soldador"), b.get("informado_por"),
                                     float(b["posicao_m"]) if b.get("posicao_m") not in (None, "") else None,
                                     b.get("maquina"), b.get("obs"))}


def p_solda_verificar(b, c):
    S.verificar_soldas(c, int(b["solda_id"]), b.get("verificado_por"), b.get("resultado"), b.get("obs"))
    return {"ok": True}


def p_foto(b, c):
    return S.registrar_foto(c, b["alvo_tipo"], b["alvo_id"], b["categoria"], b["conteudo_b64"], None,
                            b.get("data_hora"), b.get("lat"), b.get("lon"), dir_fotos=DIR_FOTOS)


def p_ok_fiscal(b, c):
    return {"medicao_id": S.ok_fiscalizacao(c, b["alvo_tipo"], b["alvo_id"], b.get("usuario") or "Engenharia Ankara", b.get("data"))}


def p_recomposicao(b, c):
    S.recomposicao_ok(c, b["alvo_tipo"], b["alvo_id"], b["tipo"], float(b["quantidade"]), b.get("data"))
    return {"ok": True}


def r_esteira(q, c):
    return S.esteira(c)


def p_cadastro(b, c):
    S.avancar_cadastro(c, b["trecho_id"], b["destino"], b.get("dados") or {}, b.get("data"))
    return {"ok": True}


def p_cadastro_conferencia(b, c):
    return {"id": S.registrar_conferencia_cadastro(c, b["trecho_id"], b.get("resultado"), b.get("checklist") or {},
                                                   b.get("revisor"), b.get("obs"))}


def r_medicoes(q, c):
    return [dict(r) for r in c.execute("SELECT * FROM medicoes ORDER BY numero")]


def p_medicao(b, c):
    return {"id": S.criar_medicao(c, int(b["numero"]), b["periodo_ini"], b["periodo_fim"], b.get("tipo", "TESTE"))}


def r_medicao(q, c):
    mid = int(q["id"])
    return {**S.resumo_medicao(c, mid), **M.complementos(c, mid)}


def _periodo(q):
    hoje = date.today()
    return q.get("ini") or hoje.replace(day=1).isoformat(), q.get("fim") or hoje.isoformat()


def r_relatorios(q, c):
    ini, fim = _periodo(q)
    return RL.painel(c, ini, fim, q.get("frente") or None)


def r_medicao_elegibilidade(q, c):
    return M.elegibilidade(c, int(q["id"]))


def p_medicao_fechar(b, c):
    S.fechar_medicao(c, int(b.get("medicao_id") or b["id"]), b.get("por"))
    return {"ok": True}


def p_medicao_conferir(b, c):
    return {"id": M.conferir(c, int(b["medicao_id"]), b.get("resultado"), b.get("checklist") or {}, b.get("por"), b.get("obs"))}


# ------------------------------------------------------------------ campo complementar (módulo B)
def _etapa(etapa):
    def f(b, c):
        return {"id": S.registrar_etapa_complementar(c, b["trecho_id"], etapa, b.get("ini_m"), b.get("fim_m"), b.get("data"),
                                                     b.get("registrado_por"), b.get("referencia"), b.get("obs"))}
    return f


def p_etapa_anular(b, c):
    S.anular_etapa_complementar(c, int(b["registro_id"]), b.get("motivo"), b.get("por"))
    return {"ok": True}


def p_ocorrencia(b, c):
    return {"id": S.abrir_ocorrencia(c, b["alvo_tipo"], b["alvo_id"], b.get("tipo"), b.get("categoria"), b.get("descricao"),
                                     b.get("data"), b.get("aberta_por"), b.get("equipe_id"))}


def p_ocorrencia_resolver(b, c):
    S.resolver_ocorrencia(c, int(b["ocorrencia_id"]), b.get("resolucao"), b.get("por"))
    return {"ok": True}


def r_ocorrencias(q, c):
    ab = q.get("abertas")
    return S.ocorrencias(c, q.get("tipo"), q.get("id"), None if ab is None else ab == "1")


# ------------------------------------------------------------------ compras e recebimento (módulo C)
def _c(fn):
    return lambda b, c: {"id": fn(b, c)}


def r_compras(q, c):
    return C.painel(c)


def r_inventarios(q, c):
    return C.inventarios(c)


def r_reservas_vencidas(q, c):
    return C.reservas_vencidas(c, q.get("hoje") or date.today().isoformat())


ROTAS_COMPRAS = {
    "/api/fornecedor": ("compras_pedir", ("por",), _c(lambda b, c: C.cadastrar_fornecedor(c, b.get("cnpj"), b.get("nome"), b["por"], b.get("contato")))),
    "/api/solicitacao": ("compras_solicitar", ("solicitante",), _c(lambda b, c: C.abrir_solicitacao(
        c, b.get("data"), b.get("itens") or [], b.get("motivo"), b["solicitante"], b.get("alvo_tipo"), b.get("alvo_id")))),
    "/api/solicitacao/decidir": ("compras_aprovar", ("por",), lambda b, c: (C.decidir_solicitacao(
        c, int(b["solicitacao_id"]), bool(b.get("aprovar")), b.get("motivo"), b["por"]), {"ok": True})[1]),
    "/api/solicitacao/cancelar": ("compras_solicitar", ("por",), lambda b, c: (C.cancelar_solicitacao(
        c, int(b["solicitacao_id"]), b.get("motivo"), b["por"]), {"ok": True})[1]),
    "/api/pedido": ("compras_pedir", ("por",), _c(lambda b, c: C.emitir_pedido(
        c, b.get("numero"), b.get("data"), int(b["fornecedor_id"]), int(b["solicitacao_id"]), b.get("itens") or [], b["por"],
        b.get("prazo"), bool(b.get("faturamento_etapas"))))),
    "/api/pedido/cancelar": ("compras_pedir", ("por",), lambda b, c: (C.cancelar_pedido(c, int(b["pedido_id"]), b.get("motivo"), b["por"]), {"ok": True})[1]),
    "/api/pedido/encerrar": ("compras_pedir", ("por",), lambda b, c: (C.encerrar_pedido(c, int(b["pedido_id"]), b.get("motivo"), b["por"]), {"ok": True})[1]),
    "/api/nf/importar-xml": ("receber", ("por",), lambda b, c: C.importar_nfe_xml(c, b.get("conteudo_b64"), b.get("nome"), b["por"])),
    "/api/nf/digitar": ("receber", ("por",), _c(lambda b, c: C.registrar_nf_digitada(
        c, b.get("numero"), int(b.get("fornecedor_id") or 0), b.get("data_emissao"), b.get("linhas") or [], b["por"],
        b.get("documento_b64"), b.get("documento_tipo"), b.get("documento_nome"), b.get("serie"), b.get("chave"), b.get("valor_total")))),
    "/api/nf/conferir": ("receber", ("por",), lambda b, c: (C.conferir_nf(c, int(b["nf_id"]), int(b.get("pedido_id") or 0),
                                                                           b.get("linhas") or [], b["por"]), {"ok": True})[1]),
    "/api/nf/cancelar": ("receber", ("por",), lambda b, c: (C.cancelar_nf(c, int(b["nf_id"]), b.get("motivo"), b["por"]), {"ok": True})[1]),
    "/api/recebimento": ("receber", ("por",), _c(lambda b, c: C.receber(c, int(b["nf_id"]), b.get("data"), b.get("itens") or [], b["por"],
                                                                       b.get("documento")))),
    "/api/inspecao": ("receber", ("por",), _c(lambda b, c: C.inspecionar(
        c, int(b["recebimento_item_id"]), b.get("aceito"), b.get("recusado"), b.get("laudo"), b["por"], b.get("data"),
        b.get("motivo_recusa"), b.get("documento_b64"), b.get("documento_nome")))),
    "/api/devolucao-fornecedor": ("receber", ("por",), _c(lambda b, c: C.devolver_ao_fornecedor(
        c, int(b["nf_item_id"]), b.get("data"), b.get("quantidade"), b.get("motivo"), b["por"], b.get("documento")))),
    "/api/transferencia": ("almox", ("por",), _c(lambda b, c: C.transferir(
        c, b.get("data"), b.get("material_id"), b.get("quantidade"), b.get("de_equipe"), b.get("para_equipe"), b.get("autorizacao"),
        b["por"], b.get("motivo")))),
    "/api/inventario/contagem": ("inventario_contar", ("por",), _c(lambda b, c: C.registrar_contagem(
        c, b.get("data"), b.get("itens") or [], b["por"], b.get("obs")))),
    "/api/inventario/decidir": ("inventario_ajustar", ("por",), lambda b, c: (C.decidir_inventario(
        c, int(b["inventario_id"]), bool(b.get("aprovar")), b.get("motivo"), b["por"]), {"ok": True})[1]),
    "/api/reservas/liberar-vencidas": ("almox", ("por",), lambda b, c: {"liberadas": C.liberar_reservas_vencidas(
        c, [int(x) for x in b.get("ids") or []], b.get("motivo"), b["por"], b.get("hoje") or date.today().isoformat())}),
}


# ------------------------------------------------------------------ acesso (módulo A)
def r_usuarios(q, c):
    return [A.publico(dict(r)) for r in c.execute("SELECT * FROM usuarios ORDER BY login")]


def p_usuarios(b, c, usuario):
    acao = b.get("acao")
    if acao == "criar":
        return {"id": A.criar_usuario(c, b.get("login"), b.get("nome"), b.get("perfil"), b.get("senha"), b.get("equipe_id") or None,
                                      usuario["login"])}
    if acao == "alterar":
        A.alterar_usuario(c, b.get("login"), usuario["login"], b.get("perfil"), b.get("ativo"), b.get("equipe_id"), b.get("nome"))
        return {"ok": True}
    if acao == "senha":
        A.redefinir_senha(c, b.get("login"), b.get("senha"))
        return {"ok": True}
    raise R.RegraViolada("Ação inválida (criar, alterar ou senha).")


def p_senha(b, c, usuario):
    A.trocar_senha(c, usuario["id"], b.get("senha_atual"), b.get("nova_senha"))
    return {"ok": True}


def r_auditoria(q, c, usuario):
    if not q.get("alvo_id"):                       # histórico completo só com a permissão de auditoria
        A.exigir(usuario, "auditoria")
    return A.consultar_auditoria(c, q.get("alvo_tipo"), q.get("alvo_id"), q.get("login"), int(q.get("limite", 100)))


GET = {"/api/resumo": r_resumo, "/api/buscar": r_buscar, "/api/detalhe": r_detalhe, "/api/previsto": r_previsto,
       "/api/mapa/estado": r_mapa_estado, "/api/equipe": r_equipe, "/api/estoque": r_estoque,
       "/api/compat-caesb": r_compat, "/api/nfs": r_nfs, "/api/checkins": r_checkins, "/api/histograma": r_histograma,
       "/api/esteira": r_esteira, "/api/medicoes": r_medicoes, "/api/medicao": r_medicao,
       "/api/movimentos": r_movimentos, "/api/reservas": r_reservas, "/api/consumo": r_consumo,
       "/api/ocorrencias": r_ocorrencias, "/api/compras": r_compras, "/api/inventarios": r_inventarios,
       "/api/reservas-vencidas": r_reservas_vencidas, "/api/programacoes": r_programacoes,
       "/api/medicao/elegibilidade": r_medicao_elegibilidade, "/api/relatorios": r_relatorios}
GET_PERM = {"/api/usuarios": (r_usuarios, "usuarios")}
GET_USUARIO = {"/api/auditoria": r_auditoria}       # recebem o usuário da sessão
POST = {"/api/funcionario": p_funcionario, "/api/maquina": p_maquina, "/api/movimento": p_movimento,
        "/api/nf/aceitar": p_nf_aceitar, "/api/checkin": p_checkin, "/api/checkout": p_checkout, "/api/clima": p_clima,
        "/api/apontamento": p_apontamento, "/api/foto": p_foto, "/api/ok-fiscal": p_ok_fiscal,
        "/api/recomposicao": p_recomposicao, "/api/cadastro": p_cadastro, "/api/medicao": p_medicao,
        "/api/medicao/fechar": p_medicao_fechar, "/api/estorno": p_estorno, "/api/retificar": p_retificar,
        "/api/intervalo/verificar": p_intervalo_verificar, "/api/legado/conciliar": p_legado_conciliar,
        "/api/intervalos/retificar": p_intervalos_retificar, "/api/cadastro/conferencia": p_cadastro_conferencia,
        "/api/solda": p_solda, "/api/solda/verificar": p_solda_verificar, "/api/reserva": p_reserva,
        "/api/reserva/cancelar": p_reserva_cancelar, "/api/liberacao": _etapa("LIBERACAO_TOPOGRAFICA"),
        "/api/escavacao": _etapa("ESCAVADO"), "/api/etapa-complementar/anular": p_etapa_anular,
        "/api/ocorrencia": p_ocorrencia, "/api/ocorrencia/resolver": p_ocorrencia_resolver}
POST.update({rota: fn for rota, (_, _, fn) in ROTAS_COMPRAS.items()})
POST.update({"/api/programacao": p_programacao, "/api/programacao/encerrar": p_programacao_encerrar,
             "/api/medicao/conferir": p_medicao_conferir})
POST_USUARIO = {"/api/usuarios": p_usuarios, "/api/senha": p_senha}
# permissão exigida por rota de gravação (config/perfis.json; None = basta estar logado)
PERMISSAO = {"/api/funcionario": "equipes", "/api/maquina": "equipes", "/api/movimento": "almox",
             "/api/nf/aceitar": "receber", "/api/checkin": "almox", "/api/checkout": "almox", "/api/clima": "campo",
             "/api/apontamento": "campo", "/api/foto": "campo", "/api/ok-fiscal": "ok_interno", "/api/recomposicao": "ok_interno",
             "/api/cadastro": "cadastro", "/api/medicao": "medicao", "/api/medicao/fechar": "medicao", "/api/estorno": "almox",
             "/api/retificar": "almox", "/api/intervalo/verificar": "verificar", "/api/legado/conciliar": "retificar_campo",
             "/api/intervalos/retificar": "retificar_campo", "/api/cadastro/conferencia": "conferir_cadastro",
             "/api/solda": "campo", "/api/solda/verificar": "verificar", "/api/reserva": "almox",
             "/api/reserva/cancelar": "almox", "/api/usuarios": "usuarios", "/api/senha": None,
             "/api/liberacao": "topografia", "/api/escavacao": "campo", "/api/etapa-complementar/anular": "retificar_campo",
             "/api/ocorrencia": "campo", "/api/ocorrencia/resolver": "verificar"}
# campos de autoria: o servidor grava o usuário da sessão, nunca o nome digitado no navegador
AUTOR = {"/api/movimento": ("responsavel",), "/api/estorno": ("responsavel",), "/api/retificar": ("responsavel",),
         "/api/reserva": ("responsavel",), "/api/apontamento": ("informado_por",), "/api/solda": ("informado_por",),
         "/api/intervalo/verificar": ("verificado_por",), "/api/solda/verificar": ("verificado_por",),
         "/api/legado/conciliar": ("responsavel",), "/api/intervalos/retificar": ("responsavel",),
         "/api/cadastro/conferencia": ("revisor",), "/api/ok-fiscal": ("usuario",),
         "/api/liberacao": ("registrado_por",), "/api/escavacao": ("registrado_por",), "/api/etapa-complementar/anular": ("por",),
         "/api/ocorrencia": ("aberta_por",), "/api/ocorrencia/resolver": ("por",)}
PERMISSAO.update({rota: perm for rota, (perm, _, _) in ROTAS_COMPRAS.items()})
PERMISSAO.update({"/api/programacao": "planejar", "/api/programacao/encerrar": "planejar", "/api/medicao/conferir": "medicao"})
AUTOR.update({"/api/programacao": ("por",), "/api/programacao/encerrar": ("por",), "/api/medicao/conferir": ("por",),
              "/api/medicao/fechar": ("por",)})
AUTOR.update({rota: campos for rota, (_, campos, _) in ROTAS_COMPRAS.items()})
assert set(PERMISSAO) == set(POST) | set(POST_USUARIO), "toda rota de gravação precisa de permissão definida"
PUBLICOS = {"/", "/index.html", "/app.js", "/app.css", "/mapa_iluminado.js", "/mapa_iluminado.css"}


def _mapa_path():
    return os.path.join(BASE, "mapa", _cfg()["arquivos"]["mapa"])


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "MorroDaCruz/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
        LOG.info("%s %s %s %s %d", self._ip(), getattr(self, "_login", "-") or "-", self.command,
                 urlparse(self.path).path, status)

    def _local(self):
        """Pedido feito no próprio computador (não veio pelo link da equipe: o túnel acrescenta Cf-Connecting-Ip)."""
        return (self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("Cf-Connecting-Ip")
                and not self.headers.get("X-Forwarded-For"))

    def _ip(self):
        return self.headers.get("Cf-Connecting-Ip") or self.client_address[0]

    def _https(self):
        return (self.headers.get("X-Forwarded-Proto") == "https" or '"https"' in (self.headers.get("Cf-Visitor") or "")
                or bool(self.headers.get("Cf-Connecting-Ip")))

    def _token(self):
        c = SimpleCookie(self.headers.get("Cookie") or "")
        return c[COOKIE].value if COOKIE in c else None

    def _usuario(self):
        u = A.sessao(CONN, self._token())
        self._login = u and u["login"]
        return u

    def _sem_usuarios(self):
        return {"erro": "Nenhum usuário cadastrado. No computador do servidor, crie o primeiro: python usuarios.py criar",
                "sem_usuarios": True}

    def _api(self, fn, arg):
        try:
            with LOCK:
                self._send(200, fn(arg, CONN))
        except A.AcessoNegado as e:
            self._send(e.status, {"erro": str(e)})
        except R.RegraViolada as e:
            self._send(422, {"erro": str(e)})
        except (KeyError, ValueError, TypeError) as e:
            self._send(400, {"erro": f"Requisição inválida: {e}"})
        except Exception as e:  # noqa: BLE001 — devolve a falha ao usuário em vez de derrubar o servidor
            LOG.exception("falha em GET %s", self.path)
            self._send(500, {"erro": f"Erro interno: {e}"})

    def _static(self, raiz, rel):
        p = os.path.realpath(os.path.join(raiz, rel))
        if not p.startswith(os.path.realpath(raiz) + os.sep) or not os.path.isfile(p):
            return self._send(404, {"erro": "não encontrado"})
        with open(p, "rb") as f:
            self._send(200, f.read(), mimetypes.guess_type(p)[0] or "application/octet-stream")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in PUBLICOS:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(WEB, "index.html"), "rb") as f:
                    html = f.read()
                if self._local():                       # avisos só para quem está no próprio computador
                    with LOCK:
                        configurado = A.acesso_configurado(CONN)
                    if DEMONSTRACAO and not configurado:
                        html = html.replace(b'id="dicaDemo" class="aviso info" hidden', b'id="dicaDemo" class="aviso info"')
                    if not configurado:
                        html = html.replace(b'id="dicaPrimeiro" class="aviso sugestao" hidden', b'id="dicaPrimeiro" class="aviso sugestao"')
                    else:
                        html = html.replace(b'id="dicaLocal" class="aviso sugestao" hidden', b'id="dicaLocal" class="aviso sugestao"')
                return self._send(200, html, "text/html; charset=utf-8")
            return self._static(WEB, "index.html" if u.path in ("/", "/index.html") else u.path.lstrip("/"))
        with LOCK:
            sem = not A.ha_usuarios(CONN)
            usuario = None if sem else self._usuario()
        if u.path == "/configurar":
            if not self._local():
                return self._send(403, "A configuração do acesso só pode ser feita no computador do programa.",
                                  "text/plain; charset=utf-8")
            return self._static(WEB, "configurar.html")
        if u.path == "/api/link":
            if usuario is None and not self._local():
                return self._send(401, {"erro": "Entre com seu usuário."})
            with LOCK:
                configurado = A.acesso_configurado(CONN)
            return self._send(200, {**link.estado, "ligado": LINK, "configurado": configurado})
        if u.path == "/api/sessao":
            if sem:
                return self._send(401, self._sem_usuarios())
            return (self._send(200, {"usuario": usuario, "demonstracao": DEMONSTRACAO}) if usuario
                    else self._send(401, {"erro": "Entre com seu usuário."}))
        if usuario is None:                            # API, fotos e mapa só com sessão
            if u.path.startswith("/api/"):
                return self._send(401, self._sem_usuarios() if sem else {"erro": "Sessão encerrada: entre de novo."})
            if u.path in ("/mapa", "/mapa/") or u.path.startswith("/fotos/"):
                return self._send(401, "Entre no sistema para ver o mapa e as fotos.", "text/plain; charset=utf-8")
        if u.path in GET:
            return self._api(GET[u.path], q)
        if u.path in GET_PERM:
            fn, perm = GET_PERM[u.path]
            return self._api(lambda a, c: (A.exigir(usuario, perm), fn(a, c))[1], q)
        if u.path in GET_USUARIO:
            return self._api(lambda a, c: GET_USUARIO[u.path](a, c, usuario), q)
        if u.path == "/api/medicao/exportar":
            try:
                A.exigir(usuario, "medicao")
                with LOCK:
                    nome, dados = exportar.planilha_medicao(CONN, int(q["id"]))
                    A.auditar(CONN, usuario, "GET", u.path, 200, q, nome)
                return self._send(200, dados, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="{nome}"'})
            except A.AcessoNegado as e:
                return self._send(e.status, {"erro": str(e)})
            except R.RegraViolada as e:
                return self._send(422, {"erro": str(e)})
        if u.path == "/api/relatorios/exportar":
            with LOCK:
                ini, fim = _periodo(q)
                nome, dados = RL.planilha(CONN, ini, fim, q.get("frente") or None)
                A.auditar(CONN, usuario, "GET", u.path, 200, q, nome)
            return self._send(200, dados, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              {"Content-Disposition": f'attachment; filename="{nome}"'})
        if u.path in ("/mapa", "/mapa/"):
            return self._mapa()
        if u.path.startswith("/fotos/"):
            return self._static(DIR_FOTOS, u.path[len("/fotos/"):])
        return self._static(WEB, u.path.lstrip("/"))

    def _ler_corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        u = urlparse(self.path)
        rota = u.path
        if rota not in POST and rota not in POST_USUARIO and rota not in ("/api/login", "/api/logout", "/api/configurar-acesso",
                                                                          "/api/entrar-local"):
            return self._send(404, {"erro": "rota inexistente"})
        if self.headers.get("X-MC") != "1":            # só a própria aplicação grava (proteção contra CSRF)
            return self._send(403, {"erro": "Requisição recusada: origem não reconhecida."})
        try:
            body = self._ler_corpo()
        except json.JSONDecodeError:
            return self._send(400, {"erro": "JSON inválido"})
        if not isinstance(body, dict):
            return self._send(400, {"erro": "JSON inválido"})
        if rota == "/api/login":
            return self._login_post(body)
        if rota == "/api/configurar-acesso":
            return self._configurar_acesso(body)
        if rota == "/api/entrar-local":
            return self._entrar_local()
        if rota == "/api/logout":
            with LOCK:
                usuario = self._usuario()
                A.encerrar(CONN, self._token())
                if usuario:
                    A.auditar(CONN, usuario, "POST", rota, 200)
            return self._send(200, {"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
        if backup.em_manutencao(os.path.dirname(os.path.abspath(DB_PATH))):
            return self._send(503, {"erro": "Manutenção em andamento (backup, restauração ou importação): gravações "
                                            "suspensas. Tente de novo quando terminar."})
        self._gravar(rota, body)

    def _login_post(self, body):
        with LOCK:
            if not A.ha_usuarios(CONN):
                return self._send(401, self._sem_usuarios())
            try:
                token, usuario = A.autenticar(CONN, body.get("login"), body.get("senha"), self._ip())
            except A.AcessoNegado as e:
                A.auditar(CONN, None, "POST", "/api/login", e.status, body, str(e), login=A.normalizar_login(body.get("login")))
                return self._send(e.status, {"erro": str(e)})
            A.auditar(CONN, usuario, "POST", "/api/login", 200, body)
            self._login = usuario["login"]
        cookie = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict" + ("; Secure" if COOKIE_SEGURO or self._https() else "")
        return self._send(200, {"usuario": usuario, "demonstracao": DEMONSTRACAO}, extra={"Set-Cookie": cookie})

    def _entrar_local(self):
        """Entrada sem senha só no próprio computador do sistema (pelo link, sempre login e senha)."""
        if not self._local():
            return self._send(403, {"erro": "Pelo link, entre com o seu usuário e senha."})
        with LOCK:
            try:
                token, usuario = A.entrar_local(CONN)
            except R.RegraViolada as e:
                return self._send(409, {"erro": str(e), "configurar": True})
            A.auditar(CONN, usuario, "POST", "/api/entrar-local", 200, None, "entrada sem senha no computador do sistema")
            self._login = usuario["login"]
        return self._send(200, {"usuario": usuario, "demonstracao": DEMONSTRACAO},
                          extra={"Set-Cookie": f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"})

    def _configurar_acesso(self, body):
        """Primeiro administrador real, só no próprio computador; depois liga o link da equipe."""
        if not self._local():
            return self._send(403, {"erro": "A configuração do acesso só pode ser feita no computador do programa."})
        with LOCK:
            try:
                with S.transacao(CONN):
                    uid, desativados = A.configurar_acesso(CONN, body.get("login"), body.get("nome"), body.get("senha"))
            except R.RegraViolada as e:
                return self._send(422, {"erro": str(e)})
            A.auditar(CONN, None, "POST", "/api/configurar-acesso", 200, {"login": body.get("login")},
                      f"administrador criado; {desativados} usuário(s) de demonstração desativado(s)", login=A.normalizar_login(body.get("login")))
        if LINK:
            link.iniciar(PORTA, _anunciar_link)
        return self._send(200, {"ok": True, "desativados": desativados, "link": dict(link.estado)})

    def _gravar(self, rota, body):
        """Uma requisição = uma transação: permissão, autoria, reenvio, a operação e a auditoria do aceite.
        Recusa ou falha desfazem tudo; a auditoria da recusa é gravada depois, fora da transação desfeita."""
        idem = self.headers.get("X-Idem") or None
        with LOCK:
            if not A.ha_usuarios(CONN):
                return self._send(401, self._sem_usuarios())
            usuario = self._usuario()
            original = json.loads(json.dumps(body))
            try:
                A.exigir(usuario, PERMISSAO[rota])
                if usuario["restrito_a_equipe"] and body.get("equipe_id") not in (None, "", usuario["equipe_id"]):
                    raise A.AcessoNegado(f"Seu usuário lança só para a equipe {usuario['equipe_id']}.", 403)
                for campo in AUTOR.get(rota, ()):
                    body[campo] = usuario["login"]
                with S.transacao(CONN):
                    anterior = A.resposta_anterior(CONN, usuario, idem, rota, original)
                    if anterior is not None:
                        A.auditar(CONN, usuario, "POST", rota, 200, original, "reenvio: resposta anterior devolvida, nada executado", idem)
                        resposta = anterior
                    else:
                        resposta = POST_USUARIO[rota](body, CONN, usuario) if rota in POST_USUARIO else POST[rota](body, CONN)
                        A.guardar_resposta(CONN, usuario, idem, rota, original, resposta)
                        A.auditar(CONN, usuario, "POST", rota, 200, original, json.dumps(resposta, default=str)[:500], idem)
                return self._send(200, resposta)
            except A.AcessoNegado as e:
                status, msg = e.status, str(e)
            except R.RegraViolada as e:
                status, msg = 422, str(e)
            except (KeyError, ValueError, TypeError) as e:
                status, msg = 400, f"Requisição inválida: {e}"
            except Exception as e:  # noqa: BLE001
                LOG.exception("falha em POST %s", rota)
                status, msg = 500, f"Erro interno: {e}"
            A.auditar(CONN, usuario, "POST", rota, status, original, msg, idem, login=None)
            return self._send(status, {"erro": msg})

    def _mapa(self):
        """Serve o HTML REV02 original com a camada do Mapa Iluminado injetada (o arquivo não é alterado)."""
        p = _mapa_path()
        if not os.path.exists(p):
            return self._static(WEB, "mapa_ausente.html")
        with open(p, encoding="utf-8") as f:
            html = f.read()
        tag = '<link rel="stylesheet" href="/mapa_iluminado.css"><script src="/mapa_iluminado.js"></script>'
        i = html.lower().rfind("</body>")
        html = html[:i] + tag + html[i:] if i >= 0 else html + tag
        self._send(200, html, "text/html; charset=utf-8")


def configurar_log(pasta_db):
    """Log de requisições e erros em <pasta do banco>/logs/servidor.log (5 arquivos de 2 MB, rotação)."""
    pasta = os.path.join(pasta_db, "logs")
    os.makedirs(pasta, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(pasta, "servidor.log"), maxBytes=2 * 1024 * 1024, backupCount=5,
                                             encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.handlers[:] = [h]
    LOG.setLevel(logging.INFO)


def _anunciar_link(url):
    print("\n" + "=" * 72)
    print(f" LINK PARA A EQUIPE:  {url}")
    print(" Envie este link. Ele vale enquanto este programa estiver aberto (muda quando reiniciar).")
    print(f" Ele também fica em {link.ARQUIVO}, na pasta do programa, e na aba 6 do sistema.")
    print("=" * 72 + "\n", flush=True)


def main():
    global CONN, DB_PATH, DIR_FOTOS, DEMONSTRACAO, LINK, PORTA
    backup.utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=S.DB_PADRAO)
    ap.add_argument("--demonstracao", action="store_true", help="mostra a faixa DEMONSTRAÇÃO na interface")
    ap.add_argument("--link", action="store_true", help="liga o link para a equipe (túnel https) depois do administrador")
    a = ap.parse_args()
    DEMONSTRACAO, LINK, PORTA = a.demonstracao, a.link, a.porta
    if not os.path.exists(a.db):
        raise SystemExit(f"Banco {a.db} não existe — rode antes: python importar.py --aplicar")
    DB_PATH = a.db
    DIR_FOTOS = os.path.join(os.path.dirname(os.path.abspath(a.db)), "fotos")
    try:
        CONN = S.conectar(a.db)
    except S.EsquemaAntigo as e:
        raise SystemExit(str(e))
    if a.host not in ("127.0.0.1", "localhost"):
        raise SystemExit("Acesso pela rede ainda não liberado (decisão D-60: hospedagem, HTTPS e rede): só 127.0.0.1.")
    configurar_log(os.path.dirname(os.path.abspath(a.db)))
    if not A.ha_usuarios(CONN):
        print("ATENÇÃO: nenhum usuário cadastrado. Crie o primeiro com: python usuarios.py criar --db " + a.db)
    srv = ThreadingHTTPServer((a.host, a.porta), Handler)
    marca = backup.marcar_servidor(os.path.dirname(os.path.abspath(a.db)), a.host, a.porta)
    print(f"Sistema Morro da Cruz em http://{a.host}:{a.porta}  (Ctrl+C para sair)")
    print("Importação e restauração exigem este servidor parado.")
    if LINK:
        if A.acesso_configurado(CONN):
            with S.transacao(CONN):
                n = A.desativar_demonstracao(CONN)       # senha pública: nunca ativos com o link ligado
            if n:
                print(f"{n} usuário(s) de demonstração desativado(s) antes de ligar o link.", flush=True)
            print("Ligando o link para a equipe (alguns segundos)…", flush=True)
            link.iniciar(PORTA, _anunciar_link)
        else:
            print(f"Link para a equipe: crie antes o administrador em http://127.0.0.1:{a.porta}/configurar", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # encerramento externo também apaga a marca
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        link.parar()
        srv.server_close()
        if os.path.exists(marca):
            os.remove(marca)


if __name__ == "__main__":
    main()
