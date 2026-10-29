# Project handoff rules

This repository is the WSI/JPEG XL part of a spatial-transcriptomics project.
Read `HANDOFF.md`, `writing/README.md`, and `writing/claims.csv` before writing.

- Research is frozen after round 6. The current task is organization and writing;
  do not start new compression experiments unless the user requests them.
- Preserve the entire input SVS byte for byte, including every pyramid level,
  original JPEG stream, metadata, label, and opaque byte. Pixel equality alone
  does not meet the contract. Do not change the user's count codec.
- Distinguish full CMU-1, the same-slide Small-Region crop, and sampled tile panels.
  Both full slides studied are Aperio RGB Q30. A crop is not a third slide.
- Distinguish native JXL, JXL plus outer compression, and coefficient operators.
  The project has not rewritten libjxl's core entropy coder or established novelty.
- Round 5 weak-ridge comparisons are post-hoc; round 6 weak-entropy and probability
  diagnostics are exploratory. Binary logloss reductions are not file-size gains.
- Preserve historical reports and raw measurements. New runs use new output names.
  Do not overwrite old results merely to make reports agree with newer code.
- `python3 scripts/check_handoff.py` checks the writing evidence snapshot using only
  the standard library. A changed evidence hash requires an explicit review.
- For code changes, build the coefficient adapter and run `python -m pytest -q -W error`
  in the documented environment. macOS arm64 is tested; Linux support needs a real
  target-machine run. Native Windows should use WSL.
- Never commit WSI files, `.wjxl` archives, reconstructed slides, virtual environments,
  compiled libraries, or credentials. Public download locations and hashes are in
  `data/README.md`; optional binary evidence is separate from the writing snapshot.
- Keep the original commit history. Do not rewrite historical experiment commits
  or claim that transferring the repository reruns their independent validations.
