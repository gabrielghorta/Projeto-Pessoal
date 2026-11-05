# Fundo de ruas nos mapas — D-209

O Mapa iluminado e Almoxarifado › Programação abrem com ruas contínuas do OpenStreetMap, sem recorte nas zonas.
O retângulo inteiro da prancha 01 inclui as ruas sem rede e o canteiro. O fundo é online, gratuito e sem chave.
Não é o serviço Esri autenticado do AutoCAD; o desenho da rede continua o do projeto corrigido pelo sistema.

## O que continua como foi pedido nos PRs anteriores

| PR | Regra preservada |
|---|---|
| #2 e #25 | Identidade da 06.1 e trecho físico; MND separado do VCA, mesmo sem nó no limite. |
| #6 e #17 | Gesto por transform na GPU, cópia leve, traços finos, geometria antes de esperar o estado do servidor. |
| #7, #9 e #22 | Situação pelos registros, dia de Brasília, atualização após gravação; verde só com cadastro aprovado pela Caesb. |
| #15 e #18 | Na Programação, o primeiro toque na obra inteira só abre a frente. Dentro dela, os toques somam; repetir não remove. Desselecionar e Limpar seleção continuam. Nó terminal automático e equipe da zona preservados. |
| #16 | Subadutora (adutora ou DE ≥ 200), dispositivos com formas, MND tracejado; diâmetro ou programação do dia. |
| #18 | Foco por zona: só a frente em foco tem rede, nós, nomes e equipes ativos. O fundo geográfico continua. No Iluminado, o trecho ainda abre a ficha diretamente. |
| #23 e #24 | Uma etiqueta por equipe e halo nos alvos do dia, sem sobrepor botões; vetor PB25 e coordenadas reais corrigidos. |

## Limite conferido no DWG

Fonte: `A.RED.SSB-D014.V03.T01.001a033-037.dwg`, layout `01`, viewport `381C4`, leitura em cópia pelo AutoCAD Core Console.
Direção perpendicular ao WCS e twist zero. Em metros, SIRGAS 2000 / UTM 23S:

| | Este | Norte |
|---|---:|---:|
| Mínimo | 202167,7188418745 | 8235224,250900868 |
| Máximo | 206007,61994125228 | 8239252,748484623 |

Centro = target + view center; altura = view height; largura = altura × paper width / paper height.
Os valores originais e o teste da conta estão em `config/mapa_contexto.json` e `tests/test_mapa_fundo.py`.
A margem necessária à proporção da tela também recebe ruas. Arrastar não permite continuar navegando para fora da prancha.
As curvas de nível não são acrescentadas.

O canteiro é o polígono real A–F, não um quadrado. Fonte: RAP.SBS2.001, 01/01; handles dos seis LINE no JSON.
O Norte do vértice C é o do desenho (8238313,55767208), preservando a correção da demarcação. Área: 4.068,66 m².
Toque ou Enter/Espaço só destaca e aproxima; não limpa a seleção de material nem muda a frente ou a equipe.

## Camadas e desempenho

`mapa_geral.geometria` acrescenta `contexto`, sem alterar os pontos anteriores. A transformação UTM ↔ desenho é ajustada
nos mesmos nós do REV02. `web/mapa_fundo.js` converte os cantos de cada tile para o desenho. Não desloca a rede para
encaixar no mapa. O resíduo do ajuste desenho/UTM é de aproximadamente 1 cm no ponto mais afastado.

Mantidos: pan, pinça, roda e animações na GPU; desenho completo ao terminar o gesto. A cópia leve usa só os tiles já
vistos, sem disparar pedidos. Zonas com preenchimento suave; contorno escuro sob os traços mantém branco e amarelo legíveis.
Camadas › Fundo do mapa oferece Ruas (novo padrão), Satélite escuro, Satélite claro e Sem fundo.
A preferência nova usa `mc-ilu-fundo-v2`; as preferências de cores, camadas e vista da sessão continuam.

## Serviço gratuito e falhas de conexão

Os pedidos vão direto do navegador para `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, com Referer normal, cache HTTP
e atribuição © OpenStreetMap sempre visível, inclusive em tela cheia. Não passam pelo servidor PythonAnywhere gratuito.
Não há pré-busca, arquivo offline ou download de áreas/níveis. A cache de memória é compartilhada pelos dois mapas.
Falhas exibem aviso e Tentar novamente; a rede e a seleção continuam disponíveis. Reconectar relê só a vista ativa.

Política do provedor: https://operations.osmfoundation.org/policies/tiles/ . O serviço público não tem garantia de
disponibilidade. Não automatizar varredura de zoom/arrasto no serviço real; nos testes de navegador, interceptar os tiles.

## Validação e instalação

- `python -m unittest discover -s tests`: inclui limites, projeção, cobertura fora das zonas, navegação e canteiro,
  além das regressões de topologia, PB25, seleção e equipe.
- Conferência de navegador em 390 e 1280 px, com tiles substituídos por fixture local: cores, cobertura, canteiro,
  seleção, equipe da Zona 08, falha e recuperação da conexão, ausência de erro JS e rolagem lateral.
  Roteiro reproduzível: `ferramentas/desempenho/conferir_mapa_ruas.cjs` (Node/Playwright/Chromium, como as outras ferramentas).
- Sem migração, dependência nova, alteração do HTML REV02 ou dado de produção.

Depois de mesclar o PR no ramo do site, no Bash do PythonAnywhere:

```bash
cd ~/Projeto-Pessoal && git fetch origin claude/powerbi-modifications-wqxekj && git reset --hard origin/claude/powerbi-modifications-wqxekj && bash morro-da-cruz/instalar_pythonanywhere.sh
```

Depois: Web › Reload e Ctrl+Shift+R. O PR não faz deploy nem merge automaticamente.
