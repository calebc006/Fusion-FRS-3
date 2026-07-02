"""
Single-image haze removal via Dark Channel Prior.
Classical (non-learned) algorithm from:
Kaiming He, Jian Sun, Xiaoou Tang, "Single Image Haze Removal Using Dark Channel Prior",
CVPR 2009. Transmission map refined with a guided filter (He et al., ECCV 2010).
"""

import cv2
import numpy as np


class DehazeEnhancer:
    """Removes haze/fog from RGB uint8 frames using the Dark Channel Prior algorithm."""

    def __init__(self, patch_size: int = 15, omega: float = 0.95, t0: float = 0.1,
                 guided_radius: int = 40, guided_eps: float = 1e-3):
        self.patch_size = patch_size
        self.omega = omega
        self.t0 = t0
        self.guided_radius = guided_radius
        self.guided_eps = guided_eps

    def dehaze(self, frame: np.ndarray) -> np.ndarray:
        """Takes an RGB uint8 frame and returns a haze-removed RGB uint8 frame of the same size."""
        img = frame.astype(np.float64) / 255.0

        dark = self._dark_channel(img)
        atmospheric_light = self._estimate_atmospheric_light(img, dark)
        raw_transmission = self._estimate_transmission(img, atmospheric_light)

        guide = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float64) / 255.0
        transmission = self._guided_filter(guide, raw_transmission)

        recovered = self._recover(img, transmission, atmospheric_light)
        return (recovered * 255.0).astype(np.uint8)

    def _dark_channel(self, img: np.ndarray) -> np.ndarray:
        """Per-pixel minimum across RGB channels, then eroded over a local patch (min filter)"""
        min_channel = np.min(img, axis=2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (self.patch_size, self.patch_size))
        return cv2.erode(min_channel, kernel)

    def _estimate_atmospheric_light(self, img: np.ndarray, dark: np.ndarray) -> np.ndarray:
        """Atmospheric light = brightest original pixel among the top 0.1% haziest (brightest-dark-channel) pixels"""
        h, w = dark.shape
        num_top = max(int(h * w * 0.001), 1)

        dark_flat = dark.reshape(-1)
        top_indices = np.argpartition(dark_flat, -num_top)[-num_top:]

        img_flat = img.reshape(-1, 3)
        candidates = img_flat[top_indices]
        return candidates[np.argmax(candidates.sum(axis=1))]

    def _estimate_transmission(self, img: np.ndarray, atmospheric_light: np.ndarray) -> np.ndarray:
        normalized = img / np.clip(atmospheric_light, 1e-6, None)
        return 1.0 - self.omega * self._dark_channel(normalized)

    def _guided_filter(self, guide: np.ndarray, src: np.ndarray) -> np.ndarray:
        """Edge-preserving refinement of the (blocky) raw transmission map, guided by the grayscale frame"""
        r = self.guided_radius
        ksize = (r, r)

        mean_guide = cv2.boxFilter(guide, cv2.CV_64F, ksize)
        mean_src = cv2.boxFilter(src, cv2.CV_64F, ksize)
        mean_guide_src = cv2.boxFilter(guide * src, cv2.CV_64F, ksize)
        cov_guide_src = mean_guide_src - mean_guide * mean_src

        mean_guide_sq = cv2.boxFilter(guide * guide, cv2.CV_64F, ksize)
        var_guide = mean_guide_sq - mean_guide * mean_guide

        a = cov_guide_src / (var_guide + self.guided_eps)
        b = mean_src - a * mean_guide

        mean_a = cv2.boxFilter(a, cv2.CV_64F, ksize)
        mean_b = cv2.boxFilter(b, cv2.CV_64F, ksize)

        return mean_a * guide + mean_b

    def _recover(self, img: np.ndarray, transmission: np.ndarray, atmospheric_light: np.ndarray) -> np.ndarray:
        t = np.clip(transmission, self.t0, 1.0)[:, :, None]
        recovered = (img - atmospheric_light) / t + atmospheric_light
        return np.clip(recovered, 0.0, 1.0)
