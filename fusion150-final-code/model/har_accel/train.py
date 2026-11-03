"""Deterministic CPU training and validation; never opens the official test split."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch import nn

from .data import ROOT, SEED, load_train_val, sha256
from .model import HARTransformer


def set_deterministic(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)


def evaluate(model, x, y, batch_size=256):
    model.eval()
    output = []
    with torch.no_grad():
        for start in range(0, len(y), batch_size):
            output.append(model(torch.from_numpy(x[start:start + batch_size])).numpy())
    logits = np.concatenate(output)
    pred = logits.argmax(1)
    return {"accuracy": float(accuracy_score(y, pred)),
            "f1_per_class": f1_score(y, pred, labels=list(range(6)), average=None, zero_division=0).tolist(),
            "prediction_sha256": hashlib.sha256(pred.tobytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--lr", type=float, default=0.001)
    args = ap.parse_args()
    set_deterministic(SEED)
    xtr, ytr, xva, yva = load_train_val()
    model = HARTransformer(eps=1e-5)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    loss_fn = nn.CrossEntropyLoss()
    history = []
    best = -1.0
    out = ROOT / "artifacts" / "float_model"
    out.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = np.random.permutation(len(ytr))
        losses = []
        for start in range(0, len(order), args.batch_size):
            batch = order[start:start + args.batch_size]
            logits = model(torch.from_numpy(xtr[batch]))
            loss = loss_fn(logits, torch.from_numpy(ytr[batch]))
            optim.zero_grad(set_to_none=True)
            loss.backward()
            optim.step()
            losses.append(float(loss.detach()))
        metrics = evaluate(model, xva, yva)
        row = {"epoch": epoch, "train_loss": float(np.mean(losses)), **metrics}
        history.append(row)
        print(json.dumps(row), flush=True)
        if metrics["accuracy"] > best:
            best = metrics["accuracy"]
            torch.save(model.state_dict(), out / "weights.pt")
            best_epoch = epoch
    config = {"model": "HARTransformer", "input_shape": [128, 9], "patch": 4,
              "tokens": 32, "width": 16, "heads": 1, "layers": 1,
              "ff_width": 32, "classes": 6, "position_encoding": "fixed sinusoidal",
              "rmsnorm_epsilon": 1e-5, "seed": SEED, "epochs": args.epochs,
              "batch_size": args.batch_size, "optimizer": "AdamW", "lr": args.lr,
              "weight_decay": 0.01, "best_epoch": best_epoch,
              "best_validation_accuracy": best,
              "weights_sha256": sha256(out / "weights.pt")}
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (out / "history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
