"""Render supplied character as a continuous 2D cutout animation, without AI video credits."""
from pathlib import Path
import math, subprocess, shutil
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
W,H,FPS=1920,1080,24
@lru_cache(None)
def ft(n,b=False):return ImageFont.truetype('C:/Windows/Fonts/segoeui'+('b' if b else '')+'.ttf',n)
INK='#1F2A22';CREAM='#F5F3E8';LIME='#D9EFA5'
script=[
'Introducing SunoCare, a voice-based visit register designed to make digital reporting more accessible for ASHA workers and frontline health workers.',
'After a household visit, recording patient details can mean filling out paper forms or navigating unfamiliar mobile applications. This can be challenging for workers with limited formal education or digital experience, who are more comfortable speaking in their native language.',
'SunoCare lets them report through a simple phone call. No internet connection, smartphone, or app installation is required for the worker—only cellular calling service. Our online backend handles the processing.',
'The worker selects a supported language, enters a visit code, and answers guided questions about the patient, symptoms, and follow-up needs. They hear their answers read back and use the keypad to confirm, correct, review, and submit.',
'This is where Gnani’s speech technology plays a central role: Prisma converts spoken responses into text, while Timbre delivers spoken prompts and confirmations. The current prototype supports Hindi and English, with regional-language expansion as a future direction.',
'Exotel connects the call, Google Gemini extracts structured information, and a Python FastAPI backend stores records in SQLite. A React dashboard helps supervisors review visits and export reports.',
'This prototype is a starting point. It demonstrates how a familiar telephone interaction can make reporting easier for ASHA workers and reduce dependence on typing and complex interfaces.',
'Next, I’ll demonstrate the complete journey using fictional patient data—from a phone call to a saved visit in SunoCare.'
]
titles=['A visit begins with a conversation','Reporting after a home visit','Just a phone call','Speak. Review. Confirm.','Powered by Gnani speech','From voice to a visit record','A starting point for easier access','Next: the real call demonstration']
labels=[['ASHA worker','A familiar phone'],['Paper forms','Digital forms','Speak naturally'],['Cellular call','No app installation','Backend online'],['Hindi / English','Visit code','Patient details','Confirm'],['Prisma · speech to text','Timbre · spoken feedback'],['Exotel → FastAPI','Gemini → structured data','SQLite → React register'],['Review unfinished visits','Export reports','Regional languages: next'],['Real phone call','Fictional patient data','Saved visit']]
# Allocate duration by narration length, preserving every word.
total=sum(len(x.split()) for x in script); bounds=[0]
for s in script:bounds.append(bounds[-1]+90*len(s.split())/total)
bounds[-1]=90
def ts(t):
 ms=round(t*1000);return f'00:{ms//60000:02d}:{ms//1000%60:02d},{ms%1000:03d}'
(OUT/'character_narration.txt').write_text('\n\n'.join(script),encoding='utf-8')
(OUT/'character_narration.srt').write_text('\n\n'.join(f'{i+1}\n{ts(bounds[i])} --> {ts(bounds[i+1])}\n{s}' for i,s in enumerate(script)),encoding='utf-8')
source=Image.open(OUT/'asha_cutout.png').convert('RGBA')
source.putalpha(source.getchannel('A').point(lambda a: 255 if a>220 else 0))
crop=source.getbbox()
poses={}
for blink in (False,True):
 for speaking in (False,True):
  pose=source.copy(); face=ImageDraw.Draw(pose)
  if blink:
   for ex in (468,544):
    face.ellipse((ex-13,187,ex+13,213),fill=(236,175,116,255))
    face.arc((ex-12,195,ex+12,206),0,180,fill=INK,width=4)
  if speaking:
   face.ellipse((490,250,529,271),fill=INK)
   face.ellipse((498,262,522,270),fill='#CC927A')
  pose=pose.crop(crop);pose.thumbnail((550,580),Image.Resampling.LANCZOS)
  poses[blink,speaking]=pose
background=Image.new('RGB',(W,H),CREAM)
def caption(draw,s):
 words=s.split(); line=''; y=890
 for word in words:
  trial=(line+' '+word).strip()
  if draw.textlength(trial,font=ft(29))>1680:
   draw.text((120,y),line,font=ft(29),fill=INK);y+=40;line=word
  else:line=trial
 draw.text((120,y),line,font=ft(29),fill=INK)
cmd=[shutil.which('ffmpeg'),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','-','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'SunoCare_character_animation.mp4')]
p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for f in range(2160):
 t=f/FPS;i=next((j for j in range(8) if t<bounds[j+1]),7);local=t-bounds[i]
 im=background.copy();d=ImageDraw.Draw(im)
 d.text((110,55),'SunoCare',font=ft(45,True),fill=INK)
 d.text((110,130),titles[i],font=ft(46,True),fill=INK)
 # Character's continuous breathing, sway, and entrance; no slide swaps.
 entrance=min(1,t/1.5);ease=1-(1-entrance)**3
 x=int(-400+720*ease+9*math.sin(t*.9));y=int(245+5*math.sin(t*2))
 d.ellipse((200,805,740,850),fill='#E3E4CE')
 sprite=poses[(t%4.3)<.16, i in (0,3,4,6) and math.sin(t*12)>.15]
 actor=sprite.rotate(1.5*math.sin(t*1.1),Image.Resampling.BICUBIC,expand=True)
 im.paste(actor,(x,y),actor)
 # Voice particles travel between worker and connected service.
 for j in range(12):
  u=(t*.25+j/12)%1;xx=730+u*300;yy=530+35*math.sin(u*math.pi*2+t)
  r=int(4+5*math.sin(u*math.pi));d.ellipse((xx-r,yy-r,xx+r,yy+r),fill='#91AF5F')
 # Waveform continuously responds beside the worker's phone.
 for j in range(16):
  h=12+36*abs(math.sin(t*4+j*.6));xx=730+j*12
  d.rounded_rectangle((xx,370-h,xx+6,370+h),3,fill='#718849')
 for j,label in enumerate(labels[i]):
  delay=j*.6; reveal=max(0,min(1,(local-delay)/.7));xx=1080+int(150*(1-reveal));yy=310+j*125+int(5*math.sin(t+j))
  if reveal:
   d.rounded_rectangle((xx+8,yy+9,xx+650,yy+100),20,fill=INK)
   d.rounded_rectangle((xx,yy,xx+642,yy+91),20,fill=LIME if j%2==0 else 'white',outline=INK,width=2)
   d.text((xx+25,yy+25),label,font=ft(29,True),fill=INK)
 d.line((110,865,1810,865),fill='#CBD1BF',width=2)
 caption(d,script[i]);d.rectangle((0,1072,int(W*t/90),1079),fill='#91AF5F')
 if f in (120,840,1560,2040):im.save(OUT/f'character_preview_{f}.jpg')
 p.stdin.write(im.tobytes())
 if f%240==0:print(f'Rendered {f//24}/90 seconds',flush=True)
p.stdin.close()
if p.wait():raise RuntimeError('Encoding failed')
print('Character animation complete',flush=True)
