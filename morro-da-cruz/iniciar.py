"""Abre o sistema com dois cliques: é o que o MorroDaCruz.exe (ou o ABRIR_SISTEMA.bat) executa.

1. Se já houver um sistema aberto neste computador, só abre o navegador nele.
2. Banco oficial (dados/morro_da_cruz.db) existente → abre o oficial. Senão → demonstração (dados_demo/, separado).
3. Primeira vez, sem planilhas: o navegador abre uma tela para escolher as planilhas e o mapa. Cada arquivo é
   reconhecido pelo conteúdo (SHA-256 do conjunto de controles CTRL-01) e guardado com o nome certo em planilhas/ ou
   mapa/. Depois disso a demonstração é montada e a tela de login aparece.
4. O navegador abre sozinho. Fechar a janela do programa fecha o sistema.

Comandos de manutenção pelo mesmo executável: MorroDaCruz.exe importar [--aplicar] | usuarios ... | backup ...
"""
import base64
import hashlib
import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import caminhos as C

PORTA = 8765
LIMITE_ARQUIVO = 80 * 1024 * 1024
OFICIAL = os.path.join(C.PASTA, "dados", "morro_da_cruz.db")


def preparar_pasta():
    """No executável, a configuração padrão é copiada para a pasta do programa na primeira vez (ela é editável:
    a aprovação dos controles e os perfis ficam lá)."""
    if C.CONGELADO and not os.path.isdir(os.path.join(C.PASTA, "config")):
        shutil.copytree(os.path.join(C.RECURSOS, "config"), os.path.join(C.PASTA, "config"))
    for d in ("planilhas", "mapa"):
        os.makedirs(os.path.join(C.PASTA, d), exist_ok=True)
        leia = os.path.join(C.RECURSOS, d, "LEIA-ME.md")
        if C.CONGELADO and os.path.exists(leia) and not os.path.exists(os.path.join(C.PASTA, d, "LEIA-ME.md")):
            shutil.copy2(leia, os.path.join(C.PASTA, d, "LEIA-ME.md"))


def ja_aberto(porta):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=1.5) as r:
            return b"Morro da Cruz" in r.read(4000)
    except OSError:
        return False


def porta_livre(porta):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


# ------------------------------------------------------------------ reconhecimento dos arquivos da primeira vez
PISTAS = (("redes", ("06.1", "REDES")), ("conexoes", ("06.2", "CONEX")), ("evidencias", ("EVIDENCIA",)),
          ("reajuste", ("REAJUSTE",)), ("bm", ("IDENTIFICACAO", "BM_")))


def esperados():
    import importacao as I
    cfg = I.carregar_config()
    shas = {}
    for c in cfg.get("controles", []):
        for chave, sha in (c.get("fontes") or {}).items():
            shas.setdefault(sha, chave)
    return cfg["arquivos"], shas


def faltando():
    arquivos, _ = esperados()
    out = []
    for chave, nome in arquivos.items():
        pasta = "mapa" if chave == "mapa" else "planilhas"
        if not os.path.exists(os.path.join(C.PASTA, pasta, nome)):
            out.append(chave)
    return out


def guardar(nome_original, dados):
    arquivos, shas = esperados()
    sha = hashlib.sha256(dados).hexdigest()
    chave, confere = shas.get(sha), True
    if not chave:
        confere = False
        up = nome_original.upper()
        if up.endswith((".HTML", ".HTM")):
            chave, confere = "mapa", True                          # o mapa não entra nos controles
        else:
            chave = next((k for k, pistas in PISTAS if any(p in up for p in pistas)), None)
    if not chave or chave not in arquivos:
        raise ValueError(f"{nome_original}: não reconheci este arquivo (não é uma das planilhas do contrato nem o mapa).")
    destino = os.path.join(C.PASTA, "mapa" if chave == "mapa" else "planilhas", arquivos[chave])
    if os.path.exists(destino):
        with open(destino, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != sha:
                raise ValueError(f"{arquivos[chave]} já existe na pasta do programa com outro conteúdo; não foi substituído.")
    else:
        with open(destino + ".parcial", "wb") as f:
            f.write(dados)
        os.replace(destino + ".parcial", destino)
    return {"chave": chave, "nome": arquivos[chave], "confere": confere}


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morro da Cruz — primeira abertura</title><style>
:root{color-scheme:dark}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:#0f141b;color:#e7ebf0}
main{max-width:720px;margin:0 auto;padding:28px 16px}h1{font-size:22px;margin:0 0 4px}.sub{color:#9aa5b1;margin:0 0 20px}
.caixa{background:#171e27;border:1px solid #273140;border-radius:10px;padding:18px;margin-bottom:16px}
.drop{border:2px dashed #3a4656;border-radius:10px;padding:26px;text-align:center;cursor:pointer}.drop.sobre{border-color:#E85D22;background:#1d2530}
ul{list-style:none;padding:0;margin:0}li{padding:6px 0;border-bottom:1px solid #222b37;display:flex;gap:10px;align-items:baseline}
.st{min-width:22px}.ok{color:#3ecf8e}.av{color:#f5a623}.er{color:#ff6b6b}small{color:#9aa5b1}
button{background:#E85D22;color:#fff;border:0;border-radius:8px;padding:11px 18px;font-size:15px;font-weight:600;cursor:pointer}
button:disabled{opacity:.45;cursor:default}#msg{margin-top:12px}</style></head><body><main>
<h1>Sistema Morro da Cruz — primeira abertura</h1>
<p class="sub">Escolha as planilhas do contrato e o mapa. Eles são copiados para a pasta do programa (os seus arquivos não são alterados) e a demonstração é montada num banco separado do oficial.</p>
<div class="caixa"><div class="drop" id="drop">Arraste os arquivos para cá ou <b>clique para escolher</b><br><small>pode escolher todos de uma vez</small>
<input type="file" id="arq" multiple hidden accept=".xlsx,.xlsm,.html,.htm"></div></div>
<div class="caixa"><ul id="lista"></ul></div>
<button id="montar" disabled>Montar a demonstração e abrir o sistema</button><div id="msg"></div>
</main><script>
const ROT={redes:'06.1 — Redes (REV01)',conexoes:'06.2 — Conexões (REV08)',evidencias:'Evidências (REV08)',bm:'BM — identificação (REV04)',reajuste:'03.3.2 — BM reajuste (REV03)',mapa:'Mapa REV02 (HTML) — opcional, mas recomendado'};
let falta=__FALTA__;const lista=document.getElementById('lista'),msg=document.getElementById('msg'),bt=document.getElementById('montar');
function desenhar(st={}){lista.innerHTML=Object.keys(ROT).map(k=>{const f=falta.includes(k),s=st[k];return `<li><span class="st ${s&&s.erro?'er':f?'':(s&&!s.confere?'av':'ok')}">${f?(s&&s.erro?'✗':'·'):(s&&!s.confere?'!':'✓')}</span><span>${ROT[k]}<br><small>${s&&s.texto||(f?'aguardando':'recebido')}</small></span></li>`}).join('');
bt.disabled=falta.some(k=>k!=='mapa');}
const ST={};desenhar();
async function enviar(arquivos){for(const a of arquivos){msg.textContent='Enviando '+a.name+'…';
 const b64=await new Promise((ok,er)=>{const r=new FileReader();r.onload=()=>ok(r.result.split(',')[1]);r.onerror=er;r.readAsDataURL(a)});
 const r=await fetch('/assistente/arquivo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nome:a.name,conteudo_b64:b64})});
 const j=await r.json();if(!r.ok){msg.innerHTML='<span class="er">'+j.erro+'</span>';continue}
 falta=j.faltando;ST[j.chave]={confere:j.confere,texto:a.name+(j.chave==='mapa'?' — recebido':j.confere?' — confere com o CTRL-01':' — ATENÇÃO: diferente do arquivo conferido no CTRL-01; a demonstração pode ser recusada')};desenhar(ST);msg.textContent='';}}
const drop=document.getElementById('drop'),inp=document.getElementById('arq');
drop.onclick=()=>inp.click();inp.onchange=()=>enviar([...inp.files]);
drop.ondragover=e=>{e.preventDefault();drop.classList.add('sobre')};drop.ondragleave=()=>drop.classList.remove('sobre');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('sobre');enviar([...e.dataTransfer.files])};
bt.onclick=async()=>{bt.disabled=true;msg.textContent='Montando a demonstração a partir das planilhas (1 a 2 minutos)…';
 const r=await fetch('/assistente/montar',{method:'POST'});const j=await r.json();
 if(!r.ok){msg.innerHTML='<span class="er">'+j.erro+'</span>';bt.disabled=false;return}
 msg.textContent='Pronto. Abrindo o sistema…';
 for(let i=0;i<120;i++){await new Promise(z=>setTimeout(z,700));try{const s=await fetch('/api/sessao');if(s.status===401||s.status===200){location.href='/configurar';return}}catch(_){}}
 msg.textContent='Atualize a página (F5).';};
</script></body></html>"""


class Assistente(BaseHTTPRequestHandler):
    concluido = threading.Event()

    def log_message(self, *a):
        pass

    def _json(self, status, obj):
        dados = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._json(404, {"erro": "ainda na primeira abertura"})
        dados = PAGINA.replace("__FALTA__", json.dumps(faltando())).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > LIMITE_ARQUIVO * 1.4:
            return self._json(413, {"erro": "Arquivo grande demais."})
        corpo = self.rfile.read(n)
        if self.path == "/assistente/arquivo":
            try:
                b = json.loads(corpo or b"{}")
                r = guardar(os.path.basename(str(b.get("nome") or "")), base64.b64decode(b.get("conteudo_b64") or ""))
            except (ValueError, TypeError) as e:
                return self._json(422, {"erro": str(e)})
            return self._json(200, {**r, "faltando": faltando()})
        if self.path == "/assistente/montar":
            if [k for k in faltando() if k != "mapa"]:
                return self._json(422, {"erro": "Ainda faltam planilhas."})
            try:
                import demo
                demo.criar()
            except SystemExit as e:
                return self._json(422, {"erro": str(e)})
            self._json(200, {"ok": True})
            Assistente.concluido.set()
            return None
        return self._json(404, {"erro": "rota inexistente"})


def primeira_abertura(porta):
    srv = ThreadingHTTPServer(("127.0.0.1", porta), Assistente)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{porta}/"
    print(f"Primeira abertura: escolha as planilhas na página que abriu no navegador ({url}).")
    webbrowser.open(url)
    Assistente.concluido.wait()
    time.sleep(0.5)                                               # deixa a resposta chegar ao navegador
    srv.shutdown()
    srv.server_close()


def manutencao(argv):
    cmd, resto = argv[0], argv[1:]
    mods = {"importar": "importar", "usuarios": "usuarios", "backup": "backup", "demo": "demo"}
    mod = __import__(mods[cmd])
    sys.argv = [cmd + ".py", *resto]
    return mod.main()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    preparar_pasta()
    if len(sys.argv) > 1 and sys.argv[1] in ("importar", "usuarios", "backup", "demo"):
        return manutencao(sys.argv[1:])
    if ja_aberto(PORTA):
        print(f"O sistema já está aberto: http://127.0.0.1:{PORTA}")
        webbrowser.open(f"http://127.0.0.1:{PORTA}/")
        time.sleep(2)
        return None
    porta = next((p for p in range(PORTA, PORTA + 30) if porta_livre(p)), PORTA)
    import demo
    import server
    demonstracao = not os.path.exists(OFICIAL)
    db = demo.DB if demonstracao else OFICIAL
    abrir = True
    if demonstracao and not os.path.exists(db):
        if [k for k in faltando() if k != "mapa"]:
            primeira_abertura(porta)
            abrir = False                                         # a página da primeira abertura já está no navegador
        else:
            demo.criar()
    import acesso
    import servicos
    c = servicos.conectar(db)
    try:
        configurado = acesso.acesso_configurado(c)
    finally:
        c.close()
    print("\n" + "=" * 72)
    print(f" Sistema Morro da Cruz — {'DEMONSTRAÇÃO (banco separado em dados_demo/)' if demonstracao else 'banco OFICIAL'}")
    print(f" Neste computador: http://127.0.0.1:{porta}")
    if not configurado:
        print(f" Para ligar o LINK DA EQUIPE, crie o seu administrador: http://127.0.0.1:{porta}/configurar")
    print(" Deixe esta janela aberta enquanto o sistema estiver em uso. Fechar a janela fecha o sistema e o link.")
    print("=" * 72 + "\n", flush=True)
    if abrir:
        destino = "/" if configurado else "/configurar"
        threading.Timer(1.2, webbrowser.open, [f"http://127.0.0.1:{porta}{destino}"]).start()
    sys.argv = (["server.py", "--db", db, "--porta", str(porta), "--link"] + (["--demonstracao"] if demonstracao else []))
    return server.main()


if __name__ == "__main__":
    main()
