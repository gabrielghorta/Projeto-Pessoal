"""Mede o custo das mesmas conversas com a API REAL da Groq: chamadas ao modelo e tokens até chegar à resposta ou ao
rascunho correto (D-226). Serve para comparar antes e depois de qualquer mudança no que é enviado ao modelo.

    GROQ_API_KEY=... python ferramentas/assistente/medir_tokens.py [--modelo-db obra.db] [--saida medida.json] [--rotulo antes]

Banco de demonstração descartável, servidor de verdade, conversa pelo HTTP como a tela faz. Gasta cerca de 15 chamadas
da cota gratuita e respeita os 8.000 tokens por minuto (leva uns 4 minutos)."""
import argparse
import datetime
import json
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cenario as C  # noqa: E402
import assistente as IA  # noqa: E402
import relogio as RL  # noqa: E402

PAUSA = 12                                # segundos entre mensagens: cabe nos 8.000 tokens por minuto


def itens_do_pedido(t):
    return {f["rotulo"]: f["valor"] for f in (t.rascunho or {}).get("form", []) if f["id"].startswith("item.")}


def conversas():
    ontem = (RL.hoje() - datetime.timedelta(days=1)).isoformat()
    return [
        ("Resposta curta (“tapume” depois de “Qual serviço?”)", "eng.demo",
         ["quero lançar um serviço", "tapume", "85 metros por 2,20 de altura, no canteiro"],
         lambda t: t.linhas().get("Item", "").startswith("5.1.2") and "187 m²" in t.linhas().get("Memória de cálculo", "")),
        ("Correção no meio (contêineres: “na verdade, foram três”)", "eng.demo",
         ["Lança dois contêineres no canteiro", "@Locação", "sanitário por um mês", "na verdade, foram três"],
         lambda t: t.linhas().get("Item", "").startswith("6.1.3") and t.linhas().get("Memória de cálculo") == "3 contêineres × 1 mês = 3 MES"),
        ("Item ambíguo (placa de obra, com medidas)", "admin.demo",
         ["ontem terminamos a placa de obra, 4 metros por 2 e meio", "@5.14.4"],
         lambda t: t.linhas().get("Item", "").startswith("5.14.4") and "10 m²" in t.linhas().get("Memória de cálculo", "")
         and (t.rascunho.get("corpo") or {}).get("data") == ontem),
        ("Dúvida sobre o OK interno", "eng.demo",
         ["eu quero dar o ok em TR confecionados, pra liberalos pra fiscalização"],
         lambda t: not t.rascunho and any(x in t.conversa[-1]["texto"] for x in ("OK interno", "Mapa iluminado"))
         and any(b.get("tela") == "iluminado" for b in t.botoes)),
        ("Pedido de material com correção", "almox.demo",
         ["tô sem luva de 110, manda 25 pra zona 4", "pensando bem, sobe pra 40"],
         lambda t: itens_do_pedido(t) == {"Luva eletrofusão 110 mm": 40} and t.rascunho["campos"].get("frente_id") == "Zona04"),
        ("Chuva numa frase só", "sup.demo",
         ["ontem de tarde caiu um aguaceiro e o pessoal do empreiteiro teve que parar tudo"],
         lambda t: bool(t.rascunho) and t.rascunho["pronto"] and t.rascunho["campos"].get("turno") == "TARDE"
         and t.rascunho["campos"].get("equipe_id") == "E1.1" and t.rascunho["campos"].get("data") == ontem),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo-db", help="obra.db de uma demonstração já montada (senão, monta das planilhas)")
    ap.add_argument("--saida", help="grava a medida em JSON neste arquivo")
    ap.add_argument("--rotulo", default="medida")
    ap.add_argument("--so", help="só as conversas com estes números (ex.: 1,4)")
    a = ap.parse_args()
    if not IA.chave():
        raise SystemExit("Defina GROQ_API_KEY (a chave gratuita da Groq).")
    pasta = C.pasta_temporaria()
    srv = C.Servidor(C.preparar_banco(pasta, a.modelo_db))
    medidas = []
    try:
        for n, (nome, login, passos, certo) in enumerate(conversas(), 1):
            if a.so and str(n) not in a.so.split(","):
                continue
            t = C.Tela(srv.url, login)
            esperas = 0
            for passo in passos:
                if passo.startswith("@"):
                    if not any(passo[1:].lower() in b["rotulo"].lower() for b in t.botoes):
                        break                     # o botão esperado não apareceu: a conversa saiu do caminho
                    t.tocar(passo[1:])
                    continue
                time.sleep(PAUSA)
                for _ in range(6):
                    r = t.dizer(passo)
                    if r.get("situacao") != "COTA":
                        break
                    if r["cota"].get("janela") == "dia":
                        raise SystemExit("A cota gratuita do dia acabou: meça de novo mais tarde.")
                    esperas += 1
                    time.sleep(r["cota"]["espera_s"] + 3)
            try:
                ok = bool(certo(t))
            except Exception:  # noqa: BLE001 — conversa que saiu do caminho conta como errada
                ok = False
            medidas.append({"n": n, "conversa": nome, "mensagens": sum(1 for p in passos if not p.startswith("@")),
                            "chamadas": t.chamadas, "tokens": t.tokens, "certo": ok, "esperas_por_cota": esperas,
                            "registro": [linha[:600] for linha in t.registro]})
            print(f"{n}. {nome}: {t.chamadas} chamada(s), {t.tokens} tokens, {'certo' if ok else 'ERRADO'}", flush=True)
            if not ok:
                print("\n".join("     " + linha[:300] for linha in t.registro), flush=True)
    finally:
        srv.fechar()
        shutil.rmtree(pasta, ignore_errors=True)
    total = {"rotulo": a.rotulo, "modelo": IA.config()["modelo"], "em": RL.hoje().isoformat(),
             "chamadas": sum(m["chamadas"] for m in medidas), "tokens": sum(m["tokens"] for m in medidas),
             "certas": sum(1 for m in medidas if m["certo"]), "conversas": medidas}
    print(f"TOTAL {a.rotulo}: {total['chamadas']} chamadas, {total['tokens']} tokens, {total['certas']} de {len(medidas)} certas")
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            json.dump(total, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
