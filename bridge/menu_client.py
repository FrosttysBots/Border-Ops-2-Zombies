"""One fixed inventory request with a finite wait for native confirmation."""
import time
from menu_wire import STATUS_FILE, REQUEST_FILE, read_packet, write_packet, validate_status


class StatusTracker:
    def __init__(self):
        self.activation = None
        self.seq = -1
        self.advances = 0
        self.last_advance = None

    def observe(self, packet, now):
        validate_status(packet)
        if self.activation != packet['activation']:
            self.activation = packet['activation']; self.seq = -1
            self.advances = 0; self.last_advance = None
        if packet['seq'] > self.seq:
            self.seq = packet['seq']; self.advances += 1; self.last_advance = now
        return (packet['active'] and self.advances >= 2 and self.last_advance is not None
                and now-self.last_advance <= 1)


def open_inventory(box, emit=lambda _: None):
    """Caller holds panel lock. Never retry native invocation after uncertain outcome."""
    tracker = StatusTracker(); ready_by = time.monotonic()+3
    status = None
    while time.monotonic() < ready_by:
        try:
            candidate = validate_status(read_packet(box/STATUS_FILE))
            if tracker.observe(candidate, time.monotonic()):
                status = candidate; break
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(.05)
    if status is None:
        raise RuntimeError('Menu adapter is offline. Run start_menu_control.py in BL2.')
    if status['last_request'] >= 128:
        raise RuntimeError('Activation request limit reached; restart the menu adapter.')
    now_ms = int(time.time()*1000)
    request = dict(schema=1, activation=status['activation'], donor_session=status['donor_session'],
                   seq=status['last_request']+1, action='open_inventory',
                   created_ms=now_ms, expires_ms=now_ms+2000)
    if not write_packet(box/REQUEST_FILE, request):
        raise RuntimeError('Request mailbox is busy; nothing was submitted.')
    emit(dict(event='submitted', activation=request['activation'], seq=request['seq']))
    deadline = time.monotonic()+4.5
    while time.monotonic() < deadline:
        try:
            current = validate_status(read_packet(box/STATUS_FILE))
        except (OSError, ValueError, KeyError, TypeError):
            time.sleep(.05); continue
        if current['activation'] != request['activation'] or current['donor_session'] != request['donor_session']:
            raise RuntimeError('Adapter restarted; old request will not be replayed.')
        fresh = tracker.observe(current, time.monotonic())
        result = current.get('result')
        if not current['active']:
            raise RuntimeError('Adapter stopped before confirmation.')
        if fresh and isinstance(result, dict) and result.get('seq') == request['seq']:
            if result.get('state') in ('opened', 'already_open'):
                emit(dict(event='confirmed', **result)); return result
            if result.get('state') != 'awaiting_menu':
                raise RuntimeError('Native request outcome: '+str(result.get('state')))
        time.sleep(.05)
    raise RuntimeError('Menu outcome unconfirmed. Check BL2; the request will not be replayed.')
