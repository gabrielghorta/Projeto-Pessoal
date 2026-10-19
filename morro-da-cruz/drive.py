"""Ligação direta com o Google Drive da obra (v15): a conta Google do responsável, conectada uma vez pelo site.

* Fotos de campo e anexos das notas fiscais (XML, PDF, imagem, laudo) sobem sozinhos para a pasta da obra, em
  subpastas por trecho e por mês, com nome claro. O arquivo original continua no servidor (backup e hash); o Drive é
  a cópia que a equipe abre. Nada é apagado no Drive; reenviar reaproveita o arquivo que já está lá (o nome leva o
  começo do hash).
* A planilha-índice dos documentos é lida pela mesma conta, sem precisar deixá-la pública.
* O id e o segredo do cliente OAuth e o token de atualização ficam no banco (parametros), nunca no código: o
  repositório é público.
* O servidor fala só com oauth2.googleapis.com e www.googleapis.com (no PythonAnywhere gratuito, .googleapis.com está na
  lista de sites liberados). O consentimento acontece no navegador, em accounts.google.com.
"""
import base64
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

import compras as C
import documentos as D
import servicos as S
from servicos import RegraViolada, _agora, _one, _rows, transacao

ESCOPO = "https://www.googleapis.com/auth/drive openid email"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REVOGAR = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true&fields=id,name,webViewLink"
PASTA_MIME = "application/vnd.google-apps.folder"
RETORNO = "/drive/retorno"
PARAM = {"cliente": "drive_cliente_id", "segredo": "drive_cliente_segredo", "token": "drive_token", "conta": "drive_conta",
         "pasta": "drive_pasta_id", "estado": "drive_oauth_estado", "erro": "drive_ultimo_erro", "conectado_em": "drive_conectado_em"}
MAX_TENTATIVAS = 5
FOTO_CATEGORIA = {"SINALIZACAO": "Sinalização", "EXECUCAO": "Execução", "CONCLUIDO": "Concluído"}
DOC_ROTULO = {"NFE_XML": "XML da NF-e", "NF_PDF": "PDF da nota", "NF_IMAGEM": "Imagem da nota", "LAUDO": "Laudo de inspeção",
              "ROMANEIO": "Romaneio", "OUTRO": "Documento"}
DOC_PASTA = {"NFE_XML": "01_Notas_Fiscais", "NF_PDF": "01_Notas_Fiscais", "NF_IMAGEM": "01_Notas_Fiscais",
             "LAUDO": "04_Laudos_de_Inspecao", "ROMANEIO": "02_Romaneios", "OUTRO": "99_Outros_Documentos"}


class SemConexao(Exception):
    """O servidor não alcançou o Google (rede, bloqueio da hospedagem): o envio fica na fila para depois."""


class ErroGoogle(Exception):
    def __init__(self, msg, status=None, definitivo=False, desconectar=False):
        super().__init__(msg)
        self.status, self.definitivo, self.desconectar = status, definitivo, desconectar


def _http(metodo, url, cabecalhos=None, corpo=None, tempo=60):
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SemConexao(f"o servidor não alcançou o Google ({getattr(e, 'reason', e)})") from None


HTTP = _http          # os testes trocam por um Google de mentira


def _json(dados):
    try:
        return json.loads(dados or b"{}")
    except ValueError:
        return {}


def _mensagem(dados, status):
    j = _json(dados)
    e = j.get("error")
    if isinstance(e, dict):
        return f"Google respondeu {status}: {e.get('message') or e.get('status') or ''}".strip()
    return f"Google respondeu {status}: {j.get('error_description') or e or (dados or b'')[:160].decode('utf-8', 'replace')}"


# ------------------------------------------------------------------ configuração (no banco, nunca no código)
def _p(conn, chave):
    return S.parametro(conn, PARAM[chave]) or ""


def _gravar(conn, chave, valor):
    D._gravar_parametro(conn, PARAM[chave], valor or "")


def _pasta_dos_documentos(conn):
    url = S.parametro(conn, "documentos_pasta_url")
    try:
        a = D.analisar_link(url) if url else None
    except RegraViolada:
        a = None
    return a["drive_id"] if a and a["google"] == "folders" else ""


def _credenciais(conn):
    return {"cliente": _p(conn, "cliente"), "segredo": _p(conn, "segredo"), "token": _p(conn, "token"),
            "pasta": _p(conn, "pasta") or _pasta_dos_documentos(conn)}


def obter_config(conn, completo=False):
    cr = _credenciais(conn)
    out = {"configurado": bool(cr["cliente"] and cr["segredo"]), "conectado": bool(cr["token"]), "conta": _p(conn, "conta"),
           "conectado_em": _p(conn, "conectado_em"), "pasta_id": cr["pasta"], "ultimo_erro": _p(conn, "erro"), "retorno": RETORNO}
    if completo:
        out.update(cliente_id=cr["cliente"], tem_segredo=bool(cr["segredo"]))
    return out


def salvar_config(conn, cliente_id, segredo, pasta_url, por):
    cliente_id, segredo, pasta_url = (str(x or "").strip() for x in (cliente_id, segredo, pasta_url))
    if cliente_id and not re.fullmatch(r"[0-9]+-[A-Za-z0-9_]+\.apps\.googleusercontent\.com", cliente_id):
        raise RegraViolada("O ID do cliente do Google termina em .apps.googleusercontent.com (Google Cloud › Clientes).")
    pasta_id = ""
    if pasta_url:
        a = D.analisar_link(pasta_url)
        if a["google"] != "folders":
            raise RegraViolada("A pasta da obra precisa ser o link de uma pasta do Drive (https://drive.google.com/drive/folders/…).")
        pasta_id = a["drive_id"]
    with transacao(conn):
        if cliente_id != _p(conn, "cliente"):            # outro cliente: a conexão antiga não vale mais
            _gravar(conn, "token", "")
            _gravar(conn, "conta", "")
        _gravar(conn, "cliente", cliente_id)
        if segredo:
            _gravar(conn, "segredo", segredo)
        if pasta_url:
            _gravar(conn, "pasta", pasta_id)


# ------------------------------------------------------------------ conexão (OAuth): uma vez, pelo navegador do responsável
def iniciar_conexao(conn, retorno_url, login):
    cr = _credenciais(conn)
    if not (cr["cliente"] and cr["segredo"]):
        raise RegraViolada("Salve antes o ID e o segredo do cliente do Google.")
    if not retorno_url.endswith(RETORNO) or not retorno_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise RegraViolada("Endereço de retorno inválido.")
    estado = secrets.token_urlsafe(24)
    with transacao(conn):
        _gravar(conn, "estado", json.dumps({"valor": estado, "login": login, "retorno": retorno_url, "expira": time.time() + 900}))
    q = {"client_id": cr["cliente"], "redirect_uri": retorno_url, "response_type": "code", "scope": ESCOPO,
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": estado}
    if _p(conn, "conta"):
        q["login_hint"] = _p(conn, "conta")
    return AUTH + "?" + urllib.parse.urlencode(q)


def consumir_estado(conn, estado):
    """O 'state' que o Google devolve precisa ser o deste sistema, ainda válido; vale uma vez só."""
    reg = _json(_p(conn, "estado").encode())
    with transacao(conn):
        _gravar(conn, "estado", "")
    if not reg or not secrets.compare_digest(str(reg.get("valor", "")), str(estado or "")) or reg.get("expira", 0) < time.time():
        raise RegraViolada("O pedido de conexão venceu ou não saiu deste sistema. Clique de novo em Conectar com o Google.")
    return reg


def trocar_codigo(cr, codigo, retorno_url):
    corpo = urllib.parse.urlencode({"code": codigo, "client_id": cr["cliente"], "client_secret": cr["segredo"],
                                    "redirect_uri": retorno_url, "grant_type": "authorization_code"}).encode()
    st, _, dados = HTTP("POST", TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo, 30)
    j = _json(dados)
    if st != 200:
        raise RegraViolada("O Google recusou a conexão: " + _mensagem(dados, st))
    if not j.get("refresh_token"):
        raise RegraViolada("O Google não devolveu a autorização permanente. Em myaccount.google.com › Segurança › Apps com "
                           "acesso, remova o acesso deste aplicativo e conecte de novo.")
    if "auth/drive" not in j.get("scope", "auth/drive"):
        raise RegraViolada("A autorização veio sem acesso ao Drive. Conecte de novo e marque a permissão do Google Drive.")
    return j


def _email(id_token):
    try:
        carga = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4))).get("email", "")
    except (AttributeError, IndexError, ValueError):
        return ""


def guardar_conexao(conn, tokens):
    with transacao(conn):
        _gravar(conn, "token", tokens["refresh_token"])
        _gravar(conn, "conta", _email(tokens.get("id_token")))
        _gravar(conn, "conectado_em", _agora())
        _gravar(conn, "erro", "")
    _ACESSO.clear()
    if tokens.get("access_token"):
        _ACESSO.update(token=tokens["access_token"], expira=time.time() + int(tokens.get("expires_in", 3600)),
                       refresh=tokens["refresh_token"])
    return _p(conn, "conta")


def desconectar(conn, por):
    tok = _p(conn, "token")
    if tok:
        try:                                            # revoga também no Google; sem rede, a conexão sai daqui assim mesmo
            HTTP("POST", REVOGAR, {"Content-Type": "application/x-www-form-urlencoded"},
                 urllib.parse.urlencode({"token": tok}).encode(), 15)
        except SemConexao:
            pass
    with transacao(conn):
        _gravar(conn, "token", "")
        _gravar(conn, "conta", "")
    _ACESSO.clear()


# ------------------------------------------------------------------ chamadas ao Drive
_ACESSO = {}
_PASTAS = {}


def _token_acesso(cr, novo=False):
    if not novo and _ACESSO.get("refresh") == cr["token"] and _ACESSO.get("expira", 0) > time.time() + 60:
        return _ACESSO["token"]
    corpo = urllib.parse.urlencode({"client_id": cr["cliente"], "client_secret": cr["segredo"], "refresh_token": cr["token"],
                                    "grant_type": "refresh_token"}).encode()
    st, _, dados = HTTP("POST", TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo, 30)
    j = _json(dados)
    if st != 200:
        if j.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client"):
            raise ErroGoogle("A conexão com o Google foi revogada ou venceu: em Documentos, clique em Conectar com o Google de novo.",
                             st, definitivo=False, desconectar=True)
        raise ErroGoogle(_mensagem(dados, st), st)
    _ACESSO.update(token=j["access_token"], expira=time.time() + int(j.get("expires_in", 3600)), refresh=cr["token"])
    return j["access_token"]


def _q(texto):
    return str(texto).replace("\\", "\\\\").replace("'", "\\'")


class Drive:
    def __init__(self, cr):
        if not cr["token"]:
            raise ErroGoogle("O Google Drive não está conectado.", desconectar=False)
        self.cr = cr

    def _req(self, metodo, url, corpo=None, tipo="application/json; charset=UTF-8", extra=None, tempo=60, bruto=False):
        for tentativa in (1, 2):
            cab = {"Authorization": "Bearer " + _token_acesso(self.cr, novo=tentativa == 2)}
            if corpo is not None:
                cab["Content-Type"] = tipo
            cab.update(extra or {})
            st, h, dados = HTTP(metodo, url, cab, corpo, tempo)
            if st == 401 and tentativa == 1:            # token de acesso vencido: pede outro e repete uma vez
                continue
            if st >= 400:
                raise ErroGoogle(_mensagem(dados, st), st, definitivo=st in (400, 403, 404))
            return (h, dados) if bruto else _json(dados)

    def item(self, fid):
        return self._req("GET", f"{API}/files/{urllib.parse.quote(fid)}?fields=id,name,webViewLink,mimeType,trashed&supportsAllDrives=true")

    def buscar(self, pai, nome, pasta):
        q = f"'{_q(pai)}' in parents and name = '{_q(nome)}' and trashed = false and mimeType {'=' if pasta else '!='} '{PASTA_MIME}'"
        url = f"{API}/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id,name,webViewLink)", "pageSize": 5,
                                                         "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        fs = self._req("GET", url).get("files") or []
        return fs[0] if fs else None

    def pasta(self, raiz, caminho):
        """Pasta do caminho a partir da pasta da obra, criando as que faltarem (nunca apaga nem renomeia)."""
        atual = _PASTAS.get((raiz, ""))
        if not atual:
            r = self.item(raiz)
            if r.get("mimeType") != PASTA_MIME or r.get("trashed"):
                raise ErroGoogle("O link da pasta da obra não é uma pasta ativa do Drive.", definitivo=True)
            atual = _PASTAS[(raiz, "")] = {"id": r["id"], "name": r["name"], "webViewLink": r.get("webViewLink")}
        feito = ""
        for nome in [s.strip() for s in caminho.split("/") if s.strip()]:
            feito = f"{feito}/{nome}" if feito else nome
            if (raiz, feito) not in _PASTAS:
                achada = self.buscar(atual["id"], nome, pasta=True)
                if not achada:
                    achada = self._req("POST", f"{API}/files?fields=id,name,webViewLink&supportsAllDrives=true",
                                       json.dumps({"name": nome, "mimeType": PASTA_MIME, "parents": [atual["id"]]}).encode())
                _PASTAS[(raiz, feito)] = achada
            atual = _PASTAS[(raiz, feito)]
        return atual

    def enviar(self, dados, nome, mime, pasta_id):
        ja = self.buscar(pasta_id, nome, pasta=False)      # já enviado antes (mesmo nome, que leva o hash): reaproveita
        if ja:
            return ja
        h, _ = self._req("POST", UPLOAD, json.dumps({"name": nome, "parents": [pasta_id]}).encode(),
                         extra={"X-Upload-Content-Type": mime or "application/octet-stream",
                                "X-Upload-Content-Length": str(len(dados))}, bruto=True)
        destino = h.get("Location") if h else None
        if not destino or not destino.startswith("https://www.googleapis.com/"):
            raise ErroGoogle("O Google não abriu o envio do arquivo (sem endereço de envio).")
        return self._req("PUT", destino, dados, tipo=mime or "application/octet-stream", tempo=180)

    def exportar_csv(self, fid):
        _, dados = self._req("GET", f"{API}/files/{urllib.parse.quote(fid)}/export?mimeType=text%2Fcsv", bruto=True, tempo=90)
        return dados.decode("utf-8-sig", errors="replace")


def testar(conn):
    cr = _credenciais(conn)
    if not cr["pasta"]:
        raise RegraViolada("Informe a pasta da obra no Drive.")
    try:
        r = Drive(cr).item(cr["pasta"])
    except SemConexao as e:
        raise RegraViolada(f"Sem acesso ao Google pelo servidor: {e}.") from None
    except ErroGoogle as e:
        _tratar_desconexao(conn, e)
        raise RegraViolada(str(e)) from None
    if r.get("mimeType") != PASTA_MIME:
        raise RegraViolada("O link da pasta da obra não é uma pasta do Drive.")
    return {"pasta": r.get("name"), "pasta_link": r.get("webViewLink"), "conta": _p(conn, "conta")}


def exportar_indice(conn, url_csv):
    """Lê a planilha-índice pela conta conectada (não precisa estar pública). O Drive exporta a primeira aba."""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{10,})/export", url_csv)
    if not m:
        return D.baixar_csv(url_csv)                      # planilha publicada na web: lê pelo endereço público
    try:
        return Drive(_credenciais(conn)).exportar_csv(m.group(1))
    except SemConexao as e:
        raise RegraViolada(f"Sem acesso ao Google pelo servidor: {e}.") from None
    except ErroGoogle as e:
        _tratar_desconexao(conn, e)
        raise RegraViolada(f"Não consegui ler a planilha-índice pelo Drive: {e}") from None


def _tratar_desconexao(conn, e):
    if e.desconectar:
        with transacao(conn):
            _gravar(conn, "token", "")
            _gravar(conn, "erro", str(e))
        _ACESSO.clear()


# ------------------------------------------------------------------ fila: nome e pasta de cada arquivo
def _limpo(texto, maximo=180):
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", str(texto or ""))
    return re.sub(r"\s+", " ", t).strip(" .-")[:maximo] or "arquivo"


def _destino_foto(conn, f):
    nome = S.nome_alvo(conn, f["alvo_tipo"], f["alvo_id"]) or f["alvo_id"]
    partes = str(nome).split("_")
    if re.fullmatch(r"Zona\d\d", partes[0]):
        zona, resto = partes[0], "_".join(partes[1:])
    elif partes[0].upper() == "ADUTORA":
        zona, resto = "Adutora", "_".join(partes[1:])
    else:
        zona, resto = "Outros", str(nome)
    quando = str(f["data_hora"] or "")[:16].replace("T", " ").replace(":", "h")
    ext = f["arquivo"].rsplit(".", 1)[-1]
    caminho = f"03_EXECUCAO_DE_CAMPO/01_Fotos_por_Trecho/{zona}/{_limpo(resto, 80)}"
    titulo = _limpo(f"Morro da Cruz - Foto de Campo - {resto} - {FOTO_CATEGORIA.get(f['categoria'], f['categoria'])} - {quando}")
    return caminho, f"{titulo} ({f['sha256'][:8]}).{ext}"


def _destino_documento(conn, d):
    ext = d["arquivo"].rsplit(".", 1)[-1]
    mes = str(d["enviado_em"] or "")[:7]
    rotulo = DOC_ROTULO.get(d["tipo"], "Documento")
    nf = _one(conn, "SELECT numero, fornecedor, data_emissao FROM notas_fiscais WHERE documento_id=? ORDER BY id LIMIT 1", d["id"])
    if nf:
        mes = str(nf["data_emissao"] or mes)[:7]
        titulo = f"Morro da Cruz - Nota Fiscal {nf['numero']} - {nf['fornecedor'] or 'fornecedor'} - {nf['data_emissao'] or mes} - {rotulo}"
    elif d["tipo"] == "LAUDO":
        ins = _one(conn, "SELECT laudo FROM inspecoes WHERE documento_id=? ORDER BY id LIMIT 1", d["id"])
        titulo = f"Morro da Cruz - Laudo de Inspeção - {ins['laudo'] if ins else d['nome_original'] or ''} - {str(d['enviado_em'])[:10]}"
    else:
        base = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", str(d["nome_original"] or ""))
        titulo = f"Morro da Cruz - {rotulo} - {base or 'sem nome'} - {str(d['enviado_em'])[:10]}"
    caminho = f"04_COMPRAS_E_ALMOXARIFADO/{DOC_PASTA.get(d['tipo'], '99_Outros_Documentos')}/{mes or 'sem-data'}"
    return caminho, f"{_limpo(titulo)} ({d['sha256'][:8]}).{ext}"


def sincronizar_fila(conn):
    """Põe na fila as fotos válidas e os anexos ainda não enviados (inclusive os de antes da conexão)."""
    fotos = _rows(conn.execute("""SELECT * FROM fotos f WHERE sha256 IS NOT NULL
                                    AND COALESCE(validacao, '') NOT IN ('INVALIDA', 'ARQUIVO_AUSENTE')
                                    AND NOT EXISTS (SELECT 1 FROM envios_drive e WHERE e.origem='FOTO' AND e.ref_id=f.id)
                                  ORDER BY id"""))
    docs = _rows(conn.execute("""SELECT * FROM documentos d
                                  WHERE NOT EXISTS (SELECT 1 FROM envios_drive e WHERE e.origem='DOCUMENTO' AND e.ref_id=d.id)
                                  ORDER BY id"""))
    if not fotos and not docs:
        return 0
    agora = _agora()
    with transacao(conn):
        for origem, lista, destino in (("FOTO", fotos, _destino_foto), ("DOCUMENTO", docs, _destino_documento)):
            for x in lista:
                caminho, nome = destino(conn, x)
                conn.execute("""INSERT INTO envios_drive(origem, ref_id, sha256, arquivo, nome, caminho, mime, criado_em)
                                VALUES (?,?,?,?,?,?,?,?)""", (origem, x["id"], x["sha256"], x["arquivo"], nome, caminho, x["mime"], agora))
    return len(fotos) + len(docs)


def _caminho_local(env, dir_fotos, dir_docs):
    return os.path.join(dir_fotos if env["origem"] == "FOTO" else dir_docs, env["arquivo"])


def processar(conn, trava, dir_fotos, limite=4, tempo=25):
    """Envia até `limite` arquivos da fila (ou até `tempo` segundos). A rede fica FORA da trava do banco: o sistema
    continua atendendo enquanto o arquivo sobe."""
    t0, enviados = time.monotonic(), []
    with trava:
        cr = _credenciais(conn)
        if not cr["token"]:
            return {"conectado": False}
        if not cr["pasta"]:
            return {"conectado": True, "erro": "Informe a pasta da obra no Drive."}
        sincronizar_fila(conn)
        ids = [r[0] for r in conn.execute("SELECT id FROM envios_drive WHERE status='PENDENTE' ORDER BY id LIMIT ?", (limite,))]
        dir_docs = C.documento_dir(conn)
    erro = None
    for eid in ids:
        if time.monotonic() - t0 > tempo:
            break
        with trava:
            env = _one(conn, "SELECT * FROM envios_drive WHERE id=?", eid)
        if not env or env["status"] != "PENDENTE":
            continue
        try:
            with open(_caminho_local(env, dir_fotos, dir_docs), "rb") as f:
                dados = f.read()
        except OSError:
            with trava:
                _falhou(conn, eid, "arquivo original ausente no servidor", definitivo=True)
            continue
        try:
            drive = Drive(cr)
            pasta = drive.pasta(cr["pasta"], env["caminho"])
            arq = drive.enviar(dados, env["nome"], env["mime"], pasta["id"])
        except SemConexao as e:
            erro = str(e)
            with trava:
                _falhou(conn, eid, erro, definitivo=False)
            break
        except ErroGoogle as e:
            erro = str(e)
            with trava:
                _falhou(conn, eid, erro, definitivo=e.definitivo)
                _tratar_desconexao(conn, e)
            if e.desconectar:
                break
            continue
        with trava:
            with transacao(conn):
                conn.execute("""UPDATE envios_drive SET status='ENVIADO', tentativas=tentativas+1, ultimo_erro=NULL, drive_id=?,
                                  drive_link=?, pasta_id=?, pasta_nome=?, pasta_link=?, enviado_em=? WHERE id=?""",
                             (arq.get("id"), arq.get("webViewLink"), pasta.get("id"), pasta.get("name"), pasta.get("webViewLink"),
                              _agora(), eid))
        enviados.append(eid)
    with trava:
        pend = conn.execute("SELECT COUNT(*) FROM envios_drive WHERE status='PENDENTE'").fetchone()[0]
    return {"conectado": True, "enviados": len(enviados), "pendentes": pend, "erro": erro}


def _falhou(conn, eid, erro, definitivo):
    with transacao(conn):
        conn.execute("""UPDATE envios_drive SET tentativas=tentativas+1, ultimo_erro=?,
                          status=CASE WHEN ? OR tentativas+1 >= ? THEN 'ERRO' ELSE 'PENDENTE' END WHERE id=?""",
                     (str(erro)[:500], 1 if definitivo else 0, MAX_TENTATIVAS, eid))


def reenviar(conn, envio_id):
    with transacao(conn):
        n = conn.execute("UPDATE envios_drive SET status='PENDENTE', tentativas=0 WHERE id=? AND status='ERRO'", (envio_id,)).rowcount
    if not n:
        raise RegraViolada("Envio não encontrado ou sem erro.")


# ------------------------------------------------------------------ o que a tela mostra
def resumo(conn, completo=False):
    out = obter_config(conn, completo)
    cont = dict(conn.execute("SELECT status, COUNT(*) FROM envios_drive GROUP BY status").fetchall())
    faltam = conn.execute("""SELECT (SELECT COUNT(*) FROM fotos f WHERE sha256 IS NOT NULL
                                       AND COALESCE(validacao,'') NOT IN ('INVALIDA','ARQUIVO_AUSENTE')
                                       AND NOT EXISTS (SELECT 1 FROM envios_drive e WHERE e.origem='FOTO' AND e.ref_id=f.id))
                                 + (SELECT COUNT(*) FROM documentos d
                                       WHERE NOT EXISTS (SELECT 1 FROM envios_drive e WHERE e.origem='DOCUMENTO' AND e.ref_id=d.id))"""
                          ).fetchone()[0]
    out["contagem"] = {"enviados": cont.get("ENVIADO", 0), "na_fila": cont.get("PENDENTE", 0) + faltam, "com_erro": cont.get("ERRO", 0)}
    out["recentes"] = _rows(conn.execute("""SELECT id, origem, nome, caminho, status, ultimo_erro, drive_link, pasta_nome, pasta_link,
                                                   enviado_em, criado_em FROM envios_drive
                                             WHERE status IN ('ENVIADO','ERRO') ORDER BY COALESCE(enviado_em, criado_em) DESC, id DESC
                                             LIMIT 15"""))
    return out


def por_ref(conn, origem, ids):
    ids = [int(i) for i in ids if i is not None]
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    return {r["ref_id"]: r for r in _rows(conn.execute(
        f"""SELECT ref_id, status, caminho, nome, ultimo_erro, drive_link, pasta_nome, pasta_link FROM envios_drive
            WHERE origem=? AND ref_id IN ({marcas})""", (origem, *ids)))}
