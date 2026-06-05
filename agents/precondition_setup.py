"""
Precondition setup manager.
Loads environment-driven runtime profile and applies test-plan preconditions
before navigation/execution begins.
"""

import re
import sqlite3
from typing import Callable, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
import os


class PreconditionSetupManager:
    def __init__(self):
        load_dotenv(override=False)

    def _env_first(self, keys: List[str]) -> str:
        for key in keys:
            value = os.getenv(key, "").strip()
            if value:
                return value
        return ""

    def _normalize_marker(self, text: str) -> str:
        # Accept markdown headings like ## Preconditions or **Preconditions**:
        normalized = text.strip().lower()
        normalized = re.sub(r"^[#\-*\s]+", "", normalized)
        normalized = normalized.replace("**", "")
        normalized = normalized.strip(" :")
        return normalized

    def get_profile_summary(self) -> Dict:
        load_dotenv(override=False)
        company_url = self._env_first(["COMPANY_URL", "COMPANY_BASE_URL", "APP_COMPANY_URL"])
        admin_user = self._env_first(["ADMIN_USERNAME", "ADMIN_USER", "ADMIN_EMAIL"])
        db_url = self._env_first(["DATABASE_URL", "DB_URL"])
        api_url = self._env_first(["PRECONDITION_API_URL", "PRECONDITION_ENDPOINT"])

        return {
            "company_url": company_url,
            "admin_configured": bool(admin_user),
            "db_configured": bool(db_url),
            "api_configured": bool(api_url),
        }

    def extract_preconditions(self, context_text: str) -> List[str]:
        if not context_text:
            return []

        preconditions: List[str] = []
        in_preconditions = False

        for raw_line in context_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            marker = self._normalize_marker(stripped)
            if marker.startswith("preconditions"):
                in_preconditions = True
                continue

            if in_preconditions and (
                marker.startswith("steps")
                or marker.startswith("steps:")
                or marker.startswith("expected")
                or marker.startswith("db validation")
            ):
                in_preconditions = False
                continue

            if not in_preconditions:
                continue

            if re.match(r"^(\d+[.)]|[-*])\s+", stripped):
                cleaned = re.sub(r"^(\d+[.)]|[-*])\s+", "", stripped).strip()
                if cleaned:
                    preconditions.append(cleaned)

        return preconditions[:40]

    def apply_preconditions(self, preconditions: List[str], send_progress: Optional[Callable] = None) -> Dict:
        def emit(msg_type: str, message: str):
            if send_progress:
                send_progress(msg_type, message)

        profile = self.get_profile_summary()
        emit(
            "progress",
            (
                "🧩 Setup profile loaded: "
                f"company_url={'set' if profile['company_url'] else 'missing'}, "
                f"admin={'set' if profile['admin_configured'] else 'missing'}, "
                f"db={'set' if profile['db_configured'] else 'missing'}, "
                f"api={'set' if profile['api_configured'] else 'missing'}"
            ),
        )

        applied = 0
        skipped = []
        errors = []

        for item in preconditions:
            parsed = self._parse_toggle_precondition(item)
            if not parsed:
                skipped.append(item)
                continue

            setting_key, enabled = parsed
            result = self._apply_setting(setting_key, enabled)
            if result.get("success"):
                applied += 1
                emit("success", f"✅ Precondition applied: {setting_key}={'enabled' if enabled else 'disabled'}")
            else:
                errors.append(f"{item}: {result.get('error', 'unknown error')}")
                emit("warning", f"⚠️ Precondition failed: {item}")

        success = len(errors) == 0
        return {
            "success": success,
            "applied": applied,
            "skipped": skipped,
            "errors": errors,
            "profile": profile,
        }

    def _parse_toggle_precondition(self, text: str) -> Optional[Tuple[str, bool]]:
        normalized = text.strip().lower()

        match = re.search(
            r"(?P<setting>[a-z0-9_\- .]+?)\s+(?:is|should be|must be)?\s*(?P<state>enabled|disabled|enable|disable)\b",
            normalized,
        )
        if match:
            setting = re.sub(r"\s+", "_", match.group("setting").strip(" .-_"))
            state = match.group("state")
            return setting, state in {"enabled", "enable"}

        # Alternate phrasing: enable/disable <setting>
        alt = re.search(r"\b(?P<state>enable|disable)\s+(?P<setting>[a-z0-9_\- .]+)", normalized)
        if alt:
            setting = re.sub(r"\s+", "_", alt.group("setting").strip(" .-_"))
            state = alt.group("state")
            return setting, state == "enable"

        return None

    def _apply_setting(self, setting_key: str, enabled: bool) -> Dict:
        api_url = self._env_first(["PRECONDITION_API_URL", "PRECONDITION_ENDPOINT"])
        if api_url:
            api_result = self._apply_via_api(api_url, setting_key, enabled)
            if api_result.get("success"):
                return api_result

        db_url = self._env_first(["DATABASE_URL", "DB_URL"])
        if db_url:
            sql_template = os.getenv(
                "PRECONDITION_SQL_ENABLE_TEMPLATE" if enabled else "PRECONDITION_SQL_DISABLE_TEMPLATE",
                "",
            ).strip()
            if not sql_template:
                return {
                    "success": False,
                    "error": "Missing SQL template. Set PRECONDITION_SQL_ENABLE_TEMPLATE/PRECONDITION_SQL_DISABLE_TEMPLATE in .env",
                }

            sql = sql_template.format(
                setting=setting_key,
                enabled=1 if enabled else 0,
                company_url=self._env_first(["COMPANY_URL", "COMPANY_BASE_URL", "APP_COMPANY_URL"]),
                admin_username=self._env_first(["ADMIN_USERNAME", "ADMIN_USER", "ADMIN_EMAIL"]),
            )
            return self._execute_sql(db_url, sql)

        return {
            "success": False,
            "error": "No precondition backend configured. Set PRECONDITION_API_URL or DATABASE_URL in .env",
        }

    def _apply_via_api(self, api_url: str, setting_key: str, enabled: bool) -> Dict:
        try:
            payload = {
                "company_url": self._env_first(["COMPANY_URL", "COMPANY_BASE_URL", "APP_COMPANY_URL"]),
                "admin_username": self._env_first(["ADMIN_USERNAME", "ADMIN_USER", "ADMIN_EMAIL"]),
                "admin_password": self._env_first(["ADMIN_PASSWORD", "ADMIN_PASS"]),
                "test_user_username": self._env_first(["TEST_USER_USERNAME", "TEST_USERNAME", "QA_USER_USERNAME"]),
                "test_user_password": self._env_first(["TEST_USER_PASSWORD", "TEST_PASSWORD", "QA_USER_PASSWORD"]),
                "setting": setting_key,
                "enabled": enabled,
            }
            response = requests.post(api_url, json=payload, timeout=25)
            if 200 <= response.status_code < 300:
                return {"success": True, "mode": "api"}
            return {"success": False, "error": f"API returned {response.status_code}: {response.text[:200]}"}
        except Exception as exc:
            return {"success": False, "error": f"API call failed: {exc}"}

    def _execute_sql(self, db_url: str, sql: str) -> Dict:
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "", 1)
            return self._execute_sqlite(db_path, sql)

        if db_url.endswith(".db") or db_url.endswith(".sqlite"):
            return self._execute_sqlite(db_url, sql)

        if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
            try:
                import psycopg2  # type: ignore

                conn = psycopg2.connect(db_url)
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                    conn.commit()
                finally:
                    conn.close()
                return {"success": True, "mode": "postgres"}
            except Exception as exc:
                return {"success": False, "error": f"Postgres execution failed: {exc}"}

        if db_url.startswith("mysql://") or db_url.startswith("mariadb://"):
            try:
                import pymysql  # type: ignore
                from urllib.parse import urlparse

                parsed = urlparse(db_url)
                conn = pymysql.connect(
                    host=parsed.hostname,
                    port=parsed.port or 3306,
                    user=parsed.username,
                    password=parsed.password,
                    database=(parsed.path or "/").lstrip("/"),
                    autocommit=True,
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                finally:
                    conn.close()
                return {"success": True, "mode": "mysql"}
            except Exception as exc:
                return {"success": False, "error": f"MySQL execution failed: {exc}"}

        return {"success": False, "error": f"Unsupported DATABASE_URL scheme: {db_url}"}

    def _execute_sqlite(self, db_path: str, sql: str) -> Dict:
        try:
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.cursor()
                cur.executescript(sql)
                conn.commit()
            finally:
                conn.close()
            return {"success": True, "mode": "sqlite"}
        except Exception as exc:
            return {"success": False, "error": f"SQLite execution failed: {exc}"}
