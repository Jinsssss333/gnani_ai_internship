# SunoCare demo intro

A locally rendered 90-second motion-graphics introduction. Ten nine-second chapters use the project's cream, green, lime and amber palette. The output is silent, with narration burned in as captions and also provided as a text script and SRT file.

## Render

### Add a supplied voiceover locally

`sync_voiceover.py` transcribes an existing recording on the computer, aligns it to the original script, shortens long pauses, and uses pitch-preserving time stretching to fit 74 seconds of narration plus a one-second silent handoff. It then renders the same ten scenes with the new timing and synchronized captions, including the Gnani reference images. This uses the supplied voice, not a cloned or newly generated voice.

```powershell
python -m pip install --target demo-video/output/audio_tools faster-whisper
python demo-video/sync_voiceover.py --download-model
python demo-video/sync_voiceover.py --transcribe --audio "C:/path/to/narration.mp3"
python demo-video/sync_voiceover.py --preview --audio "C:/path/to/narration.mp3"
python demo-video/sync_voiceover.py --render --audio "C:/path/to/narration.mp3"
```

Only installation and the model download require network access. Audio transcription uses local model files with Hugging Face offline mode enabled. Outputs are ignored by Git under `demo-video/output/voiced/`: `SunoCare_intro_75s_with_voice.mp4`, `SunoCare_narration_75s.wav`, `SunoCare_narration_75s.mp3`, `captions_synced.srt`, and `alignment.json`. Original files are preserved. Inspect the transcript and preview before rendering; the script stops if fewer than 85% of normalized script tokens match, but that threshold is not a substitute for checking recognition errors. Retiming a long narration can make delivery brisk.

### Latest: 75-second introduction with Gnani references

`render_intro_v2.py` produces ten distinct shots, each used once, in a 75-second silent video. It preserves the original character video's complete script as short caption cues. Prisma and Timbre each have a dedicated shot displaying the supplied screenshot. The illustrations are explanatory cutout/motion graphics, not recordings of a live call.

Prepare these local assets in `demo-video/output/v2/assets/`:

- `asha_cutout.png`: the same prepared character used below.
- `prisma.png`: supplied `Screenshot 2026-11-14 134844.png`.
- `timbre.png`: supplied `Screenshot 2026-11-14 134859.png`.

```powershell
python demo-video/render_intro_v2.py --preview
python demo-video/render_intro_v2.py
```

Outputs in `demo-video/output/v2/`: `SunoCare_intro_75s.mp4` (1080p, H.264, 24 fps), `narration_exact.txt`, `captions_75s.srt`, `shot_list.json`, ten shot previews, and `storyboard.jpg`. Assets and generated media are ignored by Git. No cloud generation or API credentials are required.

The complete script needs a brisk voiceover to fit 75 seconds. This render has no audio; align your narration to the shot list, or retime the scenes in an editor. Prisma appears at 00:40.8–00:46.5 and Timbre at 00:46.5–00:51.3. The supplied Timbre image displays v3.0; this is reference artwork, not verification of the backend's configured model version.

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
