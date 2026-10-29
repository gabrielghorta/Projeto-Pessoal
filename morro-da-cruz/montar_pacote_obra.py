"""Monta o pacote da obra para Windows: MorroDaCruz.exe + planilhas e mapa do Morro da Cruz + banco já montado.

    python montar_pacote_obra.py --exe caminho/MorroDaCruz.exe [--saida MorroDaCruz_Obra_Windows.zip]

* O .exe vem do GitHub Actions (Releases → MorroDaCruz-Windows.zip). Ele não pode ser gerado neste comando porque
  o PyInstaller não gera executável de Windows a partir de outro sistema.
* Planilhas e mapa são lidos de planilhas/ e mapa/ desta pasta (fora do Git). O banco de demonstração é montado com o
  perfil TESTE, como no demo.py; a aprovação real (D-01) não é usada nem preenchida.
* O pacote é entregue em particular (não vai para o Git nem para Releases).
"""
import argparse
import os
import shutil
import sys
import tempfile
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import caminhos  # noqa: E402

LEIA_ME = """SISTEMA MORRO DA CRUZ — Ankara Engenharia · CT 10.239/2026
Pacote da obra: programa + planilhas e mapa do Morro da Cruz já carregados
=========================================================================

COMO ABRIR
1. Descompacte este .zip numa pasta (por exemplo, Documentos\\MorroDaCruz).
   Não abra o programa de dentro do .zip.
2. Dê dois cliques em MorroDaCruz.exe.
   Se o Windows mostrar "O Windows protegeu o computador", clique em
   "Mais informações" e depois em "Executar assim mesmo".
3. O navegador abre sozinho, direto na tela de login.
4. Entre com o usuário eng.demo e a senha demo-morro-123.
   Outros perfis (mesma senha): eng2.demo, almox.demo, almox2.demo,
   equipe.demo (Zona01), admin.demo, topo.demo, cadastro.demo.

O QUE JÁ VEM CARREGADO
{fontes}

PARA FECHAR
Feche a janela preta do programa. Tudo o que você lançou fica salvo na pasta.

IMPORTANTE
- Está em modo DEMONSTRAÇÃO (faixa amarela no topo): os dados da obra são os
  reais, mas os lançamentos ficam num banco de teste (pasta dados_demo).
  O modo oficial depende da sua aprovação dos controles (D-01) e dos usuários reais.
- A medição é sempre de TESTE.
- O sistema abre só neste computador (http://127.0.0.1:8765).
- Para recomeçar do zero: feche o programa e apague a pasta dados_demo;
  na próxima abertura ele é montado de novo a partir das planilhas (menos de 1 minuto).
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", required=True, help="MorroDaCruz.exe gerado pelo GitHub Actions")
    ap.add_argument("--saida", default=os.path.join(AQUI, "MorroDaCruz_Obra_Windows.zip"))
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="pacote_obra_")
    p = os.path.join(tmp, "MorroDaCruz")
    try:
        os.makedirs(p)
        shutil.copy2(a.exe, os.path.join(p, "MorroDaCruz.exe"))
        for d in ("planilhas", "mapa", "config"):
            shutil.copytree(os.path.join(AQUI, d), os.path.join(p, d))
        caminhos.PASTA = p                      # o banco e a leitura das planilhas passam a usar a pasta do pacote
        import demo
        import importacao as I
        demo.criar()
        shutil.rmtree(os.path.join(p, "dados_demo", "relatorios"), ignore_errors=True)
        cfg = I.carregar_config()
        fontes = "\n".join(f"- {cfg['arquivos'][k]}" for k in ("redes", "conexoes", "evidencias", "bm", "reajuste", "mapa"))
        with open(os.path.join(p, "LEIA-ME.txt"), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(LEIA_ME.format(fontes=fontes))
        with zipfile.ZipFile(a.saida, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for raiz, _, nomes in os.walk(p):
                for n in sorted(nomes):
                    z.write(os.path.join(raiz, n), os.path.relpath(os.path.join(raiz, n), tmp))
        print(f"Pacote: {a.saida} ({os.path.getsize(a.saida) / 1e6:.1f} MB)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
