#!/usr/bin/env python3
"""
Script: yolov8_bbox_counter.py

Counts bounding boxes per class in each split of a YOLOv8 dataset.

Usage:
    python yolov8_bbox_counter.py /path/to/dataset [--image-keyword images] [--label-keyword labels]

This script expects a `data.yaml` in the dataset directory defining `train`, `val`, (and optionally `test`) paths.
It derives the label directories by replacing the image keyword in each split path with the label keyword.
Prints a breakdown of bounding box counts per class per split.
"""
import os
import argparse
from pathlib import Path
from collections import Counter

try:
    import yaml
except ImportError:
    raise ImportError("Please install pyyaml (`pip install pyyaml`) to use this script.")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Count bounding boxes per class per YOLOv8 dataset split"
    )
    parser.add_argument(
        "dataset", type=Path,
        help="Path to YOLOv8 dataset directory containing data.yaml"
    )
    parser.add_argument(
        "--image-keyword", default="images",
        help="Keyword used in paths to identify image directories (default: images)"
    )
    parser.add_argument(
        "--label-keyword", default="labels",
        help="Keyword to replace image keyword for label directories (default: labels)"
    )
    return parser.parse_args()


def load_data_yaml(dataset_path: Path) -> dict:
    data_yaml = dataset_path / "data.yaml"
    if not data_yaml.is_file():
        raise FileNotFoundError(f"data.yaml not found in {dataset_path}")
    with data_yaml.open() as f:
        return yaml.safe_load(f)


def get_label_dir(image_dir: Path, img_kw: str, lbl_kw: str) -> Path:
    """
    Replace the `img_kw` directory name in `image_dir` with `lbl_kw` to locate labels.
    Falls back to sibling structure if replacement fails.
    """
    parts = list(image_dir.parts)
    try:
        idx = parts.index(img_kw)
        parts[idx] = lbl_kw
        return Path(*parts)
    except ValueError:
        # fallback: assume labels are under a sibling folder
        return image_dir.parent / lbl_kw / image_dir.name


def count_bboxes(label_dir: Path) -> Counter:
    counter = Counter()
    if not label_dir.exists():
        print(f"Warning: Label directory {label_dir} does not exist. Skipping.")
        return counter
    for txt_file in label_dir.rglob("*.txt"):
        with txt_file.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                cls_id = int(line.split()[0])
                counter[cls_id] += 1
    return counter


def main():
    args = parse_args()
    data = load_data_yaml(args.dataset)
    # Only consider standard splits
    splits = {k: Path(v) for k, v in data.items() if k in ("train", "val", "test")}

    results = {}
    for split, rel_path in splits.items():
        image_dir = args.dataset / rel_path if not Path(rel_path).is_absolute() else rel_path
        label_dir = get_label_dir(image_dir, args.image_keyword, args.label_keyword)
        counts = count_bboxes(label_dir)
        results[split] = counts

    # Output
    print("\nBounding boxes per class per split:")
    for split, counts in results.items():
        print(f"\n== {split.upper()} ==")
        if counts:
            for cls_id, cnt in sorted(counts.items()):
                print(f"{data.get('names')[cls_id]}: {cnt}")
        else:
            print("(no bounding boxes found)")

if __name__ == "__main__":
    main()
