"""Usuários, sessões, permissões, auditoria e reenvio idempotente (módulo A).

* Senha: PBKDF2-HMAC-SHA256 com sal aleatório (biblioteca padrão); só o hash fica no banco.
* Sessão: token aleatório entregue em cookie HttpOnly/SameSite=Strict; no banco fica só o SHA-256 do token.
  Expira depois de 12 h sem uso.
* Permissão: matriz PROVISÓRIA em config/perfis.json (decisão D-10). O servidor confere a permissão de cada rota.
* Autor: quem grava é o usuário da sessão. O servidor substitui os campos de autoria enviados pelo navegador.
* Auditoria: toda gravação (aceita ou recusada), login e saída ficam em `auditoria`, com usuário, perfil, rota,
  objeto, resultado e o corpo da requisição (sem senha nem conteúdo de arquivo).
* Reenvio: a mesma chave de requisição (cabeçalho X-Idem) do mesmo usuário devolve a resposta já dada, sem
  executar de novo. A chave reaproveitada para outra operação é recusada.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta

import regras as R

BASE = os.path.dirname(os.path.abspath(__file__))
ITERACOES = 200_000
VALIDADE_SESSAO = timedelta(hours=12)
MAX_FALHAS, JANELA_FALHAS = 5, timedelta(minutes=15)
CAMPOS_OCULTOS = {"senha", "senha_atual", "nova_senha", "conteudo_b64", "xml", "arquivo_b64"}


class AcessoNegado(R.RegraViolada):
    """Login inválido, sessão ausente/expirada (401) ou permissão insuficiente (403)."""

    def __init__(self, msg, status=403):
        super().__init__(msg)
        self.status = status


def carregar_perfis():
    with open(os.path.join(BASE, "config", "perfis.json"), encoding="utf-8") as f:
        return json.load(f)


def _agora():
    return datetime.now()


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def hash_senha(senha, sal=None, iteracoes=ITERACOES):
    sal = sal or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${sal.hex()}${h.hex()}"


def conferir_senha(senha, armazenado):
    try:
        alg, it, sal, h = armazenado.split("$")
    except (AttributeError, ValueError):
        return False
    if alg != "pbkdf2_sha256":
        return False
    calc = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(sal), int(it))
    return hmac.compare_digest(calc.hex(), h)


def _validar_senha(senha):
    if not isinstance(senha, str) or len(senha) < 10:
        raise R.RegraViolada("A senha precisa ter pelo menos 10 caracteres.")


def _usuario(conn, login):
    r = conn.execute("SELECT * FROM usuarios WHERE login=?", (str(login or "").strip().lower(),)).fetchone()
    return dict(r) if r else None


def permissoes_do_perfil(perfil, perfis=None):
    perfis = perfis or carregar_perfis()
    p = perfis["perfis"].get(perfil)
    return set(p["permissoes"]) if p else set()


def publico(u, perfis=None):
    """Dados do usuário que podem ir para a tela (sem hash de senha)."""
    perfis = perfis or carregar_perfis()
    p = perfis["perfis"].get(u["perfil"], {})
    return {"id": u["id"], "login": u["login"], "nome": u["nome"], "perfil": u["perfil"], "perfil_nome": p.get("nome", u["perfil"]),
            "equipe_id": u["equipe_id"], "ativo": u["ativo"], "restrito_a_equipe": bool(p.get("restrito_a_equipe")),
            "permissoes": sorted(permissoes_do_perfil(u["perfil"], perfis))}


def criar_usuario(conn, login, nome, perfil, senha, equipe_id=None, criado_por="instalação"):
    login = str(login or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,32}", login):
        raise R.RegraViolada("Login: 3 a 32 caracteres (letras minúsculas, números, ponto, hífen ou sublinhado).")
    if not str(nome or "").strip():
        raise R.RegraViolada("Informe o nome da pessoa.")
    perfis = carregar_perfis()
    if perfil not in perfis["perfis"]:
        raise R.RegraViolada(f"Perfil inválido. Perfis: {', '.join(perfis['perfis'])}.")
    if perfis["perfis"][perfil].get("restrito_a_equipe"):
        if not equipe_id or not conn.execute("SELECT 1 FROM equipes WHERE id=?", (equipe_id,)).fetchone():
            raise R.RegraViolada("Perfil de equipe exige a equipe (Zona01…Zona11, ADUTORA, CH).")
    _validar_senha(senha)
    if _usuario(conn, login):
        raise R.RegraViolada(f"Login '{login}' já existe.")
    return conn.execute(
        "INSERT INTO usuarios(login,nome,perfil,senha,equipe_id,ativo,criado_em,criado_por) VALUES (?,?,?,?,?,1,?,?)",
        (login, nome.strip(), perfil, hash_senha(senha), equipe_id, _iso(_agora()), criado_por)).lastrowid


def alterar_usuario(conn, login, por, perfil=None, ativo=None, equipe_id=None, nome=None):
    u = _usuario(conn, login)
    if not u:
        raise R.RegraViolada(f"Usuário '{login}' não encontrado.")
    perfis = carregar_perfis()
    novo_perfil = perfil or u["perfil"]
    if novo_perfil not in perfis["perfis"]:
        raise R.RegraViolada("Perfil inválido.")
    nova_equipe = equipe_id if equipe_id is not None else u["equipe_id"]
    if perfis["perfis"][novo_perfil].get("restrito_a_equipe") and not nova_equipe:
        raise R.RegraViolada("Perfil de equipe exige a equipe.")
    if u["login"] == str(por).lower() and ativo is not None and not ativo:
        raise R.RegraViolada("Você não pode desativar o próprio usuário.")
    conn.execute("UPDATE usuarios SET perfil=?, ativo=?, equipe_id=?, nome=? WHERE id=?",
                 (novo_perfil, u["ativo"] if ativo is None else (1 if ativo else 0), nova_equipe, nome or u["nome"], u["id"]))
    if ativo is not None and not ativo:
        conn.execute("DELETE FROM sessoes WHERE usuario_id=?", (u["id"],))


def redefinir_senha(conn, login, senha):
    u = _usuario(conn, login)
    if not u:
        raise R.RegraViolada(f"Usuário '{login}' não encontrado.")
    _validar_senha(senha)
    conn.execute("UPDATE usuarios SET senha=? WHERE id=?", (hash_senha(senha), u["id"]))
    conn.execute("DELETE FROM sessoes WHERE usuario_id=?", (u["id"],))


def trocar_senha(conn, usuario_id, senha_atual, nova_senha):
    u = dict(conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone())
    if not conferir_senha(senha_atual or "", u["senha"]):
        raise AcessoNegado("Senha atual incorreta.", 403)
    _validar_senha(nova_senha)
    conn.execute("UPDATE usuarios SET senha=? WHERE id=?", (hash_senha(nova_senha), usuario_id))


def ha_usuarios(conn):
    return conn.execute("SELECT 1 FROM usuarios WHERE ativo=1 LIMIT 1").fetchone() is not None


def autenticar(conn, login, senha, origem=None):
    """Devolve (token, usuário público). Falha → AcessoNegado 401 (mensagem única, sem dizer o que errou)."""
    login = str(login or "").strip().lower()
    desde = _iso(_agora() - JANELA_FALHAS)
    falhas = conn.execute("SELECT COUNT(*) FROM auditoria WHERE rota='/api/login' AND login=? AND status=401 AND em>=?",
                          (login, desde)).fetchone()[0]
    if falhas >= MAX_FALHAS:
        raise AcessoNegado("Muitas tentativas de login sem sucesso: aguarde 15 minutos.", 429)
    u = _usuario(conn, login)
    if not u or not u["ativo"] or not conferir_senha(senha or "", u["senha"]):
        raise AcessoNegado("Login ou senha inválidos.", 401)
    token = secrets.token_urlsafe(32)
    agora = _agora()
    conn.execute("INSERT INTO sessoes(token_sha,usuario_id,criada_em,expira_em,origem) VALUES (?,?,?,?,?)",
                 (hashlib.sha256(token.encode()).hexdigest(), u["id"], _iso(agora), _iso(agora + VALIDADE_SESSAO), origem))
    conn.execute("DELETE FROM sessoes WHERE expira_em < ?", (_iso(agora),))
    return token, publico(u)


def sessao(conn, token):
    """Usuário público da sessão válida (renova a validade) ou None."""
    if not token:
        return None
    sha = hashlib.sha256(token.encode()).hexdigest()
    r = conn.execute("""SELECT u.* FROM sessoes s JOIN usuarios u ON u.id=s.usuario_id
                        WHERE s.token_sha=? AND s.expira_em>=? AND u.ativo=1""", (sha, _iso(_agora()))).fetchone()
    if not r:
        return None
    conn.execute("UPDATE sessoes SET expira_em=? WHERE token_sha=?", (_iso(_agora() + VALIDADE_SESSAO), sha))
    return publico(dict(r))


def encerrar(conn, token):
    if token:
        conn.execute("DELETE FROM sessoes WHERE token_sha=?", (hashlib.sha256(token.encode()).hexdigest(),))


def exigir(usuario, permissao):
    if usuario is None:
        raise AcessoNegado("Entre com seu usuário.", 401)
    if permissao and permissao not in usuario["permissoes"]:
        perfis = carregar_perfis()
        raise AcessoNegado(f"Seu perfil ({usuario['perfil_nome']}) não tem a permissão "
                           f"\"{perfis['permissoes'].get(permissao, permissao)}\".", 403)


def _limpo(corpo):
    if isinstance(corpo, dict):
        return {k: ("[omitido]" if k in CAMPOS_OCULTOS else _limpo(v)) for k, v in corpo.items()}
    if isinstance(corpo, list):
        return [_limpo(v) for v in corpo[:200]]
    return corpo


def _alvo(corpo):
    if not isinstance(corpo, dict):
        return None, None
    for tipo, chave in (("TRECHO", "trecho_id"), (None, "alvo_id"), ("MOVIMENTO", "movimento_id"), ("INTERVALO", "intervalo_id"),
                        ("SOLDA", "solda_id"), ("NF", "nf_id"), ("CHECKIN", "checkin_id"), ("RESERVA", "reserva_id")):
        if corpo.get(chave) not in (None, ""):
            return (tipo or corpo.get("alvo_tipo")), str(corpo[chave])
    if corpo.get("ref_tipo") and corpo.get("ref_id"):
        return corpo["ref_tipo"], str(corpo["ref_id"])
    return None, None


def auditar(conn, usuario, metodo, rota, status, corpo=None, resultado=None, idem=None, login=None):
    tipo, aid = _alvo(corpo)
    conn.execute(
        """INSERT INTO auditoria(em,usuario_id,login,perfil,metodo,rota,alvo_tipo,alvo_id,status,resultado,corpo,idem)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_iso(_agora()), usuario["id"] if usuario else None, (usuario or {}).get("login") or login,
         (usuario or {}).get("perfil"), metodo, rota, tipo, aid, status,
         None if resultado is None else str(resultado)[:2000],
         json.dumps(_limpo(corpo), ensure_ascii=False, default=str)[:20000] if corpo is not None else None, idem))


def consultar_auditoria(conn, alvo_tipo=None, alvo_id=None, login=None, limite=100):
    sql, args = "SELECT * FROM auditoria WHERE 1=1", []
    if alvo_id:
        sql, args = sql + " AND alvo_id=?", args + [alvo_id]
        if alvo_tipo:
            sql, args = sql + " AND (alvo_tipo=? OR alvo_tipo IS NULL)", args + [alvo_tipo]
    if login:
        sql, args = sql + " AND login=?", args + [login]
    return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC LIMIT ?", args + [int(limite)])]


def corpo_sha(corpo):
    return hashlib.sha256(json.dumps(corpo, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def resposta_anterior(conn, usuario, chave, rota, corpo):
    """Resposta já dada à mesma chave (reenvio) ou None. Chave reutilizada em outra operação → recusa."""
    if not chave:
        return None
    r = conn.execute("SELECT * FROM requisicoes WHERE usuario_id=? AND chave=?", (usuario["id"], chave)).fetchone()
    if not r:
        return None
    if r["rota"] != rota or r["corpo_sha"] != corpo_sha(corpo):
        raise R.RegraViolada("Chave de reenvio já usada em outra operação: recarregue a página e tente de novo.")
    return json.loads(r["resposta"])


def guardar_resposta(conn, usuario, chave, rota, corpo, resposta):
    if chave:
        conn.execute("INSERT INTO requisicoes(usuario_id,chave,rota,corpo_sha,resposta,em) VALUES (?,?,?,?,?,?)",
                     (usuario["id"], chave, rota, corpo_sha(corpo), json.dumps(resposta, ensure_ascii=False, default=str),
                      _iso(_agora())))
