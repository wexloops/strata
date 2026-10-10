Vendored from https://github.com/mir-aidj/all-in-one (MIT, see LICENSE) at PR #39
("Run neighborhood attention in plain PyTorch on CPU and MPS; make NATTEN optional"), head 3646caf.
Reason: upstream allin1 requires NATTEN <= 0.17.4, which has no kernels for current PyTorch / Blackwell GPUs.
Unmodified apart from removing the demo `assets/` folder. Install: `uv pip install -e vendor/all-in-one`.
