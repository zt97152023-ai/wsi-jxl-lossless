# WSI JPEG XL strict-lossless research prototype

Date: 2026-10-27. User authorized implementation and experiments on a public WSI.

## Scope
Optimize WSI image compression while retaining the user's Shared B8/K32 count codec unchanged. A single-slide pilot establishes engineering feasibility, not generalization or novelty.

## Data and contracts
Use the public CC0 OpenSlide CMU-1 Aperio slide and its explicitly labelled Small-Region crop for smoke tests. Preserve the source file. Distinguish exact decoded pixel recovery from original-SVS byte recovery. No background removal, color normalization, denoising, rounding, or pyramid omission.

## Candidate mechanisms
1. Standard lossless JXL Modular on RGB tiles: reference.
2. Reversible integer color prediction adapted per tile to H&E channel correlation, with all coefficients and mode flags stored; JXL codes the transformed pixels. Compare against native JXL at identical effort and tile size. Always retain an identity candidate.
3. Byte-exact JPEG-tile recompression for JPEG-compressed Aperio inputs: JXL reconstructs JPEG bytes; container and unsupported segments preserved. This is an existing JXL capability used as a practical baseline, not a novelty claim.

## Checks
Test round trips on extremes, random inputs, grayscale and odd sizes before real images. Record actual coded bytes including headers and auxiliary information, encode/decode timings, pinned software versions and source hashes. Verify in an independent process. Include all selected source regions, not just tissue. Track failure and negative results. Compare full-slide results only after a bounded pilot.

## Plan
1. Download and inspect slide, record provenance.
2. Install isolated native-architecture codec environment.
3. Implement/test reversible transforms, probe a fixed spatially stratified tile panel.
4. Keep only candidates with net gains; benchmark native alternatives.
5. Implement a recoverable archive, independently decode and verify.
6. Report measured results, limitations and next experiments.

## Evidence boundaries
WISE (CVPR 2025), JPEG XL Modular, and reversible predictive coding are prior art. No first/SOTA claim. All optimization and verification here use public images locally. A full original-file hash is required before claiming byte-exact SVS recovery.

## 2026-10-28 experimental refinement
The complete CMU-1 SVS and all original bytes are now the recovery unit. The pixel-lift candidate stays a recorded negative pilot. JPEG reconstruction plus grouped coding is the archive path; classifiers only choose group boundaries and cannot discard any bytes. The initial tissue profile and fixed group sizes are compared before proposing a local-access refinement. The latter is explicitly development on the same slide, not held-out validation. A seekable reader checks every accessed group; full decoding is independently audited in fresh processes. The output is a custom WJXL archive, not a changed JPEG XL standard or a native OpenSlide plugin.
