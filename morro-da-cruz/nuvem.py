"""Sistema na nuvem: um link fixo https, sempre no ar, sem depender de computador da obra nem do MorroDaCruz.exe.

A conta da hospedagem é sua (passo a passo em docs/NUVEM.md). Duas receitas prontas:
* Render (disco persistente): o comando de início é `python nuvem.py`; render.yaml, na raiz do repositório, já o define.
* PythonAnywhere: o arquivo WSGI do site importa `nuvem.app`; o nuvem/pythonanywhere.sh instala tudo pelo console.

O que acontece ao subir:
1. Banco oficial (<MC_DADOS>/dados/morro_da_cruz.db) existente → abre o oficial. Senão, abre a demonstração
   (<MC_DADOS>/dados_demo/obra.db), montada das planilhas do repositório com o perfil TESTE na primeira vez (faixa
   DEMONSTRAÇÃO, como no programa do Windows). A aprovação real dos controles (D-01) não é usada nem preenchida.
2. Banco de demonstração em esquema antigo (versão nova do código) → migrado sem perda, com backup verificado antes,
   pelo próprio servidor ao subir, antes de atender (é o único no ar: com disco, o Render para o antigo antes).
3. Sem administrador real → cria o que estiver em MC_ADMIN_LOGIN, MC_ADMIN_NOME e MC_ADMIN_SENHA (só nessa vez:
   depois a senha é trocada no próprio sistema). Usuários de demonstração, de senha pública, são sempre desativados.
4. O servidor atende atrás do https da hospedagem: nada é tratado como "do próprio computador" (sem /configurar, sem
   entrar sem senha) e o cookie de sessão vai com Secure.

Variáveis de ambiente:
  MC_DADOS        pasta persistente: bancos, fotos, documentos, backups e logs (padrão: a pasta do programa)
  MC_ADMIN_LOGIN, MC_ADMIN_NOME, MC_ADMIN_SENHA   primeiro administrador (senha com 10 caracteres ou mais)
  PORT            porta em que a hospedagem espera o servidor (o Render define sozinho)

Comandos:
  python nuvem.py             prepara e sobe o servidor (Render e semelhantes)
  python nuvem.py preparar    só prepara (no console do PythonAnywhere; pede o administrador se faltar)
"""
import getpass
import http.client
import io
import os
import sys
import threading
from urllib.parse import quote

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import caminhos  # noqa: E402
import acesso as A  # noqa: E402
import backup  # noqa: E402
import regras as R  # noqa: E402
import servicos as S  # noqa: E402


class MigraAoRecarregar(Exception):
    """Banco de versão anterior visto pelo console: quem migra é o site, ao recarregar (servidor parado = só ele)."""


def pasta_dados():
    return os.path.abspath(os.environ.get("MC_DADOS") or caminhos.PASTA)


def bancos(dados=None):
    dados = dados or pasta_dados()
    return os.path.join(dados, "dados", "morro_da_cruz.db"), os.path.join(dados, "dados_demo", "obra.db")


def _migrar_demonstracao(db):
    import demo
    import importacao as I
    import importar
    print("Banco de demonstração em esquema antigo: migrando sem perda (backup verificado antes)…", flush=True)
    rel = importar.aplicar(db, I.DIR_PLANILHAS, cfg=demo.cfg_demonstracao(),
                           dir_relatorios=os.path.join(os.path.dirname(db), "relatorios"))
    print(f"Migração: {rel['status']} (v{rel['esquema_antes']} → v{rel['esquema_depois']})", flush=True)


def _administrador(c, perguntar):
    login, senha = os.environ.get("MC_ADMIN_LOGIN"), os.environ.get("MC_ADMIN_SENHA")
    nome = os.environ.get("MC_ADMIN_NOME")
    if not (login and senha) and perguntar:
        print("\nCrie o seu usuário de administrador (é com ele que você entra pelo link e cadastra a equipe).")
        login = input("Login (o seu nome ou e-mail): ").strip()
        nome = input("Nome: ").strip()
        while True:
            senha = getpass.getpass("Senha (mín. 10 caracteres): ")
            if senha == getpass.getpass("Repita a senha: "):
                break
            print("As senhas não conferem.")
    if not (login and senha):
        return None
    with S.transacao(c):
        _, desativados = A.configurar_acesso(c, login, nome or login, senha)
        A.auditar(c, None, "NUVEM", "/nuvem/administrador", 200, {"login": login},
                  f"administrador criado na preparação da nuvem; {desativados} usuário(s) de demonstração desativado(s)",
                  login=A.normalizar_login(login))
    return A.normalizar_login(login)


def preparar(dados=None, perguntar=False, migrar=True):
    """Deixa o banco pronto para o servidor da nuvem. Nunca toca no banco oficial além de abri-lo.
    migrar=False no console: com o site no ar, quem migra é o site ao recarregar (servidor parado = só ele)."""
    import demo
    oficial, demonstracao_db = bancos(dados)
    demonstracao = not os.path.exists(oficial)
    db = demonstracao_db if demonstracao else oficial
    if demonstracao and not os.path.exists(db):
        demo.criar(os.path.dirname(db))
    try:
        c = S.conectar(db)
    except S.EsquemaAntigo as e:
        if not demonstracao:
            raise SystemExit(f"{e}\nNa nuvem, o banco oficial só é migrado por você, com o servidor parado (docs/NUVEM.md).")
        if not migrar:
            raise MigraAoRecarregar("O banco é de uma versão anterior: o site migra sozinho ao recarregar.") from None
        _migrar_demonstracao(db)
        c = S.conectar(db)
    try:
        criado = None
        if not A.acesso_configurado(c):
            try:
                criado = _administrador(c, perguntar)
            except R.RegraViolada as e:
                raise SystemExit(f"Administrador não criado: {e}")
        with S.transacao(c):
            desativados = A.desativar_demonstracao(c)          # senha pública: nunca ativos na internet
        configurado = A.acesso_configurado(c)
    finally:
        c.close()
    return {"db": db, "demonstracao": demonstracao, "configurado": configurado, "administrador_criado": criado,
            "demo_desativados": desativados}


# ------------------------------------------------------------------ WSGI (PythonAnywhere e semelhantes)
_Pedido = None


def _pedido(environ):
    """Um pedido WSGI entregue ao mesmo Handler do server.py: as mesmas rotas, permissões, transações e auditoria."""
    global _Pedido
    if _Pedido is None:
        import server

        class Pedido(server.Handler):
            def __init__(self):                          # sem socket: lê do environ e escreve num buffer
                pass
        _Pedido = Pedido
    p = _Pedido()
    n = int(environ.get("CONTENT_LENGTH") or 0)
    import server                                    # acima do limite o corpo nem é lido: o Handler responde 413
    p.rfile = io.BytesIO(environ["wsgi.input"].read(n) if 0 < n <= server.LIMITE_CORPO else b"")
    p.wfile = io.BytesIO()
    p.client_address = (environ.get("REMOTE_ADDR") or "", 0)
    p.command = environ.get("REQUEST_METHOD", "GET")
    qs = environ.get("QUERY_STRING")
    p.path = environ.get("REQUEST_URI") or quote(environ.get("PATH_INFO") or "/") + (f"?{qs}" if qs else "")
    p.request_version = "HTTP/1.1"
    p.requestline = f"{p.command} {p.path} HTTP/1.1"
    p.close_connection = True
    h = http.client.HTTPMessage()
    for k, v in environ.items():
        if k.startswith("HTTP_"):
            h[k[5:].replace("_", "-").title()] = v
    for k, nome in (("CONTENT_TYPE", "Content-Type"), ("CONTENT_LENGTH", "Content-Length")):
        if environ.get(k):
            h[nome] = environ[k]
    if not h.get("X-Forwarded-Proto") and environ.get("wsgi.url_scheme") == "https":
        h["X-Forwarded-Proto"] = "https"
    p.headers = h
    return p


_pronto = None
_trava = threading.Lock()


def _iniciar():
    global _pronto
    with _trava:
        if _pronto is None:
            import server
            info = preparar()
            server.abrir(info["db"], info["demonstracao"], nuvem=True)
            _pronto = info
    return _pronto


def app(environ, start_response):
    """Aplicação WSGI. No PythonAnywhere: `from nuvem import application` no arquivo WSGI do site."""
    try:
        _iniciar()
    except (SystemExit, Exception) as e:  # noqa: BLE001 — mostra o motivo em vez de derrubar o processo do site
        msg = f"O sistema não abriu: {e}".encode("utf-8")
        start_response("503 Service Unavailable", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(msg)))])
        return [msg]
    p = _pedido(environ)
    metodo = getattr(p, "do_" + p.command, None)
    if metodo is None:
        start_response("405 Method Not Allowed", [("Allow", "GET, POST"), ("Content-Length", "0")])
        return [b""]
    metodo()
    cabecalho, _, corpo = p.wfile.getvalue().partition(b"\r\n\r\n")
    linhas = cabecalho.decode("iso-8859-1").split("\r\n")
    cabecalhos = [tuple(x.split(": ", 1)) for x in linhas[1:] if ": " in x]
    start_response(linhas[0].split(" ", 1)[1], [(k, v) for k, v in cabecalhos if k.lower() not in ("connection", "server")])
    return [corpo]


application = app


def main():
    backup.utf8_console()
    if sys.argv[1:2] == ["preparar"]:
        try:
            info = preparar(perguntar=sys.stdin.isatty(), migrar=False)
        except MigraAoRecarregar as e:
            print(e)
            return None
        print(f"\nBanco: {info['db']} ({'DEMONSTRAÇÃO' if info['demonstracao'] else 'OFICIAL'})")
        if info["administrador_criado"]:
            print(f"Administrador criado: {info['administrador_criado']}")
        print("Pronto para o site." if info["configurado"] else "ATENÇÃO: ainda sem administrador; rode de novo e crie o seu.")
        return None
    info = preparar()
    if not info["configurado"]:
        raise SystemExit("Falta o administrador: defina MC_ADMIN_LOGIN, MC_ADMIN_NOME e MC_ADMIN_SENHA (mín. 10 caracteres) "
                         "nas variáveis de ambiente da hospedagem e reinicie (docs/NUVEM.md).")
    import server
    sys.argv = ["server.py", "--db", info["db"], "--host", "0.0.0.0", "--porta", os.environ.get("PORT", "8765"), "--nuvem"]
    if info["demonstracao"]:
        sys.argv.append("--demonstracao")
    return server.main()


if __name__ == "__main__":
    main()
