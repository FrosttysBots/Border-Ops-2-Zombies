"""Native BL2 read-only probe; no gun generation or inventory changes yet."""
import json
import os
import time
import uuid
from pathlib import Path
from mods_base import Game, build_mod, get_pc, hook
from unrealsdk import logging
from .wire import DONOR_FILE, HOST_FILE, REPLY_FILE, WEAPON_FILE, parse_host, read_bounded, write_atomic
from .weapon import inspect_weapon

_session = ""
_seq = 0
_next_sample = 0.0
_last_error = None
_mailbox = None


def enable():
    global _session, _seq, _next_sample, _mailbox, _last_error
    configured = os.environ.get("BLACKLANDS_MAILBOX")
    # Plutonium's observed T6 sandbox. Explicit configuration always takes priority.
    local = os.environ.get("LOCALAPPDATA")
    _mailbox = (Path(configured).resolve() if configured else
                Path(local) / 'Plutonium/storage/t6/raw/scriptdata' if local else None)
    _session, _seq, _next_sample, _last_error = uuid.uuid4().hex, 0, 0.0, None
    if _mailbox is None or not _mailbox.is_dir():
        _mailbox = None
        logging.warning("BlackLands: mailbox not found; start the BO2 probe or set BLACKLANDS_MAILBOX.")
    else:
        logging.info("BlackLands: BL2 probe v0.2.0 enabled; read-only weapon inspection, 4 Hz.")


def disable():
    global _mailbox
    _mailbox = None
    logging.info("BlackLands: BL2 probe disabled.")


@hook("Engine.PlayerController:PlayerTick")
def sample(*_args):
    global _seq, _next_sample, _last_error
    now = time.monotonic()
    if _mailbox is None or now < _next_sample:
        return
    _next_sample = now + 0.25
    try:
        pc = get_pc(possibly_loading=True)
        if pc is None or pc.Pawn is None:
            return
        # All UObject access occurs in this game-thread hook, never a worker.
        pawn = pc.Pawn
        position = pawn.Location
        weapon = pawn.Weapon
        weapon_path = "None" if weapon is None else weapon._path_name()
        host_seq = None
        try:
            host_seq = parse_host(read_bounded(_mailbox / HOST_FILE))["seq"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        _seq = (_seq + 1) % 2_000_000_001
        snapshot = dict(schema=1, source="bl2", session=_session, seq=_seq,
                        host_seq=host_seq, position=[float(position.X), float(position.Y), float(position.Z)],
                        weapon=weapon_path)
        write_atomic(_mailbox / DONOR_FILE, json.dumps(snapshot, allow_nan=False) + "\n")
        if host_seq is not None:
            write_atomic(_mailbox / REPLY_FILE, f"BLPT1|{host_seq}|{_seq}|ACK\n")
        # Separate bounded packet: diagnostics cannot prevent host acknowledgement.
        detail = dict(schema=1, source="bl2_weapon", session=_session, seq=_seq,
                      weapon=inspect_weapon(weapon))
        write_atomic(_mailbox / WEAPON_FILE, json.dumps(detail, allow_nan=False) + "\n")
        _last_error = None
    except Exception as exc:
        message = str(exc)
        if message != _last_error:
            logging.warning(f"BlackLands probe: {message}")
            _last_error = message


build_mod(name="Black Lands 2 Passthrough Probe", author="Black Lands 2",
          version="0.2.0", description="Read-only connection and native weapon inspection. No gameplay changes.",
          supported_games=Game.BL2, hooks=[sample], on_enable=enable, on_disable=disable)
