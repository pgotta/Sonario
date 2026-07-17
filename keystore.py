"""
keystore.py - remembers provider API keys between runs, locally.

Sonario's default is to keep API keys in memory only. That is the safest thing,
but it means retyping the key every launch. This module adds an OPT-IN "remember"
option: when you tick the box, the key is saved to credentials/api_keys.json so
the app can fill it in next time.

Honest about what this is:
  - The key is stored in PLAIN TEXT in your credentials/ folder (which is
    gitignored, so it never gets committed).
  - Anything that can read your user account's files can read it. There is no
    meaningful way to encrypt it locally, because the app would have to store the
    decryption key right next to it. This is the same trade-off every desktop app
    makes when it offers to remember a key.
  - It never leaves your machine, and it is only sent to the provider you picked.

Use the local models if you'd rather not store a key at all.
"""

import json
import os

CREDS_DIR = os.path.join(os.path.dirname(__file__), "credentials")
os.makedirs(CREDS_DIR, exist_ok=True)
KEYS_FILE = os.path.join(CREDS_DIR, "api_keys.json")


def _read_all():
    """Return the whole {provider_id: key} map. Never raises."""
    if not os.path.exists(KEYS_FILE):
        return {}
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all(data):
    """Write the map, best-effort. Tightens file permissions where the OS allows."""
    try:
        with open(KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # Owner read/write only. On Windows this is a no-op, but it costs nothing
        # and helps on macOS/Linux forks.
        try:
            os.chmod(KEYS_FILE, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def get_key(provider_id):
    """Return the saved key for a provider, or '' if none."""
    if not provider_id:
        return ""
    return (_read_all().get(provider_id) or "").strip()


def save_key(provider_id, key):
    """Save (or update) a provider's key. Empty key removes it."""
    if not provider_id:
        return False
    data = _read_all()
    key = (key or "").strip()
    if key:
        data[provider_id] = key
    else:
        data.pop(provider_id, None)
    return _write_all(data)


def forget_key(provider_id):
    """Remove one provider's saved key."""
    return save_key(provider_id, "")


def saved_providers():
    """List of provider ids that currently have a key saved."""
    return sorted(_read_all().keys())
