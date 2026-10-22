"""Documentos oficiais da obra (v14) — catálogo dos arquivos guardados no Google Drive.

* O sistema guarda o ENDEREÇO de cada arquivo (link do Drive) e o que é preciso para achá-lo sem abrir: título claro,
  pasta, tipo, revisão, data e código original. O arquivo continua no Drive: nada é enviado nem copiado para o servidor.
* Só links do Google Drive/Docs (https://drive.google.com/… ou https://docs.google.com/…).
* Nada é apagado: retirar da lista marca ativo=0 com quem, quando e por quê; o resto fica na auditoria.
* Índice: a planilha-índice da pasta (nome antigo, nome novo, pasta, tipo, revisão, data, link, observação) entra
  por CSV ou pelo link da própria planilha. O mesmo arquivo (mesmo id do Drive) atualiza a linha que já existe; arquivo
  que saiu do índice NÃO é retirado sozinho: aparece como "fora do índice" para alguém decidir.
"""
import csv
import io
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import servicos as S
from servicos import RegraViolada, _agora, _one, transacao

HOSTS_DRIVE = ("drive.google.com", "docs.google.com")
MAX_CSV = 12 * 1024 * 1024
MAX_LINHAS = 20000
CAMPOS = ("titulo", "pasta", "tipo", "revisao", "data_documento", "codigo", "nome_anterior", "descricao", "link")
TAMANHO = {"titulo": 300, "pasta": 300, "tipo": 120, "revisao": 40, "codigo": 200, "nome_anterior": 300, "descricao": 1000}
COLUNAS = {   # cabeçalho da planilha-índice (sem acento, minúsculo) → campo
    "titulo": ("nome novo", "novo nome", "titulo", "nome", "nome do arquivo", "arquivo", "documento"),
    "nome_anterior": ("nome antigo", "nome anterior", "nome original"),
    "pasta": ("pasta", "pasta destino", "pasta de destino", "caminho", "local"),
    "tipo": ("tipo", "tipo de documento", "formato", "extensao"),
    "revisao": ("revisao", "rev", "versao"),
    "data_documento": ("data", "data do documento"),
    "link": ("link", "url", "endereco", "link do drive", "link no drive"),
    "descricao": ("observacao", "observacoes", "obs", "descricao"),
    "codigo": ("codigo", "codigo original"),
}
TIPO_GOOGLE = {"document": "DOC GOOGLE", "spreadsheets": "PLANILHA GOOGLE", "presentation": "APRESENTAÇÃO GOOGLE",
               "folders": "PASTA", "forms": "FORMULÁRIO GOOGLE", "drawings": "DESENHO GOOGLE"}
EXTENSOES = ("pdf", "dwg", "dxf", "xlsx", "xlsm", "xlsb", "xls", "csv", "ods", "docx", "doc", "odt", "rtf", "pptx", "ppt", "odp",
             "jpg", "jpeg", "png", "html", "kmz", "kml", "zip", "rar", "7z", "txt", "xml", "json", "mp4", "md")
# arquivos do Office (e equivalentes) abrem no próprio Google Docs, Planilhas ou Apresentações, sem baixar
EDITOR_GOOGLE = {**{e: "document" for e in ("doc", "docx", "odt", "rtf")},
                 **{e: "spreadsheets" for e in ("xls", "xlsx", "xlsm", "ods", "csv")},
                 **{e: "presentation" for e in ("ppt", "pptx", "odp")}}
# pastas de trabalho (conversas e tabelas da IA, caches, duplicatas): ficam no Drive, mas fora da lista da obra
PASTAS_TRABALHO = ("07_IA_CHATGPT_E_CLAUDE", "99_TEMPORARIOS_E_SISTEMA")


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _limpo(v, campo):
    v = re.sub(r"\s+", " ", str(v or "")).strip()
    if campo in TAMANHO and len(v) > TAMANHO[campo]:
        raise RegraViolada(f"{campo}: no máximo {TAMANHO[campo]} caracteres.")
    return v or None


# ------------------------------------------------------------------ link do Drive
def analisar_link(link):
    """Valida o link (só Google Drive/Docs, https) e tira o id do arquivo e o tipo de item do Google."""
    link = str(link or "").strip()
    u = urllib.parse.urlparse(link)
    if u.scheme != "https" or (u.hostname or "").lower() not in HOSTS_DRIVE:
        raise RegraViolada("Use um link do Google Drive (https://drive.google.com/… ou https://docs.google.com/…).")
    m = re.search(r"/(file|document|spreadsheets|presentation|forms|drawings)/d/(?:e/)?([A-Za-z0-9_-]{10,})", u.path)
    tipo, did = (m.group(1), m.group(2)) if m else (None, None)
    if not m:
        f = re.search(r"/folders/([A-Za-z0-9_-]{10,})", u.path)
        if f:
            tipo, did = "folders", f.group(1)
        else:
            q = urllib.parse.parse_qs(u.query).get("id")
            if q and re.fullmatch(r"[A-Za-z0-9_-]{10,}", q[0]):
                tipo, did = "file", q[0]
    return {"link": link, "drive_id": did, "google": tipo}


def _extensao(titulo):
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", str(titulo or "").strip())
    return m.group(1).lower() if m else None


def link_baixar(link, titulo=None):
    """Download direto pelo Drive (None para pasta ou link sem id). Arquivo do Office aberto pelo Google (link
    docs.google.com/…?rtpof=true, nome com extensão) baixa o arquivo original; documento nativo do Google é exportado."""
    try:
        a = analisar_link(link)
    except RegraViolada:
        return None
    did, ext = a["drive_id"], _extensao(titulo)
    if not did or a["google"] == "folders":
        return None
    if a["google"] == "file" or ext in EXTENSOES:
        return f"https://drive.google.com/uc?export=download&id={did}"
    return {"document": f"https://docs.google.com/document/d/{did}/export?format=docx",
            "spreadsheets": f"https://docs.google.com/spreadsheets/d/{did}/export?format=xlsx",
            "presentation": f"https://docs.google.com/presentation/d/{did}/export/pptx"}.get(a["google"])


def link_abrir(link, titulo=None):
    """Ver na internet, sem baixar: Word/Excel/PowerPoint no Google Docs/Planilhas/Apresentações; PDF, imagem, DWG e
    o resto na visualização do Drive; pasta e documento nativo do Google, pelo próprio link."""
    try:
        a = analisar_link(link)
    except RegraViolada:
        return link
    did, ext = a["drive_id"], _extensao(titulo)
    if not did or a["google"] == "folders":
        return a["link"]
    editor = EDITOR_GOOGLE.get(ext)
    if editor:
        return f"https://docs.google.com/{editor}/d/{did}/edit?rtpof=true&usp=drivesdk"
    if a["google"] == "file" or ext:
        return f"https://drive.google.com/file/d/{did}/view?usp=drivesdk"
    return a["link"]


def tipo_do_arquivo(titulo, link):
    ext = _extensao(titulo)
    if ext in EXTENSOES:
        return ext.upper()
    try:
        return TIPO_GOOGLE.get(analisar_link(link)["google"])
    except RegraViolada:
        return None


def data_iso(v):
    """AAAA-MM-DD a partir de 2026-10-13, 13/10/2026, 13-10-26 ou '2026-10-13 00:00:00'; vazio → None."""
    v = str(v or "").strip()
    if not v:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        a, mes, d = m.groups()
    else:
        m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$", v)
        if not m:
            raise RegraViolada(f"Data não reconhecida: {v} (use AAAA-MM-DD ou DD/MM/AAAA).")
        d, mes, a = m.groups()
        a = ("20" + a) if len(a) == 2 else a
    try:
        return date(int(a), int(mes), int(d)).isoformat()
    except ValueError:
        raise RegraViolada(f"Data inválida: {v}.") from None


def codigo_do_titulo(titulo):
    """Código original entre parênteses no fim do nome organizado: '… (A.RED.SSB-D014.V03.T01).pdf' → A.RED.SSB-D014.V03.T01."""
    m = re.search(r"\(([^()]{2,})\)\s*(\.[A-Za-z0-9]{2,5})?\s*$", str(titulo or ""))
    return m.group(1).strip() if m else None


ACENTOS = {"medicao": "medição", "medicoes": "medições", "referencia": "referência", "licitacao": "licitação",
           "licencas": "licenças", "autorizacoes": "autorizações", "oficios": "ofícios", "correspondencias": "correspondências",
           "execucao": "execução", "revisao": "revisão", "revisoes": "revisões", "memorias": "memórias", "calculo": "cálculo",
           "especificacoes": "especificações", "inventarios": "inventários", "tecnico": "técnico", "temporarios": "temporários",
           "programacao": "programação", "ocorrencias": "ocorrências", "interferencias": "interferências",
           "conexoes": "conexões", "evidencias": "evidências", "conciliacao": "conciliação", "ultima": "última",
           "orcamento": "orçamento", "pecas": "peças", "relatorios": "relatórios", "fotografico": "fotográfico"}


def _acentuar(texto):
    def troca(m):
        w = m.group(0)
        n = ACENTOS.get(w.lower())
        return w if not n else (n.capitalize() if w[:1].isupper() else n)
    return re.sub(r"[A-Za-z]+", troca, texto)


def pasta_rotulo(pasta):
    """'01_DOCUMENTOS_OFICIAIS / 04_Medicao' → 'Documentos oficiais / Medição' (só na tela; a pasta no Drive não muda)."""
    partes = [p.strip() for p in re.split(r"\s*[/\\>]\s*", str(pasta or "")) if p.strip()]
    out = []
    for p in partes:
        p = re.sub(r"^\d{1,3}[_\-. ]+", "", p).replace("_", " ").strip()
        out.append(_acentuar(p[:1].upper() + p[1:].lower() if p.isupper() else p))
    return " / ".join(out) or "Sem pasta"


def _pasta(pasta):
    partes = [p.strip() for p in re.split(r"\s*[/\\>]\s*", str(pasta or "")) if p.strip()]
    return " / ".join(partes) or None


# ------------------------------------------------------------------ catálogo
def _linha(r):
    d = dict(r)
    d["pasta_rotulo"] = pasta_rotulo(d["pasta"])
    d["formato"] = tipo_do_arquivo(d["titulo"], d["link"])
    d["abrir"] = link_abrir(d["link"], d["titulo"])
    d["baixar"] = link_baixar(d["link"], d["titulo"])
    return d


def listar(conn):
    docs = [_linha(r) for r in conn.execute("SELECT * FROM documentos_obra WHERE ativo=1 ORDER BY pasta, titulo, id")]
    return {"documentos": docs, "total": len(docs), "config": obter_config(conn),
            "pastas": sorted({d["pasta"] for d in docs})}


def _validar(campos):
    v = {k: _limpo(campos.get(k), k) for k in CAMPOS if k not in ("link", "data_documento", "pasta")}
    if not v["titulo"]:
        raise RegraViolada("Informe o nome do documento.")
    v["pasta"] = _pasta(campos.get("pasta"))
    if not v["pasta"]:
        raise RegraViolada("Informe a pasta do documento.")
    if len(v["pasta"]) > TAMANHO["pasta"]:
        raise RegraViolada(f"pasta: no máximo {TAMANHO['pasta']} caracteres.")
    a = analisar_link(campos.get("link"))
    v["link"], v["drive_id"] = a["link"], a["drive_id"]
    v["data_documento"] = data_iso(campos.get("data_documento"))
    v["tipo"] = v["tipo"] or (tipo_do_arquivo(v["titulo"], v["link"]) or "").upper() or None   # do índice: como veio
    v["codigo"] = v["codigo"] or codigo_do_titulo(v["titulo"])
    return v


def _ativo_mesmo_arquivo(conn, drive_id, link, exceto=None):
    if drive_id:
        r = _one(conn, "SELECT * FROM documentos_obra WHERE ativo=1 AND drive_id=? AND id IS NOT ?", drive_id, exceto)
    else:
        r = _one(conn, "SELECT * FROM documentos_obra WHERE ativo=1 AND link=? AND id IS NOT ?", link, exceto)
    return r


def cadastrar(conn, campos, por, origem="MANUAL"):
    if not str(por or "").strip():
        raise RegraViolada("Cadastro de documento exige o usuário.")
    v = _validar(campos)
    outro = _ativo_mesmo_arquivo(conn, v["drive_id"], v["link"])
    if outro:
        raise RegraViolada(f"Este arquivo já está na lista como «{outro['titulo']}».")
    with transacao(conn):
        return conn.execute(
            f"""INSERT INTO documentos_obra({",".join(CAMPOS)},drive_id,origem,criado_por,criado_em)
                VALUES ({",".join("?" * len(CAMPOS))},?,?,?,?)""",
            tuple(v[k] for k in CAMPOS) + (v["drive_id"], origem, por, _agora())).lastrowid


def alterar(conn, documento_id, campos, por):
    atual = _one(conn, "SELECT * FROM documentos_obra WHERE id=? AND ativo=1", documento_id)
    if not atual:
        raise RegraViolada("Documento não encontrado (ou já retirado da lista).")
    v = _validar({**atual, **{k: campos[k] for k in CAMPOS if k in campos}})
    outro = _ativo_mesmo_arquivo(conn, v["drive_id"], v["link"], exceto=documento_id)
    if outro:
        raise RegraViolada(f"Este arquivo já está na lista como «{outro['titulo']}».")
    with transacao(conn):
        conn.execute(f"""UPDATE documentos_obra SET {",".join(k + "=?" for k in CAMPOS)}, drive_id=?, alterado_por=?, alterado_em=?
                         WHERE id=?""", tuple(v[k] for k in CAMPOS) + (v["drive_id"], por, _agora(), documento_id))


def retirar(conn, documento_id, por, motivo):
    if not str(motivo or "").strip():
        raise RegraViolada("Diga por que o documento sai da lista (o arquivo continua no Drive).")
    with transacao(conn):
        n = conn.execute("""UPDATE documentos_obra SET ativo=0, retirado_por=?, retirado_em=?, retirado_motivo=?
                            WHERE id=? AND ativo=1""", (por, _agora(), str(motivo).strip()[:500], documento_id)).rowcount
    if not n:
        raise RegraViolada("Documento não encontrado (ou já retirado da lista).")


# ------------------------------------------------------------------ planilha-índice
def ler_csv(texto):
    """Linhas do índice como dicionários de campos. Aceita vírgula, ponto e vírgula ou tabulação."""
    if len(texto or "") > MAX_CSV:
        raise RegraViolada("Arquivo do índice grande demais (máximo 12 MB).")
    texto = (texto or "").lstrip("﻿")
    if not texto.strip():
        raise RegraViolada("O índice está vazio.")
    amostra = texto[:4096]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    linhas = list(csv.reader(io.StringIO(texto), dialeto))
    if len(linhas) - 1 > MAX_LINHAS:
        raise RegraViolada(f"O índice tem mais de {MAX_LINHAS} linhas.")
    cab = [_norm(c) for c in linhas[0]]
    mapa = {}
    for campo, nomes in COLUNAS.items():
        for i, c in enumerate(cab):
            if c in nomes and campo not in mapa:
                mapa[campo] = i
    faltam = [n for n, c in (("nome novo (ou título)", "titulo"), ("link", "link")) if c not in mapa]
    if faltam:
        raise RegraViolada("O índice precisa das colunas " + " e ".join(faltam) + ". Colunas encontradas: "
                           + ", ".join(linhas[0]) + ".")
    out = []
    for n, l in enumerate(linhas[1:], start=2):
        if not any(str(x).strip() for x in l):
            continue
        out.append((n, {campo: (l[i] if i < len(l) else "") for campo, i in mapa.items()}))
    return out


def pasta_de_trabalho(pasta):
    return str(pasta or "").strip().split("/")[0].strip() in PASTAS_TRABALHO


def importar_indice(conn, texto, por, simular=False, incluir_trabalho=False):
    """Aplica (ou só simula) o índice: novos entram, os já listados (mesmo arquivo) são atualizados, linhas sem link
    válido são ignoradas com o motivo. Nada sai da lista por não estar no índice. As pastas de trabalho (IA, caches,
    temporários) ficam de fora, a não ser que se peça para incluí-las."""
    linhas = ler_csv(texto)
    novos, atualizados, iguais, ignorados, vistos, trabalho = [], [], 0, [], {}, {}
    for n, l in linhas:
        if not incluir_trabalho and pasta_de_trabalho(l.get("pasta")):
            topo = str(l.get("pasta")).strip().split("/")[0].strip()
            trabalho[topo] = trabalho.get(topo, 0) + 1
            continue
        if not str(l.get("titulo") or "").strip():
            l["titulo"] = l.get("nome_anterior")
        if not str(l.get("pasta") or "").strip():
            l["pasta"] = "Sem pasta"
        try:
            v = _validar(l)
        except RegraViolada as e:
            ignorados.append({"linha": n, "titulo": str(l.get("titulo") or "")[:120], "motivo": str(e)})
            continue
        chave = v["drive_id"] or v["link"]
        if chave in vistos:
            ignorados.append({"linha": n, "titulo": v["titulo"], "motivo": f"mesmo arquivo da linha {vistos[chave]}"})
            continue
        vistos[chave] = n
        atual = _ativo_mesmo_arquivo(conn, v["drive_id"], v["link"])
        if not atual:
            novos.append(v)
        elif any((atual[k] or None) != (v[k] or None) for k in CAMPOS):
            atualizados.append((atual["id"], v))
        else:
            iguais += 1
    ids = set(vistos)
    fora = [dict(r) for r in conn.execute("SELECT id, titulo, drive_id, link FROM documentos_obra WHERE ativo=1")
            if (r["drive_id"] or r["link"]) not in ids]
    resumo = {"simulado": bool(simular), "linhas": len(linhas), "novos": len(novos), "atualizados": len(atualizados),
              "iguais": iguais, "ignorados": ignorados, "fora_do_indice": len(fora), "pastas_de_trabalho": trabalho,
              "exemplos_fora": [f["titulo"] for f in fora[:20]],
              "exemplos_novos": [v["titulo"] for v in novos[:20]]}
    if simular:
        return resumo
    agora = _agora()
    with transacao(conn):
        for v in novos:
            conn.execute(f"""INSERT INTO documentos_obra({",".join(CAMPOS)},drive_id,origem,criado_por,criado_em)
                             VALUES ({",".join("?" * len(CAMPOS))},?,?,?,?)""",
                         tuple(v[k] for k in CAMPOS) + (v["drive_id"], "INDICE", por, agora))
        for did, v in atualizados:
            conn.execute(f"""UPDATE documentos_obra SET {",".join(k + "=?" for k in CAMPOS)}, drive_id=?, alterado_por=?, alterado_em=?
                             WHERE id=?""", tuple(v[k] for k in CAMPOS) + (v["drive_id"], por, agora, did))
        _gravar_parametro(conn, "documentos_ultima_importacao",
                          json.dumps({"em": agora, "por": por, **{k: resumo[k] for k in ("linhas", "novos", "atualizados", "iguais")},
                                      "ignorados": len(ignorados), "fora_do_indice": len(fora)}, ensure_ascii=False))
    return resumo


# ------------------------------------------------------------------ configuração e leitura pelo link da planilha
def _gravar_parametro(conn, chave, valor):
    conn.execute("INSERT INTO parametros(chave,valor,fonte) VALUES (?,?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, "
                 "fonte=excluded.fonte", (chave, valor, "tela Documentos"))


def obter_config(conn):
    ult = S.parametro(conn, "documentos_ultima_importacao")
    return {"pasta_url": S.parametro(conn, "documentos_pasta_url") or "",
            "indice_url": S.parametro(conn, "documentos_indice_url") or "",
            "ultima_importacao": json.loads(ult) if ult else None}


def salvar_config(conn, pasta_url, indice_url, por):
    pasta_url, indice_url = str(pasta_url or "").strip(), str(indice_url or "").strip()
    if pasta_url and analisar_link(pasta_url)["google"] != "folders":
        raise RegraViolada("O link da pasta precisa ser de uma pasta do Drive (https://drive.google.com/drive/folders/…).")
    if indice_url:
        url_csv_do_indice(indice_url)
    with transacao(conn):
        _gravar_parametro(conn, "documentos_pasta_url", pasta_url)
        _gravar_parametro(conn, "documentos_indice_url", indice_url)


def url_csv_do_indice(url):
    """Endereço CSV da planilha-índice: link comum (…/spreadsheets/d/<id>/edit#gid=N) ou publicado na web (…/d/e/…)."""
    u = urllib.parse.urlparse(str(url or "").strip())
    if u.scheme != "https" or (u.hostname or "").lower() != "docs.google.com" or "/spreadsheets/d/" not in u.path:
        raise RegraViolada("O índice precisa ser o link de uma planilha Google (https://docs.google.com/spreadsheets/d/…).")
    pub = re.search(r"/spreadsheets/d/e/([A-Za-z0-9_-]{10,})", u.path)
    if pub:
        q = urllib.parse.parse_qs(u.query)
        gid = (q.get("gid") or ["0"])[0]
        return f"https://docs.google.com/spreadsheets/d/e/{pub.group(1)}/pub?output=csv&gid={urllib.parse.quote(gid)}"
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{10,})", u.path)
    gid = (re.search(r"gid=(\d+)", u.fragment + "&" + u.query) or [None, "0"])[1]
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv&gid={gid}"


class _SoGoogle(urllib.request.HTTPRedirectHandler):
    """Segue redirecionamento só para o Google (o export da planilha passa por googleusercontent.com)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        h = (urllib.parse.urlparse(newurl).hostname or "").lower()
        if urllib.parse.urlparse(newurl).scheme != "https" or not (h == "docs.google.com" or h.endswith(".googleusercontent.com")):
            raise urllib.error.HTTPError(newurl, code, "redirecionamento para fora do Google recusado", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def baixar_csv(url, tempo=12):
    abrir = urllib.request.build_opener(_SoGoogle)
    try:
        with abrir.open(urllib.request.Request(url, headers={"User-Agent": "MorroDaCruz/1.0"}), timeout=tempo) as r:
            tipo = r.headers.get("Content-Type", "")
            dados = r.read(MAX_CSV + 1)
    except urllib.error.HTTPError as e:
        raise RegraViolada(f"O Google recusou a leitura da planilha (HTTP {e.code}). Confira se ela está compartilhada como "
                           "\"qualquer pessoa com o link pode ver\", ou baixe em CSV e use Importar arquivo.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RegraViolada(f"Não consegui acessar a planilha ({getattr(e, 'reason', e)}). Se a hospedagem bloquear o acesso, "
                           "baixe a planilha em CSV e use Importar arquivo.") from None
    if len(dados) > MAX_CSV:
        raise RegraViolada("Planilha-índice grande demais (máximo 12 MB).")
    if "html" in tipo.lower():
        raise RegraViolada("A planilha não está aberta para leitura pelo link (o Google pediu login). Compartilhe como "
                           "\"qualquer pessoa com o link pode ver\", ou baixe em CSV e use Importar arquivo.")
    return dados.decode("utf-8-sig", errors="replace")


def sincronizar(conn, por, simular=False, baixar=baixar_csv, incluir_trabalho=False):
    url = S.parametro(conn, "documentos_indice_url")
    if not url:
        raise RegraViolada("Cole primeiro o link da planilha-índice em Pasta e índice.")
    return importar_indice(conn, baixar(url_csv_do_indice(url)), por, simular=simular, incluir_trabalho=incluir_trabalho)
