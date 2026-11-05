"""D-209: limites do DWG, projeção do fundo e navegação. Não faz pedidos ao OpenStreetMap."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import coordenadas
import mapa_geral as MG
import server

RAIZ = Path(__file__).resolve().parents[1]


class TestContextoMapa(unittest.TestCase):
    def test_limites_reproduzem_viewport_da_prancha_01(self):
        cfg = json.loads((RAIZ / 'config/mapa_contexto.json').read_text(encoding='utf-8'))
        p = cfg['prancha01']; v = p['viewport']
        cx, cy = [a + b for a, b in zip(v['target'], v['view_center'])]
        h = v['view_height']; w = h * v['paper_width'] / v['paper_height']
        self.assertEqual(v['twist'], 0)
        for a, b in zip(p['limites_utm'], [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]):
            self.assertAlmostEqual(a, b, places=7)

    @unittest.skipUnless(os.path.exists(server._mapa_path()), 'sem mapa REV02')
    def test_enquadramento_contem_rede_e_canteiro_real(self):
        g = MG.geometria(server._mapa_path()); ctx = g['contexto']
        x0, y0, x1, y1 = ctx['limites']
        for t in g['trechos']:
            for p in t['p']:
                for x, y in zip(p[::2], p[1::2]):
                    self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1, t['n'])
        c = ctx['canteiro']['p']; self.assertEqual(len(c), 12)
        xy = [MG.aplicar(ctx['mapa_para_utm'], *p) for p in zip(c[::2], c[1::2])]
        self.assertAlmostEqual(xy[2][1], 8238313.55767208, places=6)  # o Norte do DWG, não o erro da tabela do PDF
        a, b = xy[0]
        area = abs(sum((x-a)*(yy-b)-(xx-a)*(y-b) for (x,y),(xx,yy) in zip(xy,xy[1:]+xy[:1]))/2)
        self.assertAlmostEqual(area, 4068.657765, places=4)
        self.assertTrue(all(x0 <= x <= x1 and y0 <= y <= y1 for x,y in zip(c[::2], c[1::2])))


@unittest.skipUnless(shutil.which('node'), 'sem Node para o teste de JavaScript')
class TestFundoJS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (RAIZ / 'web/mapa_fundo.js').read_text(encoding='utf-8')

    def executar(self, codigo):
        stub = 'const window={addEventListener(){}};\n'
        stub += '''function encaixar([x0,y0,x1,y1],asp) {let w=x1-x0,h=y1-y0;
          if(w/h>asp)h=w/asp;else w=h*asp; return [(x0+x1-w)/2,(y0+y1-h)/2,w,h];}\n'''
        r = subprocess.run([shutil.which('node'), '-e', stub + self.js + '\n' + codigo], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_projecao_casa_com_utm_do_projeto(self):
        pontos = [[e,n] for e in range(202000,207000,500) for n in range(8235000,8240000,500)]
        resultado = self.executar(f'console.log(JSON.stringify({json.dumps(pontos)}.map(p=>[fundoUTMGeo(...p),fundoGeoUTM(...fundoUTMGeo(...p))])));')
        for p, (geo, volta) in zip(pontos, resultado):
            self.assertLess(math.dist(p, volta), .002)
            self.assertLess(math.dist(geo, coordenadas.utm_para_geo(*p)), 1e-7)

    def test_cantos_dos_tiles_nao_desalinham_no_zoom(self):
        # A curvatura UTM dentro de um tile deve ser menor que 0,15 pixel do próprio tile em todos os níveis usados.
        out = self.executar('''const geo={utm_para_mapa:[.7,0,-141693.86,0,-.7,5767516.09]};
          console.log(JSON.stringify(Array.from({length:8},(_,i)=>{
            const z=i+12,[x,y]=fundoGeoTile(-15.92,-47.76,z).map(Math.floor),m=fundoMatrizTile(z,x,y,geo),q=fundoPontoTile(z,x+1,y+1,geo);
            return Math.hypot(m[0]*256+m[2]*256+m[4]-q[0],m[1]*256+m[3]*256+m[5]-q[1])/Math.hypot(m[0],m[1]);})));''')
        self.assertTrue(all(e < .15 for e in out), out)

    def test_arrasto_zoom_e_vista_antiga_limitados_a_prancha(self):
        out = self.executar('''const ctx={limiteMapa:[0,0,4000,4200]};
          console.log(JSON.stringify([[10000,-10000,1000,600],[-9000,9000,1000,600],[0,0,40000,20000],[-9000,9000,1200,6000]]
          .map(v=>limitarVistaMapa(ctx,v))));''')
        self.assertEqual(out[0], [3000,0,1000,600])
        self.assertEqual(out[1], [0,3600,1000,600])
        self.assertEqual(out[2], [-2200,0,8400,4200])  # só a margem necessária à proporção 2:1
        self.assertAlmostEqual(out[3][1] + out[3][3] / 2, 2100)

    def test_tiles_cobrem_vista_sem_rede_e_sem_prefetch(self):
        out = self.executar('''const geo={utm_para_mapa:[.7,0,-141693.86,0,-.7,5767516.09],mapa_para_utm:[1/.7,0,202419.8,0,-1/.7,8239308.7]};
          const vb=[-200,-100,3000,3000],qs=fundoTilesVista(vb,1280,geo),z=+qs[0].chave.split('/')[0];
          const keys=new Set(qs.map(q=>q.chave));
          const dentro=[[vb[0],vb[1]],[vb[0]+vb[2],vb[1]],[vb[0]+vb[2],vb[1]+vb[3]],[vb[0],vb[1]+vb[3]]]
          .every(p=>{const [x,y]=fundoGeoTile(...fundoUTMGeo(...fundoAfim(geo.mapa_para_utm,...p)),z).map(Math.floor);return keys.has(`${z}/${x}/${y}`);});
          console.log(JSON.stringify([qs.length,new Set(qs.map(q=>q.chave.split('/')[0])).size,dentro]));''')
        self.assertLessEqual(out[0],64); self.assertEqual(out[1:], [1,True])

    def test_afastar_na_tela_larga_nao_aproxima_por_engano(self):
        import re
        ilu = (RAIZ / 'web/iluminado.js').read_text(encoding='utf-8')
        zoom = re.search(r'function zoomEm\(.*?\n\}', ilu, re.S).group(0)
        out = self.executar('''const pararAnimacao=()=>{},gestoVista=ctx=>{ctx.vb=limitarVistaMapa(ctx,ctx.vb);};
          const ctx={base:[0,0,4000,4200],limiteMapa:[0,0,4000,4200],vb:encaixar([0,0,4000,4200],2.4)};'''
          + zoom + ';const antes=ctx.vb.slice();zoomEm(1.2,null,null,ctx);console.log(JSON.stringify([antes,ctx.vb]));')
        self.assertEqual(out[0], out[1])

    def test_canteiro_so_destaca_e_aproxima(self):
        out = self.executar('''let classe=false,foi=null;
          const GERAL={contexto:{canteiro:{p:[0,0,10,0,10,10,0,10]}}};
          const $=()=>({classList:{add:()=>{classe=true;}}}),limites=()=>[0,0,10,10],irPara=(alvo,animar,ctx)=>{foi=[alvo,animar,ctx];};
          destacarCanteiro({prefixo:'pln',svg:()=>({})}); console.log(JSON.stringify([classe,foi]));''')
        self.assertTrue(out[0]); self.assertEqual(out[1][:2], [[0,0,10,10],True])
