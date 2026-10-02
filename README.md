# jev-paint-quilt

An enhanced take on [achimala/jev-paint](https://github.com/achimala/jev-paint) that
replaces the single TypeSafe-Jev per-pixel probability call with a **local cell graph**:

- **Cells** = local models (tev1:0.8b, qwen2.5:7b) each with an ENGINEER prompt.
- **JEV pulses VECTOR advisements** (not scalar): `{coherence, contrast, balance, clarity, harmony, correction}`.
- **JEPA reads the whole-canvas "room"** (temperature = f(color entropy, coverage)) and modulates the next round.
- **mothquantum seeds entropy** (best-effort; degrades to urandom with an honest `source` flag).
- **Hebbian edges grow** (`composer→judge`, `judge→engineer`) round-over-round.
- The whole thing **cycles through a program**: compose → judge(vector) → project → engineer → recompose.

Run: `python3 quilt.py "a red boat on a dark sea at night" --rounds 3`
Output: `out/<slug>/scene.svg` + `scene.png` + `receipt.json` (hash-bound).

Architecture + honest limits: [DESIGN.md](DESIGN.md).
