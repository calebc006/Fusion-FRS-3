"""
Zero-DCE low-light image enhancement.
Model architecture and pretrained weights from https://github.com/Li-Chongyi/Zero-DCE (MIT License).
"""

import os
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights", "zerodce_epoch99.pth")


class enhance_net_nopool(nn.Module):
    def __init__(self):
        super(enhance_net_nopool, self).__init__()

        self.relu = nn.ReLU(inplace=True)

        number_f = 32
        self.e_conv1 = nn.Conv2d(3, number_f, 3, 1, 1, bias=True)
        self.e_conv2 = nn.Conv2d(number_f, number_f, 3, 1, 1, bias=True)
        self.e_conv3 = nn.Conv2d(number_f, number_f, 3, 1, 1, bias=True)
        self.e_conv4 = nn.Conv2d(number_f, number_f, 3, 1, 1, bias=True)
        self.e_conv5 = nn.Conv2d(number_f * 2, number_f, 3, 1, 1, bias=True)
        self.e_conv6 = nn.Conv2d(number_f * 2, number_f, 3, 1, 1, bias=True)
        self.e_conv7 = nn.Conv2d(number_f * 2, 24, 3, 1, 1, bias=True)

    def get_curve_params(self, x):
        """Runs the conv stack and returns the 8 concatenated per-pixel enhancement curve maps (N, 24, H, W)"""
        x1 = self.relu(self.e_conv1(x))
        x2 = self.relu(self.e_conv2(x1))
        x3 = self.relu(self.e_conv3(x2))
        x4 = self.relu(self.e_conv4(x3))

        x5 = self.relu(self.e_conv5(torch.cat([x3, x4], 1)))
        x6 = self.relu(self.e_conv6(torch.cat([x2, x5], 1)))

        return torch.tanh(self.e_conv7(torch.cat([x1, x6], 1)))

    def forward(self, x):
        return apply_curve(x, self.get_curve_params(x))


def apply_curve(x: torch.Tensor, curve_params: torch.Tensor) -> torch.Tensor:
    """Applies Zero-DCE's iterative per-pixel curve formula to x using curve_params (24-channel tensor)"""
    r1, r2, r3, r4, r5, r6, r7, r8 = torch.split(curve_params, 3, dim=1)

    x = x + r1 * (torch.pow(x, 2) - x)
    x = x + r2 * (torch.pow(x, 2) - x)
    x = x + r3 * (torch.pow(x, 2) - x)
    enhance_image_1 = x + r4 * (torch.pow(x, 2) - x)
    x = enhance_image_1 + r5 * (torch.pow(enhance_image_1, 2) - enhance_image_1)
    x = x + r6 * (torch.pow(x, 2) - x)
    x = x + r7 * (torch.pow(x, 2) - x)
    enhance_image = x + r8 * (torch.pow(x, 2) - x)
    return enhance_image


class ZeroDCEEnhancer:
    """Wraps the Zero-DCE net to enhance low-light RGB frames (uint8 HxWx3 numpy arrays)."""

    def __init__(self, device: str = "cpu", use_fp16: bool | None = None):
        self.device = torch.device(device)
        # FP16 only has real benefit (and full op support) on CUDA; default to on for GPU, off for CPU
        self.use_fp16 = use_fp16 if use_fp16 is not None else (self.device.type == "cuda")
        self.dtype = torch.float16 if self.use_fp16 else torch.float32

        self.model = enhance_net_nopool().to(self.device)
        self.model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=self.device))
        self.model.eval()
        if self.use_fp16:
            self.model.half()

    @torch.no_grad()
    def enhance(self, frame: np.ndarray) -> np.ndarray:
        """Takes an RGB uint8 frame and returns an enhanced RGB uint8 frame of the same size."""
        h, w = frame.shape[:2]

        # Zero-DCE's conv/upsample stages assume even dimensions
        pad_h, pad_w = h % 2, w % 2
        tensor = torch.from_numpy(frame).to(self.device).to(self.dtype).div(255.0)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)  # HWC -> NCHW
        if pad_h or pad_w:
            tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode="replicate")

        enhanced = self.model(tensor)

        if pad_h or pad_w:
            enhanced = enhanced[:, :, :h, :w]

        enhanced = enhanced.squeeze(0).permute(1, 2, 0).clamp(0, 1).mul(255.0)
        return enhanced.float().byte().cpu().numpy()

    @torch.no_grad()
    def enhance_fast(self, frame: np.ndarray, max_dim: int = 640) -> np.ndarray:
        """
        Estimates Zero-DCE's per-pixel curves on a downscaled copy of frame (cheap - this is where
        all the conv compute lives), then upsamples the curves and applies them directly to the
        original full-resolution frame. Avoids the blur/detail-loss of downscaling the image itself,
        since the curves are spatially smooth and the actual pixel arithmetic runs at full resolution.
        """
        h, w = frame.shape[:2]
        scale = min(1.0, max_dim / max(h, w))

        full = torch.from_numpy(frame).to(self.device).to(self.dtype).div(255.0)
        full = full.permute(2, 0, 1).unsqueeze(0)  # HWC -> NCHW

        if scale < 1.0:
            small = F.interpolate(full, scale_factor=scale, mode="bilinear", align_corners=False)
        else:
            small = full

        curve_params = self.model.get_curve_params(small)

        if scale < 1.0:
            curve_params = F.interpolate(curve_params, size=(h, w), mode="bilinear", align_corners=False)

        enhanced = apply_curve(full, curve_params)
        enhanced = enhanced.squeeze(0).permute(1, 2, 0).clamp(0, 1).mul(255.0)
        return enhanced.float().byte().cpu().numpy()
