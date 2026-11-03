"""Validation-only candidate scales; no claim of a frozen full-integer network."""
from __future__ import annotations
import json
import math
import numpy as np
import torch

from .data import ROOT, load_train_val
from .model import HARTransformer
from .train import set_deterministic


def pow2_scale(target_abs: float, denominator: int = 127) -> float:
    if target_abs <= 0:
        return 2.0 ** -24
    return 2.0 ** math.ceil(math.log2(target_abs / denominator))


def main():
    set_deterministic(20260929)
    _, _, xva, _ = load_train_val()
    model = HARTransformer()
    model.load_state_dict(torch.load(ROOT / "artifacts" / "float_model" / "weights.pt",
                                     map_location="cpu", weights_only=True))
    model.eval()
    samples = {"input": []}
    with torch.no_grad():
        for start in range(0, len(xva), 128):
            xb = torch.from_numpy(xva[start:start + 128])
            _, activations = model(xb, capture=True)
            samples["input"].append(xb.numpy().ravel())
            for name, tensor in activations.items():
                samples.setdefault(name, []).append(tensor.numpy().ravel())
    arrays = {name: np.concatenate(chunks).astype(np.float64)
              for name, chunks in samples.items()}
    qk_target = max(float(np.percentile(np.abs(arrays[name]), 99.99)) for name in ("q", "k"))
    activation = {}
    for name, arr in arrays.items():
        abs_p = qk_target if name in ("q", "k") else float(np.percentile(np.abs(arr), 99.99))
        scale = pow2_scale(abs_p)
        activation[name] = {"format": "signed_int8_symmetric_candidate", "scale": scale,
                            "zero_point": 0, "selection": "validation |x| percentile 99.99; rounded up to power of two",
                            "target_abs": abs_p,
                            "clipped_fraction": float(np.mean(np.abs(arr) > 127 * scale)),
                            "samples": int(arr.size)}
    weights = {}
    tensor_weights = {}
    for name in ("embed", "q", "k", "v", "out", "ff1", "ff2", "classifier"):
        w = getattr(model, name).weight.detach().numpy()
        scales = [pow2_scale(float(np.max(np.abs(row)))) for row in w]
        weights[name] = {"format": "signed_int8_per_output_channel_candidate",
                         "zero_point": 0, "scales": scales,
                         "max_abs_quantization_error": max(float(np.max(np.abs(w[i] - np.clip(np.round(w[i] / s), -128, 127) * s)))
                                                           for i, s in enumerate(scales))}
        tensor_scale = pow2_scale(float(np.max(np.abs(w))))
        tensor_weights[name] = {"scale": tensor_scale, "zero_point": 0,
                                "max_abs_quantization_error": float(np.max(np.abs(
                                    w - np.clip(np.round(w / tensor_scale), -128, 127) * tensor_scale)))}
    matrix_paths = (
        ("embed", "input", "embedding"), ("q", "norm1_output", "q"),
        ("k", "norm1_output", "k"), ("v", "norm1_output", "v"),
        ("out", "av", "output_projection"),
        ("ff1", "norm2_output", "ff1_pre_relu"),
        ("ff2", "ff1_post_relu", "ff2"),
        ("classifier", "pool_output", "logits"),
    )
    shift = {}
    for name, input_name, output_name in matrix_paths:
        sin = activation[input_name]["scale"]
        sw = tensor_weights[name]["scale"]
        sout = activation[output_name]["scale"]
        shift[name] = int(round(math.log2(sout / (sin * sw))))
    shift["qk_scores"] = int(round(math.log2(
        activation["attention_scores"]["scale"] /
        (activation["q"]["scale"] * activation["k"]["scale"])))) + 2
    shift["av"] = int(round(math.log2(
        activation["av"]["scale"] /
        (activation["softmax_prob"]["scale"] * activation["v"]["scale"]))))
    result = {"status": "candidate_only_not_frozen", "calibration_split": "validation_only",
              "scale_definition": "real_value = int8_value * scale",
              "q_and_k_share_activation_scale": True,
              "activation": activation, "weight_per_channel_exploratory": weights,
              "hardware_first_pass": {"weight_granularity": "per_tensor_symmetric_int8",
                                      "weight": tensor_weights,
                                      "matrix_shift_candidates": shift,
                                      "shift_semantics": "floor(acc / 2**shift), then int8 saturation; excludes bias/add/norm/softmax"},
              "unresolved": ["actual HLS vectors.h file and testbench integration", "bias and residual integer contract",
                             "integer Softmax approximation", "integer RMSNorm approximation",
                             "full-network integer agreement"]}
    out = ROOT / "artifacts" / "quant_candidate.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "activation_layers": len(activation),
                      "weight_layers": len(weights), "q_k_scale": activation["q"]["scale"]}, indent=2))


if __name__ == "__main__":
    main()
