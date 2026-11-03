"""Official UCI HAR inertial windows; no code path opens the official test split."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data" / "uci_har.zip"
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
SIGNALS = (
    "total_acc_x", "total_acc_y", "total_acc_z",
    "body_acc_x", "body_acc_y", "body_acc_z",
    "body_gyro_x", "body_gyro_y", "body_gyro_z",
)
SEED = 20260929


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_official_train() -> None:
    """Extract only train files, even though the archive also contains test data."""
    if not ZIP.exists():
        raise FileNotFoundError(f"Download official UCI archive to {ZIP}")
    required = ["train/y_train.txt", "train/subject_train.txt"] + [
        f"train/Inertial Signals/{s}_train.txt" for s in SIGNALS
    ]
    with zipfile.ZipFile(ZIP) as outer:
        names = outer.namelist()
        inner_names = [n for n in names if n.lower().endswith(".zip")]
        if inner_names and not any("train/y_train.txt" in n for n in names):
            import io
            archive = zipfile.ZipFile(io.BytesIO(outer.read(inner_names[0])))
        else:
            archive = outer
        try:
            for suffix in required:
                matches = [n for n in archive.namelist() if n.replace("\\", "/").endswith(suffix)]
                if len(matches) != 1:
                    raise ValueError(f"Expected one archive member for {suffix}, found {matches}")
                destination = RAW / suffix
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(matches[0]))
        finally:
            if archive is not outer:
                archive.close()


def prepare() -> dict:
    extract_official_train()
    train = RAW / "train"
    x = np.stack([
        np.loadtxt(train / "Inertial Signals" / f"{s}_train.txt", dtype=np.float32)
        for s in SIGNALS
    ], axis=-1)
    y = np.loadtxt(train / "y_train.txt", dtype=np.int64) - 1
    subjects = np.loadtxt(train / "subject_train.txt", dtype=np.int64)
    if x.shape != (7352, 128, 9) or y.shape != (7352,) or subjects.shape != y.shape:
        raise AssertionError((x.shape, y.shape, subjects.shape))
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    tr, va = next(splitter.split(x, y, groups=subjects))
    if set(subjects[tr]) & set(subjects[va]):
        raise AssertionError("Subject leakage")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PROCESSED / "train_val.npz", x_train=x[tr], y_train=y[tr],
                        subject_train=subjects[tr], x_val=x[va], y_val=y[va],
                        subject_val=subjects[va])
    manifest = {
        "source_url": "https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones",
        "download_url": "https://archive.ics.uci.edu/static/public/240/human%2Bactivity%2Brecognition%2Busing%2Bsmartphones.zip",
        "archive_bytes": ZIP.stat().st_size, "archive_sha256": sha256(ZIP),
        "official_train_samples": int(len(y)),
        "train_samples": int(len(tr)), "validation_samples": int(len(va)),
        "train_subjects": sorted(map(int, set(subjects[tr]))),
        "validation_subjects": sorted(map(int, set(subjects[va]))),
        "class_counts_train": np.bincount(y[tr], minlength=6).tolist(),
        "class_counts_validation": np.bincount(y[va], minlength=6).tolist(),
        "signals": list(SIGNALS), "split_seed": SEED,
        "split_index_sha256": hashlib.sha256(tr.tobytes() + va.tobytes()).hexdigest(),
        "processed_sha256": sha256(PROCESSED / "train_val.npz"),
        "official_test_read_count": 0,
    }
    (PROCESSED / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_train_val():
    with np.load(PROCESSED / "train_val.npz") as data:
        return tuple(data[k] for k in ("x_train", "y_train", "x_val", "y_val"))


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
