"""Join poem.json, timing.json and the voice features into the timeline the Remotion studio reads.

Writes remotion/public/<poem>/timeline.json (and copies build/<poem>/mix.wav next to it when it exists).
usage: .venv/bin/python prepare.py <song>
"""
import json
import shutil
import unicodedata
import sys

from common import (FPS, ROOT, build_dir, hook_video, load_analysis, load_poem, load_timing, syllables,
                    video_duration, video_shift)


def main(pid):
    poem, an, timing = load_poem(pid), load_analysis(pid), load_timing(pid)
    poem = json.loads(unicodedata.normalize("NFC", json.dumps(poem, ensure_ascii=False)))
    frames = json.loads((build_dir(pid) / "frames.json").read_text())
    shift = video_shift(poem, an)
    dur = video_duration(poem, an)
    lines = {l["id"]: l for l in poem["lines"]}
    sung = []
    for s in timing["sung"]:
        l = lines[s["line"]]
        sung.append({**l, "syl": syllables(l["translit"]),
                     "start": round(s["start"] + shift, 3), "end": round(s["end"] + shift, 3)})
    # Scenes: consecutive lines that share a motif play as one scene, handing over at the midpoint of the gap.
    scenes = []
    for i, s in enumerate(sung):
        if scenes and scenes[-1]["motif"] == s["motif"]:
            scenes[-1]["lines"].append(i)
        else:
            scenes.append({"motif": s["motif"], "lines": [i]})
    for k, sc in enumerate(scenes):
        first, last = sung[sc["lines"][0]], sung[sc["lines"][-1]]
        sc["start"] = 0.0 if k == 0 else round((sung[sc["lines"][0] - 1]["end"] + first["start"]) / 2, 3)
        sc["end"] = round(dur, 3) if k == len(scenes) - 1 else round((last["end"] + sung[sc["lines"][-1] + 1]["start"]) / 2, 3)
    out = ROOT / "remotion" / "public" / pid
    out.mkdir(parents=True, exist_ok=True)
    mix = build_dir(pid) / "mix.wav"
    if mix.exists():
        shutil.copy(mix, out / "mix.wav")
    tl = {
        "poem": pid, "fps": FPS, "durationInFrames": int(round(dur * FPS)), "width": 1080, "height": 1920,
        "title": poem["title"], "source": poem.get("source", ""), "context": poem.get("context", ""),
        "closing": poem.get("closing", ""), "credit": poem.get("credit", ""),
        "audio": f"{pid}/mix.wav" if mix.exists() else None,
        "hook": ({"text": an["spoken"]["text"], "start": round(hook_video(poem, an)[0], 3),
                  "end": round(hook_video(poem, an)[1], 3)} if an.get("spoken") else None),
        "tonic": an["tonic_hz"], "raga": an["raga_guess"][0] if an["raga_guess"] else "",
        "lines": sung, "scenes": scenes, "energy": frames["energy"], "pitch": frames["pitch"],
    }
    (out / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False))
    print(f"{out / 'timeline.json'}  {dur:.1f}s, {len(sung)} lines, {len(scenes)} scenes, audio={'yes' if mix.exists() else 'no'}")


if __name__ == "__main__":
    main(sys.argv[1])
