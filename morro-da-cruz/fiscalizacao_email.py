"""Fila durável de avisos. Sem credenciais no banco; SMTP somente depois do commit HTTP.

Não retenta automaticamente um envio de resultado incerto: evita e-mail duplicado. O contador
continua funcionando quando o SMTP estiver indisponível. Testes substituem smtplib.SMTP.
"""
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from urllib.parse import urlsplit

import servicos as S

_LOCK = threading.Lock()
_TRABALHOS = {}


def _configurada():
    return bool(os.environ.get("MC_EMAIL_USUARIO") and os.environ.get("MC_EMAIL_SENHA_APP"))


def _destinos(conn, perfil):
    import acesso as A
    out = []
    for r in conn.execute("SELECT email FROM usuarios WHERE ativo=1 AND perfil=? AND email IS NOT NULL", (perfil,)):
        try:
            email = A.validar_email(r[0])
        except S.RegraViolada:
            continue
        if email and email not in out:
            out.append(email)
    return out


def enfileirar(conn, medicao_id, envio_id, acao, perfil, linhas, valor):
    st, detalhe = "PENDENTE", "Aviso gravado. O envio ocorre depois da confirmação da operação."
    if not _configurada():
        st, detalhe = "SEM_CONFIGURACAO", "Gmail da obra ainda não configurado. Use o contador do menu."
    elif not _destinos(conn, perfil):
        st, detalhe = "SEM_DESTINATARIO", "Nenhum usuário ativo do perfil de destino tem e-mail válido."
    conn.execute("""INSERT INTO fiscalizacao_emails(medicao_id,envio_id,acao,perfil_destino,linhas,valor,situacao,detalhe,criado_em)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (medicao_id, envio_id, acao, perfil, linhas, valor, st, detalhe, S._agora()))
    if envio_id:
        conn.execute("UPDATE fiscalizacao_envios SET email_situacao=?,email_detalhe=? WHERE id=?", (st, detalhe, envio_id))
    return st


def _concluir(conn, r, st, detalhe):
    with S.transacao(conn):
        conn.execute("UPDATE fiscalizacao_emails SET situacao=?,detalhe=?,concluido_em=? WHERE id=?",
                     (st, detalhe, S._agora(), r["id"]))
        if r["envio_id"]:
            conn.execute("UPDATE fiscalizacao_envios SET email_situacao=?,email_detalhe=? WHERE id=?",
                         (st, detalhe, r["envio_id"]))


def processar(conn):
    """Processa a fila já COMMITADA, em conexão própria no worker; síncrono somente nos testes."""
    while True:
        with S.transacao(conn):
            r = S._one(conn, "SELECT * FROM fiscalizacao_emails WHERE situacao='PENDENTE' ORDER BY id LIMIT 1")
            if not r:
                return
            conn.execute("UPDATE fiscalizacao_emails SET situacao='ENVIANDO' WHERE id=?", (r["id"],))
        if not _configurada():
            _concluir(conn, r, "SEM_CONFIGURACAO", "Gmail da obra ainda não configurado. Use o contador do menu.")
            continue
        destinos = _destinos(conn, r["perfil_destino"])
        if not destinos:
            _concluir(conn, r, "SEM_DESTINATARIO", "Nenhum usuário ativo do perfil de destino tem e-mail válido.")
            continue
        try:
            numero = conn.execute("SELECT numero FROM medicoes WHERE id=?", (r["medicao_id"],)).fetchone()[0]
            msg = EmailMessage()
            msg["From"] = os.environ["MC_EMAIL_USUARIO"]
            msg["To"] = "undisclosed-recipients:;"
            msg["Subject"] = f"Morro da Cruz · Fiscalização · {numero}ª medição"
            # URL opcional validada. Não coloca login, nome, alvo nem descrição de serviço no corpo.
            raiz = os.environ.get("MC_SITE_URL", "").strip().rstrip("/")
            parsed = urlsplit(raiz)
            link = raiz + "/#fiscalizacao" if parsed.scheme == "https" and parsed.netloc and not parsed.username else "/#fiscalizacao"
            valor = f"{r['valor']:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            msg.set_content(f"Há uma atualização na {numero}ª medição.\n{r['linhas']} linha(s) · R$ {valor}.\n"
                            f"Abra a aba Fiscalização no site da obra: {link}\nAceite prévio. O oficial é o BM assinado e protocolado.")
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(os.environ["MC_EMAIL_USUARIO"], os.environ["MC_EMAIL_SENHA_APP"])
                recusados = smtp.send_message(msg, to_addrs=destinos)
                if recusados:
                    raise smtplib.SMTPException("Destinatário recusado")
            _concluir(conn, r, "ENVIADO", "Aviso enviado pelo Gmail da obra.")
        except Exception as exc:
            # Nunca grava str(exc): provedores/mocks podem incluir usuário/senha na mensagem.
            codigo = getattr(exc, "smtp_code", None)
            detalhe = "Falha no SMTP (" + type(exc).__name__ + (f", código {codigo}" if isinstance(codigo, int) else "") + "). Use o contador do menu."
            _concluir(conn, r, "FALHOU", detalhe)


def _worker(caminho, evento):
    try:
        conn = S.conectar(caminho)
        try:
            while True:
                evento.clear()
                processar(conn)
                # Sob a mesma trava de despachar: não perde novo trabalho na saída do worker.
                with _LOCK:
                    if evento.is_set():
                        continue
                    _TRABALHOS.pop(caminho, None)
                    return
        finally:
            conn.close()
    finally:
        with _LOCK:
            if _TRABALHOS.get(caminho) is evento:
                _TRABALHOS.pop(caminho, None)


def despachar(caminho):
    """Chamar após o COMMIT externo. Uma thread por banco, conexão SQLite própria, sem bloquear HTTP."""
    if not caminho or caminho == ":memory:":
        return
    with _LOCK:
        if caminho in _TRABALHOS:
            _TRABALHOS[caminho].set()
            return
        evento = threading.Event()
        _TRABALHOS[caminho] = evento
        try:
            threading.Thread(target=_worker, args=(caminho, evento), daemon=True, name="aviso-fiscalizacao").start()
        except RuntimeError:
            _TRABALHOS.pop(caminho, None)  # Fila continua PENDENTE; ação de negócio já está gravada.
