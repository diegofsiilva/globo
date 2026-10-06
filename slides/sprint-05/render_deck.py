"""Package a scene graph as native OOXML and render its vector PDF companion.

Fallback for a bundled Artifact Tool installation containing empty package
directories. Does not use python-pptx. No Microsoft Office automation required.
Dependencies: ReportLab, Pillow, openpyxl, all from the supplied Python runtime.
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image
from openpyxl import Workbook
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

SPEC = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[2])
ROOT = Path(SPEC["root"])
BUILD = ROOT / ".codex/slides-build"
W, H = SPEC["width"], SPEC["height"]
FONT = SPEC["font"]
BG, WHITE, GRAY, RED, BORDER = "0A0A0A", "FFFFFF", "B9B9BE", "FF1A00", "363638"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
XHDR = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

font_dir = Path("C:/Windows/Fonts")
for name, file in [("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(font_dir / file)))


def xml(value):
    return escape(str(value), {'"': "&quot;"})


def emu(value):
    return str(round(value * 9525))


def rgb(value):
    return tuple(int(value[i:i+2], 16) / 255 for i in (0, 2, 4))


def measure(value, size, bold=False):
    return pdfmetrics.stringWidth(value, "Arial-Bold" if bold else "Arial", size)


def wrap(value, width, size, bold=False):
    result = []
    for paragraph in str(value).split("\n"):
        if not paragraph:
            result.append("")
            continue
        current = ""
        for word in paragraph.split():
            test = f"{current} {word}".strip()
            if current and measure(test, size, bold) > width:
                result.append(current)
                current = word
            else:
                current = test
        result.append(current)
    return result


def fill(color):
    return '<a:noFill/>' if not color else f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'


def stroke(color=None, width=1, arrow=False):
    tail = '<a:tailEnd type="triangle" w="sm" len="sm"/>' if arrow else ""
    return f'<a:ln w="{emu(width)}">{fill(color)}<a:prstDash val="solid"/>{tail}</a:ln>'


def transform(e):
    return f'<a:xfrm><a:off x="{emu(e["x"])}" y="{emu(e["y"])}"/><a:ext cx="{emu(e["w"])}" cy="{emu(e["h"])}"/></a:xfrm>'


def props(size, color, bold=False):
    return f'<a:rPr lang="pt-BR" sz="{round(size*75)}" b="{int(bold)}">{fill(color)}<a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/></a:rPr>'


def text_body(text, size, color=WHITE, bold=False, align="left", margin=0):
    alignment = {"left": "l", "right": "r", "center": "ctr"}[align]
    paragraphs = []
    for line in str(text).split("\n"):
        paragraphs.append(f'<a:p><a:pPr algn="{alignment}"><a:lnSpc><a:spcPct val="118000"/></a:lnSpc></a:pPr><a:r>{props(size,color,bold)}<a:t xml:space="preserve">{xml(line)}</a:t></a:r><a:endParaRPr lang="pt-BR" sz="{round(size*75)}"/></a:p>')
    m = emu(margin)
    return f'<a:bodyPr wrap="square" lIns="{m}" tIns="{m}" rIns="{m}" bIns="{m}" anchor="t"><a:noAutofit/></a:bodyPr><a:lstStyle/>{"".join(paragraphs)}'


def group_tree():
    return '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'


def shape_xml(e, ident):
    typ = e["type"]
    geometry = {"text": "rect", "arrow": "line", "triangle": "triangle"}.get(typ, typ)
    xf = transform(e)
    geom = f'<a:prstGeom prst="{geometry}"><a:avLst/></a:prstGeom>'
    if typ == "triangle":
        geom = '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="w" b="h"/><a:pathLst><a:path w="100" h="100"><a:moveTo><a:pt x="0" y="0"/></a:moveTo><a:lnTo><a:pt x="100" y="50"/></a:lnTo><a:lnTo><a:pt x="0" y="100"/></a:lnTo><a:close/></a:path></a:pathLst></a:custGeom>'
    f = "" if typ == "text" else e.get("fill")
    tx = f'<p:txBody>{text_body(e["text"],e["size"],e["color"],e.get("bold",False),e.get("align","left"))}</p:txBody>' if typ == "text" else ""
    return f'<p:sp><p:nvSpPr><p:cNvPr id="{ident}" name="{xml(typ)} {ident}"/><p:cNvSpPr txBox="{int(typ=="text")}"/><p:nvPr/></p:nvSpPr><p:spPr>{xf}{geom}{fill(f)}{stroke(e.get("stroke"),e.get("sw",1),typ=="arrow")}</p:spPr>{tx}</p:sp>'


def table_xml(e, ident):
    values = [e["headers"]] + e["rows"]
    colw = [e["w"] * fraction for fraction in e["widths"]]
    rows = []
    for rowid, row in enumerate(values):
        cells = []
        for value in row:
            bg = "2A0905" if rowid == 0 else BG
            color = WHITE if rowid == 0 else GRAY
            cells.append(f'<a:tc><a:txBody>{text_body(value,e["size"],color,rowid==0,margin=0)}</a:txBody><a:tcPr marL="95250" marR="95250" marT="95250" marB="95250" anchor="t"><a:lnL>{fill(None)}</a:lnL><a:lnR>{fill(None)}</a:lnR><a:lnT>{fill(None)}</a:lnT><a:lnB w="9525">{fill(BORDER)}<a:prstDash val="solid"/></a:lnB>{fill(bg)}</a:tcPr></a:tc>')
        rows.append(f'<a:tr h="{emu(e["rowHeight"])}">{"".join(cells)}</a:tr>')
    grid = ''.join(f'<a:gridCol w="{emu(w)}"/>' for w in colw)
    return f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{ident}" name="Tabela {ident}"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="{emu(e["x"])}" y="{emu(e["y"])}"/><a:ext cx="{emu(e["w"])}" cy="{emu(e["h"])}"/></p:xfrm><a:graphic><a:graphicData uri="{A}/table"><a:tbl><a:tblPr firstRow="1" bandRow="0"><a:tableStyleId>{{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}}</a:tableStyleId></a:tblPr><a:tblGrid>{grid}</a:tblGrid>{"".join(rows)}</a:tbl></a:graphicData></a:graphic></p:graphicFrame>'


def relationship(ident, target, typ):
    return f'<Relationship Id="{ident}" Type="{R}/{typ}" Target="{xml(target)}"/>'


def rels(items):
    return XHDR + f'<Relationships xmlns="{REL}">{"".join(items)}</Relationships>'


def chart_xml(e, number):
    cats, vals = e["categories"], e["values"]
    maximum = e.get("max") or max(vals)*1.2
    def rich(size=20):
        return f'<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{round(size*75)}">{fill(GRAY)}<a:latin typeface="Arial"/></a:defRPr></a:pPr><a:endParaRPr lang="pt-BR"/></a:p></c:txPr>'
    n=len(vals)
    catcache=''.join(f'<c:pt idx="{i}"><c:v>{xml(v)}</c:v></c:pt>' for i,v in enumerate(cats))
    valcache=''.join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i,v in enumerate(vals))
    ser=f'<c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:strRef><c:f>Data!$B$1</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{xml(e["seriesName"])}</c:v></c:pt></c:strCache></c:strRef></c:tx><c:spPr>{fill(RED)}{stroke(None)}</c:spPr><c:cat><c:strRef><c:f>Data!$A$2:$A${n+1}</c:f><c:strCache><c:ptCount val="{n}"/>{catcache}</c:strCache></c:strRef></c:cat><c:val><c:numRef><c:f>Data!$B$2:$B${n+1}</c:f><c:numCache><c:formatCode>0</c:formatCode><c:ptCount val="{n}"/>{valcache}</c:numCache></c:numRef></c:val></c:ser>'
    cat_axis=f'<c:catAx><c:axId val="1001"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="b"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr>{stroke(BORDER)}</c:spPr>{rich()}<c:crossAx val="1002"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/></c:catAx>'
    val_axis=f'<c:valAx><c:axId val="1002"/><c:scaling><c:orientation val="minMax"/><c:max val="{maximum}"/><c:min val="0"/></c:scaling><c:delete val="0"/><c:axPos val="l"/><c:majorGridlines><c:spPr>{stroke(BORDER)}</c:spPr></c:majorGridlines><c:numFmt formatCode="0&quot; {xml(e["unit"])}&quot;" sourceLinked="0"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr>{stroke(BORDER)}</c:spPr>{rich(18)}<c:crossAx val="1001"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>'
    labels=f'<c:dLbls>{rich(23)}<c:dLblPos val="outEnd"/><c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/><c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>'
    return XHDR+f'<c:chartSpace xmlns:c="{C}" xmlns:a="{A}" xmlns:r="{R}"><c:date1904 val="0"/><c:lang val="pt-BR"/><c:roundedCorners val="0"/><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/><c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/>{ser}{labels}<c:gapWidth val="100"/><c:axId val="1001"/><c:axId val="1002"/></c:barChart>{cat_axis}{val_axis}<c:spPr>{fill(BG)}{stroke(None)}</c:spPr></c:plotArea><c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart><c:spPr>{fill(BG)}{stroke(None)}</c:spPr>{rich()}<c:externalData r:id="rIdWorkbook"><c:autoUpdate val="0"/></c:externalData></c:chartSpace>'


def graphic_chart(e, ident, rid):
    return f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{ident}" name="Gráfico editável {ident}"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="{emu(e["x"])}" y="{emu(e["y"])}"/><a:ext cx="{emu(e["w"])}" cy="{emu(e["h"])}"/></p:xfrm><a:graphic><a:graphicData uri="{C}"><c:chart xmlns:c="{C}" xmlns:r="{R}" r:id="{rid}"/></a:graphicData></a:graphic></p:graphicFrame>'


def image_xml(e, ident, rid):
    return f'<p:pic><p:nvPicPr><p:cNvPr id="{ident}" name="Captura original" descr="Captura histórica da interface Argus"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>{transform(e)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'


def make_pptx(destination):
    parts={}
    overrides=[]
    def add(name, content, kind=None):
        parts[name]=content.encode("utf-8") if isinstance(content,str) else content
        if kind: overrides.append(f'<Override PartName="/{name}" ContentType="{kind}"/>')
    prefix="application/vnd.openxmlformats-officedocument."
    theme_colors=[('dk1',BG),('lt1',WHITE),('dk2','171719'),('lt2',GRAY),('accent1',RED),('accent2','820000'),('accent3','C0C0C0'),('accent4','808080'),('accent5','555555'),('accent6','AAAAAA'),('hlink',RED),('folHlink','CC1100')]
    scheme=''.join(f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>' for k,v in theme_colors)
    fonts=''.join(f'<a:{k}><a:latin typeface="Arial"/><a:ea typeface="Arial"/><a:cs typeface="Arial"/></a:{k}>' for k in ('majorFont','minorFont'))
    styles=f'<a:fmtScheme name="Argus"><a:fillStyleLst>{fill(WHITE)*3}</a:fillStyleLst><a:lnStyleLst>{stroke(BORDER)*3}</a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst>{fill(BG)*3}</a:bgFillStyleLst></a:fmtScheme>'
    add('ppt/theme/theme1.xml',XHDR+f'<a:theme xmlns:a="{A}" name="Argus"><a:themeElements><a:clrScheme name="Argus">{scheme}</a:clrScheme><a:fontScheme name="Arial">{fonts}</a:fontScheme>{styles}</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>',prefix+'theme+xml')
    cmap='<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    add('ppt/slideMasters/slideMaster1.xml',XHDR+f'<p:sldMaster xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{group_tree()}</p:spTree></p:cSld>{cmap}<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rIdLayout"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>',prefix+'presentationml.slideMaster+xml')
    add('ppt/slideMasters/_rels/slideMaster1.xml.rels',rels([relationship('rIdLayout','../slideLayouts/slideLayout1.xml','slideLayout'),relationship('rIdTheme','../theme/theme1.xml','theme')]))
    add('ppt/slideLayouts/slideLayout1.xml',XHDR+f'<p:sldLayout xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" type="blank" preserve="1"><p:cSld name="Argus blank"><p:spTree>{group_tree()}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>',prefix+'presentationml.slideLayout+xml')
    add('ppt/slideLayouts/_rels/slideLayout1.xml.rels',rels([relationship('rIdMaster','../slideMasters/slideMaster1.xml','slideMaster')]))
    add('ppt/notesMasters/notesMaster1.xml',XHDR+f'<p:notesMaster xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{group_tree()}</p:spTree></p:cSld>{cmap}<p:notesStyle/></p:notesMaster>',prefix+'presentationml.notesMaster+xml')
    add('ppt/notesMasters/_rels/notesMaster1.xml.rels',rels([relationship('rIdTheme','../theme/theme1.xml','theme')]))
    chart_number=0
    image_number=0
    presentation_rels=[relationship('rIdMaster','slideMasters/slideMaster1.xml','slideMaster'),relationship('rIdNotesMaster','notesMasters/notesMaster1.xml','notesMaster'),relationship('rIdTheme','theme/theme1.xml','theme')]
    for num,s in enumerate(SPEC['slides'],1):
        parts_slide=[]
        sr=[relationship('rIdLayout','../slideLayouts/slideLayout1.xml','slideLayout'),relationship('rIdNotes',f'../notesSlides/notesSlide{num}.xml','notesSlide')]
        for ident,e in enumerate(s['elements'],2):
            if e['type']=='table': parts_slide.append(table_xml(e,ident))
            elif e['type']=='chart':
                chart_number+=1;rid=f'rIdChart{chart_number}'
                sr.append(relationship(rid,f'../charts/chart{chart_number}.xml','chart'))
                parts_slide.append(graphic_chart(e,ident,rid))
                add(f'ppt/charts/chart{chart_number}.xml',chart_xml(e,chart_number),prefix+'drawingml.chart+xml')
                add(f'ppt/charts/_rels/chart{chart_number}.xml.rels',rels([relationship('rIdWorkbook',f'../embeddings/data{chart_number}.xlsx','package')]))
                wb=Workbook();ws=wb.active;ws.title='Data';ws.append(['Categoria',e['seriesName']])
                for cat,val in zip(e['categories'],e['values']):ws.append([cat,val])
                stream=io.BytesIO();wb.save(stream);add(f'ppt/embeddings/data{chart_number}.xlsx',stream.getvalue(),prefix+'spreadsheetml.sheet')
            elif e['type']=='image':
                image_number+=1;rid=f'rIdImage{image_number}'
                sr.append(relationship(rid,f'../media/image{image_number}.png','image'))
                add(f'ppt/media/image{image_number}.png',(ROOT/e['path']).read_bytes());parts_slide.append(image_xml(e,ident,rid))
            else:parts_slide.append(shape_xml(e,ident))
        add(f'ppt/slides/slide{num}.xml',XHDR+f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld name="{xml(s["title"])}"><p:bg><p:bgPr>{fill(BG)}<a:effectLst/></p:bgPr></p:bg><p:spTree>{group_tree()}{"".join(parts_slide)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>',prefix+'presentationml.slide+xml')
        add(f'ppt/slides/_rels/slide{num}.xml.rels',rels(sr))
        ne={'type':'text','x':40,'y':100,'w':640,'h':500,'text':s['notes'],'size':16,'color':'000000'}
        nx=shape_xml(ne,2).replace('<p:nvPr/>','<p:nvPr><p:ph type="body" idx="1"/></p:nvPr>')
        add(f'ppt/notesSlides/notesSlide{num}.xml',XHDR+f'<p:notes xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{group_tree()}{nx}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>',prefix+'presentationml.notesSlide+xml')
        add(f'ppt/notesSlides/_rels/notesSlide{num}.xml.rels',rels([relationship('rIdNotesMaster','../notesMasters/notesMaster1.xml','notesMaster'),relationship('rIdSlide',f'../slides/slide{num}.xml','slide')]))
        presentation_rels.append(relationship(f'rIdSlide{num}',f'slides/slide{num}.xml','slide'))
    slide_ids=''.join(f'<p:sldId id="{256+i}" r:id="rIdSlide{i}"/>' for i in range(1,len(SPEC['slides'])+1))
    add('ppt/presentation.xml',XHDR+f'<p:presentation xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdMaster"/></p:sldMasterIdLst><p:notesMasterIdLst><p:notesMasterId r:id="rIdNotesMaster"/></p:notesMasterIdLst><p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx="{emu(W)}" cy="{emu(H)}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle/></p:presentation>',prefix+'presentationml.presentation.main+xml')
    add('ppt/_rels/presentation.xml.rels',rels(presentation_rels))
    add('docProps/core.xml',XHDR+'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Argus — Sprint 05</dc:title><dc:creator>G04 — Vale a Pena Ver de Novo</dc:creator><dc:description>Telemetria para diagnóstico de degradação de streaming. Corte 06/10/2026.</dc:description></cp:coreProperties>','application/vnd.openxmlformats-package.core-properties+xml')
    add('docProps/app.xml',XHDR+f'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Argus presentation builder</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>{len(SPEC["slides"])}</Slides><Notes>{len(SPEC["slides"])}</Notes></Properties>',prefix+'extended-properties+xml')
    add('_rels/.rels',XHDR+f'<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="{R}/extended-properties" Target="docProps/app.xml"/></Relationships>')
    add('[Content_Types].xml',XHDR+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'+''.join(overrides)+'</Types>')
    with ZipFile(destination,'w',ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)


fit_warnings=[]


def pdf_text(c,text,x,y,w,h,size,color=WHITE,bold=False,align='left',slide_num=0):
    lines=wrap(text,w,size,bold)
    actual=len(lines)*size*1.18
    if actual>h+2:
        fit_warnings.append({'slide':slide_num,'text':text,'needed':round(actual,1),'height':h})
    c.setFillColorRGB(*rgb(color));c.setFont('Arial-Bold' if bold else 'Arial',size)
    for i,value in enumerate(lines):
        baseline=H-y-size*.91-i*size*1.18
        if align=='center':c.drawCentredString(x+w/2,baseline,value)
        elif align=='right':c.drawRightString(x+w,baseline,value)
        else:c.drawString(x,baseline,value)


def make_pdf(destination):
    c=canvas.Canvas(str(destination),pagesize=(W*.75,H*.75),pageCompression=1)
    c.setTitle('Argus — Sprint 05');c.setAuthor('G04 — Vale a Pena Ver de Novo')
    for slide_num,s in enumerate(SPEC['slides'],1):
        c.scale(.75,.75)
        c.setFillColorRGB(*rgb(BG));c.rect(0,0,W,H,fill=1,stroke=0)
        for e in s['elements']:
            typ=e['type'];x,y,w,h=[e[k] for k in ('x','y','w','h')]
            if typ=='text':pdf_text(c,e['text'],x,y,w,h,e['size'],e['color'],e.get('bold',False),e.get('align','left'),slide_num)
            elif typ=='image':c.drawImage(ImageReader(str(ROOT/e['path'])),x,H-y-h,w,h,mask='auto')
            elif typ=='table':
                widths=[w*v for v in e['widths']]
                for row_index,row in enumerate([e['headers']]+e['rows']):
                    cy=y+row_index*e['rowHeight'];cx=x
                    if row_index==0:c.setFillColorRGB(*rgb('2A0905'));c.rect(x,H-cy-e['rowHeight'],w,e['rowHeight'],fill=1,stroke=0)
                    c.setStrokeColorRGB(*rgb(BORDER));c.setLineWidth(1);c.line(x,H-cy-e['rowHeight'],x+w,H-cy-e['rowHeight'])
                    for value,cw in zip(row,widths):
                        pdf_text(c,value,cx+10,cy+10,cw-20,e['rowHeight']-20,e['size'],WHITE if row_index==0 else GRAY,row_index==0,slide_num=slide_num);cx+=cw
            elif typ=='chart':
                maximum=e.get('max') or max(e['values'])*1.2
                px,py,pw,ph=x+75,y+20,w-92,h-83
                c.setFont('Arial',19)
                for i in range(6):
                    val=maximum*i/5;gy=H-py-ph+ph*i/5
                    c.setStrokeColorRGB(*rgb(BORDER));c.setLineWidth(1);c.line(px,gy,px+pw,gy)
                    c.setFillColorRGB(*rgb(GRAY));c.drawRightString(px-12,gy-6,f'{val:g} {e["unit"]}')
                cell=pw/len(e['values'])
                for i,(category,value) in enumerate(zip(e['categories'],e['values'])):
                    bx=px+cell*i+cell*.22;bh=ph*value/maximum;bw=cell*.56
                    c.setFillColorRGB(*rgb(RED));c.rect(bx,H-py-ph,bw,bh,fill=1,stroke=0)
                    c.setFillColorRGB(*rgb(WHITE));c.setFont('Arial-Bold',24);c.drawCentredString(bx+bw/2,H-py-ph+bh+12,str(value))
                    c.setFillColorRGB(*rgb(GRAY));c.setFont('Arial',21);c.drawCentredString(bx+bw/2,H-py-ph-32,category)
            elif typ in ('line','arrow'):
                c.setStrokeColorRGB(*rgb(e.get('stroke') or BORDER));c.setLineWidth(e.get('sw',1));c.line(x,H-y,x+w,H-y-h)
                if typ=='arrow':
                    c.setFillColorRGB(*rgb(e.get('stroke') or RED));p=c.beginPath();p.moveTo(x+w,H-y);p.lineTo(x+w-8,H-y+4);p.lineTo(x+w-8,H-y-4);p.close();c.drawPath(p,fill=1,stroke=0)
            else:
                c.setFillColorRGB(*rgb(e.get('fill') or BG));c.setStrokeColorRGB(*rgb(e.get('stroke') or BG));c.setLineWidth(e.get('sw',1))
                if typ=='ellipse':c.ellipse(x,H-y-h,x+w,H-y,fill=1,stroke=bool(e.get('stroke')))
                elif typ=='triangle':
                    p=c.beginPath();p.moveTo(x,H-y);p.lineTo(x+w,H-y-h/2);p.lineTo(x,H-y-h);p.close();c.drawPath(p,fill=1,stroke=0)
                else:c.rect(x,H-y-h,w,h,fill=1,stroke=bool(e.get('stroke')))
        c.showPage()
    c.save()


OUT.mkdir(parents=True,exist_ok=True)
make_pptx(OUT/'Argus-Sprint-05.pptx')
make_pdf(OUT/'Argus-Sprint-05.pdf')
(BUILD/'text-fit.json').write_text(json.dumps(fit_warnings,indent=2,ensure_ascii=False),encoding='utf-8')
print(f'PPTX and PDF exported, {len(fit_warnings)} text fit warnings.')
if fit_warnings:
    for warning in fit_warnings:print(warning)
