"""Proactive check-ins: when risk jumps or runs high, Airmate "calls" the person.

OWNER: A1 (agent-voice). ``register`` is called once at startup; it subscribes to every new risk
assessment. The stub below does nothing. To implement (see agents/A1-agent-voice.md):

* Trigger when ``score >= settings.high_risk_score`` OR the score rose by at least
  ``settings.checkin_jump_points`` above its minimum over the last ``settings.checkin_jump_window_s``.
  Respect ``settings.checkin_cooldown_s`` per person.
* Store a ``checkin`` event, publish ``checkin`` on ``user:<id>`` (payload in docs/API.md), and
  generate the spoken opener with Grok (fallback template when Grok is off), naming the top factor.
* If the person has not answered after ``settings.buddy_nudge_delay_s``, nudge their buddy
  (``buddy_nudge`` on ``user:<buddy_id>`` plus ntfy push when configured).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..deps import AppState


def register(state: AppState) -> None:
    async def on_risk(user_id: str, assessment: dict, previous: dict | None) -> None:
        return None  # TODO(A1): decide whether to check in

    state.risk.add_listener(on_risk)


async def on_button(state: AppState, user_id: str, press: str) -> None:
    """The device button was pressed ("short" or "long"); called by routers/devices.py.

    TODO(A1): short press answers the open check-in with "ok"; long press starts the emergency flow.
    """
    return None
