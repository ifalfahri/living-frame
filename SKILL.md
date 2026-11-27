---
name: living-frame
description: >-
  Turn any single static image (anime, illustration, game splash art, or photo) into
  an interactive 60 fps 2.5D living WebGL2 diorama with local AI depth estimation,
  perspective-locked parallax plates, hidden-background inpainting, semantic pixel
  stencils, custom GLSL shaders, tactile physics, procedural spatial Web Audio, and a
  draggable Before/After Split-Compare HUD. Use when the user asks to animate a static
  image into a 2.5D diorama, living wallpaper, parallax showcase, or Shinya Ramen-style
  WebGL2 scene.
license: MIT
metadata:
  author: ifalfahri
  version: "1.0.0"
---

# Living Frame — Single-Image to 60 fps 2.5D WebGL2 Diorama

Turn a single static JPEG/PNG into a color-true, interactive 60 fps Three.js WebGL2 2.5D living diorama—with zero AI video generation, zero looping MP4s, and zero external audio files.

> **Architecture lineage:** Adapted from Ashutosh Shrivastava's [Shinya Ramen (深夜ラーメン) 2.5D Diorama](https://ashutoshai.com/showcase/d/shinya-ramen) engineering showcase.

---

## Workflow Overview

Execute these six phases in order. Never guess image coordinates or skip visual inspection of sliced plates.

### Phase 1 — Inspect Image & Measure Landmarks
1. Check image dimensions (`W × H`, aspect ratio) and local toolchain (`uv` or `venv`, `node`/`npm`, Apple Silicon MPS / CUDA / CPU).
2. Run [`scripts/grid_overlay.py`](./scripts/grid_overlay.py) on the source image to generate a normalized `0.0–1.0` coordinate grid overlay and **visually inspect it**.
3. Classify the scene using [`references/scene-archetypes.md`](./references/scene-archetypes.md) and commit to a concrete plan:
   - **3 to 5 depth plates** (`layer0_bg` backmost → foreground cutouts) with explicit `z` values.
   - **Exact normalized anchors** (`x, y` in `[0, 1]`, top-down) for eyes, pivots, light sources, cloth roots, water/puddle boundaries, or interactive props.
   - **Packed RGB semantic stencils** (`mask_emissive.png`, `mask_motion.png`, `mask_region.png`) so every shader effect stays strictly inside its true region with zero leaking.

### Phase 2 — Build & Run Local AI Asset Pipeline (Python)
Create a project-isolated Python 3.12 environment (`uv init --python 3.12` or `.venv`) with `torch`, `torchvision`, `transformers`, `pillow`, `numpy`, `scipy`, `opencv-python-headless`, `rembg`, and `onnxruntime`.

Adapt [`scripts/pipeline_template.py`](./scripts/pipeline_template.py) for the scene's specific plates and masks:
1. **Local Guided Depth:** Run `depth-anything/Depth-Anything-V2-Small-hf` (fast, ~99 MB) or `Depth-Anything-V2-Large-hf` (highest detail, ~1.34 GB) on `mps` / `cuda` / `cpu`, then sharpen boundaries against RGB edges with an OpenCV RGB-guided filter.
   - **Important:** Run with `HF_HUB_DISABLE_XET=1` to avoid Xet CDN signed-URL `403 Forbidden` drops on slow connections.
2. **Foreground Matting & Plate Slicing:** Extract clean foreground alpha via `rembg` (`isnet-general-use`), then slice scene-specific depth plates (e.g., cloth/hanging layer, character plate, closest foreground prop) with GrabCut / HSV / polygon refinement.
3. **14 px RGB Edge-Bleed Dilation:** On every transparent plate, bleed foreground RGB colors outward into transparent pixels via Euclidean distance transform (`scipy.ndimage.distance_transform_edt`) so WebGL bilinear sampling never creates dark edge halos.
4. **Painterly Background Inpainting (`layer0_bg.png`):** Reconstruct hidden background behind every cutout using multi-scale OpenCV Telea + subtle isotropic grain. Avoid mirror-tiling textures (which create visible kaleidoscope diamonds).
5. **Occluded Under-Layer Overlap:** Where a foreground plate overlaps a midground plate, keep clean pixels underneath (inpainting strictly inside the eroded solid foreground footprint) so camera parallax never opens seams while rest-pose registration stays crisp (`rgb_corr > 0.985`).
6. **Optional 8×-Supersampled Eyelid Patch:** If a character blinks, synthesize a skin-matched closed-eyelid patch (`eyelid_patch.png`) with curved lash lines tightly fitted to each orbital socket.
7. **Export `anchors.json` & Contact Sheet:** Save normalized coordinates, plate depths, and a 2×3 `pipeline_contact_sheet.png`.

### Phase 3 — Visual Quality Gate on Plates & Masks
**Mandatory:** Visually inspect `pipeline_contact_sheet.png` (and `eyelid_patch.png` if present) before moving to WebGL2. Fix any defect immediately:
- Floating disconnected specks on cloth/prop plates → keep largest connected component(s).
- Ghost slivers of foreground props left on lower plates → dilate the open-background subtraction ROI.
- Halo fringes or muddy inpainting near silhouette rims → tighten dilation/blend radius and re-run (cached models re-run in ~6 seconds).

### Phase 4 — Build the 60 fps WebGL2 / Three.js Engine
Scaffold a Vite + TypeScript + Three.js (`three@^0.186.0`) app using the shader and math patterns in [`references/shaders-and-optics.md`](./references/shaders-and-optics.md):
- **Perspective-Locked Registration:** Scale every plate at depth `z` by exact `(d - z) / d` (with `d = 5.0` and `1.04–1.06` parallax overscan) so all plates register 1:1 with the original image at rest.
- **Color-True Pipeline:** Set `renderer.outputColorSpace = THREE.SRGBColorSpace`, `renderer.toneMapping = THREE.NoToneMapping`, and `tex.colorSpace = THREE.NoColorSpace` for raw sRGB pass-through so artwork colors and ink lines never wash out.
- **Deterministic 60 Hz Simulation:** Fixed-timestep (`1/60 s`, seeded PRNG) driving camera parallax (`Cinematic Drift` / `Mouse Parallax` + pointer drag + clamped `1.0×–1.18×` wheel zoom), Live2D character vertex rig (`128×72` breathing, rigid neck-pivot head tilt/nod, hair breeze, cursor gaze, 3-stage asymmetric blinking + 5-tap CAS sharpening), tactile spring-damper cloth/props, narrative ambient events, and interactive click/swipe toys.
- **256×256 `HalfFloatType` Ping-Pong GPU Wave PDE:** Drive interactive puddle ripples, water reflections, or arcane air refraction with reflective Neumann boundaries.
- **Single-Pass Optical Post + Split-Compare:** Selective multi-mask emissive bloom (dedicated half-res emissive pass so bloom never bleeds onto skin/dry surfaces), subtle thermal/wave refraction, draggable **Before/After Original JPEG vs. Live 2.5D Split-Compare Curtain**, and 6 Inspector render modes (`Final`, `No-Post`, `Depth`, `Masks`, `Emissive`, `Original`).

### Phase 5 — Add Procedural Spatial Web Audio & Smoked-Glass HUD
Follow [`references/audio-and-hud.md`](./references/audio-and-hud.md):
- **Zero-Asset Web Audio API:** Synthesize scene-authentic stereo ambience (filtered pink noise weather/fire/wind, harmonic drones, interactive click/swipe one-shots, plus an optional toggleable ambient radio/synth pad) with `StereoPannerNode` panning tied to camera parallax.
- **Cinema Glass HUD:** Compact top bar (`FPS`, `Controls`, `Compare [C]`, `Pause [Space]`, `Audio [M]`, `Hide [H]`), collapsible drawer (4 mood presets, 5 atmosphere sliders, camera mode toggle, narrative event trigger, reset button), expandable **Inspector & Extras (`D`)** with 6 render passes and 7 per-layer toggles, plus unclipped `375×812` mobile bottom-sheet layout.

### Phase 6 — Build & Live Browser Verification
1. Run `npm run build` (`tsc --noEmit && vite build`) and confirm zero TypeScript or bundler errors.
2. Start the Vite dev server and inspect the live page in a real browser:
   - Verify **0 console errors**, **0 WebGL/GLSL compilation errors**, and **0 failed asset requests (HTTP 200)**.
   - Confirm smooth motion, clean parallax seams, strict mask containment (zero effect bleed), interactive click/swipe responses, mood presets, `Depth`/`Masks` inspector passes, and Before/After Split-Compare alignment.
   - Visually inspect a clean screenshot of the live scene before delivering to the user.
