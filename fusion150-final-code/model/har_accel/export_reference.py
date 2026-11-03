"""Export one validation window and float intermediate outputs for integration."""
from __future__ import annotations
import json
import numpy as np
import torch
from .data import ROOT, load_train_val, sha256
from .model import HARTransformer
from .train import set_deterministic


def main():
    set_deterministic(20260929)
    _, _, xva, yva = load_train_val()
    model = HARTransformer()
    model.load_state_dict(torch.load(ROOT / "artifacts" / "float_model" / "weights.pt",
                                     map_location="cpu", weights_only=True))
    model.eval()
    with torch.no_grad():
        logits, layers = model(torch.from_numpy(xva[:1]), capture=True)
    out = ROOT / "artifacts" / "float_model" / "reference_sample_0.npz"
    np.savez_compressed(out, input=xva[0], label=yva[0],
                        **{key: value[0].numpy() for key, value in layers.items()})
    info = {"validation_index": 0, "label_zero_based": int(yva[0]),
            "predicted_zero_based": int(logits.argmax(1)[0]),
            "sha256": sha256(out), "layers": list(layers)}
    (out.parent / "reference_sample_0.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
