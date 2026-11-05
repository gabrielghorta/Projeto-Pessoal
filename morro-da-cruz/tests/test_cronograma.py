"""Cronograma da obra vindo do MS Project: leitura do XML do Project, da planilha do Excel e do CSV exportados, recusa do
.mpp e de XML perigoso ou de outro tipo, ligação das tarefas com a frente e os trechos (herdando zona e PB das
tarefas-resumo), versões guardadas e o assentado do sistema ao lado do % do Project. Planilhas SINTÉTICAS."""
import base64
import io
import os
import sys
import unittest
from datetime import datetime

from openpyxl import Workbook

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import cronograma as CR  # noqa: E402
import servicos as S  # noqa: E402
from test_acesso import TR, BaseHTTP  # noqa: E402

TR2, MND = "Zona01_PB01_Rede_TR002", "Zona02_PB04_Rede_TR036"
XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Cronograma Morro da Cruz.xml</Name><Title>Morro da Cruz - rede de água</Title>
  <StartDate>2026-10-12T08:00:00</StartDate><FinishDate>2026-11-30T17:00:00</FinishDate><MinutesPerDay>480</MinutesPerDay>
  <Tasks>
    <Task><UID>0</UID><ID>0</ID><Name>Morro da Cruz</Name><OutlineLevel>0</OutlineLevel><Summary>1</Summary></Task>
    <Task><UID>1</UID><ID>1</ID><Name>Zona 01</Name><WBS>1</WBS><OutlineLevel>1</OutlineLevel><Start>2026-10-12T08:00:00</Start>
      <Finish>2026-10-30T17:00:00</Finish><Duration>PT120H0M0S</Duration><PercentComplete>20</PercentComplete><Summary>1</Summary></Task>
    <Task><UID>7</UID><ID>2</ID><Name>PB01 - assentamento TR001 a TR002</Name><WBS>1.1</WBS><OutlineLevel>2</OutlineLevel>
      <Start>2026-10-12T08:00:00</Start><Finish>2026-10-16T17:00:00</Finish><Duration>PT40H0M0S</Duration><PercentComplete>50</PercentComplete>
      <Summary>0</Summary><Critical>1</Critical><Notes>começar pelo NÓ1.8</Notes>
      <PredecessorLink><PredecessorUID>8</PredecessorUID><Type>1</Type><LinkLag>4800</LinkLag></PredecessorLink>
      <Baseline><Number>0</Number><Start>2026-10-10T08:00:00</Start><Finish>2026-10-15T17:00:00</Finish></Baseline></Task>
    <Task><UID>8</UID><ID>3</ID><Name>Liberação topográfica</Name><WBS>1.2</WBS><OutlineLevel>2</OutlineLevel><Start>2026-10-12T08:00:00</Start>
      <Finish>2026-10-12T08:00:00</Finish><Duration>PT0H0M0S</Duration><Milestone>1</Milestone><Summary>0</Summary></Task>
    <Task><UID>9</UID><ID>4</ID><Name>Adutora - travessia</Name><WBS>2</WBS><OutlineLevel>1</OutlineLevel><Start>2026-11-02T08:00:00</Start>
      <Finish>2026-11-30T17:00:00</Finish><Duration>PT160H0M0S</Duration><PercentComplete>0</PercentComplete><Summary>0</Summary></Task>
  </Tasks>
  <Resources><Resource><UID>1</UID><Name>Equipe Zona 01</Name></Resource></Resources>
  <Assignments><Assignment><TaskUID>7</TaskUID><ResourceUID>1</ResourceUID></Assignment></Assignments>
</Project>""".encode("utf-8")


def xlsx():
    wb = Workbook()
    ws = wb.active
    ws.append(["Cronograma exportado do Project"])
    ws.append(["Id", "Nome da Tarefa", "Duração", "Início", "Término", "% concluída", "Predecessoras", "Nível da estrutura de tópicos",
               "Nomes dos recursos"])
    ws.append([1, "Zona 02", "10 dias", datetime(2026, 10, 19, 8), datetime(2026, 10, 30, 17), "0%", None, 1, None])
    ws.append([2, "PB04 - TR036 travessia MND", "16 hrs", "seg 19/10/26 08:00", "ter 20/10/26 17:00", 0.25, "1TI+2 dias", 2, "Equipe Zona 02"])
    ws.append([3, "Recomposição", "2 sems", "02/11/2026", "13/11/2026", "", "2", 2, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def b64(dados):
    return base64.b64encode(dados).decode()


class TestLeitura(unittest.TestCase):
    def test_xml_do_project(self):
        formato, projeto, ts = CR.ler(XML, "cronograma.xml")
        self.assertEqual((formato, projeto["nome"], projeto["inicio"], projeto["fim"]), ("XML", "Morro da Cruz - rede de água", "2026-10-12", "2026-11-30"))
        self.assertEqual([t["id"] for t in ts], [1, 2, 3, 4])                       # a tarefa 0 (resumo do projeto) fica de fora
        t = ts[1]
        self.assertEqual((t["nivel"], t["duracao_dias"], t["concluido"], t["critica"], t["resumo"], t["recursos"]), (2, 5.0, 50.0, True, False, ["Equipe Zona 01"]))
        self.assertEqual(t["predecessoras"], [{"id": 3, "tipo": "TI", "atraso_dias": 1.0}])   # UID 8 → ID 3; 4800 décimos de minuto = 1 dia
        self.assertEqual(t["linha_base"], {"inicio": "2026-10-10", "fim": "2026-10-15"})
        self.assertTrue(ts[2]["marco"])

    def test_planilha_e_csv_exportados(self):
        formato, _, ts = CR.ler(xlsx(), "cronograma.xlsx")
        self.assertEqual(formato, "XLSX")
        self.assertEqual([(t["id"], t["nivel"], t["resumo"]) for t in ts], [(1, 1, True), (2, 2, False), (3, 2, False)])
        t = ts[1]
        self.assertEqual((t["inicio"], t["fim"], t["duracao_dias"], t["concluido"], t["recursos"]), ("2026-10-19", "2026-10-20", 2.0, 25.0, ["Equipe Zona 02"]))
        self.assertEqual(t["predecessoras"], [{"id": 1, "tipo": "TI", "atraso_dias": 2.0}])
        self.assertEqual((ts[2]["duracao_dias"], ts[2]["inicio"], ts[2]["predecessoras"][0]["id"]), (10.0, "2026-11-02", 2))
        csv_pt = "Id;Nome;Duração;Início;Término;% concluída\n1;Zona 03 - ligações;5 dias;12/10/2026;16/10/2026;100%\n".encode("cp1252")
        formato, _, ts = CR.ler(csv_pt, "crono.csv")
        self.assertEqual((formato, ts[0]["nome"], ts[0]["duracao_dias"], ts[0]["concluido"], ts[0]["fim"]), ("CSV", "Zona 03 - ligações", 5.0, 100.0, "2026-10-16"))
        csv_en = b"ID,Task Name,Duration,Start,Finish,% Complete,Predecessors\n1,Adutora,3 days,2026-10-12,2026-10-14,10%,\n2,Travessia,1 wk,2026-10-15,2026-10-21,0%,1SS\n"
        _, _, ts = CR.ler(csv_en, "crono.csv")
        self.assertEqual([(t["duracao_dias"], t["predecessoras"]) for t in ts], [(3.0, []), (5.0, [{"id": 1, "tipo": "II", "atraso_dias": 0}])])

    def test_recusas(self):
        for dados, nome, msg in ((b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(64), "obra.mpp", "Salvar como"),
                                 (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Project/>', "x.xml", "DOCTYPE"),
                                 (b'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"/>', "nota.xml", "não é de um projeto"),
                                 (b"<Project", "x.xml", "XML inválido"), (b"\x00\x01\x02 lixo", "x.bin", "Formato não reconhecido"),
                                 (b"", "x.csv", "vazio"), (b"Id;Coisa\n1;2\n", "x.csv", "linha de títulos")):
            with self.assertRaisesRegex(S.RegraViolada, msg):
                CR.ler(dados, nome)

    def test_duracoes_datas_e_porcentagens_do_texto(self):
        self.assertEqual([CR._duracao_txt(v) for v in ("5 dias", "3,5d", "16 hrs", "2 sems", "1 ms", "5 days?", "5 edias", "30 mins", 2)],
                         [5.0, 3.5, 2.0, 10.0, 20.0, 5.0, 5.0, 0.06, 2.0])
        self.assertEqual([CR._data(v) for v in ("seg 21/10/26", "2026-10-21T08:00:00", "31/02/2026", "ND", datetime(2026, 1, 2))],
                         ["2026-10-21", "2026-10-21", None, None, "2026-01-02"])
        self.assertEqual([CR._pct(v) for v in ("35%", 0.35, 35, "", "1,5 %")], [35.0, 35.0, 35.0, None, 1.5])


class TestCronogramaHTTP(BaseHTTP):
    def test_envio_versoes_ligacao_e_assentado_do_sistema(self):
        eng, almox, enc = self.cliente("eng1"), self.cliente("almox1"), self.cliente("enc1")
        corpo = {"conteudo_b64": b64(XML), "nome": "Cronograma Morro da Cruz.xml"}
        self.assertEqual(almox.post("/api/cronograma", corpo)[0], 403)              # enviar é de quem planeja
        st, r = eng.post("/api/cronograma", corpo)
        self.assertEqual((st, r.get("versao"), r.get("n_tarefas"), r.get("ligadas_a_trechos"), r.get("com_frente")), (200, 1, 4, 1, 4), r)
        st, r = eng.post("/api/cronograma", corpo)
        self.assertEqual(st, 422)
        self.assertIn("igual à versão atual", r["erro"])
        self.assertNotIn(corpo["conteudo_b64"][:40], self.q("SELECT corpo FROM auditoria WHERE rota='/api/cronograma'")[0][0])
        self.assertEqual(enc.get("/api/cronograma")[0], 403)
        st, c = almox.get("/api/cronograma")                                        # o almoxarife consulta (mapa do Dados da obra)
        self.assertEqual(st, 200)
        t = {x["id"]: x for x in c["tarefas"]}
        self.assertEqual((t[2]["frente"], t[2]["pb"], t[2]["alvos"]), ("Zona01", "PB01", [TR, TR2]))   # zona herdada da tarefa-resumo
        self.assertEqual((t[3]["frente"], t[3]["alvos"], t[4]["frente"]), ("Zona01", [], "ADUTORA"))
        self.assertEqual((t[2]["executado_m"], t[2]["executado_pct"]), (0, 0))
        S.registrar_clima(self.c, "2026-10-15", "Zona01", "MANHA", "SOL")
        S.registrar_clima(self.c, "2026-10-15", "Zona01", "TARDE", "SOL")
        S.apontar(self.c, "2026-10-15", "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}])
        t = {x["id"]: x for x in eng.get("/api/cronograma")[1]["tarefas"]}
        self.assertEqual((t[2]["executado_m"], t[2]["executado_pct"]), (30, round(100 * 30 / (76.55 + 75.07), 1)))
        st, r = eng.post("/api/cronograma", {"conteudo_b64": b64(xlsx()), "nome": "cronograma.xlsx"})
        self.assertEqual((st, r.get("versao")), (200, 2), r)
        c = eng.get("/api/cronograma")[1]
        self.assertEqual(([v["versao"] for v in c["versoes"]], c["formato"]), ([2, 1], "planilha do Excel exportada do Project"))
        self.assertEqual({x["id"]: x["alvos"] for x in c["tarefas"]}[2], [MND])
        pasta = os.path.join(os.path.dirname(self.db), "documentos", "cronograma")
        self.assertEqual(sorted(os.path.splitext(n)[1] for n in os.listdir(pasta)), [".json", ".json", ".xlsx", ".xml"])
        st, r = eng.post("/api/cronograma", {"conteudo_b64": b64(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(64)), "nome": "obra.mpp"})
        self.assertEqual(st, 422)
        self.assertIn("Formato XML", r["erro"])


if __name__ == "__main__":
    unittest.main()
