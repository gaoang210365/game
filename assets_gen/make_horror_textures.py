"""Generate horror decal textures via gpt-image-2 (EasyTokens endpoint).
Reads key from ~/.mcp.json. Outputs PNGs to assets/textures/.
Run: game_env python assets_gen/make_horror_textures.py
"""
import os, sys, json, base64, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, "assets", "textures")


def cfg():
    p = os.path.join(os.path.expanduser("~"), ".mcp.json")
    with open(p, "r", encoding="utf-8-sig") as f:
        env = json.load(f)["mcpServers"]["gpt-image-2"]["env"]
    return env["OPENAI_API_KEY"], env["OPENAI_BASE_URL"], env["OPENAI_IMAGE_MODEL"]


JOBS = [
    ("blood_splatter.png",
     "top-down dark dried blood splatter stain on dirty concrete floor, "
     "horror game texture, seamless, muted desaturated crimson, grungy, high detail, no text"),
    ("blood_wall.png",
     "dried blood smear and handprints dripping down a grimy hospital wall, "
     "horror atmosphere, dark red brown, peeling paint, high detail, no text"),
    ("grime_wall.png",
     "filthy stained abandoned hospital wall, water damage, mold, cracks, peeling paint, "
     "desaturated green grey, horror game texture, seamless, no text"),
    ("floor_dirty.png",
     "cracked dirty hospital linoleum floor, stains, scuff marks, grime, "
     "desaturated, horror game texture, seamless tile, no text"),
]


def gen(key, base, model, prompt, out):
    body = json.dumps({"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/images/generations", data=body,
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode())
    item = data["data"][0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    else:
        with urllib.request.urlopen(item["url"], timeout=180) as ir:
            raw = ir.read()
    os.makedirs(TEX, exist_ok=True)
    with open(os.path.join(TEX, out), "wb") as f:
        f.write(raw)
    print("WROTE", out, len(raw), "bytes")


def main():
    key, base, model = cfg()
    print("ENDPOINT", base, model)
    for name, prompt in JOBS:
        path = os.path.join(TEX, name)
        if os.path.exists(path) and "--force" not in sys.argv:
            print("SKIP", name); continue
        try:
            gen(key, base, model, prompt, name)
        except Exception as e:
            print("FAIL", name, repr(e))


def make_decals():
    """Post-process blood textures into RGBA decals (dark=opaque, light=transparent)."""
    try:
        from PIL import Image
        import numpy as np
    except Exception as e:
        print("no PIL/numpy, skip decals", e); return
    def one(src, dst, power=1.5, boost=1.2):
        p = os.path.join(TEX, src)
        if not os.path.exists(p): return
        im = Image.open(p).convert("RGB")
        a = np.asarray(im, dtype=np.float32) / 255.0
        lum = 0.299*a[...,0] + 0.587*a[...,1] + 0.114*a[...,2]
        alpha = np.clip((1.0 - lum) * boost, 0, 1) ** power
        rgba = np.zeros((a.shape[0], a.shape[1], 4), dtype=np.uint8)
        rgba[...,:3] = (a*255).astype(np.uint8)
        rgba[...,3] = (alpha*255).astype(np.uint8)
        Image.fromarray(rgba).save(os.path.join(TEX, dst))
        print("DECAL", dst)
    one("blood_splatter.png", "blood_splatter_decal.png", 1.4, 1.3)
    one("blood_wall.png", "blood_wall_decal.png", 1.3, 1.2)


if __name__ == "__main__":
    main()
    make_decals()
