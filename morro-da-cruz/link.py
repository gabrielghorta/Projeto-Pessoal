"""Link para a equipe: o sistema, aberto no computador do escritório, fica acessível por um endereço https na internet.

Usa o túnel gratuito da Cloudflare (cloudflared, "quick tunnel" em trycloudflare.com): não precisa de conta, de
domínio nem de abrir porta no roteador. O servidor continua escutando só em 127.0.0.1; quem chega pelo link passa pelo
túnel. Limites, que valem para este modo:
* o link só funciona enquanto o computador e o programa estiverem ligados;
* o endereço muda a cada vez que o programa reinicia (o atual aparece na janela do programa, em LINK_DA_EQUIPE.txt e
  em Administrativo › Usuários e histórico);
* o link só é ligado depois que existir um administrador real (os usuários de demonstração são desativados antes).
"""
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime

import caminhos as C

URL = re.compile(r"https://(?!api\.)[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com")
ARQUIVO = "LINK_DA_EQUIPE.txt"
estado = {"situacao": "DESLIGADO", "url": None, "erro": None, "desde": None}
TENTATIVAS = 5                                     # o túnel caiu (internet oscilou): religa sozinho, com novo endereço
_proc = None
_quedas = 0
_trava = threading.Lock()


def executavel():
    """cloudflared ao lado do programa (vem no pacote do Windows) ou no PATH. MC_CLOUDFLARED substitui (testes)."""
    if os.environ.get("MC_CLOUDFLARED"):
        return os.environ["MC_CLOUDFLARED"]
    for nome in ("cloudflared.exe", "cloudflared"):
        p = os.path.join(C.PASTA, nome)
        if os.path.isfile(p):
            return p
    return shutil.which("cloudflared")


def _gravar(url):
    try:
        with open(os.path.join(C.PASTA, ARQUIVO), "w", encoding="utf-8") as f:
            f.write(f"Link para a equipe (vale enquanto o programa estiver aberto neste computador):\n{url}\n"
                    f"Gerado em {datetime.now():%d/%m/%Y %H:%M}\n")
    except OSError:
        pass


def iniciar(porta, ao_conectar=None):
    """Liga o túnel (se ainda não estiver ligado). Não bloqueia: o endereço aparece em `estado` quando conectar."""
    global _proc, _quedas
    with _trava:
        if estado["situacao"] in ("CONECTANDO", "NO_AR"):
            return dict(estado)
        exe = executavel()
        if not exe:
            estado.update(situacao="SEM_PROGRAMA", url=None,
                          erro="cloudflared não encontrado na pasta do programa (ele vem no pacote do Windows).")
            return dict(estado)
        estado.update(situacao="CONECTANDO", url=None, erro=None, desde=datetime.now().isoformat(timespec="seconds"))
        try:
            cmd = [sys.executable, exe] if exe.endswith(".py") else [exe]          # .py: substituto usado nos testes
            _proc = subprocess.Popen(cmd + ["tunnel", "--url", f"http://127.0.0.1:{porta}", "--no-autoupdate"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            estado.update(situacao="ERRO", erro=f"Não consegui iniciar o cloudflared: {e}")
            return dict(estado)
        proc = _proc

    def ler():
        ultimas = []
        for linha in proc.stdout:
            ultimas = (ultimas + [linha.strip()])[-5:]
            m = URL.search(linha)
            if m and not estado["url"]:
                globals()["_quedas"] = 0
                estado.update(situacao="NO_AR", url=m.group(0), erro=None)
                _gravar(m.group(0))
                if ao_conectar:
                    ao_conectar(m.group(0))
        proc.wait()
        proc.stdout.close()
        if estado["situacao"] != "DESLIGADO":
            globals()["_quedas"] += 1
            religa = _quedas <= TENTATIVAS
            estado.update(situacao="ERRO", url=None,
                          erro=("O link caiu (internet?): religando em 15 s, com um endereço novo. " if religa else
                                "O link caiu várias vezes: confira a internet e abra o programa de novo. ") + " | ".join(ultimas)[-300:])
            if religa:
                threading.Timer(15, lambda: estado["situacao"] == "ERRO" and iniciar(porta, ao_conectar)).start()

    threading.Thread(target=ler, daemon=True).start()
    return dict(estado)


def parar():
    with _trava:
        estado.update(situacao="DESLIGADO", url=None)
        if _proc and _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(5)
            except subprocess.TimeoutExpired:
                _proc.kill()
