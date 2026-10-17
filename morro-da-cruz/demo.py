"""Demonstração local: abre o sistema sobre um banco SEPARADO, para testar sem tocar no banco oficial.

    python demo.py              # cria dados_demo/ na primeira vez (lê as planilhas de planilhas/) e abre o sistema
    python demo.py --recriar    # apaga só dados_demo/ e recria do zero
    python demo.py --porta 8766

* O banco fica em dados_demo/obra.db (fotos e documentos ao lado). dados/ e as planilhas não são alterados.
* A importação usa o perfil de controles TESTE: os mesmos valores esperados do CTRL-01, marcados como demonstração.
  A aprovação real (D-01, config/controles.json) continua PENDENTE e não é preenchida.
* Cria usuários de demonstração, um por perfil, só neste banco.
"""
import argparse
import copy
import os
import shutil
import sys
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import caminhos  # noqa: E402
import acesso as A  # noqa: E402
import backup  # noqa: E402
import importacao as I  # noqa: E402
import importar  # noqa: E402
import servicos as S  # noqa: E402

PASTA = os.path.join(caminhos.PASTA, "dados_demo")
DB = os.path.join(PASTA, "obra.db")
SENHA = "demo-morro-123"
USUARIOS = (("admin.demo", "Administração (demo)", "ADMINISTRACAO", None),
            ("eng.demo", "Engenharia (demo)", "ENGENHARIA", None),
            ("eng2.demo", "Engenharia 2 (demo)", "ENGENHARIA", None),
            ("almox.demo", "Almoxarifado (demo)", "ALMOXARIFADO", None),
            ("almox2.demo", "Almoxarifado 2 (demo)", "ALMOXARIFADO", None),
            ("equipe.demo", "Encarregado Zona01 (demo)", "EQUIPE", "Zona01"),
            ("topo.demo", "Topografia (demo)", "TOPOGRAFIA", None),
            ("cadastro.demo", "Cadastro (demo)", "CADASTRO", None))


def cfg_demonstracao():
    cfg = copy.deepcopy(I.carregar_config())
    cfg["controles"] = [dict(copy.deepcopy(c), id="DEMO · " + c["id"], perfil="TESTE",
                             aprovacao={"status": "APROVADO", "por": "demonstração local (não substitui a aprovação do usuário)",
                                        "em": date.today().isoformat()}) for c in cfg["controles"]]
    cfg["perfil"] = "TESTE"
    return cfg


def criar():
    faltam = [k for k in ("redes", "conexoes", "evidencias", "bm", "reajuste") if not I.caminho(I.carregar_config(), k)]
    if faltam:
        raise SystemExit("Faltam planilhas em planilhas/ (" + ", ".join(faltam) + "). Os nomes exatos estão em planilhas/LEIA-ME.md.")
    os.makedirs(os.path.join(PASTA, "fotos"), exist_ok=True)
    print("Criando o banco de demonstração a partir das planilhas (pode levar 1 a 2 minutos)…")
    try:
        rel = importar.aplicar(DB, I.DIR_PLANILHAS, cfg=cfg_demonstracao(), dir_relatorios=os.path.join(PASTA, "relatorios"))
    except importar.ImportacaoReprovada as e:
        importar.imprimir(e.relatorio)
        raise SystemExit("A importação de demonstração foi reprovada (veja o relatório acima). Se as planilhas não são as do "
                         "CTRL-01 (mesmo SHA-256), a demonstração não tem conjunto de controles para elas.")
    print(f"Importação: {rel['status']}")
    c = S.conectar(DB)
    try:
        for login, nome, perfil, eq in USUARIOS:
            A.criar_usuario(c, login, nome, perfil, SENHA, eq, "demonstração local")
    finally:
        c.close()


def main():
    backup.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recriar", action="store_true", help="apaga dados_demo/ e recria")
    ap.add_argument("--porta", type=int, default=8765)
    a = ap.parse_args()
    if a.recriar and os.path.isdir(PASTA):
        backup.exigir_servidor_parado(PASTA, "Recriar a demonstração")
        shutil.rmtree(PASTA)
    if not os.path.exists(DB):
        criar()
    print("\n" + "=" * 72)
    print(" DEMONSTRAÇÃO — banco separado em dados_demo/ (o banco oficial em dados/ não é usado)")
    print(f" Abra http://127.0.0.1:{a.porta} e entre com um destes usuários (senha: {SENHA}):")
    for login, nome, perfil, eq in USUARIOS:
        print(f"   {login:<14} {perfil}{' · ' + eq if eq else ''}")
    print(" Para começar do zero: python demo.py --recriar")
    print("=" * 72 + "\n")
    import server
    sys.argv = ["server.py", "--db", DB, "--porta", str(a.porta), "--demonstracao"]
    server.main()


if __name__ == "__main__":
    main()
