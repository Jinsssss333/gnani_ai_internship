"""Align an existing local narration with the 75-second intro, without uploading audio.

Install faster-whisper into output/audio_tools; --download-model downloads public
model weights only. --transcribe and --render run locally, with network disabled
for Hugging Face. Original audio/video remain untouched.
"""
import argparse
import bisect
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output' / 'voiced'
MODEL = ROOT / 'output' / 'models' / 'base.en'
sys.path.insert(0, str(ROOT / 'output' / 'audio_tools'))
os.environ['HF_HOME'] = str(ROOT / 'output' / 'hf_cache')
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
OUT.mkdir(parents=True, exist_ok=True)

def download():
    from huggingface_hub import snapshot_download
    snapshot_download('Systran/faster-whisper-base.en', local_dir=str(MODEL), token=False,
                      allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.*'])
    print('Public model downloaded. No audio was sent.', flush=True)

def transcribe(audio):
    os.environ['HF_HUB_OFFLINE'] = '1'
    from faster_whisper import WhisperModel
    model = WhisperModel(str(MODEL), device='cpu', compute_type='int8', local_files_only=True)
    segments, info = model.transcribe(str(audio), language='en', beam_size=5,
        word_timestamps=True, condition_on_previous_text=False,
        initial_prompt='SunoCare. ASHA. Gnani Prisma, Timbre. Exotel. Google Gemini. FastAPI. SQLite. React.')
    result = []
    for segment in segments:
        print(f'{segment.start:.1f}-{segment.end:.1f}: {segment.text}', flush=True)
        result.extend(dict(word=w.word.strip(), start=w.start, end=w.end) for w in segment.words)
    (OUT/'words_original.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Local transcription complete.', flush=True)

def normalize(value):
    return re.findall(r'[a-z0-9]+', value.lower())

def prepare(audio):
    import render_intro_v2 as video
    spoken = json.loads((OUT/'words_original.json').read_text(encoding='utf-8'))
    expected, expected_owner, display = [], [], []
    shot_offsets = []
    for shot, sentence in enumerate(video.TEXT):
        shot_offsets.append(len(display))
        for word in sentence.split():
            for token in normalize(word):
                expected.append(token)
                expected_owner.append(len(display))
            display.append(dict(word=word, shot=shot))
    recognized, recognized_owner = [], []
    for i, w in enumerate(spoken):
        for token in normalize(w['word']):
            recognized.append(token)
            recognized_owner.append(i)
    matcher = difflib.SequenceMatcher(None, expected, recognized, autojunk=False)
    matches = {}
    for block in matcher.get_matching_blocks():
        for j in range(block.size):
            owner=expected_owner[block.a+j]
            source=spoken[recognized_owner[block.b+j]]
            matches.setdefault(owner, []).append((source['start'], source['end']))
    coverage = sum(b.size for b in matcher.get_matching_blocks()) / len(expected)
    if coverage < .85:
        raise RuntimeError(f'Script/audio mismatch: {coverage:.1%} exact token alignment. Review transcript before rendering.')
    keys=sorted(matches)
    for i, word in enumerate(display):
        if i in matches:
            word['start']=min(p[0] for p in matches[i])
            word['end']=max(p[1] for p in matches[i])
        else:
            k=bisect.bisect_left(keys,i)
            before=keys[k-1] if k else None
            after=keys[k] if k<len(keys) else None
            a=max(p[1] for p in matches[before]) if before is not None else spoken[0]['start']
            b=min(p[0] for p in matches[after]) if after is not None else spoken[-1]['end']
            count=(after if after is not None else len(display))-(before if before is not None else -1)-1
            offset=i-(before if before is not None else -1)-1
            word['start']=a+(b-a)*offset/count
            word['end']=a+(b-a)*(offset+1)/count

    # Trim only gaps exceeding 0.55s; retain 0.24s around each boundary.
    intervals=[]
    start=max(0, spoken[0]['start']-.10)
    for a,b in zip(spoken,spoken[1:]):
        if b['start']-a['end']>.55:
            intervals.append((start,a['end']+.12))
            start=b['start']-.12
    intervals.append((start,spoken[-1]['end']+.15))
    packed=sum(b-a for a,b in intervals)
    speed=packed/74.0  # last second is intentionally silent before the demo
    def remap(t):
        elapsed=0
        for a,b in intervals:
            if t<=a:return elapsed/speed
            if t<=b:return (elapsed+t-a)/speed
            elapsed+=b-a
        return elapsed/speed
    for w in display:
        w['start']=remap(w['start']);w['end']=remap(w['end'])
    starts=[0]+[max(0,display[k]['start']-.04) for k in shot_offsets[1:]]
    lengths=[b-a for a,b in zip(starts,starts[1:]+[75])]
    if any(n<=0 for n in lengths):raise RuntimeError('Non-monotonic shot boundaries')
    plan=dict(coverage=coverage, speed=speed, packed_duration=packed,
              intervals=intervals, starts=starts, lengths=lengths, words=display)
    (OUT/'alignment.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    filters=[f'[0:a]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{i}]'
             for i,(a,b) in enumerate(intervals)]
    inputs=''.join(f'[a{i}]' for i in range(len(intervals)))
    filters.append(f'{inputs}concat=n={len(intervals)}:v=0:a=1,atempo={speed:.8f},'
                   'apad,atrim=duration=75,alimiter=limit=0.95:level=false[out]')
    filter_file=OUT/'audio_filter.txt'
    filter_file.write_text(';\n'.join(filters),encoding='utf-8')
    subprocess.run([shutil.which('ffmpeg'),'-y','-v','error','-i',str(audio),
        '-filter_complex_script',str(filter_file),'-map','[out]', '-ar','48000',
        '-c:a','pcm_s16le',str(OUT/'SunoCare_narration_75s.wav')],check=True)
    subprocess.run([shutil.which('ffmpeg'),'-y','-v','error',
        '-i',str(OUT/'SunoCare_narration_75s.wav'),'-c:a','libmp3lame','-b:a','192k',
        str(OUT/'SunoCare_narration_75s.mp3')],check=True)
    print(f'Script alignment: {coverage:.1%}; pitch-preserving speed: {speed:.3f}x',flush=True)
    for i,start in enumerate(starts):print(f'Shot {i+1}: {start:.2f}s',flush=True)
    return plan

def render(audio, preview=False):
    import render_intro_v2 as video
    plan=prepare(audio)
    video.STARTS=plan['starts'];video.LENGTHS=plan['lengths']
    words=plan['words']; cues=[]
    for i in range(10):
        group=[w for w in words if w['shot']==i]
        for k in range(0,len(group),10):
            batch=group[k:k+10]
            cues.append(dict(start=batch[0]['start'],end=batch[-1]['end'],
                             text=' '.join(w['word'] for w in batch),shot=i))
    (OUT/'captions_synced.srt').write_text('\n\n'.join(
        f"{i+1}\n{video.stamp(c['start'])} --> {video.stamp(c['end'])}\n{c['text']}"
        for i,c in enumerate(cues)),encoding='utf-8')
    def subtitle(d, i, local):
        t=video.STARTS[i]+local
        current=next((c for c in cues if c['start']<=t<=c['end']+.08),None)
        if current:
            for j,line in enumerate(video.wrap(current['text'],34,1580)):
                width=d.textlength(line,font=video.font(34))
                video.text(d,((video.W-width)/2,928+j*44),line,34)
    video.subtitle=subtitle
    for i in (4,5,9):
        video.render(i,video.LENGTHS[i]/2).save(OUT/f'preview_{i+1}.jpg')
    if preview:return
    cmd=[shutil.which('ffmpeg'),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
        '-s','1920x1080','-r','24','-i','-','-i',str(OUT/'SunoCare_narration_75s.wav'),
        '-map','0:v','-map','1:a','-t','75','-c:v','libx264','-preset','fast','-crf','19',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',
        str(OUT/'SunoCare_intro_75s_with_voice.mp4')]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for f in range(75*24):
            t=f/24;i=max(j for j,a in enumerate(video.STARTS) if a<=t)
            proc.stdin.write(video.render(i,t-video.STARTS[i]).tobytes())
            if f%240==0:print(f'Rendered {f//24}/75 seconds',flush=True)
    finally:proc.stdin.close()
    if proc.wait():raise RuntimeError('Video encoding failed')
    print('Voiced video complete.',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--download-model',action='store_true')
    p.add_argument('--transcribe',action='store_true')
    p.add_argument('--render',action='store_true')
    p.add_argument('--preview',action='store_true')
    p.add_argument('--audio',type=Path)
    args=p.parse_args()
    if args.download_model:download()
    if args.transcribe or args.render or args.preview:
        if not args.audio or not args.audio.is_file():p.error('--audio must name a local recording')
        if args.transcribe:transcribe(args.audio)
        if args.render or args.preview:render(args.audio,preview=args.preview)

if __name__=='__main__':main()
