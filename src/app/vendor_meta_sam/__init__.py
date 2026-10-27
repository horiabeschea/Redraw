"""Vendored SAM mask decoder (official Meta implementation, verbatim).

Source: https://github.com/meta-models/meta-sam
Files: python/src/meta_sam_parser/_mask_codec.py, _errors.py, _types.py
Copied byte-for-byte on 2026-10-27 (sizes verified against the GitHub API).
Redistributed with the required copy of the agreement: ./LICENSE.

Only the mask decoder is vendored (pip has no usable PyPI route from this
environment). The stream parser and prompt builders were intentionally left
out; src/app/sam_segment.py implements the small request/response handling
against the documented wire grammar instead.
"""

from ._errors import InvalidSegmentationMaskError
from ._mask_codec import decode_mask_to_raster
from ._types import SegmentationMask

__all__ = ["InvalidSegmentationMaskError", "SegmentationMask",
           "decode_mask_to_raster"]
