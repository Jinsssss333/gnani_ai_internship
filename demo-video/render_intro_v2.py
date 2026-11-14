"""75-second, ten-shot SunoCare intro; original script and supplied Gnani artwork.

Local cutout/motion graphics, not generated action footage. No clips are reused.
Run --preview first. Assets live under output/v2/assets (see README).
"""
from pathlib import Path
from functools import lru_cache
import argparse
import ast
import json
import math
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output' / 'v2'
ASSETS = OUT / 'assets'
OUT.mkdir(parents=True, exist_ok=True)
W, H, FPS, DURATION = 1920, 1080, 24, 75
INK, CREAM, LIME, AMBER = '#1F2A22', '#F5F3E8', '#D9EFA5', '#FFE2A0'
MUTED, LINE = '#627061', '#CBD1BF'

# Read the original script as data; importing the old renderer would run it.
tree = ast.parse((ROOT / 'animate_character.py').read_text(encoding='utf-8'))
SCRIPT = next(ast.literal_eval(n.value) for n in tree.body
              if isinstance(n, ast.Assign) and any(isinstance(v, ast.Name) and v.id == 'script' for v in n.targets))
prisma, rest = SCRIPT[4].split('while Timbre', 1)
timbre, languages = ('while Timbre' + rest).split('The current', 1)
TEXT = SCRIPT[:4] + [prisma.strip(), timbre.strip(), 'The current' + languages] + SCRIPT[5:]
LENGTHS = [6.8, 12, 10, 12, 5.7, 4.8, 4.5, 8, 6, 5.2]
TITLES = ['A familiar way to report', 'After the household visit', 'Just a cellular call',
          'Guided from start to finish', 'Speech becomes text', 'Text becomes a voice',
          'Speak in a familiar language', 'From call to saved record',
          'A starting point for easier access', 'Next: the live demonstration']
assert ' '.join(' '.join(TEXT).split()) == ' '.join(' '.join(SCRIPT).split())
assert abs(sum(LENGTHS) - DURATION) < .001
STARTS = [sum(LENGTHS[:i]) for i in range(len(LENGTHS))]

@lru_cache(None)
def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/segoeui' + ('b' if bold else '') + '.ttf', size)

def ease(x):
    x = max(0, min(1, x))
    return 1 - (1 - x) ** 3

def wrap(text, size, width):
    d = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if d.textlength(trial, font=font(size)) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]

def text(d, xy, value, size=36, bold=False, fill=INK, width=None, gap=12):
    lines = wrap(value, size, width) if width else [value]
    for j, line in enumerate(lines):
        d.text((xy[0], xy[1] + j * (size + gap)), line, font=font(size, bold), fill=fill)

def box(d, xy, fill='white', radius=24, shadow=True):
    if shadow:
        d.rounded_rectangle(tuple(v + (8 if k % 2 == 0 else 10) for k, v in enumerate(xy)), radius, fill=INK)
    d.rounded_rectangle(xy, radius, fill=fill, outline=INK, width=2)

def arrow(d, start, end, progress=1, color=INK, width=5):
    x, y = start
    ex = x + (end[0] - x) * ease(progress)
    ey = y + (end[1] - y) * ease(progress)
    d.line((x, y, ex, ey), fill=color, width=width)
    if progress >= 1:
        angle = math.atan2(end[1] - y, end[0] - x)
        pts = [(ex, ey)] + [(ex - 18 * math.cos(angle + a), ey - 18 * math.sin(angle + a)) for a in (-.5, .5)]
        d.polygon(pts, fill=color)

def check(d, x, y, p=1, scale=1):
    pts = [(x, y), (x + 18 * scale, y + 20 * scale), (x + 58 * scale, y - 27 * scale)]
    if p > .3:
        d.line(pts[:2], fill=INK, width=max(3, int(7 * scale)))
    if p > .6:
        d.line(pts[1:], fill=INK, width=max(3, int(7 * scale)))

def wave(d, x, y, t, color=INK, count=23, spacing=14, height=55):
    for j in range(count):
        amp = 8 + height * abs(math.sin(t * 3.7 + j * .49)) * math.sin((j + 1) / (count + 1) * math.pi)
        d.rounded_rectangle((x + j * spacing, y - amp, x + j * spacing + 6, y + amp), 3, fill=color)

def phone(d, x, y, scale=1, active=None, screen='SunoCare'):
    def r(a): return (x + a[0]*scale, y+a[1]*scale, x+a[2]*scale, y+a[3]*scale)
    d.rounded_rectangle(r((0, 0, 235, 465)), int(30*scale), fill=INK)
    d.rounded_rectangle(r((20, 55, 215, 200)), int(8*scale), fill=LIME)
    text(d, (x+36*scale,y+93*scale), screen, int(26*scale), True)
    d.line((x+90*scale,y+26*scale,x+145*scale,y+26*scale), fill=CREAM,width=3)
    for j, label in enumerate('123456789*0#'):
        col, row = j%3,j//3
        xx,yy=20+col*67,224+row*54
        d.rounded_rectangle(r((xx, yy, xx+60, yy+46)), int(8*scale),fill=AMBER if label==active else '#485548')
        text(d,(x+(xx+22)*scale,y+(yy+5)*scale),label,int(24*scale),True,INK if label==active else 'white')

def house(d, x, y, scale=1):
    d.polygon([(x,y+110*scale),(x+150*scale,y),(x+300*scale,y+110*scale)],fill=AMBER,outline=INK)
    d.rectangle((x+30*scale,y+110*scale,x+270*scale,y+310*scale),fill='#ECE8D8',outline=INK,width=3)
    d.rounded_rectangle((x+110*scale,y+175*scale,x+180*scale,y+310*scale),8,fill='#8E9F65',outline=INK,width=2)
    d.rectangle((x+52*scale,y+150*scale,x+93*scale,y+200*scale),fill='white',outline=INK,width=2)

ACTOR = Image.open(ASSETS/'asha_cutout.png').convert('RGBA')
ACTOR.putalpha(ACTOR.getchannel('A').point(lambda a: 255 if a > 220 else 0))
ACTOR = ACTOR.crop(ACTOR.getbbox())
@lru_cache(32)
def actor_size(height):
    return ACTOR.resize((round(ACTOR.width * height / ACTOR.height), height), Image.Resampling.LANCZOS)

def actor(im, x, y, height, tilt=0):
    a = actor_size(height)
    if tilt:
        a = a.rotate(tilt, Image.Resampling.BICUBIC, expand=True)
    im.paste(a, (int(x), int(y)), a)

screens = {name: Image.open(ASSETS/(name+'.png')).convert('RGB') for name in ('prisma','timbre')}
screens = {key: value.resize((round(value.width*620/value.height),620),Image.Resampling.LANCZOS)
           for key,value in screens.items()}

@lru_cache(10)
def background(i):
    im = Image.new('RGB', (W,H), CREAM)
    # Blur masks, not unpremultiplied RGBA colors, to avoid gray fringes.
    for bounds,color in [((1250,-320,2200,570),'#DAEEFC' if i%2==0 else '#FFE9D0'),
                         ((-320,470,470,1100),'#E6EECF')]:
        mask=Image.new('L',(W,H))
        ImageDraw.Draw(mask).ellipse(bounds,fill=255)
        im.paste(Image.new('RGB',(W,H),color),(0,0),mask.filter(ImageFilter.GaussianBlur(130)))
    return im

def subtitle(d, i, local):
    words=TEXT[i].split()
    # Phrase-sized captions preserve every word and give the art breathing room.
    groups=[words[j:j+12] for j in range(0,len(words),12)]
    used=0
    for group in groups:
        end=(used+len(group))/len(words)*LENGTHS[i]
        if local < end:
            label=' '.join(group)
            break
        used+=len(group)
    else: label=' '.join(groups[-1])
    lines=wrap(label,34,1580)
    for j,line in enumerate(lines):
        width=d.textlength(line,font=font(34))
        text(d,((W-width)/2,928+j*44),line,34)

def render(i, local):
    im=background(i).copy();d=ImageDraw.Draw(im)
    t=STARTS[i]+local;p=local/LENGTHS[i]
    text(d,(90,47),'SUNOCARE',24,True)
    text(d,(1610,47),f'{i+1:02d} / 10',23,False,MUTED)
    d.line((90,100,1830,100),fill=LINE,width=2)
    if i != 0: text(d,(90,135),TITLES[i],51,True)

    if i==0:
        d.ellipse((1140,185,1770,825),fill=LIME)
        actor(im,1230-int(50*ease(local/1.2)),210,630,1.2*math.sin(local*.7))
        text(d,(100,270),'SunoCare',108,True)
        text(d,(105,415),'Every visit.\nA voice that counts.'.replace('\n',' '),48,False,INK,width=850)
        d.rounded_rectangle((105,580,700,650),18,fill=AMBER)
        text(d,(132,595),'A voice-based visit register',30,True)
        arrow(d,(105,745),(970,745),local/2,color='#819950')
    elif i==1:
        house(d,100,365,1.1)
        actor(im,365+20*p,330,480,-1.5*p)
        # A single growing stack of field notes, followed by a cumbersome form.
        for j in range(3):
            xx,yy=810+j*14,270+j*13
            box(d,(xx,yy,xx+405,yy+480),'white')
        text(d,(885,347),'Visit notes',35,True)
        for j in range(6):
            end=900+int(210*ease((local-j*.5)/1.2))
            d.line((885,425+j*43,end,425+j*43),fill=LINE,width=5)
        phone(d,1380,305,.9,screen='Forms')
        for j in range(3):
            d.line((1420,450+j*18,1545,450+j*18),fill=MUTED,width=3)
        text(d,(860,815),'Paperwork',27,False,MUTED)
        text(d,(1385,815),'More screens',27,False,MUTED)
    elif i==2:
        phone(d,225,265,1.15,active='1' if p<.3 else None)
        # Cellular signal arcs grow once; the online service is clearly separate.
        for j in range(3):
            if local > j*.35:
                d.arc((430-j*35,300-j*35,570+j*35,470+j*35),275,355,fill='#819950',width=6)
        arrow(d,(600,500),(1110,500),local/2)
        dot=600+(local/3%1)*500
        d.ellipse((dot-10,490,dot+10,510),fill='#819950')
        box(d,(1190,340,1750,650),LIME)
        text(d,(1250,395),'Online backend',39,True)
        text(d,(1250,465),'Processing happens here',28,False,MUTED)
        text(d,(225,810),'No app. No mobile data.',37,True)
        text(d,(1190,710),'Worker uses cellular calling',27,False,MUTED)
    elif i==3:
        # One continuous progression: language -> fields -> review -> confirmation.
        labels=['Language + code','Patient details','Review + correct','Submit']
        stage=min(3,int(p*4))
        for j,label in enumerate(labels):
            xx=110+j*455
            d.ellipse((xx,280,xx+52,332),fill=LIME if j<=stage else '#E1E3D9',outline=INK,width=2)
            text(d,(xx+18,286),str(j+1),25,True)
            text(d,(xx,350),label,28,True)
            if j<3: arrow(d,(xx+75,305),(xx+400,305),max(0,(p*4-j)),color=LINE)
        box(d,(310,450,1620,790),'white')
        if stage==0:
            text(d,(380,500),'Hindi / English',45,True)
            text(d,(380,605),'Visit code',28,False,MUTED)
            for j,n in enumerate('4821'):
                box(d,(940+j*125,540,1035+j*125,660),LIME,12,False)
                if local>.5+j*.3:text(d,(965+j*125,565),n,43,True)
        elif stage==1:
            for j,label in enumerate(['Patient','Symptoms','Follow-up']):
                text(d,(380,500+j*78),label,30,True)
                d.line((670,525+j*78,1000+90*j,525+j*78),fill=LINE,width=5)
            wave(d,1200,615,local,count=18,spacing=12)
        elif stage==2:
            text(d,(380,510),'Listen to your answers',44,True)
            text(d,(380,620),'Confirm  /  Correct  /  Review',33)
            wave(d,1200,590,local,count=18,spacing=12,color='#819950')
        else:
            d.ellipse((420,515,600,695),fill=LIME)
            check(d,465,602,min(1,(p-.75)*15),1.5)
            text(d,(690,550),'Ready to submit',52,True)
            text(d,(695,630),'You stay in control',30,False,MUTED)
    elif i in (4,5):
        key='prisma' if i==4 else 'timbre'
        shot=screens[key]
        xx=1230+int(65*(1-ease(local/.8)));yy=235
        box(d,(xx-2,yy-2,xx+shot.width+2,yy+shot.height+2),'white',20)
        im.paste(shot,(xx,yy))
        text(d,(115,320),'Gnani Prisma' if i==4 else 'Gnani Timbre',64,True)
        text(d,(120,420),'Speech → Text' if i==4 else 'Text → Speech',43)
        if i==4:
            wave(d,120,585,local,color='#54ADC2',count=27,spacing=16,height=65)
            arrow(d,(625,585),(1020,585),local/1.3)
            for j in range(3):
                d.line((865,690+j*28,865+int(235*ease((local-j*.4)/1.2)),690+j*28),fill=INK,width=5)
        else:
            for j in range(3):d.line((120,550+j*30,400,550+j*30),fill=INK,width=5)
            arrow(d,(465,585),(730,585),local/1.3)
            wave(d,780,585,local,color='#D89155',count=22,spacing=13,height=60)
        text(d,(120,815),'Spoken responses' if i==4 else 'Prompts and confirmations',30,False,MUTED)
    elif i==6:
        actor(im,220,290,570,-1+p*2)
        for j,label in enumerate(['Hindi','English']):
            xx=820+j*470;yy=360+int(65*(1-ease(local/(.8+j*.4))))
            box(d,(xx,yy,xx+380,yy+190),LIME if j==0 else AMBER)
            text(d,(xx+65,yy+60),label,52,True)
        d.line((820,660,1670,660),fill=LINE,width=3)
        text(d,(820,710),'Regional-language expansion',35,True)
        text(d,(820,770),'A future direction',27,False,MUTED)
    elif i==7:
        nodes=[('Exotel','Cellular call'),('FastAPI','Python backend'),('Gemini','Structured data'),('SQLite','Saved records')]
        for j,(label,sub) in enumerate(nodes):
            xx=110+j*455;yy=315+int(75*(1-ease((local-j*.5)/.8)))
            box(d,(xx,yy,xx+350,yy+210),LIME if j==3 else 'white')
            text(d,(xx+30,yy+45),label,42,True)
            text(d,(xx+30,yy+120),sub,25,False,MUTED)
            if j<3:arrow(d,(xx+370,420),(xx+435,420),max(0,(local-j*.5-1)))
        arrow(d,(1650,560),(1650,635),max(0,local-2.5))
        box(d,(780,650,1775,830),AMBER)
        text(d,(830,680),'React supervisor dashboard',37,True)
        text(d,(830,744),'Review visits   ·   Export reports',30)
    elif i==8:
        # Close-up composition, not a replay of the introduction shot.
        d.ellipse((160,255,800,885),fill=LIME)
        actor(im,300-int(p*24),250,720,0)
        text(d,(910,310),'Familiar phone.',57,True)
        text(d,(910,405),'Familiar language.',57,True)
        d.line((915,515,1720,515),fill=INK,width=3)
        text(d,(915,560),'Less typing.',41)
        text(d,(915,635),'Simpler reporting.',41)
        text(d,(915,750),'Prototype · built around accessibility',27,False,MUTED)
    else:
        box(d,(140,260,1780,820),LIME,32)
        d.ellipse((260,390,500,630),fill=INK)
        d.polygon([(350,450),(350,570),(440,510)],fill=CREAM)
        text(d,(610,350),'Now, see it work.',73,True)
        text(d,(615,480),'A real call → a saved visit',44)
        text(d,(615,600),'Fictional patient data',30,False,MUTED)
        arrow(d,(620,730),(1660,730),local/2)

    # Keep the caption band clear, including on the portrait close-up.
    d.rectangle((0,901,W,H),fill=CREAM)
    d.line((90,902,1830,902),fill=LINE,width=2)
    subtitle(d,i,local)
    d.rectangle((0,1075,int(W*t/DURATION),1079),fill='#91AF5F')
    return im

def stamp(t):
    ms=round(t*1000)
    return f'00:{ms//60000:02d}:{ms//1000%60:02d},{ms%1000:03d}'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    (OUT/'narration_exact.txt').write_text('\n\n'.join(SCRIPT),encoding='utf-8')
    cues=[]
    for i,s in enumerate(TEXT):
        words=s.split()
        for k in range(0,len(words),12):
            end=min(k+12,len(words))
            a=STARTS[i]+LENGTHS[i]*k/len(words);b=STARTS[i]+LENGTHS[i]*end/len(words)
            cues.append(f'{len(cues)+1}\n{stamp(a)} --> {stamp(b)}\n'+ ' '.join(words[k:end]))
    (OUT/'captions_75s.srt').write_text('\n\n'.join(cues),encoding='utf-8')
    (OUT/'shot_list.json').write_text(json.dumps([
        dict(shot=i+1,title=TITLES[i],start=STARTS[i],duration=LENGTHS[i],script=s)
        for i,s in enumerate(TEXT)],indent=2,ensure_ascii=False),encoding='utf-8')
    contact=Image.new('RGB',(960,5*270),CREAM)
    for i in range(10):
        preview=render(i,LENGTHS[i]*.55)
        preview.save(OUT/f'shot_{i+1:02d}.jpg',quality=92)
        contact.paste(preview.resize((480,270)),((i%2)*480,(i//2)*270))
    contact.save(OUT/'storyboard.jpg',quality=90)
    if args.preview:
        print('Ten-shot storyboard ready. Exact script preserved. Duration: 75 seconds.')
        return
    cmd=[shutil.which('ffmpeg'),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
         '-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast',
         '-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'SunoCare_intro_75s.mp4')]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for f in range(FPS*DURATION):
            t=f/FPS;i=max(j for j,a in enumerate(STARTS) if a<=t)
            proc.stdin.write(render(i,t-STARTS[i]).tobytes())
            if f%(FPS*10)==0: print(f'Rendered {f//FPS}/75 seconds',flush=True)
    finally:
        proc.stdin.close()
    if proc.wait(): raise RuntimeError('Video encoding failed')
    print('75-second video complete.',flush=True)

if __name__=='__main__':main()
