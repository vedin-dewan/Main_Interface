"""
file_renamer.py

Contains a small utility to poll an output directory for files matching camera/spectrometer
tokens and rename them to a canonical Experiment_ShotNNNNN_YYYYMMDD_HHMMSSmmm_label_0.ext format.

This preserves the existing behavior but extracts it from main_window.py for better testability.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Callable, Iterable, List, Optional, Set, Tuple


def default_logger(msg: str):
    try:
        print(msg)
    except Exception:
        pass


def default_match_fn(fname_lower: str, tok_lower: str) -> bool:
    return tok_lower in fname_lower


def rename_shot_files(
    outdir: str,
    tokens: Iterable[str],
    shotnum: int,
    experiment: str,
    timeout_ms: int = 5000,
    poll_ms: int = 200,
    stable_s: float = 0.3,
    processed_paths: Optional[Set[str]] = None,
    match_fn: Optional[Callable[[str, str], bool]] = None,
    logger: Optional[Callable[[str], None]] = None,
    write_info: bool = False,
    info_label: str = 'Info',
) -> Tuple[List[Tuple[str, str]], Set[str]]:
    """Poll `outdir` for files matching any of `tokens` and rename the newest stable file per token.

    Returns a tuple (renamed_pairs, processed_paths) where renamed_pairs is a list of
    (old_fullpath, new_fullpath) and processed_paths is the updated set of processed files.
    """
    if logger is None:
        logger = default_logger
    if match_fn is None:
        match_fn = default_match_fn
    if processed_paths is None:
        processed_paths = set()

    if not outdir or not os.path.isdir(outdir):
        logger(f"Rename skipped: invalid output dir '{outdir}'")
        return [], processed_paths

    toks = [str(t).strip() for t in tokens if t]
    toks_l = [t.lower() for t in toks]

    shotnum = int(shotnum or 0)
    exp = str(experiment or 'Experiment')

    max_wait_ms = int(timeout_ms or 5000)
    poll_ms = int(poll_ms or 200)
    stable_time = float(stable_s or 0.3)
    deadline = time.time() + (max_wait_ms / 1000.0)

    renamed_pairs: List[Tuple[str, str]] = []

    remaining = {i for i in range(len(toks_l))}
    candidates = {}
    last_size = {}
    stable_since = {}

    while time.time() < deadline and remaining:
        try:
            entries = [f for f in os.listdir(outdir) if os.path.isfile(os.path.join(outdir, f))]
        except Exception:
            entries = []

        now = time.time()

        for idx in list(remaining):
            tok = toks[idx]
            tok_l = toks_l[idx]
            newest = None
            newest_mtime = 0
            for fname in entries:
                full = os.path.join(outdir, fname)
                if full in processed_paths:
                    continue
                try:
                    if match_fn(fname.lower(), tok_l):
                        m = os.path.getmtime(full)
                    else:
                        m = 0
                except Exception:
                    m = 0
                if m and (newest is None or m > newest_mtime):
                    newest = full
                    newest_mtime = m

            if newest is None:
                continue

            prev = candidates.get(idx)
            if prev != newest:
                candidates[idx] = newest
                last_size[newest] = -1
                stable_since[newest] = None

            cand = candidates.get(idx)
            try:
                cur_size = os.path.getsize(cand)
            except Exception:
                cur_size = -1

            if cur_size == last_size.get(cand, -2) and cur_size >= 0:
                if stable_since.get(cand) is None:
                    stable_since[cand] = now
                elif (now - stable_since[cand]) >= stable_time:
                    # Rename
                    try:
                        e = os.path.basename(cand)
                        root, ext = os.path.splitext(e)
                        ts = datetime.now()
                        date_s = ts.strftime('%Y%m%d')
                        ms = int(ts.microsecond / 1000)
                        time_s = ts.strftime('%H%M%S') + f"{ms:03d}"
                        label = tok
                        newname = f"{exp}_Shot{shotnum:05d}_{date_s}_{time_s}_{label}_0{ext}"
                        newfull = os.path.join(outdir, newname)
                        if os.path.exists(newfull):
                            try:
                                base, ex = os.path.splitext(newfull)
                                newfull = f"{base}_dup{ex}"
                            except Exception:
                                pass
                        os.rename(cand, newfull)
                        processed_paths.add(newfull)
                        renamed_pairs.append((cand, newfull))
                        try:
                            logger(f"Renamed '{os.path.basename(cand)}' → '{os.path.basename(newfull)}'")
                        except Exception:
                            pass
                    except Exception as e:
                        try:
                            logger(f"Failed to rename '{cand}': {e}")
                        except Exception:
                            pass
                    try:
                        remaining.discard(idx)
                    except Exception:
                        pass
            else:
                last_size[cand] = cur_size
                stable_since[cand] = None

        try:
            time.sleep(poll_ms / 1000.0)
        except Exception:
            pass

    if remaining:
        for idx in sorted(remaining):
            try:
                logger(f"Rename: no stable file found for '{toks[idx]}' (or timed out).")
            except Exception:
                pass

    if not renamed_pairs:
        try:
            logger("Rename step: completed with 0 files renamed.")
        except Exception:
            pass

    # Optionally write an info file summarizing the shot and renamed files
    if write_info:
        try:
            ts = datetime.now()
            date_s = ts.strftime('%Y%m%d')
            ms = int(ts.microsecond / 1000)
            time_s = ts.strftime('%H%M%S') + f"{ms:03d}"
            info_name = f"{exp}_Shot{shotnum:05d}_{date_s}_{time_s}_{info_label}.txt"
            info_full = os.path.join(outdir, info_name)
            try:
                with open(info_full, 'w', encoding='utf-8') as fh:
                    fh.write(f"Experiment: {exp}\n")
                    fh.write(f"Shot: {shotnum}\n")
                    fh.write(f"Timestamp: {ts.isoformat()}\n")
                    fh.write("RenamedFiles:\n")
                    for old, new in renamed_pairs:
                        fh.write(f"{os.path.basename(old)} -> {os.path.basename(new)}\n")
                try:
                    logger(f"Wrote shot info file: {info_name}")
                except Exception:
                    pass
            except Exception as e:
                try:
                    logger(f"Failed to write info file '{info_name}': {e}")
                except Exception:
                    pass
        except Exception:
            pass

    return renamed_pairs, processed_paths
