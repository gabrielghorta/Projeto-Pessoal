"""REV02 do cronograma (30/10/2026): a REV01 (a obra sai do reservatório) com as correções da análise crítica.

O que muda da REV01, a pedido do responsável em 30/10/2026:
* o 2º empreiteiro (Equipes C e D) entra em 01/03/2027, e não em 01/04 (os 6 contêineres dele chegam junto);
* calendário com recesso de 22/12 a 02/01 e 4 dias úteis de chuva por mês de outubro a abril (estimativa);
* produtividade pelo diâmetro: até DE 160, a da equipe (90 m/dia); DE 225 a 315, 60 m/dia; DE 355 a 500, 45 m/dia;
* cada equipe de empreiteiro começa a meia produtividade nos 5 primeiros dias úteis;
* meio dia útil perdido em cada troca de frente (deslocamento);
* as ligações prediais são feitas pelas próprias equipes, 20 por dia, logo depois de cada trecho de DE 63;
* as peças das caixas do caminho da água (as da Subadutora inclusive) são compradas antes e montadas logo depois da
  obra civil, e a interligação de cada frente espera só as caixas do caminho até ela;
* teste hidrostático no fim de cada zona; a desinfecção fica para os dias antes da entrada em carga (depende da data do
  reservatório).
Tudo o mais é a REV01 (pé alto, ordem da água, 4 saídas, entrada das outras equipes, caixas, cadastro, canteiro).
"""
import datetime as dt

import motor

REV = 'REV02'
DATA = '30/10/2026'
ENTRADA_EMP2 = dt.date(2027, 3, 1)
OPCOES = {
    'hidro_caminho_antes': True,
    'interlig_por_caminho': True,
    'prod_por_de': ((355, 45.0), (225, 60.0)),
    'entrada_meia_dias': 5,
    'troca_frente_dias': 0.5,
    'ligacoes_por_dia': 20,
}


ROTULOS = {'id': REV, 'data': DATA, 'ant': 'REV01', 'ant_data': '30/10/2026',
           'ant_txt': 'a obra sai do reservatório (Zona 11)',
           'txt': 'a obra sai do reservatório (Zona 11), com chuva, produtividade por diâmetro e as ligações pelas equipes',
           'pronto_txt': 'o caminho testado e interligado e as caixas do caminho montadas (teste e interligação pelo '
                         'caminho da água: o pedaço da Subadutora e a entrada da zona; a desinfecção vem logo antes da carga)',
           'carga_txt': 'a entrada da zona testada e interligada pelo caminho da água (a desinfecção vem logo antes da carga)',
           'col_teste': 'TESTE HIDROSTÁTICO (término)', 'leg_teste': 'teste hidrostático',
           'calendario': 'seg a sex, 7h às 17h, sem feriados nacionais e do DF, recesso de 22/12 a 02/01 e 4 dias de chuva '
                         'por mês de out a abr'}


def preparar(chuva=True, emp2=True):
    """Aplica neste processo as premissas da REV02 que moram no motor (datas de entrada, contêineres e calendário).
    Rode uma vez, antes de programar: o calendário muda para todos os módulos. Devolve {data: motivo} dos dias tirados."""
    if emp2:
        for k, e in enumerate(motor.EQUIPES):
            if e[0] in ('E2C', 'E2D'):
                motor.EQUIPES[k] = (e[0], e[1], e[2], ENTRADA_EMP2)
        motor.CONTEINERES[:] = [(ENTRADA_EMP2, n) if d == dt.date(2027, 4, 1) else (d, n) for d, n in motor.CONTEINERES]
    return motor.aplicar_chuva_e_recesso() if chuva else {}
