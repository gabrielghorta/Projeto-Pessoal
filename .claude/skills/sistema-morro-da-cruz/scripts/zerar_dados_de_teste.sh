#!/bin/bash
# Zera os dados de TESTE do site (PythonAnywhere): apaga tudo o que foi lançado no site (NS, NF, fotos, check-ins,
# medições…) e mantém os usuários e o que vem das planilhas. Antes, guarda uma cópia do banco, dos documentos e das
# fotos em dados_demo/antes_da_limpeza_<data>. Se existir o banco OFICIAL, para sem apagar nada.
# Uso: cole no console Bash do PythonAnywhere (ou rode: bash zerar_dados_de_teste.sh). Depois: Web › Reload.
cd ~/Projeto-Pessoal/morro-da-cruz && python3 - <<'PY'
import os, shutil, sqlite3, datetime
import nuvem
oficial, db = nuvem.bancos(None)
if os.path.exists(oficial):
    raise SystemExit("Existe o banco OFICIAL (" + oficial + "): nada foi apagado.")
pasta = os.path.dirname(db)
quando = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
guarda = os.path.join(pasta, "antes_da_limpeza_" + quando)
os.makedirs(guarda)
origem = sqlite3.connect(db)
copia = sqlite3.connect(os.path.join(guarda, "obra.db"))
origem.backup(copia)
copia.close()
# o que vem das planilhas da obra (fica) e os usuários (ficam); o resto foi lançado no site (sai)
FICA = {"alteracoes", "atividades", "avisos_origem", "bm_itens", "decisao_objetos", "decisao_vinculos", "decisoes",
        "elementos", "equipes", "fontes_arquivo", "importacoes", "itens_projeto", "materiais", "nomes_historico",
        "parametros", "proveniencia", "reajuste_indices", "schema_versao", "trechos", "pendencias_importacao",
        "migracao_mapa", "usuarios", "sessoes", "auditoria"}
c = origem
c.execute("PRAGMA foreign_keys=OFF")
tabelas = [t for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
apagadas = {}
with c:
    for t in tabelas:
        if t not in FICA:
            n = c.execute(f'DELETE FROM "{t}"').rowcount
            if n:
                apagadas[t] = n
quebradas = c.execute("PRAGMA foreign_key_check").fetchall()
c.execute("VACUUM")
c.close()
for sub in ("documentos", "fotos"):
    p = os.path.join(pasta, sub)
    if os.path.isdir(p):
        shutil.move(p, os.path.join(guarda, sub))
        os.makedirs(p)
print("Apagado:", ", ".join(f"{t} ({n})" for t, n in sorted(apagadas.items())) or "nada")
print("Ligações quebradas:", len(quebradas))
print("Cópia de antes da limpeza (banco, documentos e fotos):", guarda)
PY
