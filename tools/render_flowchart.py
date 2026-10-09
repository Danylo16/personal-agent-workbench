"""Generate matching Mermaid topology, SVG and PDF from one German graph definition.
Optional authoring dependencies: reportlab, cairosvg. App itself does not need them.
No Node or Mermaid renderer required; SVG/PDF use an explicit readable layout.
"""
from pathlib import Path
import os
from html import escape
import math
import textwrap
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

OUT=Path(__file__).resolve().parents[1]/'flowchart'
OUT.mkdir(exist_ok=True)
W,H=595,842
# id, title, detail, kind, column, row
PAGES=[
('01 / Anfrage und Berechtigung','Kunde · E-Commerce-Plattform · OMS',[
('A','START · Adressänderung anfragen','Kunde → Plattform: Bestellnummer und neue Adresse','start',0,0),
('B','Anfrage registrieren','Idempotenzschlüssel; Duplikat → bisherigen Status liefern','auto',0,1),
('C','Bestellung im OMS vorhanden?','Ohne Daten anderer Kunden offenzulegen','decision',0,2),
('D','Identität und Rechte bestätigt?','Authentifizierte Sitzung / sichere Verifikation','decision',0,3),
('E','Neue Adresse zulässig?','Format, Zustellgebiet, Steuern, Betrug / Mehrkosten','decision',0,4),
('F','OMS- und WMS-Status abrufen','Version, Label, Übergabe; Timeout → Support','auto',0,5),
('G','Bereits an Carrier übergeben?','Status ist Momentaufnahme; auf Seite 2 erneut prüfen','decision',0,6),
('H','NEIN → Fortsetzung Seite 2','Versand vor Änderung gegen Parallelzugriff sperren','connector',0,7),
('R1','Kein Auftrag / keine Rechte','Neutral informieren, auditieren; ENDE ohne Änderung','exception',1,2),
('R2','Regeln nicht erfüllt','Korrektur anfordern oder Support; keine Zusage','exception',1,4),
('R3','Unklarer Systemstatus','Supportfall; Kunde erhält Zwischenmeldung','exception',1,5),
('R4','JA → Seite 3','Nur bestätigte Carrier-Umleitung prüfen','connector',1,6),
], [('A','B',''),('B','C',''),('C','D','Ja'),('C','R1','Nein'),('D','E','Ja'),('D','R1','Nein'),('E','F','Ja'),('E','R2','Nein'),('F','G','OK'),('F','R3','Fehler'),('G','H','Nein'),('G','R4','Ja')],
'Entscheidungen mit „?“ · Blau: automatisch · Orange: manuell / Ausnahme'),
('02 / Vor Versand: sicher synchronisieren','OMS · WMS · Plattform · Benachrichtigungsdienst',[
('I','WMS-Hold atomar anfordern','Mit Version/Status-Bedingung; Label/Übergabe sperren','auto',0,0),
('J','WMS bestätigt sichere Sperre?','Auch Label-Neudruck und ausstehende Jobs absichern','decision',0,1),
('K','Status + Version erneut prüfen','OMS/WMS-Abgleich unter Hold; stale → nicht schreiben','auto',0,2),
('L','OMS bedingt aktualisieren','Compare-and-swap + Outbox + Audit in einer Transaktion','auto',0,3),
('M','WMS / Plattform synchronisieren','Idempotent auf neue Version; alte Label invalidieren','auto',0,4),
('N','Alle nötigen Bestätigungen da?','Adresse, Version und Label prüfen; HTTP 200 allein reicht nicht','decision',0,5),
('O','Hold kontrolliert freigeben','Nur neue Version darf Label / Übergabe erzeugen','auto',0,6),
('P','ERFOLG · Kunde informieren','Bestätigte Adresse + Audit; Benachrichtigung idempotent','success',0,7),
('S1','Hold abgelehnt / Versand läuft','Kein blindes Update; Übergabe → S. 3, sonst Support','exception',1,1),
('S2','Konflikt / unklare Antwort','Hold-Status klären; Support übernimmt Abgleich','exception',1,3),
('S3','Fehler / Timeout / Teilzustand','Hold behalten bzw. Versand stoppen; Support abgleichen','exception',1,5),
('S4','Weiter unklar → Support','Kunde: „in Prüfung“; kein Erfolg bis Abgleich bestätigt','exception',1,6),
], [('I','J',''),('J','K','Ja'),('J','S1','Nein'),('K','L','Gültig'),('K','S2','Konflikt'),('L','M','Commit'),('L','S2','Fehler'),('M','N',''),('N','O','Ja'),('N','S3','Nein'),('S3','S4','Keine Klärung'),('O','P','Bestätigt'),('O','S4','Fehler')],
'Hold muss Versand wirklich blockieren. Ohne garantierte WMS-Sperre: manuell eskalieren.'),
('03 / Nach Übergabe und manuelle Fälle','Carrier · Kundensupport · OMS · Benachrichtigungsdienst',[
('T','Carrier-Umleitung anfragen','Nur unterstützte Änderungen; Anfrage idempotent referenzieren','auto',0,0),
('U','Carrier bestätigt neue Zieladresse?','Kein Erfolg bei „angenommen“ oder ausstehender Prüfung','decision',0,1),
('V','Bestätigung im OMS dokumentieren','Umleitung separat speichern; alte Versandhistorie erhalten','auto',0,2),
('W','ERFOLG · Kunde benachrichtigen','Bestätigte Umleitung + Einschränkungen; Audit abschließen','success',0,3),
('X','Support: Zustand rekonstruieren','OMS, WMS, Carrier abgleichen; Versand / Gebühren klären','manual',0,5),
('Y','Sichere Lösung möglich?','Kein Rollback ohne Prüfung des realen Versandzustands','decision',0,6),
('Z','Manuell lösen + prüfen + melden','Bestätigte Lösung oder begründete Ablehnung; Audit; ENDE','manual',0,7),
('T1','Abgelehnt / nicht möglich','Support: Alternativen, Rücksendung oder Neubestellung','exception',1,1),
('T2','Timeout / noch ausstehend','Statusabgleich / verifizierter Webhook; Zwischenmeldung','exception',1,2),
('T3','Ausnahmefälle von Seite 1/2','Kein automatisches Erfolgsversprechen','connector',1,5),
], [('T','U',''),('U','V','Ja'),('U','T1','Nein'),('U','T2','Unklar'),('T2','X','Ungeklärt'),('T1','X',''),('V','W','Gespeichert'),('V','X','Fehler'),('T3','X',''),('X','Y',''),('Y','Z','Ja / Nein')],
'Wahrscheinlichster Fehler: WMS erzeugt ein Label mit alter Adresse zwischen Prüfung und Update.')]
COLORS={'auto':'#eef4fc','decision':'#dceafb','start':'#e3eaf4','success':'#dff2e9','exception':'#fff0dd','manual':'#fff0dd','connector':'#edf0f3'}

pdfmetrics.registerFont(TTFont('DejaVu', os.getenv('DIAGRAM_FONT_REGULAR', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVu-Bold', os.getenv('DIAGRAM_FONT_BOLD', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')))
font='DejaVu'

def box_geometry(n):
    _,_,_,_,col,row=n
    return (34 if col==0 else 407, 136+row*75, 324 if col==0 else 154, 55)

def wrapped(text,maxchars):
    return textwrap.wrap(text,maxchars,break_long_words=False,break_on_hyphens=False)

pdf=canvas.Canvas(str(OUT/'address_change.pdf'),pagesize=(W,H))
pdf.setTitle('Adressänderung nach Bestellung — Prozess und Ausnahmen')
pdf.setAuthor('Danylo Zubrii')
svgpages=[]
mmd=['flowchart TB']
for pageidx,(title,subtitle,nodes,edges,note) in enumerate(PAGES):
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<rect width="595" height="842" fill="white"/>']
    def text(x,y,value,size=10,color='#172b46',bold=False):
        pdf.setFillColor(HexColor(color));pdf.setFont('DejaVu-Bold' if bold else font,size);pdf.drawString(x,H-y,value)
        svg.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(value)}</text>')
    def line(points,color='#5e7188'):
        pdf.setStrokeColor(HexColor(color));pdf.setLineWidth(.85)
        path=pdf.beginPath();path.moveTo(points[0][0],H-points[0][1])
        for x,y in points[1:]:path.lineTo(x,H-y)
        pdf.drawPath(path)
        coords=' '.join(f'{x},{y}' for x,y in points)
        svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width=".85"/>')
        a,b=points[-2],points[-1];theta=math.atan2(b[1]-a[1],b[0]-a[0]);
        tip=[b,(b[0]-5*math.cos(theta-.5),b[1]-5*math.sin(theta-.5)),(b[0]-5*math.cos(theta+.5),b[1]-5*math.sin(theta+.5)),b]
        pdfpath=pdf.beginPath();pdfpath.moveTo(tip[0][0],H-tip[0][1])
        for x,y in tip[1:]:pdfpath.lineTo(x,H-y)
        pdf.setFillColor(HexColor(color));pdf.drawPath(pdfpath,fill=1,stroke=0)
        svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in tip)+'" fill="'+color+'"/>')
    text(34,39,'ADRESSÄNDERUNG NACH BESTELLUNG',12,bold=True)
    text(34,73,title,18,bold=True)
    text(34,95,subtitle,10)
    text(34,117,'AUTOMATISIERTER ABLAUF / ENTSCHEIDUNGEN',8,bold=True)
    text(407,117,'AUSNAHMEN / SUPPORT',8,bold=True)
    byid={n[0]:n for n in nodes}
    # Draw local edges first, never hidden behind text.
    for src,dst,label in edges:
        s,d=byid[src],byid[dst];sx,sy,sw,sh=box_geometry(s);dx,dy,dw,dh=box_geometry(d)
        if s[4]==d[4] and d[5]>s[5]:
            if d[5]==s[5]+1:
                points=[(sx+sw/2,sy+sh),(dx+dw/2,dy)]
            else:
                points=[(sx,sy+sh/2),(sx-12,sy+sh/2),(sx-12,dy+dh/2),(dx,dy+dh/2)]
            lx,ly=(sx+sw/2+5,sy+sh+12) if d[5]==s[5]+1 else (2,sy+sh+12)
        elif s[4]==0 and d[4]==1:
            offset=14 if (src,dst)==('U','T2') else 0
            points=[(sx+sw,sy+sh/2+offset),(dx-10,sy+sh/2+offset),(dx-10,dy+dh/2),(dx,dy+dh/2)]
            lx,ly=sx+sw+5,sy+sh/2+offset-5
        else:
            # Right branch joins left via the left margin; avoid crossing nodes.
            points=[(sx+sw/2,sy+sh),(sx+sw/2,sy+sh+10),(390,sy+sh+10),(390,dy+dh/2),(dx+dw,dy+dh/2)]
            lx,ly=360,sy+sh+20
        line(points)
        if label:text(lx,ly,label,7,color='#576a82')
    mmd.append(f'subgraph PH{pageidx+1}["{title}"]')
    mmd.append('direction TB')
    for n in nodes:
        nid,ttl,detail,kind,col,row=n;x,y,w,h=box_geometry(n)
        fill=COLORS[kind]
        pdf.setFillColor(HexColor(fill));pdf.setStrokeColor(HexColor('#9baec6'));pdf.roundRect(x,H-y-h,w,h,7,fill=1,stroke=1)
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="#9baec6"/>')
        titlelines=wrapped(ttl,44 if col==0 else 22)
        detaillin=wrapped(detail,58 if col==0 else 27)
        total=len(titlelines)+len(detaillin)
        size=9 if col==0 else 8
        step=10 if total<=5 else 8.3
        yy=y+(h-total*step)/2+8
        for v in titlelines:text(x+9,yy,v,size,bold=True);yy+=step
        for v in detaillin:text(x+9,yy,v,size-1,color='#415773');yy+=step
        label=f'{ttl} / {detail}'.replace('"',"'")
        mmd.append(f'{nid}{{"{label}"}}' if kind=='decision' else f'{nid}["{label}"]')
    for a,b,l in edges:mmd.append(f'{a} -->'+(f'|"{l}"|' if l else '')+f' {b}')
    mmd.append('end')
    text(34,778,note[:100],8,bold=True)
    if len(note)>100:text(34,790,note[100:],8,bold=True)
    text(34,815,'Konzeptioneller Prozess · Integrationen nicht Teil der Python-App',8,color='#64748b')
    text(510,815,f'{pageidx+1} / 3',8)
    svg.append('</svg>'); svgpages.append(''.join(svg));pdf.showPage()
pdf.save()
mmd+=['H --> I','R4 --> T','R2 --> X','R3 --> X','S1 --> X','S2 --> X','S4 --> X','classDef automatic fill:#eef4fc,stroke:#9baec6','classDef human fill:#fff0dd,stroke:#d8a761']
for _,_,nodes,_,_ in PAGES:
    for n in nodes:
        if n[3] in ('exception','manual'):mmd.append(f'class {n[0]} human')
        elif n[3]=='auto':mmd.append(f'class {n[0]} automatic')
(OUT/'address_change.mmd').write_text('\n'.join(mmd)+'\n',encoding='utf-8')
for i,s in enumerate(svgpages,1):(OUT/f'address_change_{i}.svg').write_text(s,encoding='utf-8')
combined=f'<svg xmlns="http://www.w3.org/2000/svg" width="595" height="{3*H}" viewBox="0 0 595 {3*H}">'
for i,s in enumerate(svgpages):combined+=f'<g transform="translate(0,{i*H})">'+s.split('>',1)[1].rsplit('</svg>',1)[0]+'</g>'
combined+='</svg>'
(OUT/'address_change.svg').write_text(combined,encoding='utf-8')
try:
    import cairosvg
    for i,s in enumerate(svgpages,1):cairosvg.svg2png(bytestring=s.encode(),write_to=str(OUT/f'address_change_{i}.png'),scale=2)
except ImportError:
    print('Install cairosvg or use pdftoppm for PNGs.')
print('Created Mermaid, SVG and 3-page PDF from the same graph topology.')
