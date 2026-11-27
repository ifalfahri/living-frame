#!/usr/bin/env python3
"""
Living Frame — Reusable Offline AI Depth, Foreground Matting, Edge-Bleed,
Multi-Scale Background Inpainting, Eyelid Patch & Contact-Sheet Template.

Adapt the scene-specific ROI polygons in `slice_scene_plates()` and
`build_semantic_masks()` after inspecting the image with `grid_overlay.py`.

Run inside a Python 3.12 uv/venv environment with:
    HF_HUB_DISABLE_XET=1 uv run python pipeline/generate_assets.py --input assets/source.jpg --out public/assets
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage


def guided_filter_rgb(guide_rgb: np.ndarray, src: np.ndarray, radius: int = 8, eps: float = 1e-3) -> np.ndarray:
    """Fast edge-preserving RGB-guided filter using OpenCV boxFilter."""
    I = guide_rgb.astype(np.float32) / 255.0
    p = src.astype(np.float32)
    ksize = (2 * radius + 1, 2 * radius + 1)

    I_r, I_g, I_b = I[:, :, 0], I[:, :, 1], I[:, :, 2]

    mean_I_r = cv2.boxFilter(I_r, -1, ksize)
    mean_I_g = cv2.boxFilter(I_g, -1, ksize)
    mean_I_b = cv2.boxFilter(I_b, -1, ksize)
    mean_p = cv2.boxFilter(p, -1, ksize)

    cov_Ip_r = cv2.boxFilter(I_r * p, -1, ksize) - mean_I_r * mean_p
    cov_Ip_g = cv2.boxFilter(I_g * p, -1, ksize) - mean_I_g * mean_p
    cov_Ip_b = cv2.boxFilter(I_b * p, -1, ksize) - mean_I_b * mean_p

    var_rr = cv2.boxFilter(I_r * I_r, -1, ksize) - mean_I_r * mean_I_r + eps
    var_rg = cv2.boxFilter(I_r * I_g, -1, ksize) - mean_I_r * mean_I_g
    var_rb = cv2.boxFilter(I_r * I_b, -1, ksize) - mean_I_r * mean_I_b
    var_gg = cv2.boxFilter(I_g * I_g, -1, ksize) - mean_I_g * mean_I_g + eps
    var_gb = cv2.boxFilter(I_g * I_b, -1, ksize) - mean_I_g * mean_I_b
    var_bb = cv2.boxFilter(I_b * I_b, -1, ksize) - mean_I_b * mean_I_b + eps

    inv_rr = var_gg * var_bb - var_gb * var_gb
    inv_rg = var_rb * var_gb - var_rg * var_bb
    inv_rb = var_rg * var_gb - var_rb * var_gg
    inv_gg = var_rr * var_bb - var_rb * var_rb
    inv_gb = var_rg * var_rb - var_rr * var_gb
    inv_bb = var_rr * var_gg - var_rg * var_rg

    det = np.maximum(var_rr * inv_rr + var_rg * inv_rg + var_rb * inv_rb, 1e-8)

    a_r = (inv_rr * cov_Ip_r + inv_rg * cov_Ip_g + inv_rb * cov_Ip_b) / det
    a_g = (inv_rg * cov_Ip_r + inv_gg * cov_Ip_g + inv_gb * cov_Ip_b) / det
    a_b = (inv_rb * cov_Ip_r + inv_gb * cov_Ip_g + inv_bb * cov_Ip_b) / det

    b = mean_p - a_r * mean_I_r - a_g * mean_I_g - a_b * mean_I_b
    q = (
        cv2.boxFilter(a_r, -1, ksize) * I_r
        + cv2.boxFilter(a_g, -1, ksize) * I_g
        + cv2.boxFilter(a_b, -1, ksize) * I_b
        + cv2.boxFilter(b, -1, ksize)
    )
    return np.clip(q, 0.0, 1.0)


def estimate_depth_local(pil_img: Image.Image, model_id: str = "depth-anything/Depth-Anything-V2-Small-hf") -> np.ndarray:
    """Estimate normalized [0..1] monocular relative depth locally (MPS / CUDA / CPU)."""
    import torch
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    print(f"[depth] Loading {model_id} on {device}...")
    t0 = time.time()
    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModelForDepthEstimation.from_pretrained(model_id).to(device)
    model.eval()

    inputs = processor(images=pil_img, return_tensors="pt").to(device)
    with torch.no_grad():
        predicted_depth = model(**inputs).predicted_depth

    w, h = pil_img.size
    pred = torch.nn.functional.interpolate(
        predicted_depth.unsqueeze(1), size=(h, w), mode="bicubic", align_corners=False
    ).squeeze().cpu().numpy()

    lo, hi = np.percentile(pred, [1.0, 99.5])
    depth_norm = np.clip((pred - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    print(f"[depth] Done in {time.time() - t0:.2f}s")
    return depth_norm.astype(np.float32)


def extract_foreground_alpha(pil_img: Image.Image, rgb: np.ndarray, model_name: str = "isnet-general-use") -> np.ndarray:
    """Extract clean foreground alpha matte via rembg + RGB-guided edge refinement."""
    from rembg import new_session, remove

    print(f"[seg] Running rembg ({model_name})...")
    t0 = time.time()
    session = new_session(model_name)
    rgba = remove(pil_img, session=session, alpha_matting=False)
    alpha = np.array(rgba)[:, :, 3].astype(np.float32) / 255.0
    alpha = guided_filter_rgb(rgb, alpha, radius=3, eps=5e-4)
    alpha = np.clip((alpha - 0.06) / 0.88, 0.0, 1.0)
    print(f"[seg] Done in {time.time() - t0:.2f}s (coverage={alpha.mean() * 100:.1f}%)")
    return alpha.astype(np.float32)


def norm_poly(w: int, h: int, pts: list[tuple[float, float]]) -> np.ndarray:
    """Rasterize a normalized [0..1] polygon into a uint8 (0/255) mask."""
    arr = np.array([[int(round(x * w)), int(round(y * h))] for x, y in pts], dtype=np.int32)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [arr], 255)
    return mask


def keep_largest_component(mask: np.ndarray, threshold: float = 0.25) -> np.ndarray:
    """Remove stray floating matting specks by retaining only the largest connected component."""
    num, labels, stats, _ = cv2.connectedComponentsWithStats((mask > threshold).astype(np.uint8), connectivity=8)
    if num <= 1:
        return mask
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = cv2.dilate((labels == largest).astype(np.float32), np.ones((5, 5), np.uint8))
    return mask * keep


def edge_bleed_rgb(rgb: np.ndarray, alpha: np.ndarray, radius_px: int = 14) -> np.ndarray:
    """Bleed foreground RGB outward into transparent pixels to prevent WebGL bilinear edge halos."""
    solid = alpha > 0.35
    if not np.any(solid):
        return rgb.copy()
    dist, indices = ndimage.distance_transform_edt(~solid, return_indices=True)
    bled = rgb[indices[0], indices[1]]
    out = rgb.copy()
    bleed_zone = (~solid) & (dist <= radius_px)
    out[bleed_zone] = bled[bleed_zone]
    soft_edge = (alpha > 0.0) & (~solid) & (dist <= 3.0)
    blend = np.clip(alpha[soft_edge] / 0.35, 0.0, 1.0)[:, None]
    out[soft_edge] = (rgb[soft_edge] * blend + bled[soft_edge] * (1.0 - blend)).astype(np.uint8)
    return out


def save_rgba_plate(path: Path, rgb: np.ndarray, alpha: np.ndarray, bleed_px: int = 14) -> None:
    bled = edge_bleed_rgb(rgb, alpha, radius_px=bleed_px)
    a8 = np.clip(np.round(alpha * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([bled, a8]), mode="RGBA").save(path, optimize=True)


def inpaint_background(rgb: np.ndarray, fg_alpha: np.ndarray, dilate_px: int = 17) -> np.ndarray:
    """
    Multi-scale OpenCV Telea inpainting + subtle isotropic film grain.
    Avoids mirror-tiling artifacts while keeping unoccluded background pixels 100% original.
    """
    h, w, _ = rgb.shape
    hole = (fg_alpha > 0.05).astype(np.uint8)
    hole_dil = cv2.dilate(hole, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px)))

    small_rgb = cv2.resize(rgb, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(hole_dil, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_NEAREST)
    coarse = cv2.inpaint(small_rgb, (small_mask * 255).astype(np.uint8), 11, cv2.INPAINT_TELEA)
    coarse_bg = cv2.GaussianBlur(cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32), (31, 31), 9.0)

    telea_full = cv2.inpaint(rgb, (hole_dil * 255).astype(np.uint8), 9, cv2.INPAINT_TELEA).astype(np.float32)

    rng = np.random.default_rng(19890417)
    grain = cv2.GaussianBlur(rng.normal(0.0, 2.2, size=(h, w, 1)).astype(np.float32), (3, 3), 0.7)[:, :, None]

    dist_in = ndimage.distance_transform_edt(hole_dil > 0)
    inner_w = np.clip((dist_in - 12.0) / 36.0, 0.0, 1.0)[:, :, None]
    filled = telea_full * (1.0 - inner_w) + (coarse_bg + grain) * inner_w

    soft_hole = cv2.GaussianBlur(hole_dil.astype(np.float32), (7, 7), 1.8)[:, :, None]
    out = rgb.astype(np.float32) * (1.0 - soft_hole) + filled * soft_hole
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def build_eyelid_patch(rgb: np.ndarray, eyes: list[dict]) -> np.ndarray:
    """
    Generate an 8x-supersampled closed-eyelid patch for natural 3-stage blinking.
    Each eye dict: {"cx": float, "cy": float, "rx": float, "ry": float, "tilt": float}
    """
    h, w, _ = rgb.shape
    patch = rgb.copy().astype(np.float32)
    for eye in eyes:
        cx, cy = int(eye["cx"] * w), int(eye["cy"] * h)
        rx, ry = max(4, int(eye["rx"] * w)), max(3, int(eye["ry"] * h))
        skin_box = rgb[max(0, cy - ry * 2):max(1, cy - int(ry * 0.9)), max(0, cx - rx):min(w, cx + rx)]
        skin_med = np.median(skin_box.reshape(-1, 3), axis=0).astype(np.float32)
        lid_shadow = skin_med * np.array([0.82, 0.78, 0.76], dtype=np.float32)
        lash_color = np.array([34.0, 24.0, 22.0], dtype=np.float32)

        ss = 8
        pw, ph = rx * 3, ry * 3
        yy, xx = np.mgrid[-ph * ss:ph * ss, -pw * ss:pw * ss].astype(np.float32) / ss
        cos_t, sin_t = np.cos(eye.get("tilt", 0.0)), np.sin(eye.get("tilt", 0.0))
        ux = (xx * cos_t + yy * sin_t) / rx
        uy = (-xx * sin_t + yy * cos_t) / ry

        almond = np.sqrt((ux * 0.95) ** 2 + (uy * 1.05) ** 2)
        cover = np.clip((1.18 - almond) / 0.35, 0.0, 1.0)
        lash_dist = np.abs(uy - (0.24 - 0.22 * (ux ** 2)))
        lash = np.clip((0.20 - lash_dist) / 0.14, 0.0, 1.0) * np.clip((1.05 - np.abs(ux)) / 0.25, 0.0, 1.0)
        crease = np.clip((0.14 - np.abs(uy - (-0.35 - 0.18 * (ux ** 2)))) / 0.12, 0.0, 1.0) * np.clip((0.95 - np.abs(ux)) / 0.3, 0.0, 1.0)

        grad = np.clip((uy + 0.8) / 1.6, 0.0, 1.0)[:, :, None]
        lid_rgb = skin_med * (1.0 - grad * 0.18) + lid_shadow * (grad * 0.18)
        lid_rgb = lid_rgb * (1.0 - crease[:, :, None] * 0.25)
        lid_rgb = lid_rgb * (1.0 - lash[:, :, None] * 0.88) + lash_color * (lash[:, :, None] * 0.88)

        lid_1x = cv2.resize(lid_rgb, (pw * 2, ph * 2), interpolation=cv2.INTER_AREA)
        cov_1x = cv2.resize(cover, (pw * 2, ph * 2), interpolation=cv2.INTER_AREA)[:, :, None]
        y0, y1, x0, x1 = cy - ph, cy + ph, cx - pw, cx + pw
        patch[y0:y1, x0:x1] = patch[y0:y1, x0:x1] * (1.0 - cov_1x) + lid_1x * cov_1x

    return np.clip(np.round(patch), 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description="Living Frame generic 2-plate starter pipeline")
    ap.add_argument("--input", required=True, help="Path to source image (JPEG/PNG)")
    ap.add_argument("--out", default="public/assets", help="Output directory for WebGL2 assets")
    ap.add_argument("--model", default="depth-anything/Depth-Anything-V2-Small-hf", help="HuggingFace depth model ID")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pil_img = Image.open(src).convert("RGB")
    w, h = pil_img.size
    rgb = np.array(pil_img)
    shutil.copy2(src, out / "source.jpg")

    raw_depth = estimate_depth_local(pil_img, model_id=args.model)
    guided_depth = guided_filter_rgb(rgb, raw_depth, radius=8, eps=1.2e-3)
    depth_u8 = np.clip(np.round(guided_depth * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(depth_u8, mode="L").save(out / "depth.png", optimize=True)

    fg_alpha = extract_foreground_alpha(pil_img, rgb)
    bg = inpaint_background(rgb, fg_alpha)
    Image.fromarray(bg, mode="RGB").save(out / "layer0_bg.png", optimize=True)
    save_rgba_plate(out / "layer1_fg.png", rgb, fg_alpha, bleed_px=14)

    # Rest-pose registration sanity check
    comp = bg.astype(np.float32) * (1.0 - fg_alpha[:, :, None]) + rgb.astype(np.float32) * fg_alpha[:, :, None]
    mad = float(np.mean(np.abs(comp - rgb.astype(np.float32))))
    corr = float(np.corrcoef(comp.flatten(), rgb.astype(np.float32).flatten())[0, 1])
    print(f"[verify] Rest composite vs original: mean_abs_diff={mad:.3f}/255, rgb_corr={corr:.5f}")

    anchors = {
        "width": w,
        "height": h,
        "aspect": round(w / h, 6),
        "cameraDistance": 5.0,
        "worldHeight": 2.0,
        "worldWidth": round(2.0 * (w / h), 6),
        "plates": {"bg": {"z": -0.36}, "fg": {"z": 0.22}},
        "metrics": {"restMeanAbsDiff": round(mad, 4), "restRgbCorr": round(corr, 6)},
    }
    (out / "anchors.json").write_text(json.dumps(anchors, indent=2))
    print(f"[done] Starter assets written to {out}")


if __name__ == "__main__":
    main()
