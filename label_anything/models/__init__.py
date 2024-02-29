# Code taken from https://github.com/facebookresearch/segment-anything
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from collections import namedtuple
from .sam import Sam, AdaptedSam
from .lam import Lam, BinaryLam
from .image_encoder import ImageEncoderViT
from .mask_decoder import MaskDecoder, MaskDecoderLam
from .prompt_encoder import PromptEncoder, PromptImageEncoder
from .transformer import OneWayTransformer, TwoWayTransformer
from .build_sam import build_sam_vit_b, build_sam_vit_h, build_sam_vit_l, build_asam_vit_b
from .build_lam import build_lam_vit_b, build_lam_vit_h, build_lam_vit_l, build_lam, build_lam_no_vit
from .build_vit import build_vit_b, build_vit_h, build_vit_l
from .samfew import SAMFewShotModel
from .dcama import build_dcama
from .dummy import build_dummy


ComposedOutput = namedtuple("ComposedOutput", ["main", "aux"])

model_registry = {
    "lam": build_lam,
    "lam_no_vit": build_lam_no_vit,
    "lam_h": build_lam_vit_h,
    "lam_l": build_lam_vit_l,
    "lam_b": build_lam_vit_b,
    "sam": build_sam_vit_h,
    "sam_h": build_sam_vit_h,
    "sam_l": build_sam_vit_l,
    "sam_b": build_sam_vit_b,
    "asam_b": build_asam_vit_b,
    "dcama": build_dcama,
    "dummy": build_dummy,
    # Encoders only
    "vit": build_vit_h,
    "vit_h": build_vit_h,
    "vit_l": build_vit_l,
    "vit_b": build_vit_b,
}


def build_samfew(
    sam_model="vit_b",
    sam_params=None,
    fewshot_model="dcama",
    fewshot_params=None,
):
    sam = model_registry[sam_model](**sam_params)
    fewshot = model_registry[fewshot_model](**fewshot_params)
    return SAMFewShotModel(sam, fewshot)


model_registry["samfew"] = build_samfew