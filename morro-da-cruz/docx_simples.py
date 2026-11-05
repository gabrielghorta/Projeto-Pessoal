"""Word nativo para o RM: parágrafos e tabelas editáveis, figuras PNG; stdlib + Pillow já existente."""
import io
import os
import re
import zipfile
from xml.etree import ElementTree as ET

import pdf_simples as P

NS = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "wp":"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
      "a":"http://schemas.openxmlformats.org/drawingml/2006/main",
      "pic":"http://schemas.openxmlformats.org/drawingml/2006/picture"}
for prefixo, uri in NS.items():
    ET.register_namespace(prefixo, uri)


def el(pai, nome, **attrs):
    pre, local = nome.split(":")
    return ET.SubElement(pai, "{"+NS[pre]+"}"+local,
        {"{"+NS[k.split(":")[0]]+"}"+k.split(":")[1] if ":" in k else k:str(v) for k,v in attrs.items()})


def xml(no):
    return ET.tostring(no, encoding="utf-8", xml_declaration=True)


def texto(p, texto_, tam=11, negrito=False, italico=False, cor="000000", fundo=None):
    for i, linha in enumerate(str(texto_ if texto_ is not None else "").split("\n")):
        r=el(p,"w:r"); pr=el(r,"w:rPr")
        el(pr,"w:rFonts",**{"w:ascii":"Arial Narrow","w:hAnsi":"Arial Narrow"})
        el(pr,"w:sz",**{"w:val":round(tam*2)})
        if negrito:el(pr,"w:b")
        if italico:el(pr,"w:i")
        el(pr,"w:color",**{"w:val":cor})
        if fundo:el(pr,"w:shd",**{"w:fill":fundo,"w:val":"clear"})
        if i:el(r,"w:br")
        t=el(r,"w:t")
        t.set("{http://www.w3.org/XML/1998/namespace}space","preserve")
        t.text=re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]","",linha)


class Desenho:
    """Mesmas primitivas dos mapas/gráficos do PDF, desenhadas em PNG de alta resolução."""
    def __init__(self,w,h):
        from PIL import Image,ImageDraw
        self.k=3; self.im=Image.new("RGB",(max(1,round(w*self.k)),max(1,round(h*self.k))),"white")
        self.d=ImageDraw.Draw(self.im);self.imagens={};self.recortes=[]

    def _cor(self,c):
        return tuple(round(v*255) for v in P.cor(c)) if c is not None else None

    def _fonte(self,tam,b=False,i=False):
        from PIL import ImageFont
        win="arial"+("bi" if b and i else "bd" if b else "i" if i else "")+".ttf"
        linux="DejaVuSans"+("-BoldOblique" if b and i else "-Bold" if b else "-Oblique" if i else "")+".ttf"
        for nome in (os.path.join(os.environ.get("WINDIR","C:/Windows"),"Fonts",win),
                     "/usr/share/fonts/truetype/dejavu/"+linux,linux):
            try:return ImageFont.truetype(nome,max(1,round(tam*self.k)))
            except OSError:pass
        return ImageFont.load_default()

    def texto(self,p,x,y,s,tam=10,negrito=False,italico=False,cor_="000000",escala=P.ESCALA):
        from PIL import Image,ImageDraw
        if not s:return
        fonte=self._fonte(tam,negrito,italico);bbox=fonte.getbbox(str(s))
        im=Image.new("RGBA",(max(1,bbox[2]-bbox[0]+2),max(1,bbox[3]-bbox[1]+2)),(255,255,255,0))
        ImageDraw.Draw(im).text((-bbox[0],-bbox[1]),str(s),font=fonte,fill=self._cor(cor_))
        w=max(1,round(P.largura(str(s),tam,negrito,escala)*self.k))
        im=im.resize((w,im.height));self.im.paste(im,(round(x*self.k),round((y-tam*.78)*self.k)),im)

    def texto_girado(self,p,x,y,s,tam=8,negrito=False,cor_="000000",angulo=90):
        d=Desenho(max(20,P.largura(s,tam,negrito)+4),tam*2)
        d.texto(None,1,tam,s,tam,negrito,cor_=cor_)
        im=d.im.rotate(angulo,expand=True,fillcolor="white")
        self.im.paste(im,(round(x*self.k),round(y*self.k)-im.height))

    def ret(self,p,x,y,w,h,fundo=None,borda=None,lw=.5):
        self.d.rectangle((x*self.k,y*self.k,(x+w)*self.k,(y+h)*self.k),fill=self._cor(fundo),outline=self._cor(borda),width=max(1,round(lw*self.k)))

    def poli(self,p,pts,cor_="000000",lw=.5,traco=None,fechar=False,fundo=None):
        pts=[(round(x*self.k),round(y*self.k)) for x,y in pts]
        if len(pts)<2:return
        if fundo:self.d.polygon(pts,fill=self._cor(fundo))
        self.d.line(pts+([pts[0]] if fechar else []),fill=self._cor(cor_),width=max(1,round(lw*self.k)),joint="curve")

    def linha(self,p,x1,y1,x2,y2,cor_="000000",lw=.5,traco=None):
        self.poli(p,[(x1,y1),(x2,y2)],cor_,lw,traco)

    def tracos(self,p,segmentos,cor_="000000",lw=.5):
        for x1,y1,x2,y2 in segmentos:self.linha(p,x1,y1,x2,y2,cor_,lw)

    def circulo(self,p,x,y,r,fundo=None,borda=None,lw=.5):
        self.d.ellipse(((x-r)*self.k,(y-r)*self.k,(x+r)*self.k,(y+r)*self.k),fill=self._cor(fundo),outline=self._cor(borda),width=max(1,round(lw*self.k)))

    def check(self,p,x,y,tam=9,cor_="000000"):
        self.poli(p,[(x,y-tam*.4),(x+tam*.3,y),(x+tam*.8,y-tam*.8)],cor_,1)

    def recortar(self,p,x,y,w,h):
        self.recortes.append((self.im.copy(),tuple(round(v*self.k) for v in (x,y,x+w,y+h))))

    def fim_recorte(self,p):
        anterior,box=self.recortes.pop();anterior.paste(self.im.crop(box),box[:2]);self.im=anterior
        from PIL import ImageDraw
        self.d=ImageDraw.Draw(self.im)

    def registrar_imagem(self,dados,foto=True,max_px=1100,qualidade=78):
        from PIL import Image
        if not dados:return None
        im=Image.open(io.BytesIO(dados)).convert("RGB");iid=len(self.imagens)+1;self.imagens[iid]=im
        return iid,im.width,im.height

    def imagem(self,p,iid,x,y,w,h):
        im=self.imagens[iid].resize((max(1,round(w*self.k)),max(1,round(h*self.k))))
        self.im.paste(im,(round(x*self.k),round(y*self.k)))

    def salvar(self):
        b=io.BytesIO();self.im.save(b,format="PNG",optimize=True);return b.getvalue()


class Documento:
    def __init__(self):
        self.raiz=ET.Element("{"+NS["w"]+"}document");self.corpo=el(self.raiz,"w:body")
        self.midias=[];self.rels=[];self.paisagem=False;self.titulos=[];self._cont=[1,0,0];self._quebra=False

    @property
    def w(self):return (P.A4[1] if self.paisagem else P.A4[0])-96

    def paragrafo(self,runs,tam=11,alin="J",antes=0,depois=6,recuo=0,marcador=False,entrelinha=1.2,cor_="000000",junto=False,estilo=None,pai=None):
        p=el(pai if pai is not None else self.corpo,"w:p");pr=el(p,"w:pPr")
        if self._quebra and pai is None:el(pr,"w:pageBreakBefore");self._quebra=False
        if estilo:el(pr,"w:pStyle",**{"w:val":estilo})
        el(pr,"w:jc",**{"w:val":{"E":"left","C":"center","D":"right","J":"both"}.get(alin,"left")})
        el(pr,"w:spacing",**{"w:before":round(antes*20),"w:after":round(depois*20),"w:line":round(entrelinha*240),"w:lineRule":"auto"})
        if junto:el(pr,"w:keepNext")
        if recuo or marcador:el(pr,"w:ind",**{"w:left":round((recuo+13*bool(marcador))*20)})
        if marcador:texto(p,"• ",tam)
        if isinstance(runs,str):runs=[(runs,{})]
        for t,o in runs:
            texto(p,t,tam,o.get("negrito",False),o.get("italico",False),o.get("cor",cor_) or "000000",o.get("fundo"))
        return p

    def _secao(self,paisagem):
        s=ET.Element("{"+NS["w"]+"}sectPr")
        el(s,"w:headerReference",**{"w:type":"default","r:id":"rIdHeader"})
        el(s,"w:footerReference",**{"w:type":"default","r:id":"rIdFooter"})
        w,h=(P.A4[1],P.A4[0]) if paisagem else P.A4
        el(s,"w:pgSz",**{"w:w":round(w*20),"w:h":round(h*20),"w:orient":"landscape" if paisagem else "portrait"})
        el(s,"w:pgMar",**{"w:top":1720,"w:bottom":1000,"w:left":960,"w:right":960,"w:header":520,"w:footer":480})
        borders=el(s,"w:pgBorders",**{"w:offsetFrom":"page"})
        for lado in ("top","left","bottom","right"):el(borders,"w:"+lado,**{"w:val":"double","w:sz":4,"w:space":15,"w:color":"8B3430"})
        return s

    def nova_pagina(self,paisagem=None):
        if paisagem is not None and paisagem != self.paisagem:
            p=self.paragrafo("",depois=0);p.find("w:pPr",NS).append(self._secao(self.paisagem));self.paisagem=paisagem
        else:
            self._quebra=True

    def titulo(self,nivel,txt,nova_pagina=False,paisagem=None,numerar=True,sumario=True):
        if nova_pagina or paisagem is not None and paisagem!=self.paisagem:self.nova_pagina(paisagem)
        if numerar:
            self._cont[nivel-1]+=1
            for i in range(nivel,3):self._cont[i]=0
            num=".".join(map(str,self._cont[:nivel]));t=num+"  "+txt
        else:num="";t=txt
        self.paragrafo([(t,{"negrito":True,"italico":True})],tam=13 if nivel==1 else 11.5,alin="E",antes=8,depois=7,cor_="8B3430",junto=True,estilo="Heading"+str(nivel))
        if sumario:self.titulos.append((nivel,t))

    def tabela(self,larguras,linhas,cab=1,tam=9,cor_cab="173B59",cor_borda="D9D9D9",alin=None,total=False,pad=4,depois=5,cor_total="F2F2F2",pai=None):
        tbl=el(pai if pai is not None else self.corpo,"w:tbl");pr=el(tbl,"w:tblPr")
        el(pr,"w:tblW",**{"w:w":5000,"w:type":"pct"});el(pr,"w:tblLayout",**{"w:type":"fixed"})
        bordas=el(pr,"w:tblBorders")
        for lado in ("top","left","bottom","right","insideH","insideV"):el(bordas,"w:"+lado,**{"w:val":"single","w:sz":4,"w:color":"D9D9D9"})
        marg=el(pr,"w:tblCellMar")
        for lado in ("top","left","bottom","right"):el(marg,"w:"+lado,**{"w:w":80,"w:type":"dxa"})
        grid=el(tbl,"w:tblGrid");widths=[round(x/sum(larguras)*self.w*20) for x in larguras]
        for w in widths:el(grid,"w:gridCol",**{"w:w":w})
        for i,linha in enumerate(linhas):
            tr=el(tbl,"w:tr");rp=el(tr,"w:trPr")
            if i<cab:el(rp,"w:tblHeader")
            col=0
            for v in linha:
                v=v if isinstance(v,dict) else {"t":v};span=v.get("span",1)
                tc=el(tr,"w:tc");cp=el(tc,"w:tcPr")
                el(cp,"w:tcW",**{"w:w":sum(widths[col:col+span]),"w:type":"dxa"})
                if span>1:el(cp,"w:gridSpan",**{"w:val":span})
                el(cp,"w:vAlign",**{"w:val":"center"})
                fundo=v.get("fundo") or (cor_cab if i<cab else cor_total if total and i==len(linhas)-1 else "F2F5F7" if i%2 else "FFFFFF")
                el(cp,"w:shd",**{"w:fill":fundo})
                self.paragrafo([(v.get("t") or "",{"negrito":v.get("negrito",i<cab),"cor":v.get("cor") or ("FFFFFF" if i<cab else "000000")})],
                    tam=max(8.5,tam),alin=v.get("alin") or (alin[col] if alin else "E"),depois=2,entrelinha=1.12,pai=tc)
                col+=span
        self.paragrafo("",depois=depois,tam=2)
        return tbl

    def imagem(self,dados,w_max,h_max,legenda=None,foto=True,pai=None):
        from PIL import Image
        im=Image.open(io.BytesIO(dados));k=min(w_max/im.width,h_max/im.height);w,h=im.width*k,im.height*k
        if im.mode in ("RGBA","LA") or "transparency" in im.info:
            rgba=im.convert("RGBA");im=Image.new("RGB",im.size,"white");im.paste(rgba,mask=rgba.getchannel("A"))
        b=io.BytesIO();im.convert("RGB").save(b,format="PNG");iid=len(self.midias)+1;self.midias.append(b.getvalue())
        rid="rIdImg"+str(iid);self.rels.append((rid,"image","media/image"+str(iid)+".png"))
        p=self.paragrafo("",alin="C",depois=4,junto=bool(legenda),pai=pai);r=el(p,"w:r");dr=el(r,"w:drawing")
        inline=el(dr,"wp:inline",distT=0,distB=0,distL=0,distR=0)
        cx,cy=round(w*12700),round(h*12700)
        el(inline,"wp:extent",cx=cx,cy=cy);el(inline,"wp:docPr",id=iid,name="Figura "+str(iid),descr=legenda or "Figura do relatório mensal")
        g=el(inline,"a:graphic");gd=el(g,"a:graphicData",uri=NS["pic"]);pic=el(gd,"pic:pic")
        nv=el(pic,"pic:nvPicPr");el(nv,"pic:cNvPr",id=0,name="image"+str(iid)+".png");el(nv,"pic:cNvPicPr")
        fill=el(pic,"pic:blipFill");el(fill,"a:blip",**{"r:embed":rid});el(el(fill,"a:stretch"),"a:fillRect")
        sp=el(pic,"pic:spPr");xf=el(sp,"a:xfrm");el(xf,"a:off",x=0,y=0);el(xf,"a:ext",cx=cx,cy=cy);el(el(sp,"a:prstGeom",prst="rect"),"a:avLst")
        if legenda:self.paragrafo([(legenda,{"italico":True,"cor":"595959"})],tam=9,alin="C",depois=8,pai=pai)

    def figura(self,w,h,desenhar,legenda=None,tam_leg=8,cor_leg="595959"):
        raster=Desenho(w,h);desenhar(raster,None,0,0,w,h)
        self.imagem(raster.salvar(),min(w,self.w),min(h,355 if self.paisagem else 390),legenda,foto=False)

    def fotos(self,fotos,fora=0):
        if not fotos:self.paragrafo("Sem foto registrada no período.")
        for f in fotos:
            if f["jpeg"]:self.imagem(f["jpeg"],self.w,300,f["legenda"])
            else:self.paragrafo("Foto indisponível no servidor: "+f["legenda"])
        if fora:self.paragrafo(f"Mais {fora} foto(s) ficaram fora do limite do relatório.")

    def salvar(self,d):
        # Sumário estático com títulos nativos: editável e sem números de página presumidos.
        pos=next((i for i,p in enumerate(self.corpo) if p.find("w:pPr/w:pStyle",NS) is not None and p.find("w:pPr/w:pStyle",NS).get("{"+NS["w"]+"}val")=="Heading1"),len(self.corpo))
        tmp=ET.Element("temp");self.paragrafo([("1  Sumário",{"negrito":True})],tam=14,alin="E",depois=12,pai=tmp)
        for nivel,t in self.titulos:self.paragrafo(t,tam=10,alin="E",depois=4,recuo=(nivel-1)*12,pai=tmp)
        el(tmp[0].find("w:pPr",NS),"w:pageBreakBefore")
        for i,p in enumerate(tmp):self.corpo.insert(pos+i,p)
        self.corpo.append(self._secao(self.paisagem))
        hdr=ET.Element("{"+NS["w"]+"}hdr")
        if d["modelo"].get("logo"):self.imagem(d["modelo"]["logo"],85,28,pai=hdr)
        else:self.paragrafo([("ANKARA ENGENHARIA",{"negrito":True,"cor":"ED7D31"})],tam=12,alin="E",depois=4,pai=hdr)
        self.paragrafo(f"Contrato {d['contrato']}   ·   RM {d['medicao']['numero']:02d}/{d['fim'][:4]}   ·   {d['ini']} a {d['fim']}",tam=9,alin="E",depois=3,pai=hdr)
        if d["teste"]:self.paragrafo([("TESTE – NÃO OFICIAL",{"cor":"C00000","negrito":True})],tam=8,alin="C",pai=hdr)
        ftr=ET.Element("{"+NS["w"]+"}ftr");p=self.paragrafo("Página ",tam=9,alin="D",pai=ftr)
        for campo in ("PAGE","NUMPAGES"):
            if campo=="NUMPAGES":texto(p," | ",9)
            fld=el(p,"w:fldSimple",**{"w:instr":campo});texto(fld,"1",9)
        styles=ET.Element("{"+NS["w"]+"}styles")
        for ident,nome in (("Normal","Normal"),("Title","Title"),("Heading1","heading 1"),("Heading2","heading 2"),("Heading3","heading 3")):
            st=el(styles,"w:style",**{"w:type":"paragraph","w:styleId":ident});el(st,"w:name",**{"w:val":nome})
            if ident.startswith("Heading"):el(el(st,"w:pPr"),"w:outlineLvl",**{"w:val":int(ident[-1])-1})
        settings=ET.Element("{"+NS["w"]+"}settings");el(settings,"w:updateFields",**{"w:val":"true"})
        relns="http://schemas.openxmlformats.org/package/2006/relationships"
        rels=ET.Element("{"+relns+"}Relationships")
        for rid,t,alvo in [("rIdStyles","styles","styles.xml"),("rIdSettings","settings","settings.xml"),("rIdHeader","header","header1.xml"),("rIdFooter","footer","footer1.xml"),*self.rels]:
            ET.SubElement(rels,"{"+relns+"}Relationship",Id=rid,Type=NS["r"]+"/"+t,Target=alvo)
        headerrels=ET.Element("{"+relns+"}Relationships")
        for rid,t,alvo in self.rels:ET.SubElement(headerrels,"{"+relns+"}Relationship",Id=rid,Type=NS["r"]+"/"+t,Target=alvo)
        typesns="http://schemas.openxmlformats.org/package/2006/content-types";ct=ET.Element("{"+typesns+"}Types")
        for ext,mime in (("rels","application/vnd.openxmlformats-package.relationships+xml"),("xml","application/xml"),("png","image/png")):ET.SubElement(ct,"{"+typesns+"}Default",Extension=ext,ContentType=mime)
        for parte,t in (("document","document.main"),("styles","styles"),("settings","settings"),("header1","header"),("footer1","footer")):
            ET.SubElement(ct,"{"+typesns+"}Override",PartName="/word/"+parte+".xml",ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml."+t+"+xml")
        rootrels=ET.Element("{"+relns+"}Relationships");ET.SubElement(rootrels,"{"+relns+"}Relationship",Id="rId1",Type=NS["r"]+"/officeDocument",Target="word/document.xml")
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
            for n,no in (("[Content_Types].xml",ct),("_rels/.rels",rootrels),("word/document.xml",self.raiz),("word/styles.xml",styles),("word/settings.xml",settings),("word/header1.xml",hdr),("word/footer1.xml",ftr),("word/_rels/document.xml.rels",rels),("word/_rels/header1.xml.rels",headerrels)):z.writestr(n,xml(no))
            for i,im in enumerate(self.midias,1):z.writestr("word/media/image"+str(i)+".png",im)
        return b.getvalue()
