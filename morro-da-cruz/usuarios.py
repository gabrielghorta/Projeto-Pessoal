"""Usuários do sistema (rodar no computador do servidor).

Uso:
  python usuarios.py criar     --login maria.souza --nome "Maria Souza" --perfil ENGENHARIA [--equipe Zona01] [--db ...]
  python usuarios.py listar    [--db ...]
  python usuarios.py senha     --login maria.souza [--db ...]
  python usuarios.py desativar --login maria.souza [--db ...]
  python usuarios.py perfis

A senha é pedida no terminal (não aparece nem fica no histórico). Perfis e permissões: config/perfis.json
(matriz provisória, decisão D-10). O sistema nunca cria usuários sozinho: o primeiro é criado aqui, por você.
"""
import argparse
import getpass
import sys

import acesso as A
import backup
import servicos as S


def _senha():
    s1 = getpass.getpass("Senha (mín. 10 caracteres): ")
    s2 = getpass.getpass("Repita a senha: ")
    if s1 != s2:
        raise SystemExit("As senhas não conferem.")
    return s1


def main(argv=None):
    backup.utf8_console()
    ap = argparse.ArgumentParser(description="Usuários do sistema Morro da Cruz")
    ap.add_argument("acao", choices=["criar", "listar", "senha", "desativar", "reativar", "perfis"])
    ap.add_argument("--db", default=S.DB_PADRAO)
    ap.add_argument("--login")
    ap.add_argument("--nome")
    ap.add_argument("--perfil")
    ap.add_argument("--equipe")
    a = ap.parse_args(argv)
    if a.acao == "perfis":
        p = A.carregar_perfis()
        for k, v in p["perfis"].items():
            print(f"{k:14} {v['nome']}: {', '.join(v['permissoes'])}")
        return
    conn = S.conectar(a.db)
    try:
        if a.acao == "listar":
            for r in conn.execute("SELECT login, nome, perfil, equipe_id, ativo, criado_em, criado_por FROM usuarios ORDER BY login"):
                print(" · ".join(str(x) if x is not None else "—" for x in r))
            return
        if not a.login:
            raise SystemExit("Informe --login.")
        if a.acao == "criar":
            if not a.nome or not a.perfil:
                raise SystemExit("Informe --nome e --perfil (veja: python usuarios.py perfis).")
            A.criar_usuario(conn, a.login, a.nome, a.perfil, _senha(), a.equipe, criado_por="usuarios.py (servidor)")
            print(f"Usuário {a.login} criado ({a.perfil}).")
        elif a.acao == "senha":
            A.redefinir_senha(conn, a.login, _senha())
            print("Senha redefinida; as sessões abertas desse usuário foram encerradas.")
        else:
            A.alterar_usuario(conn, a.login, "usuarios.py (servidor)", ativo=(a.acao == "reativar"))
            print(f"Usuário {a.login} {'reativado' if a.acao == 'reativar' else 'desativado'}.")
    except A.R.RegraViolada as e:
        raise SystemExit(str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
