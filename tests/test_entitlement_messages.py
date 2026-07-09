from __future__ import annotations

import inspect

from src.billing import stub as billing_stub


def test_entitlement_denied_message_is_consistent():
    source = inspect.getsource(billing_stub)
    assert source.count("Support subscription required for this appliance.") >= 1