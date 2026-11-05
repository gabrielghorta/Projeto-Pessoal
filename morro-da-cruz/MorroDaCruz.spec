# Receita do executável (PyInstaller): python -m PyInstaller MorroDaCruz.spec --noconfirm
# Gera dist/MorroDaCruz(.exe): um arquivo só, com o programa, a interface e a configuração padrão.
# Os dados da obra (planilhas/, mapa/, config/, dados/, dados_demo/) ficam na pasta onde o executável estiver.
a = Analysis(
    ["iniciar.py"],
    pathex=["."],
    datas=[("web", "web"), ("schema.sql", "."), ("config", "config"),
           ("planilhas/LEIA-ME.md", "planilhas"), ("mapa/LEIA-ME.md", "mapa")],
    hiddenimports=["server", "demo", "importar", "usuarios", "backup"],
    excludes=["tkinter", "unittest", "pydoc"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="MorroDaCruz", console=True, upx=False)
