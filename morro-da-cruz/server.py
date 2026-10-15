"""Servidor local (privado) do Sistema Morro da Cruz — só biblioteca padrão + openpyxl.

Uso:  python server.py [--porta 8765] [--db dados/morro_da_cruz.db] [--host 127.0.0.1]
Abra http://127.0.0.1:8765
"""
import argparse
import json
import mimetypes
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import exportar
import regras as R
import servicos as S

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")
LOCK = threading.Lock()
CONN = None


def _cfg():
    with open(os.path.join(BASE, "config", "fontes.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ rotas
def r_resumo(q, c):
    one = lambda sql: c.execute(sql).fetchone()[0]
    ultima = c.execute("SELECT id, concluida_em, status FROM importacoes WHERE modo='APLICACAO' ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "contrato": S.contrato(c),
        "obra": _cfg()["obra"],
        "valor_contrato": float(S.parametro(c, "valor_contrato", 0)),
        "p0_bm": float(S.parametro(c, "p0_bm", 0)),
        "trechos": one("SELECT COUNT(*) FROM trechos WHERE vigente=1"),
        "extensao_m": one("SELECT ROUND(SUM(extensao_m),2) FROM trechos WHERE vigente=1"),
        "elementos": one("SELECT COUNT(*) FROM elementos WHERE vigente=1"),
        "atividades": one("SELECT COUNT(*) FROM atividades WHERE vigente=1"),
        "itens_pendentes": one("SELECT COUNT(*) FROM itens_projeto WHERE vigente=1 AND (quantidade IS NULL OR unidade IS NULL)"),
        "executado_m": one("SELECT ROUND(COALESCE(SUM(metros_reaterrados),0),2) FROM execucao WHERE alvo_tipo='TRECHO'"),
        "ok_fiscal": one("SELECT COUNT(*) FROM execucao WHERE ok_fiscal_em IS NOT NULL"),
        "medicao_oficial_liberada": S.medicao_oficial_liberada(c),
        "ultima_importacao": dict(ultima) if ultima else None,
        "mapa_disponivel": os.path.exists(_mapa_path()),
        "equipes": [dict(r) for r in c.execute("SELECT * FROM equipes")],
        "clima": R.CONDICOES_CLIMA,
        "contingencias": R.CONTINGENCIAS,
        "etapas": R.ETAPAS,
    }


def r_buscar(q, c):
    return S.buscar(c, q.get("q", ""))


def r_detalhe(q, c):
    return S.detalhe(c, q["tipo"], q["id"])


def r_previsto(q, c):
    return S.previsto(c, q["tipo"], q["id"], float(q.get("metros") or 0))


def r_mapa_estado(q, c):
    med = q.get("medicao")
    return S.estado_mapa(c, int(med) if med else None, q.get("data"))


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
    S.entrada_material(c, b["data"], b["material_id"], float(b["quantidade"]), b["tipo"], b.get("documento"))
    return {"ok": True}


def r_nfs(q, c):
    out = [dict(r) for r in c.execute("SELECT * FROM notas_fiscais ORDER BY id DESC")]
    for n in out:
        n["itens"] = [dict(r) for r in c.execute("SELECT * FROM nf_itens WHERE nf_id=?", (n["id"],))]
    return out


def p_nf(b, c):
    return {"id": S.registrar_nf(c, b["numero"], b.get("fornecedor"), b["data_entrega"], b["itens"],
                                 bool(b.get("faturamento_etapas")), b.get("chave_nfe"), b.get("arquivo"))}


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
                            b.get("estaca_fim"), b.get("quantidades"))}


def p_foto(b, c):
    return S.registrar_foto(c, b["alvo_tipo"], b["alvo_id"], b["categoria"], b["conteudo_b64"], b.get("extensao", "jpg"),
                            b.get("data_hora"), b.get("lat"), b.get("lon"))


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


def r_medicoes(q, c):
    return [dict(r) for r in c.execute("SELECT * FROM medicoes ORDER BY numero")]


def p_medicao(b, c):
    return {"id": S.criar_medicao(c, int(b["numero"]), b["periodo_ini"], b["periodo_fim"], b.get("tipo", "TESTE"))}


def r_medicao(q, c):
    return S.resumo_medicao(c, int(q["id"]))


def p_medicao_fechar(b, c):
    S.fechar_medicao(c, int(b["id"]))
    return {"ok": True}


GET = {"/api/resumo": r_resumo, "/api/buscar": r_buscar, "/api/detalhe": r_detalhe, "/api/previsto": r_previsto,
       "/api/mapa/estado": r_mapa_estado, "/api/equipe": r_equipe, "/api/estoque": r_estoque,
       "/api/compat-caesb": r_compat, "/api/nfs": r_nfs, "/api/checkins": r_checkins, "/api/histograma": r_histograma,
       "/api/esteira": r_esteira, "/api/medicoes": r_medicoes, "/api/medicao": r_medicao}
POST = {"/api/funcionario": p_funcionario, "/api/maquina": p_maquina, "/api/movimento": p_movimento, "/api/nf": p_nf,
        "/api/nf/aceitar": p_nf_aceitar, "/api/checkin": p_checkin, "/api/checkout": p_checkout, "/api/clima": p_clima,
        "/api/apontamento": p_apontamento, "/api/foto": p_foto, "/api/ok-fiscal": p_ok_fiscal,
        "/api/recomposicao": p_recomposicao, "/api/cadastro": p_cadastro, "/api/medicao": p_medicao,
        "/api/medicao/fechar": p_medicao_fechar}


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
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _api(self, fn, arg):
        try:
            with LOCK:
                self._send(200, fn(arg, CONN))
        except R.RegraViolada as e:
            self._send(422, {"erro": str(e)})
        except (KeyError, ValueError, TypeError) as e:
            self._send(400, {"erro": f"Requisição inválida: {e}"})
        except Exception as e:  # noqa: BLE001 — devolve a falha ao usuário em vez de derrubar o servidor
            traceback.print_exc()
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
        if u.path in GET:
            return self._api(GET[u.path], q)
        if u.path == "/api/medicao/exportar":
            try:
                with LOCK:
                    nome, dados = exportar.planilha_medicao(CONN, int(q["id"]))
                return self._send(200, dados, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="{nome}"'})
            except R.RegraViolada as e:
                return self._send(422, {"erro": str(e)})
        if u.path in ("/mapa", "/mapa/"):
            return self._mapa()
        if u.path.startswith("/fotos/"):
            return self._static(S.DIR_FOTOS, u.path[len("/fotos/"):])
        if u.path in ("/", "/index.html"):
            return self._static(WEB, "index.html")
        return self._static(WEB, u.path.lstrip("/"))

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in POST:
            return self._send(404, {"erro": "rota inexistente"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"erro": "JSON inválido"})
        self._api(POST[u.path], body)

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


def main():
    global CONN
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=S.DB_PADRAO)
    a = ap.parse_args()
    if not os.path.exists(a.db):
        raise SystemExit(f"Banco {a.db} não existe — rode antes: python importar.py --aplicar")
    try:
        CONN = S.conectar(a.db)
    except S.EsquemaAntigo as e:
        raise SystemExit(str(e))
    if a.host not in ("127.0.0.1", "localhost"):
        raise SystemExit("Este servidor não tem autenticação: só pode escutar em 127.0.0.1 (uso local).")
    print(f"Sistema Morro da Cruz em http://{a.host}:{a.porta}  (Ctrl+C para sair)")
    ThreadingHTTPServer((a.host, a.porta), Handler).serve_forever()


if __name__ == "__main__":
    main()
