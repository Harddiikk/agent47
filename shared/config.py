"""Shared configuration — single source of truth for model selection.

Set GEMINI_MODEL in .env to override (e.g. 'gemini-2.5-flash', 'gemini-2.5-pro',
'gemini-2.5-flash-lite'). Default is gemini-2.5-flash — the prior default
gemini-2.0-flash was retired by Google (404 NOT_FOUND).
"""
import os

DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
