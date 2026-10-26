"""Private account history.

The repo is public, but the running history of *every* account seen in a
pattern must not be: someone who joined one pile-on should never be findable.
So the history is encrypted with a key that lives only in the GitHub Actions
secret HISTORY_KEY. Only accounts that pass the public threshold are written
in plain text (data/accounts.json).

Accounts are referenced in public incident files by an opaque `ref` (a keyed
hash of their ID). A ref can't be reversed; the site can only resolve refs
that belong to publicly listed accounts.

Without HISTORY_KEY (local development), history is kept unencrypted in
.local/, which is git-ignored.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:  # local runs without the dependency fall back to .local/
    Fernet = None  # type: ignore


class HistoryStore:
    def __init__(self, data_dir: Path, key: str | None = None, local_dir: Path = Path(".local")):
        key = key if key is not None else os.environ.get("HISTORY_KEY")
        if key:
            if Fernet is None:
                raise RuntimeError("HISTORY_KEY is set but the 'cryptography' package is missing")
            self._fernet = Fernet(key.encode())
            self._ref_key = hashlib.sha256(b"epicenter-ref:" + key.encode()).digest()
            self.path = data_dir / "history.enc"
        else:
            self._fernet = None
            local_dir.mkdir(parents=True, exist_ok=True)
            salt_file = local_dir / "ref-salt"
            if not salt_file.exists():
                salt_file.write_text(base64.b64encode(os.urandom(32)).decode())
            self._ref_key = base64.b64decode(salt_file.read_text())
            self.path = local_dir / "history.json"

    @property
    def encrypted(self) -> bool:
        return self._fernet is not None

    def ref(self, did: str) -> str:
        return hmac.new(self._ref_key, did.encode(), hashlib.sha256).hexdigest()[:12]

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        raw = self.path.read_bytes()
        if self._fernet:
            raw = self._fernet.decrypt(raw)
        return json.loads(raw)

    def save(self, accounts: dict) -> None:
        raw = json.dumps(accounts, sort_keys=True, separators=(",", ":")).encode()
        if self._fernet:
            raw = self._fernet.encrypt(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(raw)


def generate_key() -> str:
    if Fernet is None:
        raise RuntimeError("pip install cryptography first")
    return Fernet.generate_key().decode()
