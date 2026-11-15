"""Validação do assistente com a API REAL da Groq (plano gratuito), no banco de demonstração descartável (D-219).

    GROQ_API_KEY=... python ferramentas/assistente/validar_api_real.py [--modelo-db caminho/obra.db] [--saida relatorio.md]

Monta a demonstração numa pasta temporária, sobe o servidor de verdade numa thread e conversa pelo HTTP como a tela faz,
com frases que não estão nos testes nem nas instruções do modelo. Cobre os quatro usos (dúvida, pedido de material,
chuva ou interferência, apropriação direta), correção no meio da conversa, item ambíguo, perfis diferentes e cota
excedida de verdade (429 da Groq), e confere o rascunho inteiro e o que a rota de sempre gravou depois do toque.
Gasta a cota gratuita: cerca de 40 chamadas e 55 mil tokens (o plano gratuito dá 200 mil por dia) e leva uns 8
minutos, porque respeita os 8.000 tokens por minuto. Com --partes roda só uma parte; se a cota do dia acabar no meio,
para e relata o que já conferiu. Não toca o banco do site."""
import argparse
import datetime
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cenario as C  # noqa: E402
import assistente as IA  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402

RESULTADOS, REGISTRO, COTAS = [], [], []
os.environ.setdefault("MC_IA_RASTRO", "1")


class SemCota(Exception):
    """A cota gratuita do dia acabou no meio do roteiro: para por aqui e relata o que já foi conferido."""


def conferir(nome, ok, detalhe=""):
    RESULTADOS.append((nome, bool(ok), detalhe))
    REGISTRO.append(f"  {'✔' if ok else '✘'} {nome}" + (f" — {detalhe}" if detalhe and not ok else ""))
    print(REGISTRO[-1], flush=True)


def dizer(tela, texto, pausa=11):
    """Uma mensagem, no ritmo do plano gratuito; se a cota por minuto recusar, espera o que a Groq pediu e repete."""
    time.sleep(pausa)
    for _ in range(8):
        r = tela.dizer(texto)
        if r.get("situacao") != "COTA":
            return r
        if r["cota"].get("janela") == "dia":
            raise SemCota(f"a cota gratuita do dia acabou ({r['cota']['tipo']}; a Groq pede {r['cota']['espera_s']} s).")
        COTAS.append(r["cota"])
        time.sleep(r["cota"]["espera_s"] + 3)
    raise SystemExit("a cota gratuita não voltou a tempo: rode de novo mais tarde")


def gravar(tela):
    """O toque final. Rascunho incompleto conta como falha da conferência, sem derrubar o roteiro."""
    if not (tela.rascunho and tela.rascunho["pronto"]):
        REGISTRO.append(f"    (rascunho incompleto, nada a gravar: {[f['pergunta'] for f in (tela.rascunho or {}).get('faltam', [])]})")
        return None, {}
    return tela.gravar()


def secao(titulo, tela=None):
    REGISTRO.append(f"\n### {titulo}" + (f" (login {tela.login}, perfil {tela.usuario['perfil_nome']})" if tela else ""))
    print(REGISTRO[-1], flush=True)


def funcoes(tela):
    return (tela.ultima.get("uso") or {}).get("ferramentas") or []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo-db", help="obra.db de uma demonstração já montada (senão, monta das planilhas)")
    ap.add_argument("--saida", help="grava o relatório em Markdown neste arquivo")
    ap.add_argument("--partes", default="1,2,3,4,5", help="quais partes rodar: 1 dúvida, 2 pedido, 3 chuva e interferência, "
                                                         "4 apropriação, 5 cota excedida (padrão: todas)")
    a = ap.parse_args()
    if not IA.chave():
        raise SystemExit("Defina GROQ_API_KEY (a chave gratuita da Groq) para validar com a API real.")
    partes = set(a.partes.split(","))
    pasta = C.pasta_temporaria()
    db = C.preparar_banco(pasta, a.modelo_db)
    srv = C.Servidor(db)
    c = S.conectar(db)
    hoje, ontem = RL.hoje(), RL.hoje() - datetime.timedelta(days=1)
    um = lambda sql, *args: c.execute(sql, args).fetchone()
    t0 = time.time()
    try:
        tela = lambda login: C.Tela(srv.url, login, registro=REGISTRO)

        if "1" in partes:                              # ---------------- 1. dúvida de uso
            t = tela("almox.demo")
            secao("1. Dúvida de uso", t)
            r = dizer(t, "chegou uma nota fiscal aqui, onde eu dou entrada nela?", pausa=0)
            conferir("a IA consultou o guia de uso antes de responder", "consultar_ajuda" in funcoes(t), funcoes(t))
            conferir("respondeu sem abrir rascunho", r.get("resposta") and not t.rascunho, r)
            conferir("ofereceu o botão que leva à tela", any(b.get("tela") in ("compras/notas", "almox/saldo") for b in t.botoes), t.botoes)
            t = tela("rh.demo")
            secao("1b. Perfil sem lançamento pede material", t)
            r = dizer(t, "queria pedir uns 10 tubos de 63 pra obra")
            conferir("perfil RH: nenhum rascunho é aberto e a resposta explica", not t.rascunho and r.get("resposta") and not t.botoes, r)
            conferir("perfil RH: o código recusou pela permissão e explicou quem pede", "não pede material" in (r.get("resposta") or ""), r.get("resposta"))

        if "2" in partes:                              # ---------------- 2. pedido de material
            t = tela("enc.demo")
            secao("2. Pedido de material, com correção no meio", t)
            dizer(t, "tô sem luva de 110, manda 25. e também 3 curvas de 90 de 63")
            itens = {f["rotulo"]: f["valor"] for f in (t.rascunho or {}).get("form", []) if f["id"].startswith("item.")}
            conferir("rascunho de pedido com a luva (25) e a curva (3)", t.rascunho and t.rascunho["tipo"] == "PEDIDO"
                     and itens.get("Luva eletrofusão 110 mm") == 25 and itens.get("Curva 90° eletrofusão 63 mm") == 3, itens)
            conferir("a frente do encarregado entrou sozinha (Zona 03, onde a equipe está programada)",
                     t.rascunho and t.rascunho["campos"].get("frente_id") == "Zona03", (t.rascunho or {}).get("campos"))
            dizer(t, "pensando bem, sobe as luvas pra 40")
            itens = {f["rotulo"]: f["valor"] for f in (t.rascunho or {}).get("form", []) if f["id"].startswith("item.")}
            conferir("correção: a luva foi para 40 e a curva continuou 3", itens.get("Luva eletrofusão 110 mm") == 40
                     and itens.get("Curva 90° eletrofusão 63 mm") == 3 and len(itens) == 2, itens)
            conferir("rascunho pronto, com o corpo da rota de sempre", t.rascunho and t.rascunho["pronto"] and t.rascunho["rota"] == "/api/solicitacao")
            antes = um("SELECT COUNT(*) FROM solicitacoes_compra")[0]
            conferir("nada foi gravado antes do toque", antes == 0, antes)
            st, g = gravar(t)
            linha = um("SELECT s.solicitante, d.frente_id FROM solicitacoes_compra s JOIN solicitacao_detalhes d ON d.solicitacao_id=s.id WHERE s.id=?", g.get("id"))
            gravados = dict(c.execute("SELECT material_id, quantidade FROM solicitacao_itens WHERE solicitacao_id=?", (g.get("id"),)).fetchall())
            conferir("depois do toque: requisição gravada pela rota de sempre, com o login e a frente", st == 200 and linha
                     and tuple(linha) == ("enc.demo", "Zona03") and sorted(gravados.values()) == [3.0, 40.0], (st, g, gravados))
            secao("2b. O encarregado tenta pedir para outra zona", t)
            t.conversa, t.botoes = [], []
            dizer(t, "preciso de 2 tês de 90 lá pra zona 7")
            conferir("o sistema não aceita a Zona 07 para este login (fica a frente da equipe)",
                     t.rascunho and t.rascunho["campos"].get("frente_id") == "Zona03", (t.rascunho or {}).get("campos"))

        if "3" in partes:                              # ---------------- 3. chuva e interferência
            t = tela("sup.demo")
            secao("3. Relato de chuva", t)
            dizer(t, "ontem de tarde caiu um aguaceiro e o pessoal do empreiteiro teve que parar tudo")
            campos = (t.rascunho or {}).get("campos", {})
            conferir("rascunho de chuva: ontem, à tarde, paralisou", t.rascunho and campos.get("categoria") == "CHUVA"
                     and campos.get("data") == ontem.isoformat() and campos.get("turno") == "TARDE"
                     and campos.get("clima_condicao") == "PARALISADO_CHUVA", campos)
            conferir("entendeu que 'o pessoal do empreiteiro' é a equipe do Empreiteiro 1", campos.get("equipe_id") == "E1.1", campos)
            for rotulo in ("Empreiteiro", "Tarde", "Paralisou"):   # o que o modelo não determinou, os botões resolvem sem a IA
                if t.rascunho and not t.rascunho["pronto"] and any(rotulo in b["rotulo"] for b in t.botoes):
                    t.tocar(rotulo)
            st, g = gravar(t)
            chuva = um("SELECT o.data, o.equipe_id, o.aberta_por, c.turno, c.condicao FROM ocorrencias o JOIN ocorrencia_chuvas c ON c.ocorrencia_id=o.id WHERE o.id=?", g.get("id"))
            conferir("depois do toque: chuva gravada pela rota de sempre", st == 200 and chuva
                     and tuple(chuva) == (ontem.isoformat(), "E1.1", "sup.demo", "TARDE", "PARALISADO_CHUVA"), (st, g, chuva and tuple(chuva)))
            t = tela("enc.demo")
            secao("3b. Relato de interferência, com correção do trecho", t)
            dizer(t, "abrimos a vala e demos de cara com um cabo de fibra enterrado, na zona 3 pb06 tr014")
            alvo = lambda: (um("SELECT ponto FROM trechos WHERE id=?", (t.rascunho or {}).get("campos", {}).get("alvo_id")) or [None])[0]
            conferir("rascunho de interferência no trecho dito", t.rascunho and t.rascunho["campos"].get("categoria") == "INTERFERENCIA"
                     and alvo() == "Zona03_PB06_Rede_TR014" and t.rascunho["campos"].get("descricao"), (t.rascunho or {}).get("campos"))
            dizer(t, "opa, me enganei, foi no tr015")
            conferir("correção: só o trecho mudou (TR015), o resto ficou", alvo() == "Zona03_PB06_Rede_TR015"
                     and t.rascunho["campos"].get("categoria") == "INTERFERENCIA" and t.rascunho["campos"].get("descricao"), (t.rascunho or {}).get("campos"))
            conferir("a equipe do encarregado entrou sozinha", t.rascunho["campos"].get("equipe_id") == "E1.1", t.rascunho["campos"])
            st, g = gravar(t)
            oc = um("SELECT categoria, equipe_id, aberta_por FROM ocorrencias WHERE id=?", g.get("id"))
            conferir("depois do toque: interferência gravada com o login e a equipe do encarregado",
                     st == 200 and oc and tuple(oc) == ("INTERFERENCIA", "E1.1", "enc.demo"), (st, g, oc and tuple(oc)))

        if "4" in partes:                              # ---------------- 4. apropriação direta
            t = tela("eng.demo")
            secao("4. Apropriação direta: o exemplo de aceitação", t)
            dizer(t, "Lança dois contêineres no canteiro")
            conferir("a IA procurou no orçamento e ofereceu Instalação ou Locação", [b["rotulo"] for b in t.botoes] == ["Instalação", "Locação"], t.botoes)
            t.tocar("Locação")
            conferir("Locação abre os três tipos, sem chamar a IA", len(t.botoes) == 3, t.botoes)
            dizer(t, "sanitário por um mês")
            conferir("anotou o contêiner sanitário (6.1.3) por 1 mês", t.linhas().get("Item", "").startswith("6.1.3")
                     and t.linhas().get("Memória de cálculo") == "2 contêineres × 1 mês = 2 MES", t.linhas())
            dizer(t, "na verdade, foram três")
            li = t.linhas()
            conferir("rascunho final: item 6.1.3, Canteiro e a memória de 3 contêineres por 1 mês", li.get("Item", "").startswith("6.1.3")
                     and li.get("Grupo", "").startswith("Canteiro") and li.get("Local") == "Canteiro de obra"
                     and li.get("Memória de cálculo") == "3 contêineres × 1 mês = 3 MES" and li.get("Quantidade") == "3 MES", li)
            conferir("nada gravado antes do toque", um("SELECT COUNT(*) FROM apropriacoes")[0] == 0)
            st, g = gravar(t)
            ap_ = um("SELECT item, quantidade, unidade, local_tipo, memoria_calculo, registrado_por, data FROM apropriacoes WHERE id=?", g.get("id"))
            conferir("depois do toque: apropriação gravada pela rota de sempre", st == 200 and ap_ and tuple(ap_) == (
                "1.1_6.1.3", 3.0, "MES", "CANTEIRO", "3 contêineres × 1 mês = 3 MES", "eng.demo", hoje.isoformat()), (st, g, ap_ and tuple(ap_)))
            t = tela("admin.demo")
            secao("4b. Item ambíguo e medidas", t)
            dizer(t, "ontem a gente terminou a placa de obra, ficou com 4 metros por 2 e meio")
            conferir("item ambíguo (placa de obra existe em dois orçamentos): a IA mostra as opções em botões",
                     len(t.botoes) >= 2 and not t.linhas().get("Item", "a definir").startswith(("5.", "1.")), (t.botoes, t.linhas()))
            if len(t.botoes) >= 2:
                t.tocar("5.14.4")
            li = t.linhas()
            conferir("depois do toque no item: 5.14.4, conta de 4 × 2,5 = 10 m², dia de ontem", li.get("Item", "").startswith("5.14.4")
                     and "10 m²" in li.get("Memória de cálculo", "") and li.get("Dia") == ontem.strftime("%d/%m/%Y"), li)
            t.editar("medida.0.largura", "2,4")
            conferir("campo do rascunho corrigido à mão (altura 2,4): o código refaz a conta, sem a IA", "9,6 m²" in t.linhas().get("Memória de cálculo", ""), t.linhas())
            st, g = gravar(t)
            ap_ = um("SELECT item, quantidade, registrado_por, data FROM apropriacoes WHERE id=?", g.get("id"))
            conferir("gravada com 9,6 m² e a data de ontem", st == 200 and ap_ and tuple(ap_) == ("1.2_5.14.4", 9.6, "admin.demo", ontem.isoformat()), (st, g, ap_ and tuple(ap_)))
            t = tela("almox.demo")
            secao("4c. Perfil sem a permissão tenta apropriar", t)
            antes = um("SELECT COUNT(*) FROM apropriacoes")[0]
            r = dizer(t, "lança aí 40 metros de tapume que a gente fez no canteiro")
            conferir("almoxarifado: o código recusou pela permissão e disse quem lança", "Engenharia" in (r.get("resposta") or ""), r.get("resposta"))
            conferir("almoxarifado: sem rascunho de apropriação e nada gravado", (not t.rascunho or t.rascunho["tipo"] != "APROPRIACAO")
                     and um("SELECT COUNT(*) FROM apropriacoes")[0] == antes, (t.rascunho or {}).get("tipo"))

        if "5" in partes:                              # ---------------- 5. cota excedida de verdade
            t = tela("eng2.demo")
            secao("5. Cota excedida (429 real da Groq)", t)
            t.atalho("APROPRIACAO")
            t.editar("o_que_foi_feito", "rascunho que precisa sobreviver à falta de cota")
            cota = None
            for i in range(14):                              # sem pausa, até o limite por minuto do plano gratuito recusar
                r = t.dizer(f"me explica de novo como funciona a medição e o estoque, por favor ({i + 1})")
                if r.get("situacao") == "COTA" and r["cota"]["tipo"] != "ritmo":       # por minuto ou por dia: as duas valem
                    cota = r
                    break
                if r.get("situacao") == "COTA":              # o freio por login chegou antes: espera e continua
                    time.sleep(r["cota"]["espera_s"] + 1)
            conferir("a Groq recusou por cota e a resposta veio como aviso, sem erro", cota is not None, t.ultima)
            if cota:
                conferir("o aviso fala em limite gratuito e aponta o formulário", "formulário" in cota["aviso"] and "gratuit" in cota["aviso"], cota["aviso"])
                conferir("o aviso não repete a propaganda de plano pago do serviço", "upgrade" not in cota["aviso"].lower() and "billing" not in cota["aviso"].lower())
                conferir("o rascunho voltou inteiro junto com o aviso", cota.get("rascunho") and cota["rascunho"]["campos"].get("o_que_foi_feito", "").startswith("rascunho que precisa"), cota.get("rascunho"))
                t.editar("item", "5.1.1")
                t.editar("fator.CONTAGEM", "1")
                conferir("sem a IA, o rascunho continua editável e fica pronto pelo formulário", t.rascunho["pronto"], t.rascunho["faltam"])
                st, g = gravar(t)
                conferir("fluxo manual: gravou pela rota de sempre com a cota esgotada", st == 200 and g.get("id"), (st, g))
    except SemCota as e:
        REGISTRO.append(f"\n**Interrompido: {e}** As conferências acima valem; as seguintes não foram executadas.")
        print(REGISTRO[-1], flush=True)
    finally:
        srv.fechar()
        c.close()
        shutil.rmtree(pasta, ignore_errors=True)
    certos = sum(1 for _, ok, _ in RESULTADOS if ok)
    cfg = IA.config()
    cab = [f"# Validação do assistente com a API real — {RL.hoje().strftime('%d/%m/%Y')}", "",
           f"Modelo `{cfg['modelo']}` em `{cfg['base_url']}` (plano gratuito). Banco de demonstração descartável, servidor de verdade, "
           "conversa pelo HTTP como a tela faz. Gerado por `ferramentas/assistente/validar_api_real.py`.", "",
           f"**{certos} de {len(RESULTADOS)} conferências passaram** em {int(time.time() - t0)} s, com {IA.USO['chamadas']} chamadas ao modelo e "
           f"{IA.USO['tokens']} tokens; a cota por minuto recusou {len(COTAS)} vez(es) fora do teste de cota (o roteiro esperou e repetiu).", ""]
    texto = "\n".join(cab + [linha[:1400] for linha in REGISTRO]) + "\n"
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            f.write(texto)
    print("\n" + "\n".join(cab))
    falhas = [(n, d) for n, ok, d in RESULTADOS if not ok]
    for n, d in falhas:
        print("FALHOU:", n, "—", str(d)[:600])
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
