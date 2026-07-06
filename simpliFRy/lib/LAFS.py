"""
LAFS (Landmark-based Facial Self-supervised learning) face recognition embedding, Part-fViT variant.
Model architecture and pretrained weights (WebFace4M, supervised) from
https://github.com/szlbiubiubiu/LAFS_CVPR2024 (MIT License).

Unlike Zero-DCE/Dehaze/NAFNet, this replaces the *recognition embedding* step, not a preprocessing
step - the model takes a 112x112 ArcFace-aligned face crop and outputs a 768-dim embedding (versus
insightface's 512-dim arcface embedding). It has its own internal landmark-localization sub-network
(a MobileNetV3 "STN"), so no external facial landmark detector is required beyond face detection.
"""

import os
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights", "LAFS-WebFace4M-PartfViT.pth")


# ───────────────────────────── MobileNetV3 (internal landmark STN) ─────────────────────────────

def conv_bn(inp, oup, stride, nlin_layer=nn.ReLU):
    return nn.Sequential(
        nn.Conv2d(inp, oup, 3, stride, 1, bias=False),
        nn.BatchNorm2d(oup),
        nlin_layer(inplace=True),
    )


class Hswish(nn.Module):
    def __init__(self, inplace=True):
        super().__init__()
        self.inplace = inplace

    def forward(self, x):
        return x * F.relu6(x + 3.0, inplace=self.inplace) / 6.0


class Hsigmoid(nn.Module):
    def __init__(self, inplace=True):
        super().__init__()
        self.inplace = inplace

    def forward(self, x):
        return F.relu6(x + 3.0, inplace=self.inplace) / 6.0


class SEModule(nn.Module):
    def __init__(self, channel, reduction=4):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(channel, channel // reduction, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(channel // reduction, channel, bias=False),
            Hsigmoid(),
        )

    def forward(self, x):
        b, c, _, _ = x.size()
        y = self.avg_pool(x).view(b, c)
        y = self.fc(y).view(b, c, 1, 1)
        return x * y.expand_as(x)


class Identity(nn.Module):
    def __init__(self, channel=None):
        super().__init__()

    def forward(self, x):
        return x


def make_divisible(x, divisible_by=8):
    return int(np.ceil(x * 1.0 / divisible_by) * divisible_by)


class MobileBottleneck(nn.Module):
    def __init__(self, inp, oup, kernel, stride, exp, se=False, nl="RE"):
        super().__init__()
        padding = (kernel - 1) // 2
        self.use_res_connect = stride == 1 and inp == oup
        nlin_layer = nn.ReLU if nl == "RE" else Hswish
        SELayer = SEModule if se else Identity

        self.conv = nn.Sequential(
            nn.Conv2d(inp, exp, 1, 1, 0, bias=False),
            nn.BatchNorm2d(exp),
            nlin_layer(inplace=True),
            nn.Conv2d(exp, exp, kernel, stride, padding, groups=exp, bias=False),
            nn.BatchNorm2d(exp),
            SELayer(exp),
            nlin_layer(inplace=True),
            nn.Conv2d(exp, oup, 1, 1, 0, bias=False),
            nn.BatchNorm2d(oup),
        )

    def forward(self, x):
        return x + self.conv(x) if self.use_res_connect else self.conv(x)


class MobileNetV3_backbone(nn.Module):
    """The 'large' MobileNetV3 config, used as LAFS's internal landmark-localization network."""

    def __init__(self, mode="large"):
        super().__init__()
        mobile_setting = [
            # k, exp, c,  se,     nl,  s,
            [3, 16, 16, False, "RE", 1],
            [3, 64, 24, False, "RE", 2],
            [3, 72, 24, False, "RE", 1],
            [5, 72, 40, True, "RE", 2],
            [5, 120, 40, True, "RE", 1],
            [5, 120, 40, True, "RE", 1],
            [3, 240, 80, False, "HS", 2],
            [3, 200, 80, False, "HS", 1],
            [3, 184, 80, False, "HS", 1],
            [3, 184, 80, False, "HS", 1],
            [3, 480, 112, True, "HS", 1],
            [3, 672, 112, True, "HS", 1],
            [5, 672, 160, True, "HS", 2],
            [5, 960, 160, True, "HS", 1],
            [5, 960, 160, True, "HS", 1],
        ]

        input_channel = 16
        features = [conv_bn(3, input_channel, 2, nlin_layer=Hswish)]
        for k, exp, c, se, nl, s in mobile_setting:
            output_channel = make_divisible(c)
            exp_channel = make_divisible(exp)
            features.append(MobileBottleneck(input_channel, output_channel, k, s, exp_channel, se, nl))
            input_channel = output_channel
        self.features = nn.Sequential(*features)

    def forward(self, x):
        return self.features(x)


# ───────────────────────────── Transformer (fViT) ─────────────────────────────

def drop_path(x, drop_prob=0.0, training=False):
    if drop_prob == 0.0 or not training:
        return x
    keep_prob = 1 - drop_prob
    shape = (x.shape[0],) + (1,) * (x.ndim - 1)
    random_tensor = keep_prob + torch.rand(shape, dtype=x.dtype, device=x.device)
    random_tensor.floor_()
    return x.div(keep_prob) * random_tensor


class DropPath(nn.Module):
    def __init__(self, drop_prob=None):
        super().__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        return drop_path(x, self.drop_prob, self.training)


class Residual_droppath(nn.Module):
    def __init__(self, fn, drop_path_rate=0.1):
        super().__init__()
        self.fn = fn
        self.drop_path = DropPath(drop_path_rate) if drop_path_rate > 0.0 else nn.Identity()

    def forward(self, x, **kwargs):
        return self.drop_path(self.fn(x, **kwargs)) + x


class PreNorm(nn.Module):
    def __init__(self, dim, fn):
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.fn = fn

    def forward(self, x, **kwargs):
        return self.fn(self.norm(x), **kwargs)


class FeedForward(nn.Module):
    def __init__(self, dim, hidden_dim, dropout=0.0):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, dim),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)


class Attention(nn.Module):
    def __init__(self, dim, heads=8, dim_head=64, dropout=0.0):
        super().__init__()
        inner_dim = dim_head * heads
        self.heads = heads
        self.scale = dim ** -0.5

        self.to_qkv = nn.Linear(dim, inner_dim * 3, bias=False)
        self.to_out = nn.Sequential(nn.Linear(inner_dim, dim), nn.Dropout(dropout))

    def forward(self, x, mask=None):
        b, n, _ = x.shape
        h = self.heads
        qkv = self.to_qkv(x).chunk(3, dim=-1)
        q, k, v = (t.view(b, n, h, -1).permute(0, 2, 1, 3) for t in qkv)

        dots = torch.einsum("bhid,bhjd->bhij", q, k) * self.scale
        attn = dots.softmax(dim=-1)
        out = torch.einsum("bhij,bhjd->bhid", attn, v)
        out = out.permute(0, 2, 1, 3).reshape(b, n, -1)
        return self.to_out(out)


class Transformer(nn.Module):
    def __init__(self, dim, depth, heads, dim_head, mlp_dim, dropout):
        super().__init__()
        self.layers = nn.ModuleList([])
        for _ in range(depth):
            self.layers.append(
                nn.ModuleList(
                    [
                        Residual_droppath(PreNorm(dim, Attention(dim, heads=heads, dim_head=dim_head, dropout=dropout))),
                        Residual_droppath(PreNorm(dim, FeedForward(dim, mlp_dim, dropout=dropout))),
                    ]
                )
            )

    def forward(self, x, mask=None):
        for attn, ff in self.layers:
            x = attn(x, mask=mask)
            x = ff(x)
        return x


def extract_patches_gridsample(imgs: torch.Tensor, landmarks: torch.Tensor, patch_shape: torch.Tensor, num_landm: int) -> torch.Tensor:
    """Extracts a grid of patches from imgs centered at landmarks (predicted patch locations)."""
    device = landmarks.device
    img_shape = imgs.shape[2]

    patch_half_shape = patch_shape / 2
    sampling_grid = torch.meshgrid(
        torch.arange(-patch_half_shape[0], patch_half_shape[0]),
        torch.arange(-patch_half_shape[1], patch_half_shape[1]),
        indexing="ij",
    )
    sampling_grid = torch.stack(sampling_grid, dim=0).to(device)
    sampling_grid = torch.transpose(torch.transpose(sampling_grid, 0, 2), 0, 1)

    list_patches = []
    for i in range(num_landm):
        land = landmarks[:, i, :]
        patch_grid = (sampling_grid[None, :, :, :] + land[:, None, None, :]) / (img_shape * 0.5) - 1
        list_patches.append(F.grid_sample(imgs, patch_grid, align_corners=False))

    list_patches = torch.stack(list_patches, dim=2)
    B, c, patches_num, w, h = list_patches.shape
    row = int(math.sqrt(patches_num))
    list_patches = list_patches.reshape(B, c, row, row, w, h)
    list_patches = list_patches.permute(0, 1, 2, 4, 3, 5)
    return list_patches.reshape(B, c, w * row, h * row)


class ViTFaceLandmarkPatch8(nn.Module):
    def __init__(self, image_size=112, patch_size=8, dim=768, depth=12, heads=11, mlp_dim=2048, dropout=0.1, emb_dropout=0.1):
        super().__init__()
        num_patches = (image_size // patch_size) ** 2
        patch_dim = 3 * patch_size ** 2

        self.patch_size = patch_size
        self.num_patches = num_patches
        self.row_num = int(math.sqrt(num_patches))

        self.stn = MobileNetV3_backbone(mode="large")
        self.output_layer = nn.Sequential(nn.Dropout(p=0.5), nn.Linear(160, self.row_num * self.row_num * 2))
        self.patch_shape = torch.tensor([patch_size, patch_size])

        self.pos_embedding = nn.Parameter(torch.randn(1, num_patches + 1, dim))
        self.patch_to_embedding = nn.Linear(patch_dim, dim)
        self.cls_token = nn.Parameter(torch.randn(1, 1, dim))
        self.dropout = nn.Dropout(emb_dropout)
        self.transformer = Transformer(dim, depth, heads, 64, mlp_dim, dropout)
        self.mlp_head = nn.Sequential(nn.LayerNorm(dim))

    def forward(self, x):
        p = self.patch_size
        b = x.shape[0]
        num_land = self.row_num * self.row_num

        theta = self.stn(x)
        theta = theta.mean(dim=(-2, -1))
        theta = self.output_layer(theta)

        t_max = theta.max(1)[0].unsqueeze(1).repeat(1, self.row_num * self.row_num * 2)
        t_min = theta.min(1)[0].unsqueeze(1).repeat(1, self.row_num * self.row_num * 2)
        theta = (theta - t_min) / (t_max - t_min) * 111
        theta = theta.view(-1, self.row_num * self.row_num, 2)

        x = extract_patches_gridsample(x, theta[:, :num_land], patch_shape=self.patch_shape, num_landm=num_land)

        bsz, c, H, W = x.shape
        nh, nw = H // p, W // p
        x = x.view(bsz, c, nh, p, nw, p).permute(0, 2, 4, 3, 5, 1).reshape(bsz, nh * nw, p * p * c)

        x = self.patch_to_embedding(x)
        cls_tokens = self.cls_token.expand(b, -1, -1)
        x = torch.cat((cls_tokens, x), dim=1)
        x = x + self.pos_embedding[:, : x.shape[1]]
        x = self.dropout(x)
        x = self.transformer(x)
        x = x[:, 0]
        return self.mlp_head(x)


class LAFSEmbedder:
    """Wraps the LAFS Part-fViT model to extract 768-dim face embeddings from 112x112 aligned crops."""

    def __init__(self, device: str = "cpu", use_fp16: bool | None = None):
        self.device = torch.device(device)
        self.use_fp16 = use_fp16 if use_fp16 is not None else (self.device.type == "cuda")
        self.dtype = torch.float16 if self.use_fp16 else torch.float32

        self.model = ViTFaceLandmarkPatch8()
        state_dict = torch.load(WEIGHTS_PATH, map_location="cpu")
        self.model.load_state_dict(state_dict)
        self.model.to(self.device).eval()
        if self.use_fp16:
            self.model.half()

    @torch.no_grad()
    def embed(self, aligned_face: np.ndarray) -> np.ndarray:
        """
        Takes a 112x112 RGB uint8 ArcFace-aligned face crop, returns an L2-normalized 768-dim embedding.
        Uses flip-test averaging (standard face recognition practice, used in LAFS's own evaluation
        script): embeds both the crop and its horizontal mirror, then averages and renormalizes -
        this typically improves discriminative quality over a single embedding.
        """
        tensor = torch.from_numpy(aligned_face).to(self.device).to(self.dtype).div(255.0)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)  # 1x3x112x112
        flipped = torch.flip(tensor, dims=[3])  # horizontal mirror (width axis)

        batch = torch.cat([tensor, flipped], dim=0)  # 2x3x112x112, batched through the model together
        embs = F.normalize(self.model(batch).float(), p=2, dim=1)

        combined = F.normalize(embs.sum(dim=0, keepdim=True), p=2, dim=1)
        return combined.squeeze(0).cpu().numpy()
