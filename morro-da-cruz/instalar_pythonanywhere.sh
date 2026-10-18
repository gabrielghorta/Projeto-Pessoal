#!/bin/bash
# Instala (ou atualiza) o Sistema Morro da Cruz no PythonAnywhere — a conta gratuita serve. No console Bash de lá, cole:
#
#   [ -d ~/Projeto-Pessoal ] || git clone -b claude/powerbi-modifications-wqxekj --depth 1 https://github.com/gabrielghorta/Projeto-Pessoal.git ~/Projeto-Pessoal; bash ~/Projeto-Pessoal/morro-da-cruz/instalar_pythonanywhere.sh
#
# O que ele faz: baixa a versão mais nova do código; instala o openpyxl; monta a obra das planilhas do repositório
# (banco de demonstração, perfil TESTE) e pede o seu administrador; liga o site em https://<seu usuário>.pythonanywhere.com
# Pode rodar de novo quantas vezes quiser: não apaga nada (os dados ficam em morro-da-cruz/dados_demo, fora do Git).
set -u
PASTA="$HOME/Projeto-Pessoal/morro-da-cruz"
cd "$PASTA" || { echo "Pasta $PASTA não encontrada: cole o comando completo (com o git clone)."; exit 1; }

echo "== 1/4 Código: buscando a versão mais nova"
git -C "$HOME/Projeto-Pessoal" pull --ff-only || echo "   (não consegui atualizar; sigo com a versão que já está aqui)"

PY=""
for v in 3.13 3.12 3.11; do command -v "python$v" >/dev/null && { PY="python$v"; break; }; done
[ -n "$PY" ] || { echo "Preciso do Python 3.11 ou mais novo, e não achei neste console."; exit 1; }
echo "== 2/4 Bibliotecas ($PY e as outras versões do console)"
for v in 3.13 3.12 3.11; do
  command -v "python$v" >/dev/null || continue
  "python$v" -c "import openpyxl" 2>/dev/null || "python$v" -m pip install --user --quiet "openpyxl>=3.1,<4"
  "python$v" -c "import PIL" 2>/dev/null || "python$v" -m pip install --user --quiet "pillow>=10" 2>/dev/null || true
done

echo "== 3/4 Banco da obra e administrador"
"$PY" nuvem.py preparar || exit 1

echo "== 4/4 Site"
SITE="${PYTHONANYWHERE_SITE:-www.${PYTHONANYWHERE_DOMAIN:-pythonanywhere.com}}"
DOMINIO="$USER.${PYTHONANYWHERE_DOMAIN:-pythonanywhere.com}"
WSGI="/var/www/$(echo "$DOMINIO" | tr '.' '_')_wsgi.py"
API="https://$SITE/api/v0/user/$USER/webapps"
VERSAO="python$(echo "${PY#python}" | tr -d '.')"
api() { [ -n "${API_TOKEN:-}" ] && curl -fsS -o /dev/null -H "Authorization: Token $API_TOKEN" "$@"; }

if [ ! -f "$WSGI" ] && api -X POST -d "domain_name=$DOMINIO" -d "python_version=$VERSAO" "$API/"; then
  echo "   Site criado: $DOMINIO"
fi
if [ ! -f "$WSGI" ]; then
  cat <<FIM

   Falta criar o site (uma vez só, leva 1 minuto):
     1. No menu do PythonAnywhere, abra "Web" e clique em "Add a new web app".
     2. Clique em "Next", escolha "Manual configuration" e depois "Python ${PY#python}". Clique em "Next".
     3. Volte a este console e cole de novo o mesmo comando.
FIM
  exit 0
fi

cat > "$WSGI" <<FIM
# Sistema Morro da Cruz — gerado por instalar_pythonanywhere.sh (rodar de novo regrava este arquivo)
import sys
sys.path.insert(0, "$PASTA")
from nuvem import application  # noqa: E402,F401
FIM
echo "   Arquivo do site gravado: $WSGI"

if api -X PATCH -d "force_https=true" "$API/$DOMINIO/" && api -X POST "$API/$DOMINIO/reload/"; then
  echo "   Site recarregado, só com https."
else
  cat <<FIM

   Último passo (no navegador): abra "Web", ligue "Force HTTPS" e clique no botão verde "Reload $DOMINIO".
FIM
fi
cat <<FIM

=======================================================================
 LINK DA EQUIPE (fixo):  https://$DOMINIO
 Entre com o administrador que você criou e cadastre a equipe na aba 6.
 Conta gratuita: uma vez por mês, abra "Web" e clique em "Run until 1 month from today"
 (o PythonAnywhere avisa por e-mail antes de desligar).
 Para atualizar o sistema depois: cole de novo o mesmo comando.
=======================================================================
FIM
