"""Blur the phone header in the inspected 1920x1080 Suno_final.mov layout.

The demo starts at frame 1800 (75 seconds at 24 fps). The full phone-number
line is covered, including its horizontal movement as DTMF digits accumulate.
This is a fixed-layout edit, not an automatic phone-number detector.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'output/redacted/Suno_final_blurred.mov')
    args=parser.parse_args()
    if args.source.resolve()==args.output.resolve():
        parser.error('Output must differ from original')
    probe=json.loads(subprocess.check_output([shutil.which('ffprobe'),'-v','error',
        '-show_streams','-show_format','-of','json',str(args.source)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'],video['r_frame_rate']) != (1920,1080,'24/1'):
        parser.error('This mask was inspected for 1920x1080, 24fps footage only')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    graph=("[0:v:0]split=2[base][region];"
           "[region]crop=504:72:0:36,gblur=sigma=28:steps=3[blur];"
           "[base][blur]overlay=0:36:enable='gte(t,75)':format=auto[v]")
    subprocess.run([shutil.which('ffmpeg'),'-y','-hide_banner','-loglevel','error',
        '-i',str(args.source),'-filter_complex',graph,'-map','[v]','-map','0:a?',
        '-map_metadata','-1','-map_chapters','-1','-c:v','libx264','-preset','fast',
        '-crf','18','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',
        '-progress','pipe:1','-nostats',str(args.output)],check=True)
    (args.output.parent/'redaction.json').write_text(json.dumps(dict(
        start_seconds=75,region=dict(x=0,y=36,width=504,height=72),
        filter='gblur=sigma=28:steps=3',audio='stream copied',
        source_duration=probe['format']['duration'],output=args.output.name),indent=2))
    print('Blurred copy complete. Original preserved.',flush=True)

if __name__=='__main__':main()
