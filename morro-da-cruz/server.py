"""Servidor do Sistema Morro da Cruz — só biblioteca padrão + openpyxl.

Uso:  python server.py [--porta 8765] [--db dados/morro_da_cruz.db] [--host 127.0.0.1]
Abra http://127.0.0.1:8765

Na nuvem (link fixo, sem depender de nenhum computador) quem inicia é o nuvem.py, com --nuvem: aí nenhum pedido é
tratado como "do próprio computador" (sem /configurar e sem entrar sem senha) e o cookie de sessão vai sempre com
Secure, porque a hospedagem entrega só por https.
"""
import argparse
import json
import logging
import logging.handlers
import mimetypes
import os
import re
import signal
import sys
import threading
from http.cookies import SimpleCookie

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import acesso as A
import apropriacao as AP
import caminhos
import backup
import compras as C
import cronograma as CR
import dados_obra as DO
import diario as DI
import documentos as D
import drive as DR
import medicao as M
import notas_servico as NS
import planejamento as P
import relatorios as RL
import exportar
import lev as LV
import link
import mapa_geral as MG
import regras as R
import relogio
import servicos as S
import terceirizadas as TZ
import topologia as TP

BASE = caminhos.PASTA
WEB = os.path.join(caminhos.RECURSOS, "web")
LOCK = threading.Lock()
CONN = None
DB_PATH = S.DB_PADRAO
DEMONSTRACAO = False                  # banco de demonstração (dados_demo/): a interface mostra a faixa de aviso
LINK = False                          # link para a equipe (túnel), ligado pelo programa do escritório (iniciar.py)
NUVEM = False                         # hospedado na nuvem (nuvem.py): todo pedido vem de fora, pelo https da hospedagem
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
        "ligacoes": _ligacoes(c),
    }


def _ligacoes(c):
    """Ligações prediais previstas no BM: ligação predial de água em rede de PEAD (código Caesb 8005508120013)."""
    r = c.execute("SELECT item, quantidade FROM bm_itens WHERE planilha='JUNTADA' AND vigente=1 AND codigo_caesb='8005508120013'"
                  ).fetchone()
    return {"quantidade": r[1], "fonte": f"BM, item {r[0]}"} if r and r[1] else None


def r_buscar(q, c):
    return S.buscar(c, q.get("q", ""))


def r_detalhe(q, c):
    d = S.detalhe(c, q["tipo"], q["id"])
    d["programacoes"] = [dict(r) for r in c.execute(
        "SELECT * FROM programacoes WHERE alvo_tipo=? AND alvo_id=? ORDER BY data DESC, id DESC LIMIT 15", (d["alvo_tipo"], d["id"]))]
    no_drive = DR.por_ref(c, "FOTO", [f["id"] for f in d.get("fotos") or []])
    for f in d.get("fotos") or []:
        f["drive"] = no_drive.get(f["id"])
    return d


def r_previsto(q, c):
    return S.previsto(c, q["tipo"], q["id"], float(q.get("metros") or 0))


def r_mapa_geral(q, c):
    """Satélite, zonas oficiais e traçado dos trechos da visão geral do HTML REV02 (o arquivo não é alterado)."""
    p = _mapa_path()
    if not os.path.exists(p):
        return {"ausente": True}
    return MG.geometria(p)


# planilhas oficiais versionadas com o programa (config/fontes.json): baixadas direto do sistema, sem Drive
PLANILHAS = {"bm": "Boletim de Medição com a identificação dos itens", "reajuste": "Boletim de Medição com o reajuste",
             "redes": "Levantamento de quantitativos das redes (tubos)", "conexoes": "Levantamento de conexões e peças por nó",
             "evidencias": "Evidências e conciliação entre a 06.1 e a 06.2", "mapa": "Mapa de plantas, trechos e nós (equipes)"}


def _arquivo_oficial(chave):
    nome = _cfg()["arquivos"].get(chave)
    if not nome:
        return None
    p = os.path.join(BASE, "mapa" if chave == "mapa" else "planilhas", nome)
    return p if os.path.isfile(p) else None


def r_planilhas(q, c):
    out = []
    for chave, descricao in PLANILHAS.items():
        p = _arquivo_oficial(chave)
        if p:
            out.append({"chave": chave, "arquivo": os.path.basename(p), "descricao": descricao, "bytes": os.path.getsize(p),
                        "url": "/arquivos/" + chave})
    return out


def r_topologia(q, c):
    """Trechos físicos (conexão → conexão), junções que não são conexão e pendências (config/topologia.json).
    ?trecho=<id ou nome visível> devolve só o trecho físico daquela linha; ?desenho=1 traz, para o mapa REV02, as
    pontas a encaixar no nó em cada desenho e os trechos físicos com mais de uma linha."""
    if q.get("desenho"):
        p = _mapa_path()
        return {"correcoes": MG.correcoes(p) if os.path.exists(p) else {}, "fisicos": TP.mapa(c)}
    return TP.consulta(c, q.get("trecho"))


def r_mapa_estado(q, c):
    med = q.get("medicao")
    out = S.estado_mapa(c, int(med) if med else None, q.get("data"))
    out["camadas"] = P.camadas_mapa(c, q.get("data"))
    return out


# ------------------------------------------------------------------ planejamento (módulo D)
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
    # do intervalo, só o que a pessoa informa: verificação e ligação com a NS nunca vêm do navegador
    intervalos = [{k: i.get(k) for k in ("etapa", "ini_m", "fim_m", "referencia")} for i in b.get("intervalos") or []
                  if isinstance(i, dict)]
    return {"id": S.apontar(c, b["data"], b["equipe_id"], b["alvo_tipo"], b["alvo_id"], float(b.get("metros_executados") or 0),
                            float(b.get("metros_reaterrados") or 0), bool(b.get("concluido_100")), b.get("estaca_ini"),
                            b.get("estaca_fim"), b.get("quantidades"), intervalos or None, b.get("informado_por"),
                            b.get("motivo_sem_ns"))}


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
    mid = S.criar_medicao(c, int(b["numero"]), b["periodo_ini"], b["periodo_fim"], b.get("tipo", "TESTE"))
    return {"id": mid, "liberados": AP.sincronizar(c)}          # o que estava parado e já foi liberado entra nesta


def r_medicao(q, c):
    mid = int(q["id"])
    return {**S.resumo_medicao(c, mid), **M.complementos(c, mid)}


def _periodo(q):
    hoje = relogio.hoje()
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


# ------------------------------------------------------------------ campo: diário do dia e interferências
def r_diario(q, c, usuario):
    """O encarregado (perfil restrito à equipe) vê só o diário da própria equipe."""
    equipe = usuario["equipe_id"] if usuario["restrito_a_equipe"] else q.get("equipe")
    return DI.diario(c, q.get("data") or relogio.hoje().isoformat(), equipe)


def r_lev_cronograma(q, c):
    return LV.cronograma(_arquivo_oficial("reajuste") or _arquivo_oficial("bm"))


def r_lev_bm(q, c):
    return LV.bm(c, q.get("planilha"), q.get("q"))


def r_lev_redes(q, c):
    return LV.redes(c, q.get("frente") or None, q.get("q"))


def r_lev_conexoes(q, c):
    return LV.conexoes(c, q.get("frente") or None, q.get("q"))


def r_interferencias(q, c):
    ab = q.get("abertas")
    return DI.interferencias(c, None if ab in (None, "") else ab == "1", q.get("equipe"), q.get("tipo"), q.get("categoria"),
                             q.get("ini"), q.get("fim"))


# ------------------------------------------------------------------ topografia e cadastro de campo (terceirizadas)
def r_topografia(q, c):
    return TZ.topografia(c, q.get("frente") or None)


def r_cadastro_campo(q, c):
    return TZ.cadastro_campo(c, q.get("frente") or None)


def p_cadastro_campo(b, c):
    return {"id": S.registrar_cadastro_campo(c, b["trecho_id"], b.get("ini_m"), b.get("fim_m"), b.get("data"),
                                             b.get("referencia"), b.get("por"))}


# ------------------------------------------------------------------ Planejamento: Dados da obra (mapa) e cronograma do Project
def r_dados_obra_selecao(q, c):
    return DO.selecao(c, q.get("linhas"), q.get("nos"), q.get("data") or None, q.get("equipe") or None)


def r_dados_obra_estado(q, c):
    return DO.estado(c, q.get("data") or None)


def p_dados_obra_programar(b, c):
    return DO.programar(c, b.get("linhas"), b.get("nos"), b.get("equipe_id"), b.get("servico"), b.get("data"), b["por"],
                        b.get("obs"), bool(b.get("confirmar")))


def p_dados_obra_cancelar(b, c):
    return {"canceladas": DO.cancelar_lote(c, b.get("lote"), b.get("motivo"), b["por"], b.get("a_partir_de"))}


def p_dados_obra_liberar(b, c):
    return DO.liberar(c, b.get("data"), b.get("equipe_id"), b.get("linhas"), b.get("nos"), b.get("materiais") or [], b["por"],
                      b.get("funcionarios") or [], b.get("maquinas") or [])


def p_dados_obra_reservar(b, c):
    return DO.reservar(c, b.get("data"), b.get("equipe_id"), b.get("linhas"), b.get("nos"), b.get("materiais") or [], b["por"])


def r_cronograma(q, c):
    return CR.consultar(c)


def p_cronograma(b, c):
    return CR.importar(c, b.get("conteudo_b64"), b.get("nome"), b["por"])


def r_quarentena(q, c):
    return C.a_inspecionar(c)


ROTAS_PLANEJAMENTO = {"/api/dados-obra/programar": ("planejar", p_dados_obra_programar),
                      "/api/dados-obra/cancelar-lote": ("planejar", p_dados_obra_cancelar),
                      "/api/dados-obra/liberar": ("almox", p_dados_obra_liberar),
                      "/api/dados-obra/reservar": ("almox", p_dados_obra_reservar),
                      "/api/cronograma": ("planejar", p_cronograma)}


# ------------------------------------------------------------------ nota de serviço por upload (v18)
# Quem abre a tela vê as NS daquele tipo; o encarregado vê as de serviço e as do dia da equipe dele.
TIPOS_DA_TELA = {"notas": set(NS.TIPOS), "topografia": {"TOPOGRAFIA"}, "cadastro_campo": {"CADASTRO"},
                 "campo": {"SERVICO", "EXECUCAO"}, "diario": {"SERVICO", "EXECUCAO"}}


def _tipos_visiveis(usuario):
    return set().union(*(TIPOS_DA_TELA.get(t, set()) for t in usuario["telas"]))


def _ns_visivel(usuario, ns):
    if ns["tipo"] not in _tipos_visiveis(usuario):
        return False
    return not (usuario["restrito_a_equipe"] and ns["tipo"] == "EXECUCAO" and ns["equipe_id"] != usuario["equipe_id"])


def _exigir_ns(usuario, ns_ou_tipo):
    """Registrar, aplicar e anular exigem também a permissão do tipo (topografia, cadastro de campo)."""
    tipo = ns_ou_tipo if isinstance(ns_ou_tipo, str) else ns_ou_tipo["tipo"]
    if tipo == "EXECUCAO":
        raise A.AcessoNegado("A NS do dia é enviada e anulada pela tela Nota do dia.", 403)
    if NS.PERMISSAO_TIPO.get(tipo):
        A.exigir(usuario, NS.PERMISSAO_TIPO[tipo])


def r_ns(q, c, usuario):
    if q.get("tipo") and q["tipo"] not in _tipos_visiveis(usuario):
        raise A.AcessoNegado("O seu perfil não abre as notas de serviço deste tipo.", 403)
    lista = NS.listar(c, q.get("tipo") or None, q.get("zona") or None, q.get("vigentes", "1") == "1",
                      q.get("equipe") or None, q.get("data") or None)
    return [n for n in lista if _ns_visivel(usuario, n)]


def r_ns_detalhe(q, c, usuario):
    d = NS.detalhe(c, int(q["id"]))
    if not _ns_visivel(usuario, d):
        raise A.AcessoNegado("Esta nota de serviço não é de uma tela que o seu perfil abre.", 403)
    return d


def p_ns_ler(b, c, usuario):
    return NS.ler(c, b.get("tipo"), b.get("pdf_b64"), b.get("planilha_b64"), b.get("zona") or None, b.get("pb") or None,
                  croqui_b64=b.get("croqui_b64"))


def p_ns(b, c, usuario):
    _exigir_ns(usuario, b.get("tipo") or "")
    return NS.registrar(c, b.get("tipo"), b.get("pdf_b64"), b["por"], b.get("decisoes"), b.get("croqui_b64"),
                        b.get("planilha_b64"), {k: b.get(f"{k}_nome") for k in ("pdf", "croqui", "planilha")},
                        b.get("zona") or None, b.get("pb") or None)


def p_ns_anexo(b, c, usuario):
    _exigir_ns(usuario, NS._ns(c, int(b["ns_id"])))
    return NS.anexar(c, int(b["ns_id"]), b.get("croqui_b64"), b.get("croqui_nome"), b["por"])


def p_ns_aplicar(b, c, usuario):
    _exigir_ns(usuario, NS._ns(c, int(b["ns_id"])))
    return NS.aplicar(c, int(b["ns_id"]), b["por"])


def p_ns_anular(b, c, usuario):
    _exigir_ns(usuario, NS._ns(c, int(b["ns_id"])))
    return NS.anular(c, int(b["ns_id"]), b.get("motivo"), b["por"])


ROTAS_NS = {"/api/ns/ler": p_ns_ler, "/api/ns": p_ns, "/api/ns/anexo": p_ns_anexo, "/api/ns/aplicar": p_ns_aplicar,
            "/api/ns/anular": p_ns_anular}
TELAS_NS = ("notas", "campo", "diario", "topografia", "cadastro_campo")


# NS do dia: a equipe (o encarregado só a dele) ou, em nome dela, supervisor, engenharia e administração
def r_ns_dia(q, c, usuario):
    equipe = usuario["equipe_id"] if usuario["restrito_a_equipe"] else (q.get("equipe") or None)
    return NS.listar_dia(c, q.get("data") or None, equipe, q.get("fila") == "1", q.get("desde") or None)


def p_ns_dia(b, c, usuario):
    equipe = b.get("equipe_id") or (usuario["equipe_id"] if usuario["restrito_a_equipe"] else None)
    return NS.enviar_dia(c, equipe, b.get("pdf_b64"), b.get("croqui_b64"), b["por"], b.get("planilha_b64"),
                         {k: b.get(f"{k}_nome") for k in ("pdf", "croqui", "planilha")}, b.get("clima"))


def p_ns_dia_conferir(b, c, usuario):
    return NS.conferir_dia(c, int(b["ns_id"]), b.get("decisoes") or [], b["por"])


def p_ns_dia_anular(b, c, usuario):
    """O encarregado anula o envio da equipe dele enquanto nenhum registro foi verificado; depois, só quem retifica."""
    ns = NS._ns(c, int(b["ns_id"]))
    if ns["tipo"] != "EXECUCAO":
        raise R.RegraViolada("Aqui se anula só a NS do dia; as outras, na tela Notas de serviço.")
    if "retificar_campo" not in usuario["permissoes"]:
        if usuario["restrito_a_equipe"] and ns["equipe_id"] != usuario["equipe_id"]:
            raise A.AcessoNegado(f"Seu usuário anula só os envios da equipe {usuario['equipe_id']}.", 403)
        if NS.verificado_dia(c, ns["id"]):
            raise A.AcessoNegado("Um registro desta nota já foi verificado: agora só a engenharia ou a administração anula.", 403)
    return NS.anular(c, ns["id"], b.get("motivo"), b["por"])


ROTAS_NS_DIA = {"/api/ns/dia": ("campo", p_ns_dia), "/api/ns/dia/conferir": ("retificar_campo", p_ns_dia_conferir),
                "/api/ns/dia/anular": ("campo", p_ns_dia_anular)}


# ------------------------------------------------------------------ apropriação direta e base de custo (D-90 em diante)
def r_base_custo_busca(q, c):
    return {"itens": AP.buscar(c, q.get("q"), q.get("grupo") or None, q.get("tipo") or None)}


def r_base_custo_itens(q, c):
    """Com ref: o item com a situação e o saldo; com grupo e tipo: os itens do subgrupo; sem nada: as listas da tela."""
    if q.get("ref"):
        it = AP.item(c, q["ref"])
        return {"item": {**AP.publico(it), **AP.saldo(c, it)}}
    itens = AP.itens_do_subgrupo(c, q["grupo"], q["tipo"]) if q.get("grupo") and q.get("tipo") else []
    return {**AP.grupos(), "itens": itens}


def r_apropriacoes(q, c, usuario):
    equipe = usuario["equipe_id"] if usuario["restrito_a_equipe"] else (q.get("equipe") or None)
    return AP.listar(c, q.get("ini") or None, q.get("fim") or None, equipe)


def r_medicao_restricoes(q, c):
    r = AP.restricoes(c, q.get("medicao") or None)
    return {**r, "itens_a_aprovar": AP.itens_a_aprovar(c, r["linhas"])}


ROTAS_APROPRIACAO = {
    "/api/apropriacao": ("apropriacao", lambda b, c: AP.apropriar(c, b, b["por"], C.documento_dir(c))),
    "/api/apropriacao/estornar": ("apropriacao", lambda b, c: AP.estornar(c, int(b["apropriacao_id"]), b.get("motivo"), b["por"])),
    "/api/base-custo/item-novo": ("apropriacao", lambda b, c: AP.propor_item(c, b, b["por"])),
    "/api/base-custo/decidir": ("medicao", lambda b, c: AP.decidir_item(c, b, b["por"], C.documento_dir(c))),
    "/api/base-custo/codigo-oficial": ("medicao", lambda b, c: AP.registrar_codigo_oficial(c, b, b["por"], C.documento_dir(c))),
}
TELAS_BASE_CUSTO = ("campo", "medicao", "lev")
TELAS_APROPRIACAO = ("campo", "diario", "medicao")


# ------------------------------------------------------------------ documentos oficiais (links do Google Drive)
def r_documentos(q, c):
    return D.listar(c)


def p_documento(b, c):
    campos = {k: b.get(k) for k in D.CAMPOS if k in b}
    if b.get("documento_id"):
        D.alterar(c, int(b["documento_id"]), campos, b["por"])
        return {"id": int(b["documento_id"])}
    return {"id": D.cadastrar(c, campos, b["por"])}


def p_documento_retirar(b, c):
    D.retirar(c, int(b["documento_id"]), b["por"], b.get("motivo"))
    return {"ok": True}


def p_documentos_importar(b, c):
    return D.importar_indice(c, b.get("csv") or "", b["por"], simular=bool(b.get("simular")),
                             incluir_trabalho=bool(b.get("incluir_trabalho")))


def p_documentos_config(b, c):
    D.salvar_config(c, b.get("pasta_url"), b.get("indice_url"), b["por"])
    return {"ok": True}


def p_documentos_sincronizar(b, c):
    baixar = (lambda url: DR.exportar_indice(c, url)) if DR.obter_config(c)["conectado"] else D.baixar_csv
    return D.sincronizar(c, b["por"], simular=bool(b.get("simular")), incluir_trabalho=bool(b.get("incluir_trabalho")),
                         baixar=baixar)


# ------------------------------------------------------------------ Google Drive conectado (v15)
def p_drive_config(b, c):
    DR.salvar_config(c, b.get("cliente_id"), b.get("cliente_segredo"), b.get("pasta_url"), b["por"])
    return {"ok": True}


def p_drive_desconectar(b, c):
    DR.desconectar(c, b["por"])
    return {"ok": True}


def p_drive_reenviar(b, c):
    DR.reenviar(c, int(b["envio_id"]))
    return {"ok": True}


ROTAS_DRIVE = {"/api/drive/config": p_drive_config, "/api/drive/desconectar": p_drive_desconectar,
               "/api/drive/reenviar": p_drive_reenviar, "/api/drive/testar": lambda b, c: DR.testar(c)}
# rotas do Drive tratadas à parte: precisam do endereço do pedido (conectar) ou fazem rede fora da trava (processar)
ROTAS_DRIVE_ESPECIAIS = ("/api/drive/conectar", "/api/drive/processar")
_DRIVE_OCUPADO = threading.Lock()


ROTAS_DOCUMENTOS = {"/api/documento": p_documento, "/api/documento/retirar": p_documento_retirar,
                    "/api/documentos/importar": p_documentos_importar, "/api/documentos/config": p_documentos_config,
                    "/api/documentos/sincronizar": p_documentos_sincronizar}


# ------------------------------------------------------------------ compras e recebimento (módulo C)
def _c(fn):
    return lambda b, c: {"id": fn(b, c)}


def r_compras(q, c):
    p = C.painel(c)
    no_drive = DR.por_ref(c, "DOCUMENTO", [n.get("documento_id") for n in p.get("notas") or []])
    for n in p.get("notas") or []:
        n["drive"] = no_drive.get(n.get("documento_id"))
    return p


def r_inventarios(q, c):
    return C.inventarios(c)


def r_reservas_vencidas(q, c):
    return C.reservas_vencidas(c, q.get("hoje") or relogio.hoje().isoformat())


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
        c, [int(x) for x in b.get("ids") or []], b.get("motivo"), b["por"], b.get("hoje") or relogio.hoje().isoformat())}),
}


# ------------------------------------------------------------------ acesso (módulo A)
def r_usuarios(q, c):
    """Com tem_historico: só a conta sem nenhum registro pode ser excluída (as outras, desativadas)."""
    usados = {r[0] for r in c.execute("SELECT usuario_id FROM auditoria UNION SELECT usuario_id FROM requisicoes")}
    return [dict(A.publico(dict(r)), tem_historico=r["id"] in usados) for r in c.execute("SELECT * FROM usuarios ORDER BY login")]


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
    if acao == "excluir":
        A.excluir_usuario(c, b.get("login"), usuario["login"])
        return {"ok": True}
    raise R.RegraViolada("Ação inválida (criar, alterar, senha ou excluir).")


def p_senha(b, c, usuario):
    A.trocar_senha(c, usuario["id"], b.get("senha_atual"), b.get("nova_senha"))
    return {"ok": True}


def r_auditoria(q, c, usuario):
    if not q.get("alvo_id"):                       # histórico completo só com a permissão de auditoria
        A.exigir(usuario, "auditoria")
    return A.consultar_auditoria(c, q.get("alvo_tipo"), q.get("alvo_id"), q.get("login"), int(q.get("limite", 100)))


GET = {"/api/resumo": r_resumo, "/api/buscar": r_buscar, "/api/detalhe": r_detalhe, "/api/previsto": r_previsto,
       "/api/mapa/estado": r_mapa_estado, "/api/equipe": r_equipe, "/api/estoque": r_estoque,
       "/api/compat-caesb": r_compat, "/api/nfs": r_nfs, "/api/histograma": r_histograma,
       "/api/esteira": r_esteira, "/api/medicoes": r_medicoes, "/api/medicao": r_medicao,
       "/api/movimentos": r_movimentos, "/api/reservas": r_reservas, "/api/consumo": r_consumo,
       "/api/ocorrencias": r_ocorrencias, "/api/compras": r_compras, "/api/inventarios": r_inventarios,
       "/api/reservas-vencidas": r_reservas_vencidas,
       "/api/medicao/elegibilidade": r_medicao_elegibilidade, "/api/relatorios": r_relatorios,
       "/api/documentos": r_documentos, "/api/mapa/geral": r_mapa_geral, "/api/planilhas": r_planilhas,
       "/api/interferencias": r_interferencias, "/api/lev/cronograma": r_lev_cronograma, "/api/lev/bm": r_lev_bm,
       "/api/lev/redes": r_lev_redes, "/api/lev/conexoes": r_lev_conexoes, "/api/topologia": r_topologia,
       "/api/topografia": r_topografia, "/api/cadastro-campo": r_cadastro_campo,
       "/api/dados-obra/selecao": r_dados_obra_selecao, "/api/dados-obra/estado": r_dados_obra_estado,
       "/api/cronograma": r_cronograma, "/api/almox/quarentena": r_quarentena,
       "/api/base-custo/busca": r_base_custo_busca, "/api/base-custo/itens": r_base_custo_itens,
       "/api/medicao/restricoes": r_medicao_restricoes}
GET_PERM = {"/api/usuarios": (r_usuarios, "usuarios")}
GET_USUARIO = {"/api/auditoria": r_auditoria, "/api/diario": r_diario,
               "/api/drive": lambda q, c, u: DR.resumo(c, completo="documentos" in u["permissoes"]),      # recebem o usuário da sessão
               "/api/ns": r_ns, "/api/ns/detalhe": r_ns_detalhe, "/api/ns/dia": r_ns_dia, "/api/apropriacoes": r_apropriacoes}
POST = {"/api/funcionario": p_funcionario, "/api/maquina": p_maquina, "/api/movimento": p_movimento,
        "/api/nf/aceitar": p_nf_aceitar, "/api/checkout": p_checkout, "/api/clima": p_clima,
        "/api/apontamento": p_apontamento, "/api/foto": p_foto, "/api/ok-fiscal": p_ok_fiscal,
        "/api/recomposicao": p_recomposicao, "/api/cadastro": p_cadastro, "/api/medicao": p_medicao,
        "/api/medicao/fechar": p_medicao_fechar, "/api/estorno": p_estorno, "/api/retificar": p_retificar,
        "/api/intervalo/verificar": p_intervalo_verificar, "/api/legado/conciliar": p_legado_conciliar,
        "/api/intervalos/retificar": p_intervalos_retificar, "/api/cadastro/conferencia": p_cadastro_conferencia,
        "/api/solda": p_solda, "/api/solda/verificar": p_solda_verificar, "/api/reserva": p_reserva,
        "/api/reserva/cancelar": p_reserva_cancelar, "/api/liberacao": _etapa("LIBERACAO_TOPOGRAFICA"),
        "/api/escavacao": _etapa("ESCAVADO"), "/api/etapa-complementar/anular": p_etapa_anular,
        "/api/ocorrencia": p_ocorrencia, "/api/ocorrencia/resolver": p_ocorrencia_resolver,
        "/api/cadastro-campo": p_cadastro_campo}
POST.update({rota: fn for rota, (_, _, fn) in ROTAS_COMPRAS.items()})
POST.update(ROTAS_DOCUMENTOS)
POST.update(ROTAS_DRIVE)
POST.update({"/api/medicao/conferir": p_medicao_conferir})
POST.update({rota: fn for rota, (_, fn) in ROTAS_PLANEJAMENTO.items()})
POST.update({rota: fn for rota, (_, fn) in ROTAS_APROPRIACAO.items()})
POST_USUARIO = {"/api/usuarios": p_usuarios, "/api/senha": p_senha, **ROTAS_NS,
                **{rota: fn for rota, (_, fn) in ROTAS_NS_DIA.items()}}
# permissão exigida por rota de gravação (config/perfis.json; None = basta estar logado)
PERMISSAO = {"/api/funcionario": "equipes", "/api/maquina": "equipes", "/api/movimento": "almox",
             "/api/nf/aceitar": "receber", "/api/checkout": "almox", "/api/clima": "campo",
             "/api/apontamento": "campo", "/api/foto": "campo", "/api/ok-fiscal": "ok_interno", "/api/recomposicao": "ok_interno",
             "/api/cadastro": "cadastro", "/api/medicao": "medicao", "/api/medicao/fechar": "medicao", "/api/estorno": "almox",
             "/api/retificar": "almox", "/api/intervalo/verificar": "verificar", "/api/legado/conciliar": "retificar_campo",
             "/api/intervalos/retificar": "retificar_campo", "/api/cadastro/conferencia": "conferir_cadastro",
             "/api/solda": "campo", "/api/solda/verificar": "verificar", "/api/reserva": "almox",
             "/api/reserva/cancelar": "almox", "/api/usuarios": "usuarios", "/api/senha": None,
             "/api/liberacao": "topografia", "/api/escavacao": "campo", "/api/etapa-complementar/anular": "retificar_campo",
             "/api/ocorrencia": "campo", "/api/ocorrencia/resolver": "verificar", "/api/cadastro-campo": "cadastro_campo"}
# campos de autoria: o servidor grava o usuário da sessão, nunca o nome digitado no navegador
AUTOR = {"/api/movimento": ("responsavel",), "/api/estorno": ("responsavel",), "/api/retificar": ("responsavel",),
         "/api/reserva": ("responsavel",), "/api/apontamento": ("informado_por",), "/api/solda": ("informado_por",),
         "/api/intervalo/verificar": ("verificado_por",), "/api/solda/verificar": ("verificado_por",),
         "/api/legado/conciliar": ("responsavel",), "/api/intervalos/retificar": ("responsavel",),
         "/api/cadastro/conferencia": ("revisor",), "/api/ok-fiscal": ("usuario",),
         "/api/liberacao": ("registrado_por",), "/api/escavacao": ("registrado_por",), "/api/etapa-complementar/anular": ("por",),
         "/api/ocorrencia": ("aberta_por",), "/api/ocorrencia/resolver": ("por",), "/api/cadastro-campo": ("por",)}
PERMISSAO.update({rota: perm for rota, (perm, _, _) in ROTAS_COMPRAS.items()})
PERMISSAO.update({"/api/medicao/conferir": "medicao"})
AUTOR.update({"/api/medicao/conferir": ("por",),
              "/api/medicao/fechar": ("por",)})
AUTOR.update({rota: campos for rota, (_, campos, _) in ROTAS_COMPRAS.items()})
PERMISSAO.update({rota: perm for rota, (perm, _) in ROTAS_PLANEJAMENTO.items()})
AUTOR.update({rota: ("por",) for rota in ROTAS_PLANEJAMENTO})
PERMISSAO.update({rota: "documentos" for rota in ROTAS_DOCUMENTOS})
AUTOR.update({rota: ("por",) for rota in ROTAS_DOCUMENTOS})
PERMISSAO.update({rota: "documentos" for rota in ROTAS_DRIVE})
AUTOR.update({rota: ("por",) for rota in ROTAS_DRIVE})
PERMISSAO.update({rota: "notas_servico" for rota in ROTAS_NS})
AUTOR.update({rota: ("por",) for rota in ROTAS_NS})
PERMISSAO.update({rota: perm for rota, (perm, _) in ROTAS_NS_DIA.items()})
AUTOR.update({rota: ("por",) for rota in ROTAS_NS_DIA})
PERMISSAO.update({rota: perm for rota, (perm, _) in ROTAS_APROPRIACAO.items()})
AUTOR.update({rota: ("por",) for rota in ROTAS_APROPRIACAO})
assert set(PERMISSAO) == set(POST) | set(POST_USUARIO), "toda rota de gravação precisa de permissão definida"
# tela que cada consulta serve (config/perfis.json, "telas"): o perfil precisa abrir uma delas; COMUNS valem para qualquer sessão
COMUNS = {"/api/resumo", "/api/buscar", "/api/detalhe", "/api/previsto", "/api/mapa/estado", "/api/mapa/geral"}
_CAMPO = ("campo", "diario", "interferencias")
_ALMOX = ("almox", "equipes", "mapa")                   # Equipes e o Dados da obra (liberar e devolver) também montam o almoxarifado
TELA_GET = {"/api/equipe": ("equipes", "mapa") + _CAMPO, "/api/estoque": _ALMOX + ("compras",),
            "/api/compat-caesb": _ALMOX, "/api/nfs": _ALMOX, "/api/movimentos": _ALMOX, "/api/reservas": _ALMOX,
            "/api/consumo": _ALMOX, "/api/histograma": ("equipes",) + _CAMPO,
            "/api/compras": ("compras",), "/api/inventarios": ("compras",), "/api/reservas-vencidas": ("compras",),
            "/api/ocorrencias": _CAMPO + ("mapa", "topografia", "cadastro_campo"),
            "/api/esteira": ("esteira",), "/api/relatorios": ("relatorios",), "/api/medicoes": ("medicao",),
            "/api/medicao": ("medicao",), "/api/medicao/elegibilidade": ("medicao",), "/api/planilhas": ("lev",),
            "/api/documentos": ("admin",), "/api/drive": ("admin",), "/api/usuarios": ("admin",), "/api/auditoria": ("admin", "mapa"),
            "/api/diario": ("diario",), "/api/interferencias": ("interferencias",), "/api/topografia": ("topografia",),
            "/api/cadastro-campo": ("cadastro_campo",), "/api/topologia": ("mapa", "iluminado"),
            "/api/dados-obra/selecao": ("mapa",), "/api/dados-obra/estado": ("mapa",), "/api/cronograma": ("cronograma", "mapa"),
            "/api/almox/quarentena": ("almox", "compras"),
            "/api/ns": TELAS_NS, "/api/ns/detalhe": TELAS_NS, "/api/ns/dia": ("campo", "diario", "notas"),
            "/api/base-custo/busca": TELAS_BASE_CUSTO, "/api/base-custo/itens": TELAS_BASE_CUSTO,
            "/api/apropriacoes": TELAS_APROPRIACAO, "/api/medicao/restricoes": ("medicao",),
            **dict.fromkeys(("/api/lev/cronograma", "/api/lev/bm", "/api/lev/redes", "/api/lev/conexoes"), ("lev",))}
assert set(GET) | set(GET_PERM) | set(GET_USUARIO) == COMUNS | set(TELA_GET), "toda consulta precisa de tela definida (ou ser comum)"
TELA_ARQUIVO = {"/api/relatorios/exportar": ("relatorios",), "/api/medicao/exportar": ("medicao",),   # downloads (/arquivos/: LEV)
                "/api/ns/arquivo": TELAS_NS, "/api/apropriacao/arquivo": TELAS_APROPRIACAO}
LIMITE_CORPO = 32 * 1024 * 1024                  # PDF + croqui + planilha da NS em base64 cabem; acima: 413 sem ler o corpo
PUBLICOS = {"/", "/index.html", "/app.js", "/app.css", "/mapa_iluminado.js", "/mapa_iluminado.css"}


class CorpoGrande(Exception):
    """Content-Length acima do limite: recusado (413) sem ler o corpo."""


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
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if NUVEM:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
        LOG.info("%s %s %s %s %d", self._ip(), getattr(self, "_login", "-") or "-", self.command,
                 urlparse(self.path).path, status)

    def _local(self):
        """Pedido feito no próprio computador (não veio pelo link da equipe: o túnel acrescenta Cf-Connecting-Ip).
        Na nuvem, nunca: o "computador do sistema" é da hospedagem e todo pedido chega pela internet."""
        return (not NUVEM and self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("Cf-Connecting-Ip")
                and not self.headers.get("X-Forwarded-For"))

    def _ip(self):
        encaminhado = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() if NUVEM else ""
        return self.headers.get("Cf-Connecting-Ip") or encaminhado or self.client_address[0]

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
        if NUVEM:
            return {"erro": "Nenhum usuário ativo. Na hospedagem, defina MC_ADMIN_LOGIN e MC_ADMIN_SENHA e reinicie "
                            "(docs/NUVEM.md).", "sem_usuarios": True}
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
        if NUVEM and self.headers.get("X-Forwarded-Proto") == "http":     # endereço digitado sem https
            return self._send(301, "", "text/plain; charset=utf-8", {"Location": f"https://{self.headers.get('Host', '')}{self.path}"})
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
        if u.path == DR.RETORNO:
            return self._drive_retorno(q)
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
            if u.path in ("/mapa", "/mapa/") or u.path.startswith(("/fotos/", "/mapa/", "/arquivos/")):
                return self._send(401, "Entre no sistema para ver o mapa, as fotos e os arquivos.", "text/plain; charset=utf-8")
        telas = TELA_GET.get(u.path) or TELA_ARQUIVO.get(u.path) or (("lev",) if u.path.startswith("/arquivos/") else None)
        if telas:                                      # a consulta é de uma tela que o perfil precisa abrir
            try:
                A.exigir_tela(usuario, telas)
            except A.AcessoNegado as e:
                return self._send(e.status, {"erro": str(e)})
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
        if u.path == "/api/ns/arquivo":
            return self._ns_arquivo(q, usuario)
        if u.path == "/api/apropriacao/arquivo":
            return self._apropriacao_arquivo(q, usuario)
        if u.path in ("/mapa", "/mapa/"):
            return self._mapa()
        if u.path.startswith("/mapa/"):
            return self._mapa_imagem(u.path[len("/mapa/"):])
        if u.path.startswith("/arquivos/"):
            p = _arquivo_oficial(u.path[len("/arquivos/"):])
            if not p:
                return self._send(404, {"erro": "não encontrado"})
            with open(p, "rb") as f:
                dados = f.read()
            nome = os.path.basename(p)
            return self._send(200, dados, mimetypes.guess_type(p)[0] or "application/octet-stream",
                              {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}"})
        if u.path.startswith("/fotos/"):
            rel = u.path[len("/fotos/"):]
            if not os.path.isfile(os.path.join(DIR_FOTOS, rel)):      # original só no Drive: mostra a miniatura
                with LOCK:
                    rel = DR.miniatura_de(CONN, rel) or rel
            return self._static(DIR_FOTOS, rel)
        return self._static(WEB, u.path.lstrip("/"))

    def _ns_arquivo(self, q, usuario):
        """PDF, croqui ou planilha de uma NS registrada, para abrir no navegador (inline, sem executar nada)."""
        try:
            with LOCK:
                ns, doc, nome = NS.arquivo(CONN, int(q.get("id") or 0), q.get("qual") or "pdf")
                if not _ns_visivel(usuario, ns):
                    raise A.AcessoNegado("Esta nota de serviço não é de uma tela que o seu perfil abre.", 403)
                caminho = os.path.join(C.documento_dir(CONN), doc["arquivo"])
                no_drive = (DR.por_ref(CONN, "DOCUMENTO", [doc["id"]]) or {}).get(doc["id"]) or {}
        except A.AcessoNegado as e:
            return self._send(e.status, {"erro": str(e)})
        except R.RegraViolada as e:
            return self._send(404, {"erro": str(e)})
        except (KeyError, ValueError, TypeError) as e:
            return self._send(400, {"erro": f"Requisição inválida: {e}"})
        if not os.path.isfile(caminho):                 # saiu do servidor depois de ir para o Drive
            if no_drive.get("drive_link"):
                return self._send(302, "", "text/plain; charset=utf-8", {"Location": no_drive["drive_link"]})
            return self._send(404, {"erro": "O arquivo não está no servidor."})
        with open(caminho, "rb") as f:                  # fora da trava: o arquivo é lido sem segurar o banco
            dados = f.read()
        return self._send(200, dados, doc["mime"] or "application/octet-stream",
                          {"Content-Disposition": f"inline; filename*=UTF-8''{quote(nome)}",
                           "Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=3600"})

    def _apropriacao_arquivo(self, q, usuario):
        """Evidência de uma apropriação direta ou o documento da Caesb de um item a aprovar (inline, sem executar nada)."""
        try:
            with LOCK:
                doc, nome = AP.arquivo(CONN, int(q.get("doc") or 0))
                caminho = os.path.join(C.documento_dir(CONN), doc["arquivo"])
                no_drive = (DR.por_ref(CONN, "DOCUMENTO", [doc["id"]]) or {}).get(doc["id"]) or {}
        except R.RegraViolada as e:
            return self._send(404, {"erro": str(e)})
        except (KeyError, ValueError, TypeError) as e:
            return self._send(400, {"erro": f"Requisição inválida: {e}"})
        if not os.path.isfile(caminho):
            if no_drive.get("drive_link"):
                return self._send(302, "", "text/plain; charset=utf-8", {"Location": no_drive["drive_link"]})
            return self._send(404, {"erro": "O arquivo não está no servidor."})
        with open(caminho, "rb") as f:
            dados = f.read()
        return self._send(200, dados, doc["mime"] or "application/octet-stream",
                          {"Content-Disposition": f"inline; filename*=UTF-8''{quote(nome)}",
                           "Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=3600"})

    def _ler_corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > LIMITE_CORPO:
            raise CorpoGrande(n)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        u = urlparse(self.path)
        rota = u.path
        if rota not in POST and rota not in POST_USUARIO and rota not in ("/api/login", "/api/logout", "/api/configurar-acesso",
                                                                          "/api/entrar-local", *ROTAS_DRIVE_ESPECIAIS):
            return self._send(404, {"erro": "rota inexistente"})
        if self.headers.get("X-MC") != "1":            # só a própria aplicação grava (proteção contra CSRF)
            return self._send(403, {"erro": "Requisição recusada: origem não reconhecida."})
        try:
            body = self._ler_corpo()
        except CorpoGrande as e:
            self.close_connection = True                 # o corpo não foi lido: a conexão não serve para outro pedido
            return self._send(413, {"erro": f"Envio grande demais ({e.args[0] / 2 ** 20:.0f} MB): o limite é "
                                            f"{LIMITE_CORPO // 2 ** 20} MB por envio (PDF da NS até 5 MB, croqui até 15 MB)."})
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
        if rota in ROTAS_DRIVE_ESPECIAIS:
            return self._drive_post(rota)
        self._gravar(rota, body)

    def _drive_post(self, rota):
        with LOCK:
            usuario = self._usuario()
        if not usuario:
            return self._send(401, {"erro": "Sessão encerrada: entre de novo."})
        if rota == "/api/drive/conectar":
            esquema = "https" if NUVEM or self._https() else "http"
            retorno = f"{esquema}://{self.headers.get('Host', '')}{DR.RETORNO}"
            with LOCK:
                try:
                    A.exigir(usuario, "documentos")
                    url = DR.iniciar_conexao(CONN, retorno, usuario["login"])
                except A.AcessoNegado as e:
                    A.auditar(CONN, usuario, "POST", rota, e.status, None, str(e))
                    return self._send(e.status, {"erro": str(e)})
                except R.RegraViolada as e:
                    return self._send(422, {"erro": str(e)})
                A.auditar(CONN, usuario, "POST", rota, 200, {"retorno": retorno}, "conexão com o Google iniciada")
            return self._send(200, {"url": url, "retorno": retorno})
        # /api/drive/processar: qualquer pessoa logada dispara (a foto que ela acabou de enviar sobe para o Drive)
        if not _DRIVE_OCUPADO.acquire(blocking=False):
            return self._send(200, {"ocupado": True})
        try:
            r = DR.processar(CONN, LOCK, DIR_FOTOS, limite=4, tempo=25)
        except Exception as e:  # noqa: BLE001 — o envio nunca derruba o servidor; o erro aparece na tela Documentos
            LOG.exception("falha ao enviar para o Drive")
            r = {"erro": f"Erro interno no envio para o Drive: {e}"}
        finally:
            _DRIVE_OCUPADO.release()
        return self._send(200, r)

    def _drive_retorno(self, q):
        """Volta do consentimento do Google. O cookie de sessão (SameSite=Strict) não vem nesta navegação: quem prova a
        origem é o 'state', guardado no banco ao clicar em Conectar e válido uma vez só."""
        erro = None
        with LOCK:
            try:
                reg = DR.consumir_estado(CONN, q.get("state"))
                cr = DR._credenciais(CONN)
            except R.RegraViolada as e:
                erro = str(e)
        if erro:                                        # fora da trava: _pagina_retorno grava o erro com a trava
            return self._pagina_retorno(erro)
        if q.get("error"):
            return self._pagina_retorno(f"O Google não autorizou ({q['error']}).")
        try:
            tokens = DR.trocar_codigo(cr, q.get("code", ""), reg["retorno"])
        except (R.RegraViolada, DR.SemConexao) as e:
            return self._pagina_retorno(str(e))
        with LOCK:
            conta = DR.guardar_conexao(CONN, tokens)
            A.auditar(CONN, None, "GET", DR.RETORNO, 200, None, f"Google Drive conectado: {conta}", login=reg.get("login"))
        return self._pagina_retorno(None)

    def _pagina_retorno(self, erro):
        if erro:
            with LOCK:
                with S.transacao(CONN):
                    D._gravar_parametro(CONN, DR.PARAM["erro"], erro)
        msg = "Google Drive conectado. Voltando ao sistema…" if not erro else "Não deu para conectar. Voltando ao sistema…"
        html = (f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="1;url=/#docs">'
                f'<title>Morro da Cruz</title><p style="font:16px system-ui;padding:24px">{msg}</p>')
        return self._send(200, html, "text/html; charset=utf-8")

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
                if rota == "/api/apontamento" and "cadastro_campo" not in usuario["permissoes"] and any(
                        isinstance(i, dict) and i.get("etapa") == "CADASTRO_CAMPO" for i in body.get("intervalos") or []):
                    raise A.AcessoNegado("O cadastro de campo é feito por equipe terceirizada e registrado pela engenharia "
                                         "na aba Cadastro de campo, não no lançamento do dia.", 403)
                if rota == "/api/apontamento" and str(body.get("alvo_tipo") or "").upper() == "TRECHO":
                    if "lancar_sem_ns" not in usuario["permissoes"]:      # o avanço do trecho vem da NS do dia
                        raise A.AcessoNegado("O avanço do trecho vem da nota de serviço do dia (tela Nota do dia). Lançar à mão, "
                                             "sem nota, é exceção da engenharia e da administração.", 403)
                    if not str(body.get("motivo_sem_ns") or "").strip():
                        raise R.RegraViolada("Lançamento sem nota de serviço: informe o motivo (fica guardado junto do apontamento).")
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

    def _mapa_imagem(self, rel):
        """Satélite da visão geral (mosaico das 25 PBs) ou a imagem de uma PB, tirados do HTML REV02."""
        p = _mapa_path()
        m = re.fullmatch(r"pb/(PB\d\d)\.webp", rel)
        dados = None
        if os.path.exists(p):                     # mapa_geral tem trava própria: não segura o banco
            dados = MG.mosaico(p) if rel == "geral.webp" else MG.imagem_pb(p, m.group(1)) if m else None
        if not dados:
            return self._send(404, {"erro": "não encontrado"})
        self._send(200, dados, "image/webp", {"Cache-Control": "private, max-age=86400"})

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
    print(f" Ele também fica em {link.ARQUIVO}, na pasta do programa, e no sistema (Administrativo › Usuários e histórico).")
    print("=" * 72 + "\n", flush=True)


def abrir(db, demonstracao=False, nuvem=False):
    """Abre o banco e define o modo do servidor. Usado pelo main e pelo adaptador WSGI da nuvem (nuvem.py)."""
    global CONN, DB_PATH, DIR_FOTOS, DEMONSTRACAO, NUVEM, COOKIE_SEGURO
    if not os.path.exists(db):
        raise SystemExit(f"Banco {db} não existe — rode antes: python importar.py --aplicar")
    try:
        conn = S.conectar(db)
    except S.EsquemaAntigo as e:
        raise SystemExit(str(e))
    CONN, DB_PATH, DEMONSTRACAO, NUVEM = conn, db, demonstracao, nuvem
    COOKIE_SEGURO = nuvem                  # na nuvem a hospedagem só entrega por https
    DIR_FOTOS = os.path.join(os.path.dirname(os.path.abspath(db)), "fotos")
    configurar_log(os.path.dirname(os.path.abspath(db)))
    threading.Thread(target=_preparar_mapa_geral, daemon=True).start()


def _preparar_mapa_geral():
    """Monta a visão geral do mapa (traçado e satélite) em segundo plano, para o primeiro acesso não esperar."""
    try:
        if os.path.exists(_mapa_path()):
            MG.geometria(_mapa_path())
            MG.mosaico(_mapa_path())
    except Exception:  # noqa: BLE001 — sem visão geral o mapa monta as PBs uma a uma; nada para no servidor
        LOG.exception("falha ao preparar a visão geral do mapa")


def main():
    global LINK, PORTA
    backup.utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=S.DB_PADRAO)
    ap.add_argument("--demonstracao", action="store_true", help="mostra a faixa DEMONSTRAÇÃO na interface")
    ap.add_argument("--link", action="store_true", help="liga o link para a equipe (túnel https) depois do administrador")
    ap.add_argument("--nuvem", action="store_true", help="hospedado na nuvem atrás do https da hospedagem (use o nuvem.py)")
    a = ap.parse_args()
    if a.host not in ("127.0.0.1", "localhost") and not a.nuvem:
        raise SystemExit("Acesso pela rede só no modo nuvem (python nuvem.py, atrás do https da hospedagem): aqui, só 127.0.0.1.")
    LINK, PORTA = a.link and not a.nuvem, a.porta
    abrir(a.db, a.demonstracao, a.nuvem)
    if not A.ha_usuarios(CONN):
        print("ATENÇÃO: nenhum usuário cadastrado. Crie o primeiro com: python usuarios.py criar --db " + a.db)
    srv = ThreadingHTTPServer((a.host, a.porta), Handler)
    marca = backup.marcar_servidor(os.path.dirname(os.path.abspath(a.db)), a.host, a.porta)
    print(f"Sistema Morro da Cruz em http://{a.host}:{a.porta}{'  (nuvem)' if NUVEM else ''}  (Ctrl+C para sair)", flush=True)
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
