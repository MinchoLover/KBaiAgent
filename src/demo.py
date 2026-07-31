"""Backward-compatible offline demo entry points."""

from src.application.demo_service import (
    run_decision_support_demo,
    run_integrated_decision_demo,
    run_offline_demo,
)


__all__ = [
    "run_decision_support_demo",
    "run_integrated_decision_demo",
    "run_offline_demo",
]
