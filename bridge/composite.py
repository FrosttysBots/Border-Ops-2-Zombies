"""Pure CPU chroma-key helpers for BL2 gun+HUD over BO2. Requires numpy (render venv).

BL2 isolation mode paints the donor world with a dense magenta fog. After BL2's own
tonemapping the live key measured about BGR (244, 9, 181), so the matte is based on
how much both red and blue exceed green rather than on one exact colour. This is a
colour key, not native alpha: translucent HUD pixels blend with the key and are
partially despilled, not recovered exactly.
"""
import json
import time
from pathlib import Path

import numpy as np

KEY_LOW = 60.    # min(R,B)-G at or below this is fully opaque donor content
KEY_HIGH = 140.  # at or above this is fully keyed (transparent)
COVERAGE_ROWS = 0.4  # upper part of the frame, mostly world, used to confirm keying
MIN_COVERAGE = 0.5
STATUS_FILE = 'blacklands_isolation.json'
STATUS_MAX_BYTES = 65536
STATUS_MAX_AGE = 2.0


def keyness(bgr):
    pixels = bgr.astype(np.float32)
    b, g, r = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    return np.minimum(r, b) - g


def alpha(bgr):
    """Donor opacity in 0..1: 0 where the key fog is, 1 for gun/HUD pixels."""
    return 1. - np.clip((keyness(bgr) - KEY_LOW) / (KEY_HIGH - KEY_LOW), 0., 1.)


def coverage(bgr):
    """Fraction of the upper frame that is fully keyed; low means isolation is not active."""
    top = bgr[:max(1, int(bgr.shape[0] * COVERAGE_ROWS))]
    return float((alpha(top) == 0.).mean())


def despill(bgr, a):
    """Pull the magenta tint out of partially keyed edges toward the green channel."""
    out = bgr.astype(np.float32)
    g = out[..., 1]
    edge = (a > 0.) & (a < 1.)
    for channel in (0, 2):
        c = out[..., channel]
        c[edge] = np.minimum(c[edge], np.maximum(g[edge], c[edge] * a[edge]))
    return out


def composite(host, donor):
    """Lay keyed donor (BL2) over host (BO2). Donor is resized to the host frame.

    Stretching to the host size is a temporary layout choice: HUD placement mapping
    between the two games is not decided yet.
    """
    if host.ndim != 3 or donor.ndim != 3 or host.shape[2] != 3 or donor.shape[2] != 3:
        raise ValueError('Expected BGR frames')
    if donor.shape[:2] != host.shape[:2]:
        import cv2
        donor = cv2.resize(donor, (host.shape[1], host.shape[0]), interpolation=cv2.INTER_AREA)
    a = alpha(donor)
    fg = despill(donor, a)
    out = fg * a[..., None] + host.astype(np.float32) * (1. - a[..., None])
    return np.clip(out, 0, 255).astype(np.uint8)


def read_status(path, session=None):
    """Bounded read of the BL2 isolation heartbeat; returns the parsed dict."""
    path = Path(path)
    with path.open('rb') as handle:
        data = handle.read(STATUS_MAX_BYTES + 1)
    if len(data) > STATUS_MAX_BYTES:
        raise ValueError('Isolation status too large')
    status = json.loads(data.decode('utf-8'))
    if not isinstance(status, dict) or status.get('schema') != 1:
        raise ValueError('Unexpected isolation status schema')
    if not isinstance(status.get('seq'), int) or status['seq'] < 1:
        raise ValueError('Invalid isolation sequence')
    if session is not None and status.get('donor_session') != session:
        raise ValueError('Isolation status belongs to another donor session')
    return status


class IsolationTracker:
    """Composite only while BL2 reports an active, isolated, advancing heartbeat."""

    def __init__(self):
        self.seq = None
        self.last_advance = None
        self.advances = 0
        self.phase = None
        self.active = False

    def observe(self, status, now=None):
        now = time.monotonic() if now is None else now
        if self.seq is None or status['seq'] > self.seq:
            if self.seq is not None:
                self.advances += 1
            self.seq = status['seq']
            self.last_advance = now
        self.phase = status.get('phase')
        self.active = bool(status.get('active'))

    def ready(self, now=None):
        now = time.monotonic() if now is None else now
        if not self.active or self.phase != 'isolated':
            return False, 'isolation_inactive'
        if self.advances < 1 or self.last_advance is None:
            return False, 'awaiting_heartbeat'
        if now - self.last_advance > STATUS_MAX_AGE:
            return False, 'heartbeat_stale'
        return True, 'isolated'
