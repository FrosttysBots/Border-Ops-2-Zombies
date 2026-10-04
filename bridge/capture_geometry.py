"""Validate client-area cropping against measured window bounds; no guessed offsets."""
def client_crop(frame_size, outer_bounds, client_bounds):
    width, height = frame_size
    left, top, right, bottom = outer_bounds
    cl, ct, cr, cb = client_bounds
    if (right-left, bottom-top) != (width, height):
        raise ValueError('Captured dimensions do not match measured window bounds')
    if not (left <= cl < cr <= right and top <= ct < cb <= bottom):
        raise ValueError('Client bounds fall outside the captured window')
    return cl-left, ct-top, cr-left, cb-top
