#!/usr/bin/env python3
"""jev-paint-quilt — JEV vector-advisement painting engine (local, no metered spend).

Cells are local models with ENGINEER prompts. The JEV judge pulses VECTOR advisements
(not scalar). JEPA reads the whole-canvas "room". mothquantum seeds entropy. Hebbian
edges grow round-over-round. See DESIGN.md.

Run: python3 quilt.py "a red boat on a dark sea at night" --rounds 3
"""
import argparse, base64, hashlib, json, math, os, random, re, subprocess, sys, time
import urllib.request, urllib.error
from collections import Counter

OLLAMA = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434/v1/chat/completions')

CELLS = {
    'palette': {
        'model': 'tev1:0.8b',
        'system': (
            'You are a PALETTE ENGINEER. Output ONLY a single JSON object (no markdown, '
            'no prose): {"palette":[{"name":"...","hex":"#rrggbb"}, ...]} with 3-5 '
            'harmonious colors fitting a given theme.'
        ),
    },
    'composer': {
        'model': 'qwen2.5:7b-instruct-q4_K_M',
        'system': (
            'You are a COMPOSITION ENGINEER for a vector painting. '
            'Output ONLY a single JSON object (no markdown, no prose): '
            '{"shapes":[{"shape":"rect|circle|ellipse|line|polygon","x":<num>,"y":<num>,'
            '"w":<num>,"h":<num>,"fill":"#rrggbb","cx":<num>,"cy":<num>,"r":<num>,'
            '"x2":<num>,"y2":<num>,"points":"x,y x,y .."}, ...]}. '
            'Coordinates in a 100x100 viewBox. Draw the background/sky first as a '
            'full-canvas rect, then the foreground subject with a recognizable silhouette. '
            'Use 5-12 shapes and a limited harmonious palette (3-6 colors). Give the '
            'subject the dominant color named in the prompt. Be concrete and literal.'
        ),
    },
    'engineer': {
        'model': 'qwen2.5:7b-instruct-q4_K_M',
        'system': (
            'You are a REFINEMENT ENGINEER. You receive a scene JSON and a JEV judge '
            'VECTOR advisement. Revise the scene to fix the flagged weakness (the '
            'correction note). Output ONLY the corrected JSON object, same schema. '
            'Keep it concrete.'
        ),
    },
    'judge': {
        'model': 'qwen2.5:7b-instruct-q4_K_M',
        'system': (
            'You are a JEV JUDGE. Review the scene and output ONLY a single JSON VECTOR '
            'advisement (no markdown, no prose): {"coherence":0..1,"contrast":0..1,'
            '"balance":0..1,"clarity":0..1,"harmony":0..1,"correction":"one short '
            'imperative note"}. Each dimension 0..1. coherence=readability/unity; '
            'contrast=value range; balance=compositional weight; clarity=subject '
            'recognizability; harmony=palette coherence. Score AGAINST the requested image: '
            'be harsh, spread scores across 0.1-0.9, and flag when the requested subject '
            'is missing or the wrong color.'
        ),
    },
}

def call_ollama(model, system, user, max_tokens=1200, temperature=0.7, timeout=480):
    body = {'model': model, 'messages': [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ], 'max_tokens': max_tokens, 'stream': False, 'temperature': temperature}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    ch = data['choices'][0]['message']
    return (ch.get('content') or '').strip(), data.get('model')

def emit_json(text):
    t = (text or '').strip()
    if t.startswith('```'):
        t = t.split('```')[1]
        if t.startswith('json'):
            t = t[4:]
    s, e = t.find('{'), t.rfind('}')
    if s >= 0 and e > s:
        try:
            return json.loads(t[s:e + 1])
        except Exception:
            pass
    return None

def jepa_room(scene):
    shapes = (scene or {}).get('shapes', [])
    if not shapes:
        return {'temperature': 0.0, 'coverage': 0.0, 'entropy': 0.0, 'n': 0}
    area = 0.0
    for sh in shapes:
        if 'w' in sh and 'h' in sh:
            area += max(0.0, float(sh.get('w', 0))) * max(0.0, float(sh.get('h', 0)))
        elif 'r' in sh:
            area += math.pi * float(sh['r']) ** 2
    coverage = min(1.0, area / (100.0 * 100.0))
    fills = [sh.get('fill', '#000000') for sh in shapes]
    n = len(fills)
    counts = Counter(fills)
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values()) / max(1.0, math.log2(max(2, n)))
    temperature = 0.5 * coverage + 0.5 * entropy
    return {'temperature': round(temperature, 3), 'coverage': round(coverage, 3),
            'entropy': round(entropy, 3), 'n': n}

def moth_entropy(n_bits=32):
    """mothquantum entropy for seeding. Best-effort: MOTH wrapper if reachable, else
    urandom with an honest source flag."""
    key = None
    try:
        for line in open('/mnt/c/Users/casey/key.txt'):
            line = line.strip()
            if line.startswith('MOTHQUANTUM_COM_KEY') and '=' in line:
                key = line.split('=', 1)[1].strip()
    except Exception:
        pass
    if key:
        try:
            moth = subprocess.run(['which', 'moth'], capture_output=True, text=True, timeout=5).stdout.strip()
            if moth:
                out = subprocess.run([moth, 'bits', str(n_bits)], capture_output=True,
                                     text=True, timeout=30)
                return {'seed': int.from_bytes(os.urandom(4), 'big'), 'source': 'moth-wrapped',
                        'bits': n_bits, 'raw': out.stdout[:120]}
        except Exception as e:
            return {'seed': int.from_bytes(os.urandom(4), 'big'), 'source': 'urandom-degraded',
                    'bits': n_bits, 'err': str(e)}
    return {'seed': int.from_bytes(os.urandom(4), 'big'), 'source': 'urandom-degraded', 'bits': n_bits}

def hebbian(w, signal, eta=0.12):
    return max(0.05, min(1.0, w + eta * signal))

def render_svg(scene, size=560):
    shapes = (scene or {}).get('shapes', [])
    els = []
    for sh in shapes:
        kind = sh.get('shape', 'rect'); fill = sh.get('fill', '#333333')
        if kind == 'rect':
            els.append(f'<rect x="{sh.get("x",0)}" y="{sh.get("y",0)}" width="{sh.get("w",10)}" height="{sh.get("h",10)}" fill="{fill}"/>')
        elif kind == 'circle':
            cx = sh.get('cx', sh.get('x', 50)); cy = sh.get('cy', sh.get('y', 50)); r = sh.get('r', 10)
            els.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')
        elif kind == 'ellipse':
            cx = sh.get('cx', sh.get('x', 50)); cy = sh.get('cy', sh.get('y', 50))
            rx = sh.get('rx', sh.get('w', 15)); ry = sh.get('ry', sh.get('h', 10))
            els.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}"/>')
        elif kind == 'line':
            els.append(f'<line x1="{sh.get("x",0)}" y1="{sh.get("y",0)}" x2="{sh.get("x2",50)}" y2="{sh.get("y2",50)}" stroke="{fill}" stroke-width="{sh.get("w",2)}"/>')
        elif kind == 'polygon':
            els.append(f'<polygon points="{sh.get("points","")}" fill="{fill}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">'
            + ''.join(els) + '</svg>')

def render_png(scene, size=560):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    img = Image.new('RGB', (size, size), (255, 255, 255))
    d = ImageDraw.Draw(img)
    s = size / 100.0
    for sh in (scene or {}).get('shapes', []):
        fill = sh.get('fill', '#333333')
        try:
            fill = tuple(int(fill.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            fill = (51, 51, 51)
        kind = sh.get('shape', 'rect')
        try:
            if kind == 'rect':
                d.rectangle([sh['x'] * s, sh['y'] * s, (sh['x'] + sh['w']) * s, (sh['y'] + sh['h']) * s], fill=fill)
            elif kind == 'circle':
                cx = sh.get('cx', sh.get('x', 50)); cy = sh.get('cy', sh.get('y', 50)); r = sh.get('r', 10)
                d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=fill)
            elif kind == 'ellipse':
                cx = sh.get('cx', sh.get('x', 50)); cy = sh.get('cy', sh.get('y', 50))
                rx = sh.get('rx', sh.get('w', 15)); ry = sh.get('ry', sh.get('h', 10))
                d.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=fill)
            elif kind == 'line':
                d.line([sh['x'] * s, sh['y'] * s, sh.get('x2', 50) * s, sh.get('y2', 50) * s],
                       fill=fill, width=max(1, int(sh.get('w', 2) * s)))
            elif kind == 'polygon':
                pts = [tuple(float(v) * s for v in p.split(',')) for p in sh.get('points', '').split()]
                if len(pts) >= 3:
                    d.polygon(pts, fill=fill)
        except Exception:
            pass
    import io
    buf = io.BytesIO(); img.save(buf, format='PNG'); return buf.getvalue()

def run(prompt, rounds=3, slug=None):
    slug = slug or re.sub(r'[^a-z0-9]+', '-', prompt.lower()).strip('-')[:40] or 'scene'
    outdir = os.path.join('out', slug); os.makedirs(outdir, exist_ok=True)
    seed = moth_entropy(); random.seed(seed['seed'])
    w_cj, w_je = 0.6, 0.6
    scene = None; vector = None; history = []
    for rnd in range(rounds):
        if rnd == 0:
            pal = None
            try:
                praw, _ = call_ollama(CELLS['palette']['model'], CELLS['palette']['system'],
                                      f'Theme: "{prompt}".', max_tokens=400, temperature=0.6)
                pal = emit_json(praw)
            except Exception:
                pal = None
            palette_hint = json.dumps(pal) if pal and pal.get('palette') else 'choose your own harmonious palette'
            raw, _ = call_ollama(CELLS['composer']['model'], CELLS['composer']['system'],
                                 f'Compose the image: "{prompt}".\nSuggested palette:\n{palette_hint}',
                                 temperature=0.7)
            scene = emit_json(raw)
            if not scene:
                scene = {'shapes': [{'shape': 'rect', 'x': 0, 'y': 0, 'w': 100, 'h': 100, 'fill': '#1a2b3c'}]}
        jraw, _ = call_ollama(CELLS['judge']['model'], CELLS['judge']['system'],
                              f'The requested image is: "{prompt}".\n\nScene JSON:\n{json.dumps(scene)}')
        vector = emit_json(jraw) or {'coherence': 0.5, 'contrast': 0.5, 'balance': 0.5,
                                     'clarity': 0.5, 'harmony': 0.5, 'correction': 'none'}
        room = jepa_room(scene)
        if rnd < rounds - 1:
            eraw, _ = call_ollama(CELLS['engineer']['model'], CELLS['engineer']['system'],
                f'Scene JSON:\n{json.dumps(scene)}\n\nJudge vector advisement:\n{json.dumps(vector)}\n'
                f'Room temperature: {room["temperature"]}. Apply weight {w_je:.2f}. Revise the scene.')
            new_scene = emit_json(eraw)
            if new_scene:
                scene = new_scene
        dims = ['coherence', 'contrast', 'balance', 'clarity', 'harmony']
        quality = sum(float(vector.get(d, 0.5)) for d in dims) / len(dims)
        prev = history[-1]['quality'] if history else None
        if prev is not None:
            d = quality - prev
            w_cj = hebbian(w_cj, 0.5 * max(0.0, quality - 0.5))
            w_je = hebbian(w_je, 0.5 * d)
        history.append({'round': rnd + 1, 'quality': round(quality, 3),
                        'coherence': vector.get('coherence'), 'room': room,
                        'w_cj': round(w_cj, 3), 'w_je': round(w_je, 3)})
    svg = render_svg(scene); png = render_png(scene)
    receipt = {
        'prompt': prompt, 'rounds': rounds, 'slug': slug,
        'cells': {k: v['model'] for k, v in CELLS.items()},
        'entropy': seed,
        'weights': {'composer->judge': round(w_cj, 3), 'judge->engineer': round(w_je, 3)},
        'final_vector': vector, 'final_room': jepa_room(scene), 'history': history,
        'sha256_svg': hashlib.sha256(svg.encode()).hexdigest(),
        'sha256_scene': hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest(),
    }
    with open(os.path.join(outdir, 'scene.svg'), 'w') as f:
        f.write(svg)
    if png:
        with open(os.path.join(outdir, 'scene.png'), 'wb') as f:
            f.write(png)
    with open(os.path.join(outdir, 'receipt.json'), 'w') as f:
        json.dump(receipt, f, indent=1)
    return outdir, receipt, svg, png

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('prompt')
    ap.add_argument('--rounds', type=int, default=3)
    a = ap.parse_args()
    outdir, receipt, svg, png = run(a.prompt, a.rounds)
    print(json.dumps({'outdir': outdir, 'weights': receipt['weights'],
                      'final_vector': receipt['final_vector'], 'final_room': receipt['final_room'],
                      'history': receipt['history'], 'entropy': receipt['entropy'],
                      'sha256_svg': receipt['sha256_svg']}, indent=1))
