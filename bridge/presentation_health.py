"""Select only advancing capture frames; donor failure can fall back to the host."""
def choose_capture(desired, states, now):
    def ready(source):
        state = states[source]
        return (not state['closed'] and not state['error'] and state['latest'] is not None
                and 0 <= now-state['latest'][0] <= 2)
    if ready(desired):
        return desired, None
    if desired == 'bl2' and ready('bo2'):
        return 'bo2', 'bl2_capture_unavailable'
    return None, f'{desired}_capture_unavailable'
