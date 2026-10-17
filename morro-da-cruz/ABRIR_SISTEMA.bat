@echo off
chcp 65001 >nul
title Sistema Morro da Cruz
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo O Python nao esta instalado neste computador.
  echo Baixe em https://www.python.org/downloads/ e, na instalacao, marque "Add python.exe to PATH".
  echo Depois, de dois cliques de novo neste arquivo.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
python -c "import openpyxl" >nul 2>nul || python -m pip install --user openpyxl pillow
python iniciar.py
pause
