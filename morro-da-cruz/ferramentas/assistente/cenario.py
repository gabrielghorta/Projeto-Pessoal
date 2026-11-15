"""Apoio dos roteiros do assistente (D-219): um banco de demonstração descartável, com equipes e um login de cada
perfil, o servidor de verdade numa thread e uma "tela" que conversa pelo HTTP como o navegador faz (mensagem, toque no
botão, edição do campo e o toque final, que grava pela rota de sempre). Nada aqui toca o banco do site."""
import http.cookiejar
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
import acesso as A  # noqa: E402
import demo  # noqa: E402
import equipes as EQ  # noqa: E402
import planejamento as P  # noqa: E402
import relogio as RL  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402

SENHA = demo.SENHA
EXTRAS = (("sup.demo", "Supervisor (demo)", "SUPERVISOR"), ("rh.demo", "RH (demo)", "RH"))


def preparar_banco(pasta, modelo=None):
    """Monta (ou copia de `modelo`) a demonstração em <pasta>/obra.db e acrescenta o que os roteiros usam: duas equipes
    com integrantes, o encarregado de uma delas (programada na Zona 03 hoje) e um supervisor e um RH."""
    db = os.path.join(pasta, "obra.db")
    if modelo:
        os.makedirs(os.path.join(pasta, "fotos"), exist_ok=True)
        shutil.copy(modelo, db)
    else:
        demo.criar(pasta)
    c = S.conectar(db)
    try:
        if not c.execute("SELECT 1 FROM usuarios WHERE login='enc.demo'").fetchone():
            a1 = EQ.criar(c, "ANKARA", "", "roteiro do assistente")
            e1 = EQ.criar(c, "E1", "", "roteiro do assistente")
            for eq, nome in ((a1, "Integrante de teste A"), (e1, "Integrante de teste B")):
                EQ.membro(c, eq, nome, "ajudante")
            with S.transacao(c):
                for login, nome, perfil in EXTRAS:
                    A.criar_usuario(c, login, nome, perfil, SENHA, None, "roteiro do assistente")
                A.criar_usuario(c, "enc.demo", "Encarregado (demo)", "EQUIPE", SENHA, e1, "roteiro do assistente")
                trecho = c.execute("SELECT id FROM trechos WHERE vigente=1 AND frente_id='Zona03' ORDER BY ponto LIMIT 1").fetchone()[0]
                P.programar(c, RL.hoje().isoformat(), e1, "TRECHO", trecho, "ASSENTAMENTO", "roteiro do assistente")
    finally:
        c.close()
    return db


class Servidor:
    """O server.py de verdade numa thread, sobre o banco do roteiro."""

    def __init__(self, db):
        self.db, self.conn = db, S.conectar(db)
        self._antes = (server.CONN, server.DB_PATH, server.DIR_FOTOS)
        server.CONN, server.DB_PATH, server.DIR_FOTOS = self.conn, db, os.path.join(os.path.dirname(db), "fotos")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def fechar(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        server.CONN, server.DB_PATH, server.DIR_FOTOS = self._antes
        self.conn.close()


class Tela:
    """O que o web/assistente.js faz, sem navegador: guarda a conversa, o rascunho e os botões, e manda cada passo."""

    def __init__(self, url, login, senha=SENHA, registro=None):
        self.url, self.login, self.registro = url, login, registro if registro is not None else []
        sem_proxy = urllib.request.ProxyHandler({})
        self.op = urllib.request.build_opener(sem_proxy, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        st, r = self.req("/api/login", {"login": login, "senha": senha})
        assert st == 200, r
        self.usuario = r["usuario"]
        self.conversa, self.rascunho, self.botoes, self.ultima, self.chamadas, self.tokens = [], None, [], None, 0, 0
        self.pergunta = None                      # a única parte da conversa que volta ao servidor (D-226)

    def req(self, rota, corpo=None):
        r = urllib.request.Request(self.url + rota, data=None if corpo is None else json.dumps(corpo).encode(),
                                   headers={"Content-Type": "application/json", "X-MC": "1"}, method="GET" if corpo is None else "POST")
        try:
            with self.op.open(r, timeout=90) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def _nota(self, quem, texto):
        self.registro.append(f"{quem}: {texto}")

    def _receber(self, r):
        self.ultima = r
        if "rascunho" in r:
            self.rascunho = r["rascunho"]
        if r.get("situacao", "OK") == "OK":
            self.botoes = r.get("botoes") or []
            self.pergunta = r.get("pergunta")
            if r.get("resposta"):
                self.conversa.append({"de": "a", "texto": r["resposta"]})
                self._nota("IA", r["resposta"] + (" [" + " | ".join(b["rotulo"] for b in self.botoes) + "]" if self.botoes else ""))
        else:
            self._nota("AVISO", r.get("aviso"))
        return r

    def _cru(self):
        return {"tipo": self.rascunho["tipo"], "campos": self.rascunho["campos"]} if self.rascunho else None

    def dizer(self, texto):
        self._nota(self.login, texto)
        st, r = self.req("/api/assistente/mensagem", {"texto": texto, "pergunta": self.pergunta, "rascunho": self._cru(),
                                                     "opcoes": self.botoes})
        assert st == 200, (st, r)
        if r.get("situacao") == "OK":
            self.conversa.append({"de": "u", "texto": texto})
            if r.get("resposta"):                       # a fala entra depois da pergunta
                pass
        uso = r.get("uso") or {}
        self.chamadas += uso.get("chamadas", 0)
        self.tokens += uso.get("tokens", 0)
        for passo in uso.get("rastro") or []:
            self.registro.append(f"    · {passo['funcao']}({json.dumps(passo['argumentos'], ensure_ascii=False)}) → "
                                 f"{json.dumps(passo['resultado'], ensure_ascii=False, default=str)[:300]}")
        self.registro.append(f"    ({uso.get('chamadas', 0)} chamada(s), {uso.get('tokens', 0)} tokens; {', '.join(uso.get('ferramentas') or []) or 'sem função'})")
        return self._receber(r)

    def tocar(self, trecho_do_rotulo):
        b = next((x for x in self.botoes if trecho_do_rotulo.lower() in x["rotulo"].lower()), None)
        assert b, f"botão '{trecho_do_rotulo}' não está na tela: {[x['rotulo'] for x in self.botoes]}"
        self._nota(self.login, f"[toca em “{b['rotulo']}”]")
        self.conversa.append({"de": "u", "texto": b["rotulo"]})
        if b.get("sub"):                                # grupo: os itens dele aparecem sem chamar ninguém
            self.botoes, self.pergunta = b["sub"], b["pergunta"]
            self.conversa.append({"de": "a", "texto": b["pergunta"]})
            self._nota("IA", b["pergunta"] + " [" + " | ".join(x["rotulo"] for x in self.botoes) + "]")
            return {"situacao": "OK", "resposta": b["pergunta"], "botoes": self.botoes}
        if b.get("aplicar"):
            corpo = {"rascunho": self._cru(), "mudar": b["aplicar"]}
            if b.get("tipo") and (not self.rascunho or self.rascunho["tipo"] != b["tipo"]):
                corpo["iniciar"] = b["tipo"]
            st, r = self.req("/api/assistente/rascunho", corpo)
            assert st == 200, (st, r)
            return self._receber(r)
        if b.get("texto"):
            self.conversa.pop()
            return self.dizer(b["texto"])
        return b

    def atalho(self, tipo, chuva=False):
        self._nota(self.login, f"[atalho {tipo}{' · chuva' if chuva else ''}]")
        st, r = self.req("/api/assistente/rascunho", {"rascunho": self._cru(), "iniciar": tipo, "chuva": chuva})
        assert st == 200, (st, r)
        return self._receber(r)

    def editar(self, campo, valor):
        self._nota(self.login, f"[no formulário: {campo} = {valor}]")
        st, r = self.req("/api/assistente/rascunho", {"rascunho": self._cru(), "mudar": {campo: valor}})
        assert st == 200, (st, r)
        return self._receber(r)

    def gravar(self):
        """O toque da pessoa: o corpo conferido vai para a rota de sempre."""
        assert self.rascunho and self.rascunho["pronto"], f"rascunho não está pronto: {self.rascunho and self.rascunho['faltam']}"
        st, r = self.req(self.rascunho["rota"], self.rascunho["corpo"])
        self._nota(self.login, f"[toca em “{self.rascunho['confirmar']}”] → {self.rascunho['rota']} respondeu {st}: "
                               f"{json.dumps(r, ensure_ascii=False, default=str)[:160]}")
        return st, r

    def linhas(self):
        return {a: b for a, b in (self.rascunho or {}).get("linhas", [])}


def pasta_temporaria():
    return tempfile.mkdtemp(prefix="assistente_")
