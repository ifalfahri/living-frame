# Procedural Spatial Web Audio & Smoked-Glass HUD Reference

---

## 1. Zero-Asset Spatial Web Audio API

Never bundle MP3/WAV files—synthesize 100% of the soundscape live via Web Audio API and unlock `AudioContext` on the user's first Audio toggle click:

- **Shared Pink-Noise Buffer (3 s seamless loop):** Generate once on init with a Paul Kellet 3-pole pinking filter so fire, rain, wind, cloth swooshes, and electric crackles all share one tiny in-memory buffer.
- **Parallax Stereo Panning:** Route directional sound beds through `StereoPannerNode` and dynamically shift pan slightly opposite camera movement (`pan = clamp(basePan - camX * 0.28, -0.95, 0.95)`).
- **Recommended 4-Layer Mix:**
  1. **Environmental Bed A (e.g., Rain / Left Brazier Fire / Ocean Surf):** Low-pass or band-pass pink noise + stochastic short crackle/drip bursts.
  2. **Environmental Bed B (e.g., Alley Wind / Hall Draft / Foliage Rustle):** Slowly LFO-swept resonant bandpass noise scaled by the `Wind` slider.
  3. **Signature Harmonic Drone (e.g., 120 Hz Neon Hum / Crystalline Blade Hum / Hearth Simmer):** Soft detuned sine/triangle oscillators behind a warm low-pass filter.
  4. **Interactive One-Shots & Optional Ambient Radio/Pad:** Trigger crisp transient bursts on canvas clicks/swipes (sparks, crystal chimes, puddle splashes, cloth whooshes) plus a toggleable low-pass generative chord pad or lo-fi Rhodes loop inside `Inspector & Extras`.

---

## 2. Smoked-Glass Cinema HUD Spec

Design a refined, non-intrusive HUD that lets the artwork breathe on both desktop and mobile (`375×812` zero horizontal overflow):

- **Top-Left Brand Pill:** Accent dot, short scene title, `2.5D LIVING FRAME` tag, and live `FPS` readout pill.
- **Top-Right Quick Toolbar:**
  - `Controls` (opens/closes smoked-glass drawer)
  - `Compare [C]` (toggles draggable Before/After Split-Compare curtain)
  - `Pause [Space]`
  - `Audio [M]`
  - `Hide [H]` (fades HUD completely; shows subtle `HUD hidden — press H to restore` pill)
- **Collapsible & Draggable Controls Drawer (`320px` desktop side sheet → bottom sheet on `<= 680px`):**
  - **Header-Only Dragging (Desktop `> 680px`):** Subtle `⋮⋮` grip + `grab`/`grabbing` cursor on `.drawer-header`, viewport-clamped (`12px` margin on drag and window resize), `stopPropagation()` so dragging never steers the 3D camera underneath, and double-click header (or `Reset Defaults`) to snap back to top-right. Disabled on mobile bottom-sheet (`<= 680px`).
  - **4 Director Mood Presets** tailored to the scene (e.g., balanced default, storm/overcharge, quiet midnight, warm glow/inferno).
  - **5 Atmosphere Sliders** (`0.00×` to `2.00×`, default `1.00×`, live monospace readout).
  - **Camera Steering Toggle:** `Cinematic Drift` (gentle default figure-eight orbit + relaxing pointer drag) vs. `Mouse Parallax`.
  - **Action Buttons:** One-click Narrative Event trigger (e.g., `⚡ Lightning` / `⚡ Arcane Surge`) + `Reset Defaults`.
  - **Accordion `Inspector & Extras [D]`:**
    - Toggle for optional procedural music/radio pad.
    - **6-Mode Render Pass Switcher:** `Final`, `No-Post`, `Depth`, `Masks`, `Emissive`, `Original`.
    - **7 Per-Layer Toggle Switches** matching the scene's shader passes.
  - **Footer Hint:** One-line list of canvas toys (`Swipe … · Click … · Drag canvas · Scroll to zoom · Press C to compare`).
