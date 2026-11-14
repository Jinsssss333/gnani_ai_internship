"""Render SunoCare's silent, narrated-by-user intro using Pillow and FFmpeg."""
from pathlib import Path
import math, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
W,H,FPS = 1920,1080,24
INK='#1F2A22'; CREAM='#F5F3E8'; LIME='#D9EFA5'; AMBER='#FFE2A0'; MUTED='#627064'
FONT='C:/Windows/Fonts/segoeui.ttf'
BOLD='C:/Windows/Fonts/segoeuib.ttf'
def font(n,bold=False): return ImageFont.truetype(BOLD if bold else FONT,n)
scenes=[
 ('Meet SunoCare','A visit register.\nOne phone call.', 'Voice-guided reporting for frontline health workers.',
  'Introducing SunoCare, a voice-based visit register designed to make digital reporting more accessible for ASHA workers and frontline health workers.', 'phone'),
 ('Built around the worker','Less typing.\nMore accessibility.', 'A familiar conversation, one question at a time.',
  'After a household visit, paper forms and unfamiliar applications add work. SunoCare supports workers who are more comfortable speaking than navigating digital forms.', 'cards'),
 ('An ordinary phone is enough','No app.\nNo mobile data.', 'Cellular calling required. Processing happens online.',
  'The worker needs no smartphone, app installation, or internet connection. A basic phone with cellular calling service is enough. Our online backend handles processing.', 'phone'),
 ('Start with a call','Choose a language.\nEnter a visit code.', 'Current prototype: Hindi and English.',
  'Workers call the service, select Hindi or English, and enter a visit code. Guided prompts help them move through the form using speech and keypad choices.', 'language'),
 ('Speak the visit details','Patient details,\none answer at a time.', 'Name · Age · Symptoms · Follow-up · Notes',
  'The call captures visit completion, patient name, age, symptoms, follow-up requirements, and additional notes. Each answer becomes a structured field in the visit record.', 'form'),
 ('Powered by Gnani speech','Speech becomes text.\nText speaks back.', 'Gnani Prisma transcription + Gnani Timbre voice feedback',
  'Gnani Prisma transcribes spoken responses, while Gnani Timbre delivers prompts and confirmations. This is the speech layer that makes the telephone workflow possible.', 'wave'),
 ('Keep the worker in control','Listen. Correct.\nConfirm.', 'Review individual fields before submitting.',
  'The worker hears answers read back and can correct mistakes with the keypad. Final review makes it possible to check individual fields before submitting the visit.', 'review'),
 ('From call to register','Connected tools.\nOne clear workflow.', 'Exotel · Gemini · FastAPI · SQLite · React',
  'Exotel connects the call. Gemini extracts structured information. FastAPI manages the workflow, SQLite stores records, and the React dashboard brings them to supervisors.', 'stack'),
 ('A starting point','Accessible reporting.\nRoom to grow.', 'Review unfinished visits and export submitted records.',
  'Supervisors can review incomplete visits and export reports. This prototype demonstrates easier access for ASHA workers, with regional-language expansion as a future direction.', 'dashboard'),
 ('See it in action','From a real call\nto a saved visit.', 'Next: the live workflow demonstration.',
  'Next, I will demonstrate the complete journey using fictional patient data: from a real telephone call, through confirmation, to a saved visit in SunoCare.', 'final'),
]
def card(d,box,fill='white',r=26):
 x,y,x2,y2=box
 d.rounded_rectangle((x+10,y+12,x2+10,y2+12),r,fill=INK)
 d.rounded_rectangle(box,r,fill=fill,outline=INK,width=3)
def text(d,xy,s,size=32,fill=INK,bold=False): d.text(xy,s,font=font(size,bold),fill=fill,spacing=12)
def lines(d,s,x,y,width,size=28):
 words=s.split(); line=''
 for word in words:
  test=(line+' '+word).strip()
  if d.textlength(test,font=font(size))>width and line:
   text(d,(x,y),line,size);y+=43;line=word
  else:line=test
 text(d,(x,y),line,size)
def phone(d,t,x=1240,y=210):
 card(d,(x,y,x+330,y+560),INK)
 d.rounded_rectangle((x+24,y+32,x+306,y+210),18,fill=LIME)
 text(d,(x+57,y+65),'SunoCare',38,bold=True)
 text(d,(x+65,y+130),'Call connected',23)
 for row in range(4):
  for col in range(3):
   cx=x+76+col*89; cy=y+270+row*68
   d.ellipse((cx-24,cy-24,cx+24,cy+24),fill=CREAM)
   text(d,(cx-9,cy-19),'123456789*0#'[row*3+col],25)
 for i in range(5):
  radius=28+i*12+int(t*15)%12
  d.arc((x+350-radius,y+120-radius,x+350+radius,y+120+radius),-60,60,fill=MUTED,width=3)
def visual(d,kind,t):
 if kind=='phone':phone(d,t);return
 card(d,(1080,220,1760,770))
 if kind=='wave':
  text(d,(1120,270),'VOICE → TEXT → VOICE',29,bold=True)
  for i in range(29):
   height=35+120*abs(math.sin(i*.55+t*3))*math.sin((i+1)*math.pi/30)
   x=1130+i*20;d.rounded_rectangle((x,490-height,x+10,490+height),5,fill=MUTED if i%3 else '#88A843')
  text(d,(1130,680),'Prisma STT     •     Timbre TTS',28)
 elif kind=='language':
  text(d,(1125,270),'SELECT YOUR LANGUAGE',29,bold=True)
  for i,s in enumerate(['2   Hindi','4   English','4821   Visit code']):
   d.rounded_rectangle((1120,350+i*110,1720,430+i*110),16,fill=LIME if i==0 else CREAM)
   text(d,(1150,370+i*110),s,31)
 elif kind in ('form','review','dashboard','final'):
  text(d,(1120,260),'VISIT REGISTER' if kind!='review' else 'REVIEW YOUR ANSWERS',29,bold=True)
  entries=[('Patient','Amina'),('Age','26'),('Symptoms','Fever, nausea'),('Follow-up','20 / 11 / 2026')]
  for i,(label,value) in enumerate(entries):
   yy=340+i*81
   text(d,(1120,yy),label,24,MUTED);text(d,(1340,yy),value,27,bold=True)
   d.line((1120,yy+57,1715,yy+57),fill='#DEE3D7',width=2)
  d.rounded_rectangle((1120,687,1720,742),12,fill=LIME)
  text(d,(1150,697),'Confirmed and submitted' if kind in ('dashboard','final') else '1 Confirm     2 Correct',25,bold=True)
 elif kind=='stack':
  for i,s in enumerate(['Exotel  /  Telephone connection','Gemini  /  Structured extraction','FastAPI  /  Guided workflow','SQLite  /  Record storage','React  /  Supervisor dashboard']):
   yy=260+i*96
   d.rounded_rectangle((1110,yy,1730,yy+73),12,fill=LIME if i%2==0 else CREAM)
   text(d,(1135,yy+21),s,25,bold=True)
 else:
  text(d,(1125,270),'AFTER THE HOME VISIT',29,bold=True)
  for i,s in enumerate(['Make a phone call','Speak your answers','Confirm the record']):
   yy=370+i*115
   d.ellipse((1120,yy,1180,yy+60),fill=LIME)
   text(d,(1140,yy+8),str(i+1),30,bold=True)
   text(d,(1210,yy+10),s,29)

base=Image.new('RGB',(W,H),CREAM)
# Restrained colour wash along the right edge, keeping text high contrast.
p=base.load()
for yy in range(H):
 for xx in range(1000,W):
  a=.13*math.exp(-((xx-1850)/480)**2-((yy-500)/550)**2)
  target=(170,190,240) if yy>550 else (255,195,150)
  p[xx,yy]=tuple(int(c*(1-a)+v*a) for c,v in zip((245,243,232),target))

narration=[]; srt=[]
def stamp(sec):return f'00:{sec//60:02d}:{sec%60:02d},000'
for i,scene in enumerate(scenes):
 narration.append(f'{i*9:02d}–{(i+1)*9:02d} seconds\n{scene[3]}\n')
 srt.append(f'{i+1}\n{stamp(i*9)} --> {stamp((i+1)*9)}\n{scene[3]}\n')
(OUT/'narration.txt').write_text('\n'.join(narration),encoding='utf-8')
(OUT/'narration.srt').write_text('\n'.join(srt),encoding='utf-8')
cmd=[shutil.which('ffmpeg'),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-', '-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'SunoCare_intro_90s_1080p.mp4')]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for i,scene in enumerate(scenes):
 for frame in range(9*FPS):
  t=frame/FPS; im=base.copy();d=ImageDraw.Draw(im)
  text(d,(110,65),'SunoCare',42,bold=True);d.ellipse((320,89,333,102),fill='#88A843')
  text(d,(110,220),scene[0].upper(),24,MUTED,bold=True)
  text(d,(105,295),scene[1],72,bold=True)
  lines(d,scene[2],110,535,840,31)
  visual(d,scene[4],t)
  d.line((110,830,1810,830),fill='#CCD3C5',width=2)
  lines(d,scene[3],110,865,1690,28)
  text(d,(110,1010),'PROTOTYPE  •  FICTIONAL PATIENT DATA',18,MUTED)
  text(d,(1710,1010),f'{i+1:02d} / 10',20,MUTED)
  progress=(i*9+t)/90
  d.rectangle((0,1072,int(W*progress),1079),fill='#88A843')
  # Short fade through the cream canvas between chapters.
  opacity=min(1,t/.35,(9-t)/.35)
  if opacity<1:im=Image.blend(base,im,max(0,opacity))
  if frame==96:im.save(OUT/f'preview_{i+1:02d}.jpg',quality=90)
  proc.stdin.write(im.tobytes())
 print(f'Rendered scene {i+1}/10',flush=True)
proc.stdin.close()
if proc.wait()!=0:raise RuntimeError('Video encoding failed')
print('Saved output/SunoCare_intro_90s_1080p.mp4',flush=True)
