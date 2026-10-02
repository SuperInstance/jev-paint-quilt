# jev-paint-quilt — JEV vector-advisement painting (local, no metered spend)

An enhanced take on achimala/jev-paint. The original sends per-pixel *probability*
questions to a single TypeSafe Jev model. This version replaces that with a **local cell
graph** where the JEV judge pulses **vector advisements**, JEPA reads the whole-canvas
"room", mothquantum seeds entropy, and Hebbian edges grow round-over-round.

## The core shift
- Old: one model, N scalar questions (pixel → choice/noul/score probabilities).
- New: a graph of local cells (tev1, qwen2.5:3b/7b), each with an ENGINEER prompt, that
  emit **results to questions** and cycle through a program while a JEV cell pulses
  **advisement as a vector** into them.

## Architecture
1. **Cells = local models with engineer prompts.** `composer` (3b) proposes a scene,
   `engineer` (7b) revises it, `judge` (7b, the JEV) reviews it. tev1:0.8b/4b slot in as
   cheap composer/palette cells.
2. **JEV pulses VECTOR advisement** — not a scalar yes/no. The judge emits
   `{coherence, contrast, balance, clarity, harmony, correction}`. That vector is
   PROJECTED into the next cell (scaled by the edge weight), exactly like jev-net's prism.
3. **JEPA room** — the whole canvas is the unit of perception. We compute a global
   `temperature` = f(color entropy, coverage) and modulate the next round's sampling, so
   each cell fires in the *context of the whole image*, not its local patch.
4. **mothquantum** — seeds the stochastic sampling (jitter / tie-breaks / temperature
   jitter) and the receipt is hash-bound (sha256 over scene + svg + entropy).
5. **Hebbian growth** — edges `composer→judge` and `judge→engineer` update via
   `w += η·signal` (η=0.12, clamp [0.05,1.0]); the engineer is reinforced when it raises
   coherence, the composer when it lands coherent on the first pass. The local system
   *grows*: its trust structure changes in response to its own judge's vectors.
6. **The cycling program** — compose → judge(vector) → project → engineer → recompose,
   N rounds, weights recorded every round (the trajectory IS the growth).

## Output
`out/<slug>/scene.svg` + `scene.png` + `receipt.json` (hash-bound, full history).
Run: `python3 quilt.py "a red boat on a dark sea" --rounds 3`.

## Honest limits
- Local models emit SVG-scene JSON, not calibrated per-pixel probabilities — this is an
  *artistic* composition engine, faithful to the original's "artistic transformation, not
  a lossless probability chart" line.
- mothquantum degrades to urandom with an honest `source` flag if the MOTH wrapper isn't
  reachable; the receipt records which.
