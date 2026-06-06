"""
AI Test Navigator Agent
AI-guided test-plan executor built on top of UIExplorerAgent.
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional


class AITestNavigatorAgent:
    """Executes markdown test plans by navigating current app UI."""

    def __init__(self, ui_explorer_agent):
        self.ui_explorer = ui_explorer_agent
        self.collected_locators: Dict[str, Dict] = {}
        self.locator_ids = set()

    def parse_test_plan(self, test_plan_path: str) -> List[Dict]:
        test_cases = []

        with open(test_plan_path, "r", encoding="utf-8") as f:
            content = f.read()

        tc_pattern = r"#### (TC\d+): (.+?)\n"
        matches = list(re.finditer(tc_pattern, content))

        for i, match in enumerate(matches):
            tc_id = match.group(1)
            tc_name = match.group(2)
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            tc_content = content[start_pos:end_pos]

            steps = []
            steps_section = re.search(r"\*\*Steps\*\*:\n(.*?)\n\n", tc_content, re.DOTALL)
            if steps_section:
                for line in steps_section.group(1).strip().split("\n"):
                    step_text = re.sub(r"^\d+\.\s*", "", line.strip())
                    if step_text:
                        steps.append(step_text)

            expected = []
            expected_section = re.search(r"\*\*Expected Results\*\*:\n(.*?)\n\n", tc_content, re.DOTALL)
            if expected_section:
                for line in expected_section.group(1).strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        expected.append(line[2:])

            test_cases.append({
                "id": tc_id,
                "name": tc_name,
                "steps": steps,
                "expected": expected,
            })

        return test_cases

    def _find_element_by_hint(self, hint: str, ui_elements: List[Dict]) -> Optional[Dict]:
        hint_lower = (hint or "").lower()
        keywords = [k for k in re.split(r"\W+", hint_lower) if len(k) > 2]

        best_match = None
        best_score = 0

        for elem in ui_elements:
            haystack = " ".join(
                [
                    str(elem.get("resource_id") or ""),
                    str(elem.get("text") or ""),
                    str(elem.get("accessibility_id") or ""),
                    str(elem.get("id") or ""),
                ]
            ).lower()
            score = sum(1 for k in keywords if k in haystack)
            if score > best_score:
                best_score = score
                best_match = elem

        if best_match:
            return best_match

        for elem in ui_elements:
            if elem.get("clickable"):
                return elem

        return None

    def _get_current_screen_elements(self) -> List[Dict]:
        if not self.ui_explorer.driver:
            return []
        screen_result = self.ui_explorer.explore_current_screen("CurrentScreen")
        if not screen_result.get("success"):
            return []
        return screen_result.get("elements", [])

    def _save_locator_if_new(self, element: Dict, test_case_id: str, step_text: str) -> bool:
        locator_id = element.get("resource_id") or element.get("text") or element.get("accessibility_id")
        if not locator_id or locator_id in self.locator_ids:
            return False

        self.locator_ids.add(locator_id)
        self.collected_locators[locator_id] = {
            "resource_id": element.get("resource_id"),
            "xpath": element.get("xpath"),
            "accessibility_id": element.get("accessibility_id"),
            "text": element.get("text"),
            "type": element.get("type"),
            "clickable": element.get("clickable"),
            "test_case": test_case_id,
            "step": step_text,
        }
        return True

    def _execute_action(self, action: str, element: Optional[Dict], input_value: Optional[str] = None) -> Dict:
        if not self.ui_explorer.driver:
            return {"success": False, "error": "Driver not connected"}

        action_lower = (action or "click").lower()

        try:
            if action_lower in {"wait", "verify"}:
                return {"success": True}

            if action_lower == "scroll":
                self.ui_explorer.driver.swipe(500, 1500, 500, 500, 500)
                return {"success": True}

            if not element:
                return {"success": False, "error": "No target element"}

            xpath = element.get("xpath")
            if not xpath:
                return {"success": False, "error": "No xpath for target element"}

            found = self.ui_explorer.driver.find_element("xpath", xpath)
            if action_lower in {"enter", "type", "input"}:
                found.clear()
                found.send_keys(input_value or "")
            else:
                found.click()

            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _save_locators_file(self, test_case_id: str) -> str:
        workspace_path = os.getcwd()
        out_dir = os.path.join(workspace_path, "locators")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = os.path.join(out_dir, f"{test_case_id}_{ts}_locators.txt")

        with open(out_file, "w", encoding="utf-8") as f:
            f.write(f"# Locators for {test_case_id}\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
            for key, value in self.collected_locators.items():
                f.write(f"- id: {key}\n")
                f.write(json.dumps(value, ensure_ascii=True, indent=2))
                f.write("\n\n")

        return out_file

    def execute_test_case_with_ai(
        self,
        test_case: Dict,
        device_name: str = "127.0.0.1:6555",
        app_package: str = None,
        app_activity: str = None,
    ) -> Dict:
        connection = self.ui_explorer.connect_to_emulator(
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity,
        )
        if not connection.get("success"):
            return {
                "success": False,
                "error": connection.get("error", "connect failed"),
                "test_case_id": test_case.get("id", "unknown"),
            }

        execution_log = []
        steps_executed = 0
        locators_collected = 0

        for step in test_case.get("steps", []):
            current_elements = self._get_current_screen_elements()
            target = self._find_element_by_hint(step, current_elements)

            if target and self._save_locator_if_new(target, test_case.get("id", "TC"), step):
                locators_collected += 1

            action = "click"
            step_lower = step.lower()
            if any(k in step_lower for k in ["enter", "type", "input"]):
                action = "enter"
            elif "scroll" in step_lower:
                action = "scroll"
            elif "wait" in step_lower:
                action = "wait"

            action_result = self._execute_action(action, target)
            execution_log.append(
                {
                    "step": step,
                    "action": action,
                    "result": action_result,
                    "target": target.get("text") if target else None,
                }
            )
            steps_executed += 1
            time.sleep(0.3)

        self.ui_explorer.disconnect()
        locators_file = self._save_locators_file(test_case.get("id", "TC"))

        return {
            "success": True,
            "test_case_id": test_case.get("id"),
            "test_case_name": test_case.get("name"),
            "steps_executed": steps_executed,
            "locators_collected": locators_collected,
            "locators_file": locators_file,
            "execution_log": execution_log,
            "locators": self.collected_locators,
        }

    def execute_test_plan_with_ai(
        self,
        test_plan_path: str,
        device_name: str = "127.0.0.1:6555",
        app_package: str = None,
        app_activity: str = None,
    ) -> Dict:
        if not os.path.exists(test_plan_path):
            return {"success": False, "error": f"Test plan not found: {test_plan_path}"}

        test_cases = self.parse_test_plan(test_plan_path)
        results = []
        total_locators = 0

        for test_case in test_cases:
            self.collected_locators = {}
            self.locator_ids = set()
            result = self.execute_test_case_with_ai(
                test_case,
                device_name=device_name,
                app_package=app_package,
                app_activity=app_activity,
            )
            results.append(result)
            if result.get("success"):
                total_locators += result.get("locators_collected", 0)

        return {
            "success": True,
            "test_plan_path": test_plan_path,
            "test_cases_executed": len(test_cases),
            "total_locators_collected": total_locators,
            "results": results,
        }
