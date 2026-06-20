"""
Account storage
"""

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any


class AccountStorage:
    """Account data storage"""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path or self._default_storage_path())
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.accounts_dir = self.storage_path / "accounts"
        self.accounts_dir.mkdir(exist_ok=True)

    def _default_storage_path(self) -> str:
        """Get default storage path"""
        # Check environment variable
        env_path = os.environ.get("WEIXIN_CLAWBOT_STORAGE")
        if env_path:
            return env_path

        # Use ~/.weixin-clawbot
        home = Path.home()
        return str(home / ".weixin-clawbot")

    def save_account(
        self,
        account_id: str,
        token: str,
        base_url: str,
        user_id: Optional[str] = None,
    ):
        """Save account credentials"""
        data = {
            "account_id": account_id,
            "token": token,
            "base_url": base_url,
            "user_id": user_id,
        }

        account_file = self.accounts_dir / f"{account_id}.json"
        with open(account_file, "w") as f:
            json.dump(data, f, indent=2)

        # Update index
        self._update_index(account_id)

    def load_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Load account credentials"""
        account_file = self.accounts_dir / f"{account_id}.json"

        if not account_file.exists():
            return None

        try:
            with open(account_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def list_accounts(self) -> List[str]:
        """List all saved account IDs"""
        index_file = self.storage_path / "accounts.json"

        if not index_file.exists():
            return []

        try:
            with open(index_file, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, IOError):
            pass

        return []

    def _update_index(self, account_id: str):
        """Update account index"""
        index_file = self.storage_path / "accounts.json"

        accounts = self.list_accounts()
        if account_id not in accounts:
            accounts.append(account_id)
            with open(index_file, "w") as f:
                json.dump(accounts, f, indent=2)

    def save_sync_buf(self, account_id: str, sync_buf: str):
        """Save sync buffer"""
        sync_file = self.accounts_dir / f"{account_id}.sync.json"
        data = {"get_updates_buf": sync_buf}
        with open(sync_file, "w") as f:
            json.dump(data, f)

    def load_sync_buf(self, account_id: str) -> str:
        """Load sync buffer"""
        sync_file = self.accounts_dir / f"{account_id}.sync.json"

        if not sync_file.exists():
            return ""

        try:
            with open(sync_file, "r") as f:
                data = json.load(f)
                return data.get("get_updates_buf", "")
        except (json.JSONDecodeError, IOError):
            return ""

    def delete_account(self, account_id: str):
        """Delete account"""
        account_file = self.accounts_dir / f"{account_id}.json"
        sync_file = self.accounts_dir / f"{account_id}.sync.json"

        if account_file.exists():
            account_file.unlink()

        if sync_file.exists():
            sync_file.unlink()

        # Update index
        accounts = self.list_accounts()
        if account_id in accounts:
            accounts.remove(account_id)
            index_file = self.storage_path / "accounts.json"
            with open(index_file, "w") as f:
                json.dump(accounts, f, indent=2)
