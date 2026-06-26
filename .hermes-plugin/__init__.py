"""Hermes SIP VoIP Gateway plugin."""

from .adapter import SiprecPassiveAdapter, register

__all__ = ["SiprecPassiveAdapter", "register"]
