# Shaders, Perspective Math & Optics Reference

Core WebGL2 / Three.js r186+ building blocks for a color-true 60 fps 2.5D Living Frame diorama.

---

## 1. Exact Perspective-Locked Plate Scaling

Every depth plate placed at world `z` must scale by `(d - z) / d` (where `d = 5.0` is camera distance) so that at rest (`camera.position = (0, 0, d)`), all plates project 1:1 onto the exact pixels of the original image:

```ts
const worldH = 2.0;
const worldW = worldH * (imgW / imgH);
const camDist = 5.0;
const overscan = 1.055; // hides edges during ±0.24 parallax shift

const makePlateGeo = (z: number, segX: number, segY: number) => {
  const scale = (camDist - z) / camDist;
  return new THREE.PlaneGeometry(worldW * scale, worldH * scale, segX, segY);
};
```

For viewport cover-fit that keeps the **Original JPEG** and **Before/After Split-Compare** pixel-aligned with the live 3D projection:

```ts
let fovScale = 1.0;
let cropScaleX = 1.0 / overscan;
let cropScaleY = 1.0 / overscan;
if (viewAspect > artAspect) {
  fovScale = artAspect / viewAspect;
  cropScaleY = (artAspect / viewAspect) / overscan;
} else {
  cropScaleX = (viewAspect / artAspect) / overscan;
}
const visibleH = (worldH / overscan) * fovScale;
baseFov = THREE.MathUtils.radToDeg(2 * Math.atan(visibleH / (2 * camDist)));
// Pass uUvCrop = vec4(cropScaleX, cropScaleY, (1 - cropScaleX) * 0.5, (1 - cropScaleY) * 0.5)
```

---

## 2. Color-True sRGB Pipeline (No Gamma Washout)

To preserve anime/illustration ink work and painterly palette fidelity (`rgbCorr > 0.99`):
- Set `renderer.outputColorSpace = THREE.SRGBColorSpace` and `renderer.toneMapping = THREE.NoToneMapping`.
- Load all artwork textures with `tex.colorSpace = THREE.NoColorSpace`, `generateMipmaps = false`, `minFilter = magFilter = THREE.LinearFilter`.
- Render the live scene into a `THREE.HalfFloatType` `WebGLRenderTarget` and run a separate half-resolution **selective emissive pass** (`uEmissivePass = 1.0`) so bloom adds *only* from explicitly masked emissive regions (neon, blades, lanterns, flames, crystals) with zero skin/dry-area bleed.

---

## 3. Neighborhood-Clamped 5-Tap CAS Sharpening

Apply adaptive Contrast Adaptive Sharpening on deformed character/cloth meshes (`strength` ~ `0.32–0.72` scaled by vertex displacement magnitude) so vertex animation never blurs painted lines:

```glsl
vec3 casSample(sampler2D tex, vec2 uv, vec2 texel, float strength) {
  vec3 c = texture2D(tex, uv).rgb;
  vec3 n = texture2D(tex, uv + vec2(0.0, texel.y)).rgb;
  vec3 s = texture2D(tex, uv - vec2(0.0, texel.y)).rgb;
  vec3 e = texture2D(tex, uv + vec2(texel.x, 0.0)).rgb;
  vec3 w = texture2D(tex, uv - vec2(texel.x, 0.0)).rgb;
  vec3 mn = min(c, min(min(n, s), min(e, w)));
  vec3 mx = max(c, max(max(n, s), max(e, w)));
  vec3 avg = (n + s + e + w) * 0.25;
  return clamp(c + (c - avg) * strength, mn, mx);
}
```

---

## 4. 128×72 Live2D Character Vertex Rig & 3-Stage Eye Blink

- **Breathing (`mask_motion.b`):** Subtle vertical lift + radial chest expansion (`sin(t * 1.65)`).
- **Rigid Head Pivot (`mask_region.b`):** Aspect-corrected 2D rotation around `uNeckPivot` so facial anatomy never stretches like rubber.
- **Hair Wind Sway (`mask_motion.g`):** Multi-harmonic wave masked to 0 at the scalp crown and 0 over the eye sockets.
- **Cursor Gaze & 3-Stage Asymmetric Blink:**
  - Clamp iris UV drift tightly (`±0.0022` UV) inside each eye ellipse.
  - Drive `uBlink` through 3 stages: fast snap close (`34%`), brief closed hold (`14%`), smooth ease-out open (`52%`), with occasional double-blinks. Blend `eyelid_patch.png` top-down across each eye ellipse.

---

## 5. Tactile Spring-Damper Cloth / Hanging Props

Use a 6-node 1D spring-damper chain (`stiffness ~ 24`, `damping ~ 4.2`, neighbor coupling `~ 12`) fed by both traveling wind gusts and cursor velocity impulses. Pass `uDisp[6]` to the vertex shader and modulate by `mask_motion.r` (0 at pinned rod/shoulder root → 1 at free tip).

---

## 6. 256×256 `HalfFloat` Ping-Pong GPU Shallow-Water / Energy Wave PDE

Use two `256×256` `RGBAFormat` + `HalfFloatType` render targets (`R = hCur`, `G = hPrev`, `B = dH/dx`, `A = dH/dy`):
- Clamp neighbor samples inside `[texel, 1 - texel]` (or wall masks) for reflective **Neumann boundaries**.
- Update `hNext = ((hL + hR + hD + hU) * 0.5 - hPrev) * 0.978`.
- Inject up to 4 Gaussian impulses per frame from cursor drags, raindrops/drips, or light surges.
- Sample `rip.ba` in the wet-surface or post-processing shader to perturb reflections or arcane air refraction.

---

## 7. Single-Pass Optical Post & Split-Compare Curtain

In the final fullscreen quad:
- Support 6 inspector modes via `uniform int uRenderMode`: `0 = Final`, `1 = No-Post`, `2 = Depth` (Inferno palette), `3 = Masks` (color-coded stencil overlay), `4 = Emissive` (isolated glow pass), `5 = Original` (raw static image).
- When `uCompareActive > 0.5 && vUv.x < uCompareSplit`, output `texture2D(uOriginalTex, clampedArtUv)` directly so dragging the vertical divider compares the untouched original JPEG pixel-for-pixel against the live WebGL2 scene.
