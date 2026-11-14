# SunoCare demo intro

A locally rendered 90-second motion-graphics introduction. Ten nine-second chapters use the project's cream, green, lime and amber palette. The output is silent, with narration burned in as captions and also provided as a text script and SRT file.

## Render

### Character animation

`animate_character.py` renders the newer 90-second 2D cutout version, using the supplied ASHA character design. It animates blinking, mouth poses, body sway, waveforms and workflow cards. These are procedural cutout movements, not newly drawn poses or audio-synchronized lip movements.

Place the prepared transparent character asset at `demo-video/output/asha_cutout.png`, then run:

```powershell
python demo-video/animate_character.py
```

The renderer expects the prepared 1024 × 1536 cutout; its facial animation coordinates are specific to that image. The asset is local and ignored by Git, so a fresh checkout needs that asset copied separately.

Outputs: `SunoCare_character_animation.mp4` (silent 1080p, 24 fps), `character_narration.txt` (the exact requested script), `character_narration.srt`, and character preview images. Eight narration sections are timed by word count across 90 seconds. Add a recorded voiceover in your editor and adjust timing to the actual delivery.

### Original motion graphics

Requires Python with Pillow, FFmpeg on PATH, and Windows Segoe UI fonts.

```powershell
python demo-video/render_intro.py
```

Generated files are in `demo-video/output/` (ignored by Git):

- `SunoCare_intro_90s_1080p.mp4`: 1920 × 1080, 24 fps, H.264.
- `narration.txt`: voiceover script with scene timings.
- `narration.srt`: optional subtitle track; captions already appear in the video.
- `preview_01.jpg` through `preview_10.jpg`: scene review images.

## Assemble in DaVinci Resolve

1. Use a 1920 × 1080 timeline at 24 fps.
2. Place the intro before the recorded call/dashboard demo.
3. Record the script in ten segments, about nine seconds each. Place each segment at its matching chapter start, or adjust clip timings to your delivery.
4. Add your voice track and adjust levels so the speech is clear.
5. Export H.264 video with AAC audio. Check the submission's duration limit against the complete timeline.

The illustrations represent the workflow; they are not live UI recordings. The real call recording belongs after the introduction. The script accurately distinguishes the caller's cellular connection from the internet-connected backend.
