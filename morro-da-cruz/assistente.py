"""Assistente: a IA conversacional do sistema (D-219 a D-224).

A pessoa escreve (ou fala) livremente em "O que você quer fazer?". O modelo de linguagem lê a mensagem inteira com o
contexto da conversa e decide: responder, consultar o sistema ou pedir um esclarecimento. O modelo só INTERPRETA; quem
valida, calcula e grava é o código do sistema:

* consultas por chamadas de função específicas (catálogo de materiais, orçamento, frentes e equipes do login, pedidos
  que o login vê, ajuda de uso), sempre com as permissões e as telas de quem está logado;
* o que a pessoa quer lançar vira um RASCUNHO (pedido de material, interferência ou chuva, apropriação direta), montado
  e conferido aqui com as mesmas regras das rotinas (solicitacoes.py, servicos.py, apropriacao.py, memoria_calculo.py);
* nada é gravado por este módulo. A tela mostra o rascunho como formulário e, só depois do toque da pessoa, envia o
  corpo pronto à rota de sempre (/api/solicitacao, /api/ocorrencia, /api/apropriacao), que confere tudo de novo com
  permissão, autoria, reenvio e auditoria.

Custo de API zero (D-220): só o plano gratuito da Groq, com a chave em GROQ_API_KEY (variável de ambiente ou
segredos.env, fora do Git). Cota esgotada vira aviso na tela, com o rascunho guardado e o formulário manual à mão; não
existe troca automática para outro serviço. Só biblioteca padrão (urllib), como o drive.py.
"""
import datetime
import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import deque

import apropriacao as AP
import caminhos
import equipes as EQ
import memoria_calculo as MC
import regras as R
import relogio as RL
import servicos as S
import solicitacoes as SOL
from servicos import RegraViolada

LIMITE_TEXTO = 1200                    # caracteres de uma mensagem da pessoa
LIMITE_FALA = 500                      # caracteres de cada mensagem antiga reenviada ao modelo
TIPOS = {"PEDIDO": "Pedido de material", "OCORRENCIA": "Interferência ou chuva", "APROPRIACAO": "Apropriação direta"}
PERMISSAO = {"PEDIDO": "compras_solicitar", "OCORRENCIA": "campo", "APROPRIACAO": "apropriacao"}
ROTA = {"PEDIDO": "/api/solicitacao", "OCORRENCIA": "/api/ocorrencia", "APROPRIACAO": "/api/apropriacao"}
MANUAL = {"PEDIDO": ("compras/requisicoes", "Requisições"), "OCORRENCIA": ("campo/interferencia", "Interferências e chuva"),
          "APROPRIACAO": ("campo/apropriacao", "Apropriação direta")}
SEM_PERMISSAO = {
    "PEDIDO": "Seu perfil não pede material pelo sistema. Fale com o almoxarifado ou com a engenharia.",
    "OCORRENCIA": "Seu perfil não registra interferência nem chuva. Avise o supervisor ou a engenharia.",
    "APROPRIACAO": "A apropriação direta é lançada só pela Engenharia e pela Administração. Passe os dados a elas.",
}
TURNOS = {"MANHA": "Manhã", "TARDE": "Tarde", "DIA_TODO": "Dia todo"}
EFEITOS = {"CHUVA_FRACA_TENDA": "Chuva fraca, seguiu com tenda", "PARALISADO_CHUVA": "Paralisou o serviço",
           "VALA_ALAGADA_BOMBA": "Vala alagada, usou bomba"}
CATEGORIAS = {"CHUVA": "Chuva", "INTERFERENCIA": "Interferência (rede ou obstáculo)", "FALTA_MATERIAL": "Falta de material",
              "ACESSO": "Acesso", "SEGURANCA": "Segurança", "PROJETO": "Projeto", "LIBERACAO": "Liberação", "OUTRO": "Outro"}
NAO_CONFORMIDADES = {"EXECUCAO": "Execução", "MATERIAL": "Material", "SOLDA": "Solda", "SEGURANCA": "Segurança",
                     "CADASTRO": "Cadastro", "DOCUMENTO": "Documento", "OUTRO": "Outro"}
# unidade composta do orçamento: dois números que se multiplicam (3 contêineres × 1 mês = 3 MES)
COMPOSTAS = {"MES": ("CONTAGEM", "MES"), "LOC/UN/MES": ("CONTAGEM", "MES"), "H": ("CONTAGEM", "HORA"), "CHP": ("CONTAGEM", "HORA"),
             "CHI": ("CONTAGEM", "HORA"), "M3XKM": ("VOLUME", "KM"), "TXKM": ("PESO", "KM")}
PAPEIS = {"CONTAGEM": ("Quantos", "unidades"), "MES": ("Meses", "meses"), "HORA": ("Horas", "horas"), "KM": ("Distância (km)", "km"),
          "VOLUME": ("Volume (m³)", "m³"), "PESO": ("Peso (t)", "t")}
PERGUNTA_PAPEL = {"CONTAGEM": "Quantas unidades?", "MES": "Por quantos meses?", "HORA": "Quantas horas?", "KM": "Qual a distância, em km?",
                  "VOLUME": "Qual o volume, em m³?", "PESO": "Qual o peso, em toneladas?"}
_RX_PAPEL = (("MES", r"MES(ES)?"), ("HORA", r"H|HRS?|HORAS?"), ("KM", r"KM|QUILOMETROS?"), ("VOLUME", r"M3|METROS? CUBICOS?"),
             ("PESO", r"T|TON|TONELADAS?"), ("LARGURA", r"ALTURA|LARGURA"), ("PROFUNDIDADE", r"PROFUNDIDADE|ESPESSURA"),
             ("COMPRIMENTO", r"COMPRIMENTO|EXTENSAO|PERIMETRO|METROS?( LINEARES?)?|M"))
_DIMENSOES = ("COMPRIMENTO", "LARGURA", "PROFUNDIDADE")          # fatores com nome de medida viram a parte da memória de cálculo


class CotaExcedida(Exception):
    """O plano gratuito recusou a chamada (429): o que acabou ('tokens' ou 'requests'), em que janela ('minuto' ou
    'dia') e a espera que o serviço pediu."""

    def __init__(self, tipo, espera_s, janela="minuto"):
        super().__init__(tipo)
        self.tipo, self.espera_s, self.janela = tipo, espera_s, janela


class IAIndisponivel(Exception):
    """Sem chave, chave recusada, rede fora ou resposta inválida: a conversa para e o formulário manual continua.
    `detalhe` guarda o motivo que o serviço deu (para o console e o log; a tela mostra só a frase curta)."""

    def __init__(self, mensagem, detalhe=""):
        super().__init__(mensagem)
        self.detalhe = detalhe


def _motivo(status, dados):
    """O que o serviço respondeu num erro, em uma linha: código e mensagem, sem o identificador da organização e sem o
    convite para o plano pago."""
    erro = (dados or {}).get("error")
    if isinstance(erro, dict):
        texto = f"{erro.get('code') or erro.get('type') or 'erro'}: {erro.get('message') or ''}"
    elif (dados or {}).get("nao_json"):
        texto = "a resposta não veio da API, e sim da borda do serviço: " + dados["nao_json"]
    else:
        texto = json.dumps(dados, ensure_ascii=False) if dados else "sem corpo"
    texto = re.sub(r"org_[A-Za-z0-9]+", "org_***", texto)
    texto = re.sub(r"\s*Need more tokens\?.*$", "", texto)
    return f"HTTP {status} · {_limpo(texto, 400)}"


# ------------------------------------------------------------------ configuração e chave
def config():
    """config/assistente.json (o da pasta do programa; senão o padrão que vem com ele), com o modelo e o endereço
    trocáveis por variável de ambiente."""
    for raiz in (caminhos.PASTA, caminhos.RECURSOS):
        p = os.path.join(raiz, "config", "assistente.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
            break
    else:
        raise IAIndisponivel("Falta o arquivo config/assistente.json.")
    cfg["modelo"] = (os.environ.get("MC_IA_MODELO") or cfg["modelo"]).strip()
    cfg["base_url"] = (os.environ.get("MC_IA_BASE_URL") or cfg["base_url"]).strip().rstrip("/")
    return cfg


def arquivo_segredos():
    return os.environ.get("MC_SEGREDOS") or os.path.join(caminhos.PASTA, "segredos.env")


def _chave_bruta():
    k = (os.environ.get("GROQ_API_KEY") or "").strip()
    if k:
        return k
    try:
        with open(arquivo_segredos(), encoding="utf-8", errors="replace") as f:
            for linha in f:
                nome, _, valor = linha.strip().partition("=")
                if nome.strip().lstrip("\ufeff") == "GROQ_API_KEY" and valor.strip():
                    return valor.strip().strip("'\"")
    except OSError:
        pass
    return ""


def chave():
    """GROQ_API_KEY: da variável de ambiente ou do segredos.env da pasta do programa (fora do Git). Nunca vai à tela,
    ao log nem à auditoria. Saem os caracteres invisíveis que colar no terminal pode deixar (marcas de colagem, CR)."""
    k = re.sub(r"\x1b\[20[01]~", "", _chave_bruta())
    return "".join(c for c in k if c.isprintable() and not c.isspace())


def forma_da_chave():
    """Diagnóstico sem mostrar a chave: o tamanho, se começa como as chaves da Groq e o que há de estranho nela."""
    bruta, k = _chave_bruta(), chave()
    problemas = []
    if bruta != k:
        problemas.append(f"vieram {len(bruta) - len(k)} caractere(s) invisível(is) ou espaço(s) junto com ela (foram ignorados)")
    if not k.startswith("gsk_"):
        problemas.append("não começa com gsk_, como as chaves da Groq")
    if re.search(r"[^A-Za-z0-9_\-]", k):
        problemas.append("tem caractere que não é letra, número, _ ou -")
    if k.count("gsk_") > 1:
        problemas.append("parece ter sido colada mais de uma vez")
    return len(k), problemas


def _pode(usuario, tipo):
    return PERMISSAO[tipo] in usuario["permissoes"]


def estado(usuario):
    """O que a tela precisa para abrir: se a IA está ligada e o que este login pode lançar (com o caminho manual)."""
    ligada = bool(chave())
    return {"disponivel": ligada,
            "motivo": None if ligada else "A IA ainda não foi ligada neste servidor (falta a chave gratuita da Groq).",
            "usos": [{"tipo": t, "nome": TIPOS[t], "tela": MANUAL[t][0], "pagina": MANUAL[t][1]} for t in TIPOS if _pode(usuario, t)]}


# ------------------------------------------------------------------ texto e números
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s if s is not None else ""))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c)).upper()).strip()


def _limpo(v, limite=600):
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:limite]


def _numero(v):
    """Número positivo e finito vindo do modelo ou do formulário ('2,5', 3, '3'); senão None."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(str(v).strip().replace(".", "").replace(",", ".") if isinstance(v, str) and "," in v else v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and 0 < x <= 1e9 else None


def _fmt(v):
    return R.fmt_num(float(v), 4)


def _plural(nome, valor):
    """'contêiner'/'contêineres' e 'mês'/'meses' conforme o número: só para a memória de cálculo ficar legível."""
    n = _limpo(nome, 40)
    if not n or " " in n or len(n) < 3 or n.lower() in ("km", "m³", "m3"):
        return n
    b = n.lower()
    if abs(float(valor) - 1) < 1e-9:
        if b == "meses":
            return "mês"
        if b.endswith("ões"):
            return n[:-3] + "ão"
        if b.endswith(("res", "zes")):
            return n[:-2]
        return n[:-1] if b.endswith("s") and not b.endswith(("ês", "ss", "is")) else n
    if b in ("mês", "mes"):
        return "meses"
    if b.endswith("ão"):
        return n[:-2] + "ões"
    if b.endswith(("r", "z")):
        return n + "es"
    return n + "s" if b[-1] in "aeiouáéíóúâêô" else n


def _data(v, hoje):
    """'2026-11-13', '13/11/2026', '13/11', 'hoje', 'ontem', 'anteontem' → ISO; senão None."""
    t = _norm(v)
    if not t:
        return None
    if t in ("HOJE", "ONTEM", "ANTEONTEM"):
        return (hoje - datetime.timedelta(days=("HOJE", "ONTEM", "ANTEONTEM").index(t))).isoformat()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t) or None
    if m:
        a, me, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
        if not m:
            return None
        d, me, a = int(m.group(1)), int(m.group(2)), int(m.group(3) or hoje.year)
        a += 2000 if a < 100 else 0
    try:
        return datetime.date(a, me, d).isoformat()
    except ValueError:
        return None


def _br(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso and len(iso) >= 10 else ""


def _variantes(palavra):
    """A palavra e o singular provável ('LUVAS' → 'LUVA', 'CONTEINERES' → 'CONTEINER', 'REDUCOES' → 'REDUCAO')."""
    out = [palavra]
    if len(palavra) > 4 and palavra.endswith("OES"):
        out.append(palavra[:-3] + "AO")
    if len(palavra) > 4 and palavra.endswith("ES"):
        out.append(palavra[:-2])
    if len(palavra) > 3 and palavra.endswith("S"):
        out.append(palavra[:-1])
    return out


# ------------------------------------------------------------------ consultas (as chamadas de função de leitura)
def nome_frente(fid):
    if str(fid).startswith("Zona"):
        return "Zona " + str(fid)[4:]
    return {"ADUTORA": "Subadutora", "CH": "Caixas hidráulicas"}.get(fid, str(fid))


def _frente(texto):
    """'zona 3', 'Zona03', 'z3', 'adutora', 'subadutora', 'caixas' → id da frente; senão None."""
    t = _norm(texto)
    if not t:
        return None
    for f in R.FRENTES:
        if t == _norm(f) or t == _norm(nome_frente(f)):
            return f
    m = re.fullmatch(r"(?:ZONA|Z)?\s*0*(\d{1,2})", t)
    if m and f"Zona{int(m.group(1)):02d}" in R.FRENTES:
        return f"Zona{int(m.group(1)):02d}"
    if "ADUTORA" in t:
        return "ADUTORA"
    if t in ("CH", "CAIXAS", "CAIXA", "CAIXAS HIDRAULICAS"):
        return "CH"
    return None


def frentes_do_login(conn, usuario):
    """As frentes para as quais este login pede material (o encarregado: só onde a equipe dele está programada)."""
    permitidas = SOL.frentes_do_usuario(conn, usuario)
    return [f for f in R.FRENTES if f in permitidas]


def equipes_do_login(conn, usuario):
    """As equipes ativas que este login pode usar num lançamento (o encarregado: só a dele)."""
    eqs = [e for e in EQ.listar(conn) if e["ativa"]]
    if usuario.get("restrito_a_equipe"):
        eqs = [e for e in eqs if e["id"] == usuario.get("equipe_id")]
    return [{"id": e["id"], "nome": e["nome"]} for e in eqs]


def _equipe(conn, usuario, texto):
    t = _norm(texto)
    eqs = equipes_do_login(conn, usuario)
    for e in eqs:
        if t in (_norm(e["id"]), _norm(e["nome"])):
            return e
    achadas = [e for e in eqs if t and (t in _norm(e["nome"]) or t in _norm(e["id"]) or _norm(e["id"]) in t.split())]
    return achadas[0] if len(achadas) == 1 else None


def rotulo_material(m):
    return m["nome"] + (" · tubo fornecido pela Caesb" if m.get("caesb") else "")


def buscar_materiais(conn, texto, limite=8):
    """O catálogo de Pedir material (D-173) por palavras, em qualquer ordem, com plural e bitola ('luvas de 110').
    Quem casa todas as palavras no NOME vem sozinho (a luva, não a curva que cita luva na descrição); o mesmo material
    repetido em dois orçamentos parciais aparece uma vez."""
    palavras = [p for p in re.findall(r"[A-Z0-9/\"]+", _norm(texto)) if p not in AP.PARADAS and p not in ("MM", "UN", "PECAS", "PECA")]
    palavras = [re.sub(r"^(?:DN|DE)?(\d+)(?:MM)?$", r"\1", p) for p in palavras]
    if not palavras:
        return []
    out, vistos = [], set()
    for m in SOL.catalogo(conn):
        alvo = _norm(m["nome"]) + " | " + _norm(m["descricao"])
        nome_toks, toks = set(re.findall(r"[A-Z0-9/\"]+", _norm(m["nome"]))), set(re.findall(r"[A-Z0-9/\"]+", alvo))
        pontos, no_nome = 0, 0
        for p in palavras:
            vs = _variantes(p)
            if any(v in nome_toks for v in vs):
                pontos, no_nome = pontos + 4, no_nome + 1
            elif any(v in toks for v in vs):
                pontos += 2
            elif not p.isdigit() and any(t.startswith(v) for v in vs for t in toks if len(v) >= 3):
                pontos += 1
            else:
                break
        else:
            igual = (m["nome"], m["descricao"], m["caesb"])
            if igual not in vistos:
                vistos.add(igual)
                out.append((-no_nome, -pontos, len(m["nome"]), m["nome"], m))
    out.sort(key=lambda x: x[:4])
    if out and -out[0][0] == len(palavras):                                 # alguém casou tudo pelo nome: só esses
        out = [x for x in out if x[0] == out[0][0]]
    return [x[4] for x in out[:limite]]


def buscar_orcamento(conn, texto, grupo=None, limite=8):
    """A busca da base de custo (apropriacao.buscar) tolerante a plural: todas as palavras como vieram; sem resultado,
    o singular de cada uma ('contêineres' → 'contêiner', 'tapumes' → 'tapume')."""
    cat = AP.catalogo(conn, com_reprovados=False)
    ws = AP.palavras(texto)
    tentativas = [" ".join(ws)]
    for corte in (lambda w: w[:-3] + "AO" if w.endswith("OES") else w[:-2] if w.endswith("ES") and len(w) > 4 else w[:-1] if w.endswith("S") and len(w) > 3 else w,
                  lambda w: w[:-1] if w.endswith("S") and len(w) > 3 else w):
        t = " ".join(corte(w) for w in ws)
        if t not in tentativas:
            tentativas.append(t)
    for t in tentativas:
        achados = AP.buscar(conn, t, grupo or None, limite=limite, catalogo_=cat) if t else []
        if achados:
            return achados
    return []


def _item_curto(it):
    return {"id": it["item"], "item": it["item_bm"] or it["item"], "nome": (it.get("resumida") or it["descricao"])[:70],
            "un": it["unidade"], "grupo": it["grupo"].capitalize(), "tipo": it["tipo"].lower()}


def _resolver_item(conn, texto):
    """Um item do orçamento pelo que o modelo passou: a chave ('1.1_6.1.3'), a referência ('BM:390'), o número do item
    ('6.1.3') ou palavras. Devolve (item, candidatos): um item certo, ou os candidatos para a pessoa escolher."""
    t = _limpo(texto, 120)
    if not t:
        return None, []
    try:
        return AP.item(conn, t), []
    except RegraViolada:
        pass
    cat = AP.catalogo(conn, com_reprovados=False)
    iguais = [it for it in cat if _norm(it["item_bm"]) == _norm(t)]
    if len(iguais) == 1:
        return iguais[0], []
    if iguais:
        return None, iguais[:8]
    achados = buscar_orcamento(conn, t)
    if len(achados) == 1:
        return AP.item(conn, achados[0]["ref"]), []
    return None, achados


def ajuda(cfg, usuario, assunto):
    """As duas seções do guia de uso que mais casam com o assunto (config/assistente.json), com a tela que a pessoa abre."""
    palavras = {v for p in re.findall(r"[A-Z0-9]+", _norm(assunto)) if p not in AP.PARADAS and len(p) > 2 for v in _variantes(p)}
    pontuadas = []
    for i, s in enumerate(cfg.get("ajuda") or []):
        chaves = set(re.findall(r"[A-Z0-9]+", _norm(s.get("palavras", "") + " " + s["titulo"])))
        pontos = len(palavras & chaves)
        if pontos:
            pontuadas.append((-pontos, i, s))
    pontuadas.sort(key=lambda x: x[:2])
    return [s for _, _, s in pontuadas[:2]]


def _abre(usuario, secao):
    """A pessoa abre a tela da seção de ajuda? (as telas do perfil e, se a seção pedir, a permissão)."""
    if not secao.get("tela"):
        return False
    if secao.get("permissao") and secao["permissao"] not in usuario["permissoes"]:
        return False
    return bool(set(secao.get("telas_perfil") or ()) & set(usuario["telas"]))


def pedidos_do_login(conn, usuario, abertos=True, limite=8):
    """As requisições que este login vê (solicitacoes.listar: quem abre Compras vê as da obra; os outros, as suas)."""
    out = []
    for s in SOL.listar(conn, usuario):
        if abertos and s["situacao"] not in ("ABERTA", "AGUARDANDO"):
            continue
        itens = "; ".join(f"{i['nome']} {_fmt(i['quantidade'])} {i['unidade_nome']}" for i in s["itens"] + s["avulsos"])
        out.append({"numero": s["id"], "data": _br(s["data"]), "frente": nome_frente(s.get("frente_id")),
                    "situacao": {"ABERTA": "aberta", "AGUARDANDO": "aguardando a entrega", "RECEBIDA": "recebida",
                                 "CANCELADA": "cancelada"}.get(s["situacao"], s["situacao"]),
                    "pediu": s["solicitante"], "itens": itens[:200]})
        if len(out) >= limite:
            break
    return out


# ------------------------------------------------------------------ rascunho: os campos e a vista para a tela
def _novo(tipo):
    return {"tipo": tipo, "campos": {}}


def _texto_campos(campos, *nomes):
    return {n: _limpo(campos.get(n)) for n in nomes if _limpo(campos.get(n))}


def normalizar(conn, usuario, bruto):
    """O rascunho que volta do navegador é dado não confiável: fica só o que tem forma válida, e tudo é conferido de
    novo ao montar a vista (e outra vez pela rota que grava)."""
    if not isinstance(bruto, dict) or bruto.get("tipo") not in TIPOS or not _pode(usuario, bruto["tipo"]):
        return None
    c = bruto.get("campos") if isinstance(bruto.get("campos"), dict) else {}
    tipo, hoje = bruto["tipo"], RL.hoje()
    out = {}
    if _data(c.get("data"), hoje):
        out["data"] = _data(c.get("data"), hoje)
    if tipo == "PEDIDO":
        if c.get("frente_id") in R.FRENTES:
            out["frente_id"] = c["frente_id"]
        itens = []
        for i in (c.get("itens") if isinstance(c.get("itens"), list) else [])[:50]:
            if not isinstance(i, dict):
                continue
            q = _numero(i.get("quantidade"))
            if i.get("material_id"):
                itens.append({"material_id": str(i["material_id"])[:60], "quantidade": q})
            elif _limpo(i.get("descricao")):
                itens.append({"descricao": _limpo(i["descricao"]), "quantidade": q,
                              "unidade": i.get("unidade") if i.get("unidade") in SOL.UNIDADES else "UN"})
        out["itens"] = itens
        out.update(_texto_campos(c, "observacao"))
    elif tipo == "OCORRENCIA":
        nc = c.get("tipo") == "NAO_CONFORMIDADE"
        out["tipo"] = "NAO_CONFORMIDADE" if nc else "IMPEDIMENTO"
        if c.get("categoria") in (NAO_CONFORMIDADES if nc else CATEGORIAS):
            out["categoria"] = c["categoria"]
        for campo, validos in (("turno", TURNOS), ("clima_condicao", EFEITOS)):
            if c.get(campo) in validos:
                out[campo] = c[campo]
        if c.get("todas_equipes") is True and not usuario.get("restrito_a_equipe"):
            out["todas_equipes"] = True
        elif c.get("equipe_id"):
            out["equipe_id"] = str(c["equipe_id"])[:40]
        if c.get("alvo_tipo") in ("TRECHO", "ATIVIDADE") and c.get("alvo_id"):
            out.update(alvo_tipo=c["alvo_tipo"], alvo_id=str(c["alvo_id"])[:60])
        out.update(_texto_campos(c, "descricao", "local_texto"))
    else:
        if c.get("item_ref"):
            out["item_ref"] = str(c["item_ref"])[:60]
        fatores = {}
        for papel, f in (c.get("fatores") if isinstance(c.get("fatores"), dict) else {}).items():
            if papel in PAPEIS and isinstance(f, dict) and _numero(f.get("valor")):
                fatores[papel] = {"nome": _limpo(f.get("nome"), 40) or PAPEIS[papel][1], "valor": _numero(f["valor"])}
        if fatores:
            out["fatores"] = fatores
        medidas = []
        for p in (c.get("medidas") if isinstance(c.get("medidas"), list) else [])[:MC.MAX_PARTES]:
            if isinstance(p, dict):
                m = {k: _limpo(p.get(k), 150) for k in ("descricao", "comprimento", "largura", "profundidade") if _limpo(p.get(k))}
                if p.get("repeticoes") not in (None, "", 1, "1"):
                    m["repeticoes"] = _limpo(p["repeticoes"], 6)
                if m:
                    medidas.append(m)
        if medidas:
            out["medidas"] = medidas
        if c.get("local_tipo") in AP.LOCAIS:
            out["local_tipo"] = c["local_tipo"]
            if c.get("local_id"):
                out["local_id"] = str(c["local_id"])[:60]
        if c.get("equipe_id"):
            out["equipe_id"] = str(c["equipe_id"])[:40]
        out.update(_texto_campos(c, "local_texto", "o_que_foi_feito", "justificativa"))
    return {"tipo": tipo, "campos": out}


def _opcoes(mapa):
    return [{"v": k, "r": v} for k, v in mapa.items()]


def vista(conn, usuario, rascunho):
    """O rascunho como a tela mostra: linhas de leitura, campos editáveis, o que falta (com a pergunta e os botões), os
    avisos das regras e, quando está completo, a rota de sempre com o corpo pronto para o toque da pessoa."""
    if not rascunho:
        return None
    tipo, c = rascunho["tipo"], rascunho["campos"]
    v = {"tipo": tipo, "campos": c, "titulo": TIPOS[tipo], "linhas": [], "form": [], "faltam": [], "avisos": [],
         "rota": ROTA[tipo], "corpo": None, "manual": {"tela": MANUAL[tipo][0], "rotulo": MANUAL[tipo][1]}}
    {"PEDIDO": _vista_pedido, "OCORRENCIA": _vista_ocorrencia, "APROPRIACAO": _vista_apropriacao}[tipo](conn, usuario, c, v)
    v["pronto"] = not v["faltam"] and v["corpo"] is not None
    if not v["pronto"]:
        v["corpo"] = None
    return v


def _falta(v, campo, pergunta, botoes=None):
    v["faltam"].append({"campo": campo, "pergunta": pergunta, "botoes": botoes or []})


def _campo_data(v, c, hoje, rotulo="Dia"):
    data = c.get("data") or hoje.isoformat()
    v["form"].append({"id": "data", "rotulo": rotulo, "tipo": "data", "valor": data, "max": hoje.isoformat()})
    if data > hoje.isoformat():
        v["avisos"].append("A data está no futuro: só se registra o que já aconteceu.")
        _falta(v, "data", "Em que dia foi?")
    return data


def _vista_pedido(conn, usuario, c, v):
    v["confirmar"] = "Enviar requisição"
    catalogo = {m["id"]: m for m in SOL.catalogo(conn)}
    permitidas = frentes_do_login(conn, usuario)
    itens, corpo_itens = c.get("itens") or [], []
    for i, it in enumerate(itens):
        m = catalogo.get(it.get("material_id")) if it.get("material_id") else None
        if it.get("material_id") and not m:
            v["avisos"].append("Um material do rascunho não existe mais no catálogo e foi tirado.")
            continue
        nome = rotulo_material(m) if m else it["descricao"]
        un = m["unidade_nome"] if m else SOL.UNIDADES.get(it.get("unidade"), "unidades")
        v["form"].append({"id": f"item.{i}.quantidade", "rotulo": nome + (" (escrito, a identificar por Compras)" if not m else ""),
                          "tipo": "numero", "valor": it.get("quantidade"), "sufixo": un, "remover": f"item.{i}.remover"})
        if not it.get("quantidade"):
            _falta(v, f"item.{i}.quantidade", f"Quanto de {nome}? ({un})")
        corpo_itens.append({"material_id": m["id"], "quantidade": it.get("quantidade")} if m else
                           {"descricao": it["descricao"], "quantidade": it.get("quantidade"), "unidade": it.get("unidade") or "UN"})
    v["form"].append({"id": "material", "rotulo": "Acrescentar material (nome e bitola)", "tipo": "texto", "valor": "", "dica": "ex.: luva 110"})
    if not corpo_itens:
        _falta(v, "itens", "Qual material você precisa, e quanto?")
    frente = c.get("frente_id")
    if frente and frente not in permitidas:
        v["avisos"].append(f"Seu usuário não pede para {nome_frente(frente)}: o encarregado pede para a frente em que a equipe está programada.")
        frente = None
    if not frente and len(permitidas) == 1:
        frente = c["frente_id"] = permitidas[0]
    v["form"].append({"id": "frente", "rotulo": "Para onde", "tipo": "opcoes", "valor": frente or "",
                      "opcoes": [{"v": f, "r": nome_frente(f)} for f in permitidas]})
    if not permitidas:
        v["avisos"].append("Sua equipe não está programada em nenhuma frente: peça à engenharia para programar a equipe antes de pedir material.")
        _falta(v, "frente", "Sua equipe ainda não está programada em nenhuma frente.")
    elif not frente:
        _falta(v, "frente", "Para qual zona ou frente é o material?",
               [{"rotulo": nome_frente(f), "aplicar": {"frente": f}} for f in permitidas])
    v["form"].append({"id": "observacao", "rotulo": "Observação (opcional)", "tipo": "area", "valor": c.get("observacao", ""), "max": 600})
    v["linhas"] = [["Para onde", nome_frente(frente) if frente else "a definir"], ["Materiais", str(len(corpo_itens))]]
    v["corpo"] = {"frente_id": frente, "observacao": c.get("observacao", ""), "itens": corpo_itens}


def _vista_ocorrencia(conn, usuario, c, v):
    hoje, restrito = RL.hoje(), bool(usuario.get("restrito_a_equipe"))
    nc = c.get("tipo") == "NAO_CONFORMIDADE"
    categorias = NAO_CONFORMIDADES if nc else CATEGORIAS
    cat = c.get("categoria")
    chuva = cat == "CHUVA" and not nc
    v["titulo"] = "Chuva no dia" if chuva else "Não conformidade" if nc else "Interferência"
    v["confirmar"] = "Registrar chuva" if chuva else "Registrar"
    v["form"].append({"id": "categoria", "rotulo": "Categoria", "tipo": "opcoes", "valor": cat or "", "opcoes": _opcoes(categorias)})
    if not cat:
        _falta(v, "categoria", "O que aconteceu?", [{"rotulo": r, "aplicar": {"categoria": k}} for k, r in categorias.items()])
    data = _campo_data(v, c, hoje)
    equipes = equipes_do_login(conn, usuario)
    if restrito:
        c.pop("todas_equipes", None)
        if equipes:
            c["equipe_id"] = equipes[0]["id"]
    equipe = next((e for e in equipes if e["id"] == c.get("equipe_id")), None)
    if c.get("equipe_id") and not equipe:
        v["avisos"].append("A equipe do rascunho não está ativa: escolha outra.")
        c.pop("equipe_id", None)
    todas = bool(c.get("todas_equipes")) and chuva
    opcoes_eq = [{"v": e["id"], "r": e["nome"]} for e in equipes]
    if chuva and not restrito:
        opcoes_eq.insert(0, {"v": "TODAS", "r": "Todas as equipes com check-in no dia"})
    v["form"].append({"id": "equipe", "rotulo": "Equipe" + ("" if chuva else " (opcional)"), "tipo": "opcoes",
                      "valor": "TODAS" if todas else (equipe or {}).get("id", ""), "opcoes": opcoes_eq})
    corpo = {"tipo": "NAO_CONFORMIDADE" if nc else "IMPEDIMENTO", "categoria": cat, "data": data,
             "equipe_id": None if todas else (equipe or {}).get("id"), "descricao": c.get("descricao", "")}
    alvo = None
    if c.get("alvo_id"):
        try:
            alvo = S.alvo(conn, c["alvo_tipo"], c["alvo_id"])
        except RegraViolada:
            c.pop("alvo_id", None), c.pop("alvo_tipo", None)
    local = {"id": "local", "rotulo": "Trecho, nó ou caixa" + (" (opcional)" if chuva else ""), "tipo": "texto",
             "valor": R.nome_completo(alvo["nome"]) if alvo else c.get("local_texto", ""), "dica": "ex.: Zona 03 PB06 TR014"}
    if alvo:
        corpo.update(alvo_tipo=alvo["alvo_tipo"], alvo_id=alvo["id"])
    if chuva:
        if not equipes:
            v["avisos"].append("Não há equipe ativa para registrar a chuva: crie a equipe em Administrativo › Equipes.")
            _falta(v, "equipe", "Ainda não há equipe ativa cadastrada.")
        elif not todas and not equipe:
            botoes = [{"rotulo": e["nome"], "aplicar": {"equipe": e["id"]}} for e in equipes[:8]]
            if not restrito:
                botoes.insert(0, {"rotulo": "Todas com check-in no dia", "aplicar": {"equipe": "TODAS"}})
            _falta(v, "equipe", "Para qual equipe?", botoes)
        if todas and not conn.execute("SELECT 1 FROM checkins WHERE data=? LIMIT 1", (data,)).fetchone():
            v["avisos"].append("Nenhuma equipe tem check-in nesse dia: escolha uma equipe.")
            _falta(v, "equipe", "Nenhuma equipe tem check-in nesse dia. Para qual equipe é a chuva?",
                   [{"rotulo": e["nome"], "aplicar": {"equipe": e["id"]}} for e in equipes[:8]])
        v["form"].append({"id": "turno", "rotulo": "Quando choveu", "tipo": "opcoes", "valor": c.get("turno", ""), "opcoes": _opcoes(TURNOS)})
        if not c.get("turno"):
            _falta(v, "turno", "Choveu de manhã, à tarde ou o dia todo?", [{"rotulo": r, "aplicar": {"turno": k}} for k, r in TURNOS.items()])
        v["form"].append({"id": "efeito", "rotulo": "Efeito no serviço", "tipo": "opcoes", "valor": c.get("clima_condicao", ""),
                          "opcoes": _opcoes(EFEITOS)})
        if not c.get("clima_condicao"):
            _falta(v, "efeito", "Qual foi o efeito da chuva no serviço?", [{"rotulo": r, "aplicar": {"efeito": k}} for k, r in EFEITOS.items()])
        v["form"].append(local)
        v["form"].append({"id": "descricao", "rotulo": "Observação (opcional)", "tipo": "area", "valor": c.get("descricao", ""), "max": 600})
        corpo.update(turno=c.get("turno"), clima_condicao=c.get("clima_condicao"), todas_equipes=todas)
        v["linhas"] = [["Dia", _br(data)], ["Equipe", "todas com check-in no dia" if todas else (equipe or {}).get("nome", "a definir")],
                       ["Quando", TURNOS.get(c.get("turno"), "a definir")], ["Efeito", EFEITOS.get(c.get("clima_condicao"), "a definir")]]
    else:
        v["form"].append(local)
        if cat and not alvo:
            _falta(v, "local", "Em qual trecho, nó ou caixa? (ex.: Zona 03 PB06 TR014)")
        v["form"].append({"id": "descricao", "rotulo": "O que foi encontrado", "tipo": "area", "valor": c.get("descricao", ""), "max": 600})
        if cat and not c.get("descricao"):
            _falta(v, "descricao", "Descreva o que foi encontrado.")
        v["linhas"] = [["Tipo", "Não conformidade" if nc else "Impedimento"], ["Categoria", categorias.get(cat, "a definir")],
                       ["Dia", _br(data)], ["Onde", R.nome_completo(alvo["nome"]) if alvo else "a definir"],
                       ["Equipe", (equipe or {}).get("nome", "não informada")]]
    v["corpo"] = corpo


def _unidade(it):
    return _norm(R.normalizar_unidade(it["unidade"])).replace("²", "2").replace("³", "3")


def _vista_apropriacao(conn, usuario, c, v):
    hoje = RL.hoje()
    v["confirmar"] = "Gravar apropriação"
    it = None
    if c.get("item_ref"):
        try:
            it = AP.item(conn, c["item_ref"])
            it.update(AP.saldo(conn, it))
        except RegraViolada as e:
            v["avisos"].append(str(e))
            c.pop("item_ref", None)
    v["form"].append({"id": "item", "rotulo": "Item do orçamento (número ou palavras do serviço)", "tipo": "texto",
                      "valor": (it or {}).get("item_bm") or "", "dica": "ex.: 6.1.3 ou tapume"})
    if not it:
        _falta(v, "item", "Qual item do orçamento? Diga o serviço ou o número do item.")
        v["linhas"].append(["Item", "a definir"])
        fat = c.get("fatores") or {}
        if fat:
            v["linhas"].append(["Anotado", " × ".join(f"{_fmt(f['valor'])} {_plural(f['nome'], f['valor'])}" for f in fat.values())])
        _campo_data(v, c, hoje, "Dia do serviço")
        return
    grupo = AP.GRUPOS.get(it["grupo"], it["grupo"].capitalize())
    v["linhas"] += [["Item", f"{it['item_bm'] or it['item']} · {it.get('resumida') or it['descricao'][:90]}"],
                    ["Grupo", f"{grupo} · {it['tipo'].lower()}"], ["Situação", it["rotulo"]]]
    if it["tipo_ref"] == "BM" and it["item"] == AP.CHAVE_ADM:
        v["avisos"].append("A administração local não se apropria: ela entra na medição pela folha da ADM (D-141).")
        _falta(v, "item", "Esse item não se apropria. Qual outro item?")
    if it["situacao"] == "REPROVADO":
        v["avisos"].append("Item reprovado pela Caesb: escolha outro item.")
        _falta(v, "item", "Esse item foi reprovado. Qual outro item?")
    if it["situacao"] == "A_APROVAR":
        v["avisos"].append("Item a aprovar: a apropriação é gravada, mas fica fora da medição até a Caesb dar o código oficial.")
    if it["classificacao"] == "MATERIAL":
        v["avisos"].append("Material: fica fora da medição até a matriz de regimes ser aprovada (D-53/D-54).")
    u, fat = _unidade(it), dict(c.get("fatores") or {})
    dim, quantidade, memoria, parcelas = MC.DIMENSOES.get(u, 0), None, "", None
    if u in COMPOSTAS:
        a, b = COMPOSTAS[u]
        for papel in (a, b):
            f = fat.get(papel)
            v["form"].append({"id": f"fator.{papel}", "rotulo": PAPEIS[papel][0] + (f" ({f['nome']})" if f and papel == "CONTAGEM" else ""),
                              "tipo": "numero", "valor": f["valor"] if f else None})
            if not f:
                _falta(v, f"fator.{papel}", PERGUNTA_PAPEL[papel])
        if a in fat and b in fat:
            quantidade = fat[a]["valor"] * fat[b]["valor"]
            memoria = (f"{_fmt(fat[a]['valor'])} {_plural(fat[a]['nome'], fat[a]['valor'])} × "
                       f"{_fmt(fat[b]['valor'])} {_plural(fat[b]['nome'], fat[b]['valor'])} = {_fmt(quantidade)} {it['unidade']}")
    elif dim:
        medidas = c.get("medidas") or []
        if not medidas and dim == 1 and fat.get("CONTAGEM"):
            medidas = [{"comprimento": _fmt(fat["CONTAGEM"]["valor"]).replace(".", "")}]
        rot = (("comprimento", "Comprimento ou soma dos lados (m)"), ("largura", "Altura ou largura (m)" if dim == 2 else "Largura (m)"),
               ("profundidade", "Profundidade ou espessura (m)"))[:dim]
        for i, p in enumerate(medidas or [{}]):
            for chave_, rotulo in rot:
                v["form"].append({"id": f"medida.{i}.{chave_}", "rotulo": rotulo + (f" · parte {i + 1}" if len(medidas) > 1 else ""),
                                  "tipo": "texto", "valor": p.get(chave_, ""), "dica": "80 + 50 + 40" if chave_ == "comprimento" else "2,00"})
        if medidas:
            try:
                calculo = MC.calcular(it["unidade"], [dict(p) for p in medidas])
                quantidade, memoria, parcelas = calculo["quantidade"], calculo["memoria"], medidas
            except RegraViolada as e:
                v["avisos"].append(str(e))
                _falta(v, "medidas", "Confira as medidas: " + str(e))
        else:
            _falta(v, "medidas", "Quais são as medidas? " + {1: "O comprimento, em metros.", 2: "Comprimento (ou a soma dos lados) e altura, em metros.",
                                                        3: "Comprimento, largura e profundidade, em metros."}[dim])
    else:
        f = fat.get("CONTAGEM")
        v["form"].append({"id": "fator.CONTAGEM", "rotulo": f"Quantidade ({it['unidade']})", "tipo": "numero", "valor": f["valor"] if f else None})
        if f:
            quantidade = f["valor"]
        else:
            _falta(v, "fator.CONTAGEM", f"Qual a quantidade, em {it['unidade']}?")
    if quantidade is not None:
        quantidade = round(quantidade, 4)
        if memoria:
            v["linhas"].append(["Memória de cálculo", memoria])
        v["linhas"].append(["Quantidade", f"{_fmt(quantidade)} {it['unidade']}"])
        if it.get("saldo") is not None and quantidade > it["saldo"] + 1e-9:
            v["avisos"].append(f"A quantidade passa do saldo do item ({_fmt(it['saldo'])} {it['unidade']}): o excedente fica "
                               "parado até aditivo ou apostilamento.")
    data = _campo_data(v, c, hoje, "Dia do serviço")
    local_tipo, local_id = c.get("local_tipo"), c.get("local_id")
    local_nome = ""
    if local_tipo in ("TRECHO", "ATIVIDADE"):
        try:
            local_nome = R.nome_completo(S.alvo(conn, local_tipo, local_id)["nome"])
        except RegraViolada:
            local_tipo = local_id = None
            c.pop("local_tipo", None), c.pop("local_id", None)
    elif local_tipo == "ZONA":
        if local_id not in R.FRENTES:
            local_tipo = local_id = None
        else:
            local_nome = nome_frente(local_id)
    elif local_tipo == "CANTEIRO":
        local_nome = "Canteiro de obra"
    v["form"].append({"id": "local", "rotulo": "Local (opcional)", "tipo": "texto", "valor": local_nome or c.get("local_texto", ""),
                      "dica": "canteiro, Zona 03 ou o trecho"})
    v["linhas"].append(["Local", local_nome or c.get("local_texto") or "não informado"])
    equipes = equipes_do_login(conn, usuario)
    equipe = next((e for e in equipes if e["id"] == c.get("equipe_id")), None)
    if equipes:
        v["form"].append({"id": "equipe", "rotulo": "Equipe da obra que executou (opcional)", "tipo": "opcoes",
                          "valor": (equipe or {}).get("id", ""), "opcoes": [{"v": e["id"], "r": e["nome"]} for e in equipes]})
    v["form"].append({"id": "o_que_foi_feito", "rotulo": "O que foi feito (opcional)", "tipo": "area", "valor": c.get("o_que_foi_feito", ""), "max": 600})
    v["form"].append({"id": "justificativa", "rotulo": "Justificativa (opcional)", "tipo": "area", "valor": c.get("justificativa", ""), "max": 600})
    v["linhas"].append(["Dia", _br(data)])
    v["corpo"] = {"item_ref": it["ref"], "data": data, "quantidade": quantidade, "parcelas": parcelas,
                  "memoria_calculo": "" if parcelas else memoria, "local_tipo": local_tipo,
                  "local_id": local_id if local_tipo in ("ZONA", "TRECHO", "ATIVIDADE") else None,
                  "local_texto": "" if local_tipo else c.get("local_texto", ""),
                  "executor_tipo": "EQUIPE_OBRA" if equipe else "NAO_INFORMADO", "equipe_id": (equipe or {}).get("id"),
                  "o_que_foi_feito": c.get("o_que_foi_feito", ""), "justificativa": c.get("justificativa", ""), "evidencias": []}
    if quantidade is None:
        v["corpo"] = None


# ------------------------------------------------------------------ rascunho: aplicar o que o modelo ou a pessoa informou
class _Turno:
    """O que uma mensagem produziu: o rascunho, a fala e os botões que o código já sabe montar (sem outra chamada)."""

    def __init__(self, rascunho=None):
        self.rascunho, self.fala, self.botoes, self.telas, self.ferramentas = rascunho, None, [], [], []
        self.itens, self.candidatos, self.pediu_item, self.notas = {}, None, False, []


def _iniciar(turno, usuario, tipo):
    """Abre (ou troca) o rascunho do tipo. Sem a permissão da rota que grava, não há rascunho: só a explicação."""
    if not _pode(usuario, tipo):
        turno.fala = SEM_PERMISSAO[tipo]
        return False
    if not turno.rascunho or turno.rascunho["tipo"] != tipo:
        turno.rascunho = _novo(tipo)
    return True


def _local(conn, c, texto, erros):
    """'canteiro', 'zona 3' ou um trecho/nó/caixa (servicos.buscar). Mais de um resultado: fica só o texto e o aviso."""
    t = _limpo(texto, 120)
    for k in ("local_tipo", "local_id", "local_texto", "alvo_tipo", "alvo_id"):
        c.pop(k, None)
    if not t:
        return []
    if "CANTEIRO" in _norm(t):
        c["local_tipo"] = "CANTEIRO"
        return []
    f = _frente(t)
    if f:
        c.update(local_tipo="ZONA", local_id=f)
        return []
    achados = S.buscar(conn, t, limite=6)
    if len(achados) == 1:
        c.update(local_tipo=achados[0]["tipo"], local_id=achados[0]["id"], alvo_tipo=achados[0]["tipo"], alvo_id=achados[0]["id"])
        return []
    c["local_texto"] = t
    if not achados:
        erros.append(f"Não achei o trecho, nó ou caixa '{t}'.")
    return achados


def _botoes_local(achados):
    return [{"rotulo": a["nome"] + (f" ({a['extra']})" if a.get("extra") else ""), "aplicar": {"local": a["id"], "local_tipo": a["tipo"]}}
            for a in achados[:6]]


def aplicar_campos(conn, usuario, turno, tipo, args):
    """Põe no rascunho o que veio (do modelo, de um botão ou do formulário). Devolve os erros que quem mandou precisa
    saber; o que ficou ambíguo vira pergunta com botões (turno.fala, turno.botoes)."""
    if not _iniciar(turno, usuario, tipo):
        return []
    c, erros, hoje = turno.rascunho["campos"], [], RL.hoje()
    if "data" in args and args["data"] not in (None, ""):
        d = _data(args["data"], hoje)
        if not d:
            erros.append(f"Data '{args['data']}' não entendida: use AAAA-MM-DD.")
        elif d > hoje.isoformat():
            erros.append(f"A data {_br(d)} está no futuro: só se registra o que já aconteceu.")
        else:
            c["data"] = d
    {"PEDIDO": _aplicar_pedido, "OCORRENCIA": _aplicar_ocorrencia, "APROPRIACAO": _aplicar_apropriacao}[tipo](conn, usuario, turno, c, args, erros)
    return erros


def _aplicar_pedido(conn, usuario, turno, c, args, erros):
    if args.get("frente") not in (None, ""):
        f, permitidas = _frente(args["frente"]), frentes_do_login(conn, usuario)
        if f in permitidas:
            c["frente_id"] = f
        elif len(permitidas) == 1:                                           # o encarregado: só a frente da equipe dele
            if f:
                turno.notas.append(f"Este login não pede para {nome_frente(f)}: o pedido fica para {nome_frente(permitidas[0])}, onde a equipe está programada.")
        elif not f:
            erros.append(f"Frente '{args['frente']}' não existe: são as Zonas 01 a 11, a Subadutora e as Caixas hidráulicas.")
        else:
            erros.append(f"Este login não pede para {nome_frente(f)}.")
    if "observacao" in args:
        c["observacao"] = _limpo(args.get("observacao"))
    itens = c.setdefault("itens", [])
    catalogo = None
    novos = list(args.get("itens") or [])
    if _limpo(args.get("material")):                                         # o campo "Acrescentar material" do formulário
        novos.append({"material": args["material"]})
    for novo in novos[:20]:
        if not isinstance(novo, dict):
            continue
        q, texto = _numero(novo.get("quantidade")), _limpo(novo.get("material") or novo.get("material_id"), 120)
        if _limpo(novo.get("descricao")) and not texto:                     # pedido por escrito: Compras identifica depois
            un = _norm(novo.get("unidade")) or "UN"
            itens.append({"descricao": _limpo(novo["descricao"]), "quantidade": q, "unidade": un if un in SOL.UNIDADES else "UN"})
            continue
        if not texto:
            continue
        catalogo = catalogo or {m["id"]: m for m in SOL.catalogo(conn)}
        limpo = _norm(re.sub(r"\s*[×xX=]\s*[\d.,?]+\s*$", "", texto))          # "Luva eletrofusão 110 mm × 25": o nome que o rascunho mostra
        mesmo_nome = [m for m in catalogo.values() if limpo in (_norm(m["nome"]), _norm(rotulo_material(m)))]
        mesmo_nome = [m for m in mesmo_nome if any(i.get("material_id") == m["id"] for i in itens)] or mesmo_nome[:1]
        achados = [catalogo[texto]] if texto in catalogo else mesmo_nome or buscar_materiais(conn, texto)
        if not achados:
            erros.append(f"Não achei '{texto}' no catálogo. Tente outras palavras em consultar_catalogo ou passe 'descricao' "
                         "para pedir por escrito.")
        elif len(achados) > 1:
            turno.fala = f"Achei mais de um material para “{texto}”. Qual deles?"
            turno.botoes = [{"rotulo": rotulo_material(m), "aplicar": {"itens": [{"material_id": m["id"], "quantidade": q}]},
                             "ctx": f"id {m['id']} = {rotulo_material(m)}"} for m in achados[:8]]
        else:
            mid = achados[0]["id"]
            atual = next((i for i in itens if i.get("material_id") == mid), None)
            if atual:
                atual["quantidade"] = q or atual.get("quantidade")
            else:
                itens.append({"material_id": mid, "quantidade": q})
    for alvo in (args.get("remover") or [])[:20]:
        t = _norm(alvo)
        catalogo = catalogo or {m["id"]: m for m in SOL.catalogo(conn)}
        antes = len(itens)
        itens[:] = [i for i in itens if not (t and (t == _norm(i.get("material_id")) or t in _norm(i.get("descricao"))
                                                   or t in _norm((catalogo.get(i.get("material_id")) or {}).get("nome"))))]
        if len(itens) == antes:
            erros.append(f"'{alvo}' não está no pedido.")
    for chave_, valor in args.items():                                       # edição no formulário: item.<i>.quantidade / .remover
        m = re.fullmatch(r"item\.(\d+)\.(quantidade|remover)", str(chave_))
        if m and int(m.group(1)) < len(itens):
            if m.group(2) == "remover":
                itens[int(m.group(1))] = None
            else:
                itens[int(m.group(1))]["quantidade"] = _numero(valor)
    itens[:] = [i for i in itens if i]


def _aplicar_ocorrencia(conn, usuario, turno, c, args, erros):
    if args.get("tipo") in ("IMPEDIMENTO", "NAO_CONFORMIDADE"):
        c["tipo"] = args["tipo"]
    nc = c.get("tipo") == "NAO_CONFORMIDADE"
    if args.get("categoria") not in (None, ""):
        cat = _norm(args["categoria"]).replace(" ", "_")
        if cat in (NAO_CONFORMIDADES if nc else CATEGORIAS):
            c["categoria"] = cat
        else:
            erros.append(f"Categoria '{args['categoria']}' inválida: " + ", ".join(NAO_CONFORMIDADES if nc else CATEGORIAS) + ".")
    for campo, chave_, validos in (("turno", "turno", TURNOS), ("efeito", "clima_condicao", EFEITOS)):
        if args.get(campo) not in (None, ""):
            valor = _norm(args[campo]).replace(" ", "_")
            if valor in validos:
                c[chave_] = valor
            else:
                erros.append(f"{campo} '{args[campo]}' inválido: " + ", ".join(validos) + ".")
    if args.get("todas_equipes") is True or _norm(args.get("equipe")) == "TODAS":
        if usuario.get("restrito_a_equipe"):
            erros.append("Este login registra chuva só para a própria equipe.")
        else:
            c["todas_equipes"] = True
            c.pop("equipe_id", None)
    elif "equipe" in args and args["equipe"] in (None, ""):                  # o campo foi esvaziado no formulário
        c.pop("equipe_id", None), c.pop("todas_equipes", None)
    elif args.get("equipe") not in (None, ""):
        e = _equipe(conn, usuario, args["equipe"])
        if e:
            c["equipe_id"] = e["id"]
            c.pop("todas_equipes", None)
        else:
            nomes = ", ".join(x["nome"] for x in equipes_do_login(conn, usuario)) or "nenhuma equipe ativa"
            erros.append(f"Equipe '{args['equipe']}' não encontrada para este login. Equipes: {nomes}.")
    if "descricao" in args:
        c["descricao"] = _limpo(args.get("descricao"))
    if "local" in args:
        if args.get("local_tipo") in ("TRECHO", "ATIVIDADE"):                 # botão: o alvo já está determinado
            for k in ("local_texto", "local_tipo", "local_id"):
                c.pop(k, None)
            c.update(alvo_tipo=args["local_tipo"], alvo_id=str(args["local"]))
        else:
            chuva = c.get("categoria") == "CHUVA" and c.get("tipo") != "NAO_CONFORMIDADE"
            sobra = []
            achados = _local(conn, c, args.get("local"), sobra)
            for k in ("local_tipo", "local_id"):                              # a ocorrência é num trecho, nó ou caixa
                c.pop(k, None)
            if chuva and not c.get("alvo_id") and not achados:               # na chuva o lugar é opcional: sem achar, fica sem
                c.pop("local_texto", None)
            elif not c.get("alvo_id") and args.get("local") and not achados:
                erros.append(sobra[0] if sobra else "A interferência precisa do trecho, nó ou caixa (ex.: Zona 03 PB06 TR014).")
            if len(achados) > 1:
                turno.fala, turno.botoes = "Achei mais de um lugar com esse nome. Qual deles?", _botoes_local(achados)


def _papel(nome):
    t = _norm(nome)
    return next((papel for papel, rx in _RX_PAPEL if re.search(rf"(?<![A-Z0-9])(?:{rx})(?![A-Z0-9])", t)), "CONTAGEM")


def _aplicar_apropriacao(conn, usuario, turno, c, args, erros):
    if args.get("item") not in (None, ""):
        it, candidatos = _resolver_item(conn, args["item"])
        if it:
            if c.get("item_ref") and c["item_ref"] != it["ref"]:
                c.pop("medidas", None)                                        # outro item: as medidas eram do anterior
            c["item_ref"] = it["ref"]
        elif candidatos:
            turno.fala = f"O orçamento tem mais de um item para “{_limpo(args['item'], 60)}”. Qual é?"
            turno.botoes = _botoes_itens(candidatos[:8])
            turno.candidatos = [_item_curto(x) for x in candidatos[:8]]
        else:
            erros.append(f"Item '{args['item']}' não encontrado no orçamento: use consultar_orcamento com outras palavras.")
    fat = c.setdefault("fatores", {})
    if args.get("item") in (None, "") and not c.get("item_ref"):
        contado = next((f.get("nome") for f in args.get("fatores") or [] if isinstance(f, dict) and _papel(f.get("nome")) == "CONTAGEM"
                        and _norm(f.get("nome")) not in ("UNIDADE", "UNIDADES", "UN", "")), None)
        if contado:
            it, candidatos = _resolver_item(conn, contado)
            if it:
                c["item_ref"] = it["ref"]
            elif candidatos:
                turno.fala = f"O orçamento tem mais de um item para “{_limpo(contado, 60)}”. Qual é?"
                turno.botoes, turno.candidatos = _botoes_itens(candidatos[:8]), [_item_curto(x) for x in candidatos[:8]]
    if args.get("quantidade") not in (None, ""):
        q = _numero(args["quantidade"])
        if q:
            fat["CONTAGEM"] = {"nome": (fat.get("CONTAGEM") or {}).get("nome") or "unidades", "valor": q}
        else:
            erros.append("A quantidade precisa ser um número maior que zero.")
    dims = None
    for f in (args.get("fatores") or [])[:6]:
        if not isinstance(f, dict):
            continue
        q = _numero(f.get("valor"))
        if not q:
            erros.append(f"Fator '{f.get('nome')}': o valor precisa ser um número maior que zero.")
            continue
        papel = _papel(f.get("nome"))
        if papel in _DIMENSOES:                                              # "85 de comprimento por 2,2 de altura": é medida
            dims = dims or {}
            dims[papel.lower()] = _fmt(q).replace(".", "")
        else:
            fat[papel] = {"nome": _limpo(f.get("nome"), 40) or "unidades", "valor": q}
    if dims and not isinstance(args.get("medidas"), list):
        parte = (c.get("medidas") or [{}])[0] if len(c.get("medidas") or []) <= 1 else {}
        c["medidas"] = [{**parte, **dims}]
    if isinstance(args.get("medidas"), list):
        medidas = []
        for p in args["medidas"][:MC.MAX_PARTES]:
            if isinstance(p, dict):
                m = {k: _limpo(str(p.get(k)).replace(".", ",") if isinstance(p.get(k), (int, float)) else p.get(k), 150)
                     for k in ("descricao", "comprimento", "largura", "profundidade") if p.get(k) not in (None, "")}
                if p.get("repeticoes") not in (None, "", 1, "1"):
                    m["repeticoes"] = _limpo(p["repeticoes"], 6)
                medidas.append(m)
        c["medidas"] = [m for m in medidas if m]
    for chave_, valor in args.items():                                       # edição no formulário
        m = re.fullmatch(r"fator\.([A-Z]+)", str(chave_))
        if m and m.group(1) in PAPEIS:
            q = _numero(valor)
            if q:
                fat[m.group(1)] = {"nome": (fat.get(m.group(1)) or {}).get("nome") or PAPEIS[m.group(1)][1], "valor": q}
            else:
                fat.pop(m.group(1), None)
        m = re.fullmatch(r"medida\.(\d+)\.(comprimento|largura|profundidade)", str(chave_))
        if m:
            medidas = c.setdefault("medidas", [])
            while len(medidas) <= int(m.group(1)) < MC.MAX_PARTES:
                medidas.append({})
            if int(m.group(1)) < len(medidas):
                medidas[int(m.group(1))][m.group(2)] = _limpo(valor, 150)
    if not fat:
        c.pop("fatores", None)
    if "local" in args:
        if args.get("local_tipo") in ("TRECHO", "ATIVIDADE"):
            c.pop("local_texto", None)
            c.update(local_tipo=args["local_tipo"], local_id=str(args["local"]))
        else:
            sobra = []
            achados = _local(conn, c, args.get("local"), sobra)              # local é opcional: sem achar, fica o texto
            for k in ("alvo_tipo", "alvo_id"):
                c.pop(k, None)
            if len(achados) > 1:
                turno.fala, turno.botoes = "Achei mais de um lugar com esse nome. Qual deles?", _botoes_local(achados)
    if args.get("equipe") not in (None, ""):
        e = _equipe(conn, usuario, args["equipe"])
        if e:                                                                # quem executou é opcional: sem achar, fica para o formulário
            c["equipe_id"] = e["id"]
    elif "equipe" in args:
        c.pop("equipe_id", None)
    for campo in ("o_que_foi_feito", "justificativa"):
        if campo in args:
            c[campo] = _limpo(args.get(campo))
    if "descricao" in args:
        c["o_que_foi_feito"] = _limpo(args.get("descricao"))


def _botoes_itens(candidatos):
    """Os itens possíveis como botões. Quando a primeira palavra do nome separa os itens em poucos grupos (Instalação ×
    Locação), o botão é o grupo e o toque abre os itens dele: a pessoa decide em dois toques, sem outra chamada."""
    grupos = {}
    for it in candidatos:
        palavra = (it.get("resumida") or it["descricao"]).split()[0].strip(",.;:")
        grupos.setdefault(_norm(palavra), (palavra.capitalize(), []))[1].append(it)
    if not 2 <= len(grupos) < len(candidatos):
        return [dict(_botao_item(it), tipo="APROPRIACAO") for it in candidatos]
    botoes = []
    for rotulo, itens in grupos.values():
        if len(itens) == 1:
            botoes.append(dict(_botao_item(itens[0]), rotulo=rotulo, tipo="APROPRIACAO"))
        else:
            botoes.append({"rotulo": rotulo, "pergunta": f"Qual {rotulo.lower()}?", "tipo": "APROPRIACAO",
                           "sub": [dict(_botao_item(it), tipo="APROPRIACAO") for it in itens],
                           "ctx": "; ".join(_botao_item(it)["ctx"] for it in itens)})
    return botoes


def _botao_item(it):
    grupo = AP.GRUPOS.get(it["grupo"], it["grupo"].capitalize())
    nome = it.get("resumida") or it["descricao"][:70]
    return {"rotulo": f"{it['item_bm'] or it['item']} · {nome} ({grupo}, {it['unidade']})", "aplicar": {"item": it["item"]},
            "ctx": f"id {it['item']} = {nome}"}


def _fechar(conn, usuario, turno):
    """Monta a vista e, se o código ainda não tem o que dizer, a fala: a próxima pergunta (com botões) ou o rascunho pronto."""
    v = vista(conn, usuario, turno.rascunho)
    if v and turno.notas and not turno.fala:
        proxima = v["faltam"][0]["pergunta"] if v["faltam"] else f"Confira o rascunho e toque em “{v['confirmar']}”."
        turno.fala, turno.botoes = " ".join(turno.notas) + " " + proxima, v["faltam"][0]["botoes"] if v["faltam"] else []
    if v and not turno.fala:
        if v["faltam"]:
            turno.fala, turno.botoes = v["faltam"][0]["pergunta"], v["faltam"][0]["botoes"]
        else:
            turno.fala = f"Anotei: {sintese(conn, v)}. Confira o rascunho e toque em “{v['confirmar']}”."
    return v


def _resposta(conn, usuario, turno, **extra):
    v = _fechar(conn, usuario, turno)
    return {"situacao": "OK", "resposta": turno.fala or "", "botoes": turno.botoes, "rascunho": v, **extra}


def aplicar(conn, usuario, pedido):
    """Sem modelo: o toque num botão, a edição de um campo do rascunho, começar por um atalho ou descartar. É o que
    poupa chamadas da cota: o que já está determinado o próprio sistema aplica."""
    turno = _Turno(normalizar(conn, usuario, pedido.get("rascunho")))
    if pedido.get("descartar"):
        turno.rascunho, turno.fala = None, "Rascunho descartado. O que você quer fazer?"
        return _resposta(conn, usuario, turno)
    tipo = pedido.get("iniciar") or (turno.rascunho or {}).get("tipo")
    if tipo not in TIPOS:
        raise RegraViolada("Não há rascunho aberto.")
    mudar = pedido.get("mudar") if isinstance(pedido.get("mudar"), dict) else {}
    if pedido.get("iniciar") == "OCORRENCIA" and pedido.get("chuva"):
        mudar = {**mudar, "categoria": "CHUVA"}
    erros = aplicar_campos(conn, usuario, turno, tipo, mudar)
    if erros and not turno.fala:
        turno.fala = " ".join(erros)
    return _resposta(conn, usuario, turno)


# ------------------------------------------------------------------ as chamadas de função oferecidas ao modelo
def _f(nome, descricao, propriedades, obrigatorios=()):
    return {"type": "function", "function": {"name": nome, "description": descricao, "parameters": {
        "type": "object", "properties": propriedades, "required": list(obrigatorios)}}}


_S, _N = {"type": "string"}, {"type": "number"}
_FATOR = {"type": "object", "properties": {"nome": _S, "valor": _N}, "required": ["nome", "valor"]}
_MEDIDA = {"type": "object", "properties": {"descricao": _S, "comprimento": {"type": "string", "description": "m; lados com +"},
                                            "largura": {"type": "string", "description": "altura ou largura, m"},
                                            "profundidade": _S, "repeticoes": _N}}
FERRAMENTAS = [                         # descrições curtas de propósito: o plano gratuito conta 8.000 tokens por minuto
    _f("consultar_orcamento", "Lista itens do orçamento (BM) por palavras do serviço.", {"busca": _S}, ["busca"]),
    _f("consultar_catalogo", "Lista materiais do catálogo de pedido por palavras (ex.: 'luva 110').", {"busca": _S}, ["busca"]),
    _f("consultar_frentes", "Zonas para as quais este login pede material e equipes que ele usa.", {}),
    _f("consultar_pedidos", "Pedidos de material que este login vê.", {"quais": {"type": "string", "enum": ["ABERTOS", "TODOS"]}}),
    _f("consultar_ajuda", "Guia de uso: onde fica e como se faz cada coisa no sistema.", {"assunto": _S}, ["assunto"]),
    _f("rascunho_apropriacao",
       "Serviço que FOI FEITO ou item a lançar (fizemos, instalamos, lança, apropria): anota/corrige a apropriação direta. Não serve para dar OK, liberar, verificar ou medir trecho. item (sempre): palavras do serviço no singular como a pessoa falou (ex.: "
       "'contêiner') ou o id do item já escolhido ou listado; o sistema procura. fatores: números que se multiplicam, com o nome do que contam, "
       "ex. [{nome:'contêineres',valor:3},{nome:'mês',valor:1}]. medidas: só para m, m², m³.",
       {"item": _S, "fatores": {"type": "array", "items": _FATOR}, "medidas": {"type": "array", "items": _MEDIDA},
        "data": {"type": "string", "description": "AAAA-MM-DD"}, "local": {"type": "string", "description": "canteiro, zona ou trecho"}},
       ["item"]),
    _f("rascunho_pedido",
       "A pessoa PRECISA de material: anota/corrige o pedido. material: o nome como a pessoa falou (ex.: 'luva 110') ou id do catálogo; o "
       "sistema procura. Repetir o material troca a quantidade.",
       {"itens": {"type": "array", "items": {"type": "object", "properties": {
           "material": _S, "quantidade": _N, "descricao": {"type": "string", "description": "só se não existe no catálogo"}}}},
        "remover": {"type": "array", "items": _S}, "frente": {"type": "string", "description": "zona de destino"}}),
    _f("rascunho_ocorrencia", "Só quando algo ATRAPALHOU o serviço (choveu, rede no caminho, sem acesso, faltou material): anota/corrige o relato de chuva ou interferência.",
       {"categoria": {"type": "string", "enum": list(CATEGORIAS)}, "tipo": {"type": "string", "enum": ["IMPEDIMENTO", "NAO_CONFORMIDADE"]},
        "data": {"type": "string", "description": "AAAA-MM-DD"}, "equipe": {"type": "string", "description": "nome da equipe citada, ou TODAS"},
        "turno": {"type": "string", "enum": list(TURNOS), "description": "parte do dia em que choveu, se dita (de manhã, de tarde, o dia todo)"},
        "efeito": {"type": "string", "enum": list(EFEITOS), "description": "o que a chuva causou"},
        "local": {"type": "string", "description": "trecho, nó ou caixa, só se a pessoa disse"}, "descricao": _S}),
    _f("oferecer_opcoes", "Pergunta com botões e encerra a vez. Em cada opção: itens (ids do orçamento) ou materiais (ids do catálogo).",
       {"pergunta": _S, "opcoes": {"type": "array", "items": {"type": "object", "properties": {
           "rotulo": _S, "itens": {"type": "array", "items": _S}, "materiais": {"type": "array", "items": _S}}, "required": ["rotulo"]}}},
       ["pergunta", "opcoes"]),
    _f("descartar_rascunho", "A pessoa desistiu do lançamento.", {}),
]
_RASCUNHOS = {"rascunho_apropriacao": "APROPRIACAO", "rascunho_pedido": "PEDIDO", "rascunho_ocorrencia": "OCORRENCIA"}


def executar(conn, cfg, usuario, turno, nome, args):
    """Uma chamada de função do modelo. Devolve (resultado para o modelo, segue): segue=True quando o modelo precisa
    ler o resultado (consulta ou erro); False quando o código já sabe responder à pessoa."""
    turno.ferramentas.append(nome)
    if nome == "consultar_orcamento":
        if not _pode(usuario, "APROPRIACAO"):
            return {"erro": SEM_PERMISSAO["APROPRIACAO"]}, True
        achados = buscar_orcamento(conn, args.get("busca"))
        turno.itens = {it["item"]: it for it in achados}
        return {"itens": [_item_curto(it) for it in achados]} if achados else {"itens": [], "dica": "nada achado: tente outra palavra"}, True
    if nome == "consultar_catalogo":
        if not _pode(usuario, "PEDIDO"):
            return {"erro": SEM_PERMISSAO["PEDIDO"]}, True
        achados = buscar_materiais(conn, args.get("busca"))
        return {"materiais": [{"id": m["id"], "nome": rotulo_material(m), "un": m["unidade_nome"]} for m in achados]}, True
    if nome == "consultar_frentes":
        return {"frentes_para_pedir": [nome_frente(f) for f in frentes_do_login(conn, usuario)] if _pode(usuario, "PEDIDO") else [],
                "equipes": [e["nome"] for e in equipes_do_login(conn, usuario)]}, True
    if nome == "consultar_pedidos":
        if not ({"solicitar", "compras"} & set(usuario["telas"])):
            return {"erro": "Este login não vê pedidos de material."}, True
        return {"pedidos": pedidos_do_login(conn, usuario, abertos=args.get("quais") != "TODOS")}, True
    if nome == "consultar_ajuda":
        secoes = ajuda(cfg, usuario, args.get("assunto"))
        turno.telas += [s for s in secoes if _abre(usuario, s)]
        if not secoes:
            return {"ajuda": [], "assuntos": [s["titulo"] for s in cfg.get("ajuda") or []]}, True
        return {"ajuda": [{"titulo": s["titulo"], "texto": s["texto"],
                           "este_login_abre_a_tela": _abre(usuario, s) if s.get("tela") else None} for s in secoes]}, True
    if nome in _RASCUNHOS:
        tipo = _RASCUNHOS[nome]
        if not _pode(usuario, tipo):
            turno.fala, turno.botoes = SEM_PERMISSAO[tipo], []
            return {"erro": SEM_PERMISSAO[tipo]}, False
        turno.fala, turno.botoes, turno.candidatos = None, [], None          # a pergunta de uma tentativa anterior não vale mais
        antes = json.loads(json.dumps(turno.rascunho))
        erros = aplicar_campos(conn, usuario, turno, tipo, args)
        c = turno.rascunho["campos"]
        if (tipo == "APROPRIACAO" and not (antes and antes["tipo"] == tipo) and not turno.botoes
                and not any(c.get(k) for k in ("item_ref", "fatores", "medidas"))):
            turno.rascunho = antes                                           # nada de concreto: o rascunho vazio não é aberto
            return {"erro": "Nenhum item do orçamento nem quantidade para anotar. Se a pessoa quer outra ação do sistema (dar OK ou "
                            "liberar trecho, verificar, nota de serviço, estoque, medição), isso não é apropriação: use "
                            "consultar_ajuda e diga onde se faz. Se é um serviço feito, pergunte qual serviço e quanto.",
                    "erros": erros}, True
        v = vista(conn, usuario, turno.rascunho)
        r = {"ok": not erros, "erros": erros, "rascunho": resumo(conn, v), "falta": [f["pergunta"] for f in v["faltam"]]}
        if turno.candidatos:                                                 # vários itens possíveis: os botões já estão montados
            r.update(itens_possiveis=turno.candidatos)
            return r, False
        if tipo == "APROPRIACAO" and not turno.rascunho["campos"].get("item_ref") and not args.get("item") and not turno.pediu_item:
            turno.pediu_item = True                                          # uma vez por mensagem: o modelo esqueceu de dizer o serviço
            r.update(faca="se a pessoa disse qual é o serviço, chame de novo com 'item' = as palavras do serviço")
            return r, True
        return r, bool(erros)
    if nome == "oferecer_opcoes":
        botoes = _botoes_do_modelo(conn, usuario, turno, args)
        if not botoes:
            return {"erro": "nenhuma opção válida: use ids vindos das consultas"}, True
        turno.fala, turno.botoes = _limpo(args.get("pergunta"), 300) or "Qual destes?", botoes
        return {"ok": True}, False
    if nome == "descartar_rascunho":
        turno.rascunho, turno.fala, turno.botoes = None, "Certo, descartei o rascunho. O que você quer fazer?", []
        return {"ok": True}, False
    return {"erro": f"função {nome} não existe"}, True


def _botoes_do_modelo(conn, usuario, turno, args):
    """As opções do modelo viram botões que o próprio sistema aplica: um item ou material determinado entra direto no
    rascunho; um grupo (ex.: Locação, com três itens) abre os itens dele, sem outra chamada ao modelo."""
    botoes, catalogo = [], None
    for o in (args.get("opcoes") or [])[:8]:
        if not isinstance(o, dict) or not _limpo(o.get("rotulo"), 80):
            continue
        rotulo = _limpo(o["rotulo"], 80)
        itens = []
        for ref in (o.get("itens") or [])[:8]:
            it, _ = _resolver_item(conn, ref) if _pode(usuario, "APROPRIACAO") else (None, [])
            if it and it["item"] not in [x["item"] for x in itens]:
                itens.append(it)
        materiais = []
        if o.get("materiais") and _pode(usuario, "PEDIDO"):
            catalogo = catalogo or {m["id"]: m for m in SOL.catalogo(conn)}
            materiais = [catalogo[m] for m in o["materiais"][:8] if m in catalogo]
        if len(itens) == 1:
            botoes.append({"rotulo": rotulo, "aplicar": {"item": itens[0]["item"]}, "tipo": "APROPRIACAO", "ctx": _botao_item(itens[0])["ctx"]})
        elif itens:
            botoes.append({"rotulo": rotulo, "pergunta": f"Qual {rotulo.lower()}?", "tipo": "APROPRIACAO",
                           "sub": [dict(_botao_item(it), tipo="APROPRIACAO") for it in itens],
                           "ctx": "; ".join(_botao_item(it)["ctx"] for it in itens)})
        elif len(materiais) == 1:
            botoes.append({"rotulo": rotulo, "aplicar": {"itens": [{"material_id": materiais[0]["id"]}]}, "tipo": "PEDIDO",
                           "ctx": f"id {materiais[0]['id']} = {rotulo_material(materiais[0])}"})
        elif materiais:
            botoes.append({"rotulo": rotulo, "pergunta": f"Qual {rotulo.lower()}?", "tipo": "PEDIDO",
                           "sub": [{"rotulo": rotulo_material(m), "aplicar": {"itens": [{"material_id": m["id"]}]}, "tipo": "PEDIDO",
                                    "ctx": f"id {m['id']} = {rotulo_material(m)}"} for m in materiais]})
        elif not o.get("itens") and not o.get("materiais"):
            botoes.append({"rotulo": rotulo, "texto": rotulo})                # opção livre: volta como texto da pessoa
    return botoes


def sintese(conn, v):
    """O rascunho pronto em uma frase, para a pessoa ver na conversa o que ficou anotado (e o que a correção mudou)."""
    linhas, c = dict(v["linhas"]), v["campos"]
    if v["tipo"] == "APROPRIACAO":
        return f"{linhas['Item']}, {linhas.get('Memória de cálculo') or linhas['Quantidade']}, {linhas['Local'].lower()}, dia {linhas['Dia']}"
    if v["tipo"] == "PEDIDO":
        itens = "; ".join(f"{f['rotulo']}: {_fmt(f['valor'])} {f.get('sufixo', '')}".strip() for f in v["form"] if f["id"].startswith("item."))
        return f"{itens}, para {linhas['Para onde']}"
    if c.get("categoria") == "CHUVA" and c.get("tipo") != "NAO_CONFORMIDADE":
        return f"chuva em {linhas['Dia']}, {linhas['Quando'].lower()}, {linhas['Efeito'].lower()}, equipe: {linhas['Equipe']}"
    return f"{linhas['Categoria'].lower()} em {linhas['Onde']}, dia {linhas['Dia']}"


def resumo(conn, v):
    """O rascunho em uma linha, para o modelo saber o que já está anotado (e corrigir só o que mudou)."""
    if not v:
        return "nenhum"
    c, partes = v["campos"], [v["tipo"]]
    if v["tipo"] == "APROPRIACAO":
        if c.get("item_ref"):
            try:
                it = AP.item(conn, c["item_ref"])
                partes.append(f"item {it['item']} ({it['item_bm']} {(it.get('resumida') or it['descricao'])[:50]}, {it['unidade']})")
            except RegraViolada:
                pass
        if c.get("fatores"):
            partes.append("fatores " + ", ".join(f"{f['nome']}={_fmt(f['valor'])}" for f in c["fatores"].values()))
        if c.get("medidas"):
            partes.append("medidas " + json.dumps(c["medidas"], ensure_ascii=False))
    elif v["tipo"] == "PEDIDO":
        nomes = {m["id"]: m["nome"] for m in SOL.catalogo(conn)} if c.get("itens") else {}
        partes.append("itens " + ("; ".join(f"material '{nomes.get(i.get('material_id')) or i.get('descricao')}' quantidade "
                                           f"{_fmt(i['quantidade']) if i.get('quantidade') else '?'}" for i in c.get("itens") or []) or "nenhum"))
        if c.get("frente_id"):
            partes.append("frente " + nome_frente(c["frente_id"]))
    else:
        partes += [f"{k}={c[k]}" for k in ("tipo", "categoria", "turno", "clima_condicao", "equipe_id", "todas_equipes", "descricao") if c.get(k)]
    partes += [f"{rot.lower()} {val}" for rot, val in v["linhas"] if rot in ("Local", "Onde", "Dia")]
    partes.append("falta: " + ("; ".join(f["pergunta"] for f in v["faltam"]) or "nada, pronto para a pessoa conferir"))
    return " | ".join(partes)


# ------------------------------------------------------------------ o modelo (Groq, plano gratuito)
def _http(url, cabecalhos, corpo, tempo):
    req = urllib.request.Request(url, data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"), method="POST", headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return r.status, dict(r.headers.items()), json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        bruto = e.read().decode("utf-8", "replace")
        try:
            dados = json.loads(bruto or "{}")
        except ValueError:                               # não veio da API (ex.: página "400 Bad Request" da borda do serviço)
            dados = {"nao_json": re.sub(r"<[^>]+>|\s+", " ", bruto).strip()[:200]}
        return e.code, dict(e.headers.items()), dados if isinstance(dados, dict) else {}


TRANSPORTE = _http                      # os testes trocam por um modelo simulado; a rede só existe aqui
DORMIR = time.sleep
USO = {"chamadas": 0, "tokens": 0, "restam_chamadas": None, "restam_tokens": None}      # só para diagnóstico e auditoria


def _segundos(texto):
    """'9', '8.93', '2m52.8s', '1h2m3s' → segundos."""
    t = str(texto or "").strip()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return float(t)
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", t)
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)) if m and t else None


def chamar_modelo(cfg, mensagens, ferramentas=None):
    """Uma chamada ao modelo. 429 com espera curta: aguarda e tenta de novo, uma vez; espera longa ou cota do dia:
    CotaExcedida. Nunca tenta outro serviço."""
    k = chave()
    if not k:
        raise IAIndisponivel("A IA ainda não foi ligada neste servidor (falta a chave gratuita da Groq).")
    corpo = {"model": cfg["modelo"], "messages": mensagens, **(cfg.get("parametros") or {})}
    if ferramentas:
        corpo.update(tools=ferramentas, tool_choice="auto")
    cab = {"Content-Type": "application/json", "Authorization": "Bearer " + k, "User-Agent": "assistente-obra/1.0"}
    falhou_formato = esperou = False
    for tentativa in range(3):
        if falhou_formato and tentativa == 2 and ferramentas:               # o modelo insiste numa chamada inválida: responde em texto
            corpo["tool_choice"] = "none"
        try:
            status, h, dados = TRANSPORTE(cfg["base_url"] + "/chat/completions", cab, corpo, cfg.get("tempo_s", 20))
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise IAIndisponivel("Não consegui falar com o serviço da IA (rede ou tempo esgotado).") from e
        h = {str(a).lower(): b for a, b in (h or {}).items()}
        USO["chamadas"] += 1
        for campo, cabecalho in (("restam_chamadas", "x-ratelimit-remaining-requests"), ("restam_tokens", "x-ratelimit-remaining-tokens")):
            if h.get(cabecalho) is not None:
                USO[campo] = h[cabecalho]
        erro = (dados or {}).get("error") or {}
        if status == 200 and (dados.get("choices") or [{}])[0].get("message"):
            USO["tokens"] += int((dados.get("usage") or {}).get("total_tokens") or 0)
            return dados["choices"][0]["message"], dados.get("usage") or {}
        if status == 429:
            tipo = "requests" if erro.get("type") == "requests" else "tokens"
            espera = _segundos(h.get("retry-after"))
            if espera is None:
                espera = _segundos(h.get(f"x-ratelimit-reset-{tipo}")) or 60
            if not esperou and espera <= cfg.get("espera_maxima_s", 6):
                esperou = True
                DORMIR(espera + 0.3)
                continue
            # a mensagem do serviço diz a janela: "(TPM)"/"(RPM)" por minuto, "(TPD)"/"(RPD)" por dia (o teto diário de
            # tokens não aparece nos cabeçalhos); só a janela é aproveitada, o resto do texto não vai à tela
            janela = "dia" if re.search(r"\((?:TPD|RPD)\)|per day", str(erro.get("message") or "")) or espera > 120 else "minuto"
            raise CotaExcedida(tipo, int(math.ceil(espera)), janela)
        if status == 413:                                                    # pedido maior que o limite por minuto
            raise CotaExcedida("tokens", 60)
        if status == 400 and erro.get("code") == "tool_use_failed" and tentativa < 2:
            falhou_formato = True                                            # o modelo errou o formato da chamada: tenta outra vez
            continue
        if status in (401, 403):
            raise IAIndisponivel("A chave da IA foi recusada pelo serviço: confira a GROQ_API_KEY no servidor.", _motivo(status, dados))
        raise IAIndisponivel(f"O serviço da IA respondeu com erro ({status}).", _motivo(status, dados))
    raise IAIndisponivel("O serviço da IA não respondeu de forma válida.")


_DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def instrucoes(conn, usuario, turno, opcoes, texto=""):
    hoje = RL.hoje()
    equipe = " (encarregado: a equipe e a zona dele entram sozinhas)" if usuario.get("restrito_a_equipe") else ""
    equipes = [] if usuario.get("restrito_a_equipe") or not _pode(usuario, "OCORRENCIA") else [e["nome"] for e in equipes_do_login(conn, usuario)]
    t = f"""Você é o assistente do sistema da obra Morro da Cruz (rede de água). Fale português do Brasil, simples e curto (até 3 frases), sem markdown.
Hoje: {_DIAS[hoje.weekday()]}, {hoje.isoformat()}. Perfil de quem fala: {usuario['perfil_nome']}{equipe}.
Você cuida de quatro coisas: dúvida de uso do sistema; pedido de material (a pessoa precisa de algo); relato de chuva ou interferência (algo atrapalhou o serviço); apropriação direta (um serviço foi feito ou um item do orçamento deve ser lançado, ex.: canteiro).
Regras:
1. Leia a mensagem inteira e o contexto e decida: responder, consultar ou perguntar o que falta (uma pergunta por vez).
2. Nunca invente item, material, zona, equipe, número, data nem como o sistema funciona. Dúvida de uso: consultar_ajuda antes.
3. Dados de lançamento vão para rascunho_apropriacao, rascunho_pedido ou rascunho_ocorrencia: tudo o que a mensagem trouxe (serviço ou material, números com o nome do que contam, lugar, dia) e só isso. O sistema procura, valida, calcula e mostra o formulário; você não grava nem calcula.
4. Se a pessoa escolhe uma das opções da tela por texto, anote o id dela (a de nome mais próximo do que ela disse, sem nada a mais). Na dúvida, pergunte.
5. Correção ("na verdade foram três") muda só aquele campo do rascunho atual.
6. Qualquer outra ação do sistema (dar OK ou liberar trecho, verificar, nota de serviço, apontamento, estoque, nota fiscal, cadastro, medição) NÃO é lançamento seu: não abra rascunho; use consultar_ajuda e diga onde a pessoa faz. Assunto fora da obra: diga em uma frase o que você faz.
7. Não decida você se a pessoa pode ou não lançar: chame a função do assunto e o sistema confere a permissão do login."""
    if 0 < len(equipes) <= 8:
        t += "\nEquipes: " + "; ".join(equipes) + "."
    v = vista(conn, usuario, turno.rascunho)
    t += "\nRascunho atual: " + resumo(conn, v)
    if opcoes:
        t += "\nOpções na tela agora (a pessoa pode escolher por texto):\n" + "\n".join("- " + o for o in opcoes)
        perto = mais_proxima(texto, opcoes)
        if perto:
            t += "\nPelas palavras da mensagem, a opção mais próxima é: " + perto
    return t


def _opcoes_vistas(lista, grupo=True):
    """As opções que estavam na tela, uma por linha e com o id, para o modelo entender 'o segundo' ou 'o sanitário'.
    O grupo (Locação) entra pelos itens dele."""
    out = []
    for b in (lista if isinstance(lista, list) else [])[:8]:
        if not isinstance(b, dict) or not _limpo(b.get("rotulo"), 80):
            continue
        if grupo and isinstance(b.get("sub"), list):                        # um nível só: o que vem do navegador não é confiável
            out += _opcoes_vistas(b["sub"], grupo=False)
        elif _limpo(b.get("ctx")):
            out.append(_limpo(b["ctx"], 160))
        else:
            out.append(_limpo(b["rotulo"], 80))
    return out[:12]


def mais_proxima(texto, opcoes):
    """A opção da tela cujo nome mais casa com as palavras da pessoa, só quando ganha sozinha e com folga: conta a
    favor a palavra do nome que a pessoa disse; conta contra a palavra do nome que ela não disse e a palavra que ela
    disse e é de outra opção. É uma dica para o modelo (que continua decidindo), não uma escolha do código."""
    ditas = {v for p in re.findall(r"[A-Z0-9]+", _norm(texto)) if p not in AP.PARADAS for v in _variantes(p)}
    nomes = [set(t for t in re.findall(r"[A-Z0-9]+", _norm(o.split("=", 1)[-1])) if t not in AP.PARADAS) for o in opcoes]
    if len(nomes) < 2:
        return None
    comuns, todas = set.intersection(*nomes), set.union(*nomes)
    pontos = []
    for nome in nomes:
        a_favor = len(nome & ditas)
        pontos.append(a_favor - len(nome - ditas - comuns) - len((ditas & todas) - nome) if a_favor else -99)
    melhor = max(pontos)
    return opcoes[pontos.index(melhor)] if melhor > 0 and pontos.count(melhor) == 1 and sorted(pontos)[-2] <= melhor - 2 else None


_RITMO = {}
_TRAVA_RITMO = threading.Lock()


def _ritmo(cfg, usuario):
    """Freio por login (mensagens por minuto), para uma pessoa não gastar sozinha a cota gratuita de todos."""
    agora, limite = time.monotonic(), int(cfg.get("mensagens_por_minuto", 8))
    with _TRAVA_RITMO:
        fila = _RITMO.setdefault(usuario["id"], deque())
        while fila and agora - fila[0] > 60:
            fila.popleft()
        if len(fila) >= limite:
            return int(math.ceil(60 - (agora - fila[0])))
        fila.append(agora)
    return 0


def _aviso_cota(janela, espera):
    if janela == "dia":
        volta = "" if espera > 6 * 3600 else f" (dá para tentar de novo em cerca de {max(1, math.ceil(espera / 60))} minutos)"
        return f"A cota gratuita de hoje da IA acabou. Ela volta sozinha, aos poucos{volta}; enquanto isso, use o formulário."
    quando = f"em {espera} segundos" if espera < 90 else f"em cerca de {math.ceil(espera / 60)} minutos"
    return f"A IA atingiu o limite gratuito por agora. Tente de novo {quando}, ou siga pelo formulário."


def conversar(conn, trava, usuario, pedido):
    """Uma mensagem da pessoa. As chamadas ao modelo ficam FORA da trava do banco; cada consulta ou anotação entra na
    trava só enquanto lê. Nada é gravado: a resposta traz a fala, os botões e o rascunho conferido."""
    texto = _limpo(pedido.get("texto"), LIMITE_TEXTO)
    if not texto:
        raise RegraViolada("Escreva o que você quer fazer.")
    with trava:
        turno = _Turno(normalizar(conn, usuario, pedido.get("rascunho")))
        base = {"rascunho": vista(conn, usuario, turno.rascunho)}
    try:
        cfg = config()
        if not chave():
            raise IAIndisponivel("A IA ainda não foi ligada neste servidor (falta a chave gratuita da Groq).")
    except IAIndisponivel as e:
        return {"situacao": "INDISPONIVEL", "aviso": str(e), **base, "uso": {"chamadas": 0, "tokens": 0, "ferramentas": []}}
    espera = _ritmo(cfg, usuario)
    if espera:
        return {"situacao": "COTA", "cota": {"tipo": "ritmo", "espera_s": espera}, **base,
                "aviso": f"Muitas mensagens em pouco tempo. Tente de novo em {espera} segundos, ou siga pelo formulário.",
                "uso": {"chamadas": 0, "tokens": 0, "ferramentas": []}}
    with trava:
        sistema = instrucoes(conn, usuario, turno, _opcoes_vistas(pedido.get("opcoes")), texto)
    mensagens = [{"role": "system", "content": sistema}]
    for m in (pedido.get("conversa") if isinstance(pedido.get("conversa"), list) else [])[-int(cfg.get("historico_mensagens", 8)):]:
        if isinstance(m, dict) and _limpo(m.get("texto")):
            mensagens.append({"role": "user" if m.get("de") == "u" else "assistant", "content": _limpo(m["texto"], LIMITE_FALA)})
    mensagens.append({"role": "user", "content": texto})
    uso = {"chamadas": 0, "tokens": 0, "ferramentas": turno.ferramentas}
    rastro = uso.setdefault("rastro", []) if os.environ.get("MC_IA_RASTRO") else None      # só nos roteiros de validação
    fala_modelo = None
    try:
        for _ in range(int(cfg.get("chamadas_por_mensagem", 3))):
            msg, consumo = chamar_modelo(cfg, mensagens, FERRAMENTAS)
            uso["chamadas"] += 1
            uso["tokens"] += int(consumo.get("total_tokens") or 0)
            chamadas = msg.get("tool_calls") or []
            if not chamadas:
                fala_modelo = _limpo(msg.get("content"), 1500)
                break
            mensagens.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": chamadas})
            segue = False
            for ch in chamadas[:6]:
                fn = ch.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = None
                with trava:
                    if not isinstance(args, dict):
                        resultado, continua = {"erro": "argumentos inválidos (JSON)"}, True
                    else:
                        try:
                            resultado, continua = executar(conn, cfg, usuario, turno, fn.get("name"), args)
                        except RegraViolada as e:
                            resultado, continua = {"erro": str(e)}, True
                segue = segue or continua
                if rastro is not None:
                    rastro.append({"funcao": fn.get("name"), "argumentos": args, "resultado": resultado})
                mensagens.append({"role": "tool", "tool_call_id": ch.get("id"), "content": json.dumps(resultado, ensure_ascii=False, default=str)})
            for ch in chamadas[6:]:
                mensagens.append({"role": "tool", "tool_call_id": ch.get("id"), "content": '{"erro": "chamadas demais de uma vez"}'})
            if not segue or "oferecer_opcoes" in [(c.get("function") or {}).get("name") for c in chamadas] and turno.botoes:
                break
    except CotaExcedida as e:
        # a cota acabou no meio: o que já foi anotado nesta mensagem fica no rascunho devolvido, e a tela guarda o texto
        with trava:
            v = vista(conn, usuario, turno.rascunho)
        return {"situacao": "COTA", "cota": {"tipo": e.tipo, "janela": e.janela, "espera_s": e.espera_s}, "aviso": _aviso_cota(e.janela, e.espera_s),
                "rascunho": v, "uso": uso}
    except IAIndisponivel as e:
        with trava:
            v = vista(conn, usuario, turno.rascunho)
        uso["motivo"] = e.detalhe                                            # vai para a auditoria e o log, não para a tela
        return {"situacao": "INDISPONIVEL", "aviso": str(e), "rascunho": v, "uso": uso}
    with trava:
        if fala_modelo and not turno.botoes:
            turno.fala = fala_modelo
            if turno.telas:                                                  # dúvida de uso: o botão que leva à tela
                vistas = {}                                                  # um botão por tela, com o nome da tela
                for sec in turno.telas:
                    vistas.setdefault(sec["tela"], {"rotulo": "Abrir " + (sec.get("botao") or sec["titulo"]), "tela": sec["tela"]})
                turno.botoes = list(vistas.values())[:2]
        elif not turno.fala and not turno.rascunho:
            turno.fala = "Não consegui entender. Pode dizer de outro jeito?"
        return _resposta(conn, usuario, turno, uso=uso)


# ------------------------------------------------------------------ teste pelo console (python assistente.py testar)
def testar():
    """Uma chamada mínima ao serviço, para conferir no console do servidor a chave e a saída para a internet. Não usa o
    banco e gasta uma chamada da cota gratuita. Diz o motivo que o serviço deu, sem mostrar a chave."""
    cfg = config()
    print(f"Modelo: {cfg['modelo']}  ·  Endereço: {cfg['base_url']}")
    if not chave():
        print(f"SEM CHAVE: defina GROQ_API_KEY ou grave {arquivo_segredos()} (docs/ASSISTENTE_IA.md).")
        return 1
    tamanho, problemas = forma_da_chave()
    print(f"Chave: {tamanho} caracteres" + ("; " + "; ".join(problemas) if problemas else ", com a forma esperada") + ".")
    try:
        msg, uso = chamar_modelo(dict(cfg, espera_maxima_s=0), [{"role": "user", "content": "Responda só: ok"}])
    except CotaExcedida as e:
        print(f"A chave funciona, mas a cota gratuita está esgotada agora ({e.tipo} por {e.janela}; volta em {e.espera_s} s).")
        return 0
    except IAIndisponivel as e:
        causa = repr(e.__cause__) if e.__cause__ else ""
        print(f"NÃO FUNCIONOU: {e} {causa}")
        if e.detalhe:
            print(f"O que o serviço respondeu: {e.detalhe}")
        if "403" in causa or "Tunnel" in causa or "Forbidden" in causa:
            print("A hospedagem bloqueou a saída para api.groq.com. Na conta gratuita do PythonAnywhere o endereço precisa "
                  "estar na lista de sites liberados: peça a inclusão pelo formulário deles (é grátis; docs/ASSISTENTE_IA.md).")
        elif "organization_restricted" in e.detalhe:
            print("A Groq restringiu a conta dona desta chave. Isso é do lado deles: fale com o suporte da Groq ou gere a "
                  "chave em outra conta gratuita.")
        elif "model" in e.detalhe and ("not_found" in e.detalhe or "decommissioned" in e.detalhe or "terms" in e.detalhe):
            print("O problema é o modelo nesta conta: veja a mensagem acima (aceite de termos no painel da Groq, ou troque "
                  "o modelo em config/assistente.json).")
        elif problemas or "borda do serviço" in e.detalhe or "401" in e.detalhe[:9]:
            print("A chave gravada parece errada ou incompleta: gere uma nova no painel da Groq, copie pelo botão de copiar "
                  "e grave de novo com o comando de docs/ASSISTENTE_IA.md.")
        return 1
    print(f"OK: a IA respondeu “{_limpo(msg.get('content'), 60)}” ({uso.get('total_tokens', '?')} tokens). "
          f"Restam hoje {USO['restam_chamadas']} chamadas; neste minuto, {USO['restam_tokens']} tokens.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(testar() if sys.argv[1:2] == ["testar"] else print("Uso: python assistente.py testar") or 2)
