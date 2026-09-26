"""API routers, all mounted under /api. Owners are listed in AGENTS.md."""

from . import agent, buddy, community, devices, report, stream, users

ALL = (devices.router, users.router, stream.router, agent.router, community.router, buddy.router, report.router)
