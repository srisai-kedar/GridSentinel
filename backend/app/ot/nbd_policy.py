"""
nbd_policy.py
-------------
Network-Behaviour-Detector (NBD) policy: decides whether an *observed* Modbus
request is acceptable for this deployment.

DESIGN RULE (anti-leakage)
==========================
The verdict "unexpected write" is a pure function of what appeared on the wire:
the Modbus function code (and, optionally, the register address). It is NEVER
supplied by whoever generated the traffic, and it never depends on scenario
labels, attack types, ground truth, or a free-text "source" name. Emitters
(SCADA master, attacker scripts, tests) cannot declare their own traffic
"unexpected"; only :func:`is_unexpected_write` can, and only from wire facts.

Deployment model
----------------
In the simulated distribution SCADA the master only ever *reads* telemetry
(FC03). RTUs are read-only from the master's perspective, so every write-class
function code is unexpected unless an explicit allow-rule says otherwise.
``AUTHORIZED_WRITES`` is the allow-list hook (empty by default).

Limitation (stated, not hidden)
-------------------------------
pymodbus does not expose the peer IP to server-side trace hooks, so this policy
cannot do source/path binding. A real passive tap (SPAN port) would add that.
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Set, Tuple

# Modbus function codes that modify server state.
#   5  Write Single Coil         15 Write Multiple Coils
#   6  Write Single Register     16 Write Multiple Registers
#   21 Write File Record         22 Mask Write Register
#   23 Read/Write Multiple Registers (contains a write)
WRITE_CLASS_FUNCTION_CODES: FrozenSet[int] = frozenset({5, 6, 15, 16, 21, 22, 23})

# Function codes the master legitimately uses against RTUs in this deployment.
READ_ONLY_FUNCTION_CODES: FrozenSet[int] = frozenset({3})

# Allow-list hook: set of (function_code, register_address) pairs that are
# authorised writes. Empty: no legitimate writer exists in this deployment.
AUTHORIZED_WRITES: Set[Tuple[int, int]] = set()


def is_write_class(function_code: int) -> bool:
    """True if the function code modifies RTU state."""
    return int(function_code) in WRITE_CLASS_FUNCTION_CODES


def is_unexpected_write(function_code: int, address: Optional[int] = None) -> bool:
    """
    Policy verdict for ONE observed request.

    Depends only on the observed function code (and optionally address).
    """
    fc = int(function_code)
    if not is_write_class(fc):
        return False
    if address is not None and (fc, int(address)) in AUTHORIZED_WRITES:
        return False
    return True
