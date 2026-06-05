"""
Unified conversational automation agent.
Supports Gemini and Ollama for response + planning.
"""

import json
import os
import re
from difflib import SequenceMatcher
from datetime import datetime
from typing import Callable, Dict, List, Optional

import requests
from dotenv import load_dotenv
from agents.precondition_setup import PreconditionSetupManager

load_dotenv()


class UnifiedChatAgent:
    def __init__(self, mcp_server=None):
        self.mcp_server = mcp_server
        self.sessions: Dict[str, Dict] = {}

        self.available_ollama_models: List[str] = []
        self.default_ollama_model: Optional[str] = None
        self.use_ollama = False

        self.gemini_api_key = ""
        self.has_gemini = False
        self.anthropic_api_key = ""
        self.has_anthropic = False
        self._refresh_gemini_key()
        self._refresh_anthropic_key()
        self.precondition_setup = PreconditionSetupManager()

        self._init_ollama()

    def _refresh_gemini_key(self):
        # Re-load .env to pick up any key updates without requiring code changes.
        load_dotenv(override=False)
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GOOGLE_GENAI_API_KEY", "").strip()
        )
        self.has_gemini = bool(self.gemini_api_key)

    def _refresh_anthropic_key(self):
        load_dotenv(override=False)
        self.anthropic_api_key = (
            os.getenv("ANTHROPIC_API_KEY", "").strip()
            or os.getenv("CLAUDE_API_KEY", "").strip()
        )
        self.has_anthropic = bool(self.anthropic_api_key)

    def _init_ollama(self):
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                self.available_ollama_models = [m.get("name") for m in models if m.get("name")]
                if self.available_ollama_models:
                    self.default_ollama_model = self.available_ollama_models[0]
                    self.use_ollama = True
                    print(f"✅ UnifiedChatAgent using Ollama default: {self.default_ollama_model}")
        except Exception:
            print("⚠️ UnifiedChatAgent: Ollama unavailable")

    def process_message(
        self,
        user_message: str,
        workspace_path: str,
        device_name: str,
        app_package: str,
        app_activity: str,
        progress_callback: Optional[Callable] = None,
        session_id: Optional[str] = None,
        agent_type: str = "balanced",
        model: Optional[str] = None,
        context_mode: str = "workspace",
        attached_files: Optional[List[str]] = None,
    ) -> Dict:
        def send_progress(msg_type: str, message: str, data: dict = None):
            if progress_callback:
                progress_callback(msg_type, message, data)

        sid = session_id or "default"
        session = self._get_or_create_session(sid)

        attached_files = attached_files or []
        selected_model = model or session.get("model") or self.default_ollama_model

        user_message, inline_context = self._extract_inline_context(user_message)

        session["agent_type"] = agent_type or session.get("agent_type", "balanced")
        session["model"] = selected_model
        session["context_mode"] = context_mode or session.get("context_mode", "workspace")
        session["attached_files"] = attached_files

        send_progress("understanding", f"🎯 {user_message}")
        send_progress(
            "progress",
            f"⚙️ Mode={session['agent_type']} | Model={selected_model or 'heuristic'} | Context={session['context_mode']}",
        )

        self._refresh_gemini_key()
        self._refresh_anthropic_key()
        if self._is_gemini_model(selected_model):
            if self.has_gemini:
                send_progress("progress", f"🧠 Gemini active: {selected_model}")
            else:
                send_progress(
                    "warning",
                    "⚠️ Gemini selected but no API key found. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in .env and restart server; falling back",
                )
        elif self._is_claude_model(selected_model):
            if self.has_anthropic:
                send_progress("progress", f"🧠 Claude active: {selected_model}")
            else:
                send_progress(
                    "warning",
                    "⚠️ Claude selected but no API key found. Set ANTHROPIC_API_KEY in .env and restart server; falling back",
                )

        session["history"].append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": datetime.now().isoformat(),
            }
        )

        attachment_context = "\n\n".join(part for part in [inline_context, self._build_attachment_context(attached_files)] if part)
        plan_steps = self._extract_plan_steps(attachment_context)
        if plan_steps:
            session["plan_steps"] = plan_steps
            session["current_plan_step"] = 0
            session["plan_search_attempts"] = {}
            send_progress("progress", f"🗺️ Loaded {len(plan_steps)} plan step(s) from context")
            preview = " | ".join(f"{i + 1}) {step}" for i, step in enumerate(plan_steps[:3]))
            send_progress("progress", f"🧭 Plan preview: {preview}")
            expected_outcomes = self._extract_expected_outcomes(attachment_context)
            session["expected_outcomes"] = expected_outcomes
            if expected_outcomes:
                send_progress("progress", f"✅ Loaded {len(expected_outcomes)} expected outcome(s) for validation")
        elif "test plan" in user_message.lower() and "CURRENT FILE:" in attachment_context:
            send_progress(
                "warning",
                "⚠️ Current file context was loaded, but it does not look like a step-based test plan. Open the markdown/text plan file before running this command.",
            )
        intent = self._detect_intent(user_message, session)
        if intent["type"] in {"navigate", "navigate_and_generate"} and session.get("plan_steps"):
            default_steps = intent.get("max_steps", self._steps_for_agent_type(session.get("agent_type", "balanced")))
            plan_budget = min(40, max(default_steps, len(session.get("plan_steps", [])) * 2))
            intent["max_steps"] = plan_budget
            send_progress("progress", f"🧮 Execution budget set to {plan_budget} steps for plan coverage")
        send_progress("intent", f"💡 Intent: {intent['type']} - {intent['description']}")

        if intent["type"] == "help":
            response = self._help_text()
            session["history"].append({"role": "assistant", "content": response})
            send_progress("chat_response", response)
            return {
                "success": True,
                "type": "help",
                "message": response,
                "session_id": sid,
                "state": self._session_state(session),
            }

        if intent["type"] == "general_chat":
            response = self._dynamic_chat_response(user_message, session, attachment_context)
            session["history"].append({"role": "assistant", "content": response})
            send_progress("chat_response", response)
            return {
                "success": True,
                "type": "chat",
                "message": response,
                "session_id": sid,
                "state": self._session_state(session),
            }

        if intent["type"] in {"navigate", "navigate_and_generate"}:
            send_progress("progress", "🔌 Connecting to device...")
            connection = self._connect_device_mcp(device_name, app_package, app_activity)
            if not connection.get("success"):
                connect_error = connection.get("error") or connection.get("message") or "Failed to connect device via MCP"
                send_progress("warning", f"⚠️ Device connect failed: {connect_error}")
                return {
                    "success": False,
                    "type": intent["type"],
                    "error": "Failed to connect device via MCP",
                    "details": connect_error,
                    "session_id": sid,
                    "state": self._session_state(session),
                }
            send_progress("success", f"✅ Connected to {device_name}")

            plan_preconditions = self.precondition_setup.extract_preconditions(attachment_context)
            if plan_preconditions:
                send_progress("progress", f"🛠️ Applying {len(plan_preconditions)} precondition(s) from plan")
                setup_result = self.precondition_setup.apply_preconditions(
                    plan_preconditions,
                    send_progress,
                    workspace_path=workspace_path,
                )
                if not setup_result.get("success"):
                    guidance = (
                        "I could not apply preconditions, so I am stopping before unreliable execution.\n"
                        f"Missing/failed setup: {'; '.join(setup_result.get('errors', []))}.\n"
                        "Next: either (1) add .env setup keys and backend config, or (2) rewrite preconditions in explicit toggle format like 'insights should be enabled'.\n"
                        "Then send: retry with preconditions."
                    )
                    send_progress("chat_response", guidance)
                    return {
                        "success": False,
                        "type": intent["type"],
                        "error": "Precondition setup failed",
                        "details": "; ".join(setup_result.get("errors", [])) or "Unable to apply required preconditions",
                        "message": guidance,
                        "session_id": sid,
                        "state": self._session_state(session),
                    }

                for warn in setup_result.get("warnings", []):
                    send_progress("warning", f"⚠️ {warn}")

                if int(setup_result.get("applied", 0)) > 0:
                    send_progress("progress", "🔄 Relaunching app to sync precondition changes")
                    relaunch = self.mcp_server.call_tool(
                        "perform_action",
                        {
                            "action": "relaunch_app",
                            "app_package": app_package,
                            "app_activity": app_activity,
                        },
                    )
                    if not relaunch.get("success"):
                        return {
                            "success": False,
                            "type": intent["type"],
                            "error": "App relaunch failed after preconditions",
                            "details": relaunch.get("error", "Relaunch action failed"),
                            "session_id": sid,
                            "state": self._session_state(session),
                        }
                    send_progress("success", "✅ Preconditions applied and app relaunched")
                else:
                    send_progress("progress", "ℹ️ No machine-applied precondition change detected; continuing without relaunch")

            exploration = self._run_agent_loop(
                session=session,
                user_message=user_message,
                workspace_path=workspace_path,
                send_progress=send_progress,
                max_steps=intent.get("max_steps", self._steps_for_agent_type(session.get("agent_type", "balanced"))),
                attachment_context=attachment_context,
            )

            if not exploration.get("success"):
                if self._is_recoverable_navigation_error(exploration):
                    healed = self._attempt_autonomous_recovery(
                        session=session,
                        send_progress=send_progress,
                        app_package=app_package,
                        app_activity=app_activity,
                        attachment_context=attachment_context,
                    )
                    if healed:
                        send_progress("progress", "🔁 Retrying navigation after auto-heal")
                        exploration = self._run_agent_loop(
                            session=session,
                            user_message=user_message,
                            workspace_path=workspace_path,
                            send_progress=send_progress,
                            max_steps=intent.get("max_steps", self._steps_for_agent_type(session.get("agent_type", "balanced"))),
                            attachment_context=attachment_context,
                        )

                if exploration.get("success"):
                    session["autonomous_retry_count"] = 0
                else:
                    session["autonomous_retry_count"] = 0

            if not exploration.get("success"):
                if exploration.get("error") == "Expected result not observed":
                    profile = self.precondition_setup.get_profile_summary(workspace_path=workspace_path)
                    missing = []
                    if not profile.get("company_url"):
                        missing.append("COMPANY_URL")
                    if not profile.get("admin_configured"):
                        missing.extend(["ADMIN_USERNAME", "ADMIN_PASSWORD"])
                    if not (profile.get("db_configured") or profile.get("api_configured")):
                        missing.append("PRECONDITION_API_URL or DATABASE_URL")

                    if missing:
                        guidance = (
                            "Expected result was not observed. This usually means precondition config/state is incomplete.\n"
                            f"Missing setup in .env: {', '.join(dict.fromkeys(missing))}.\n"
                            "Next: fill these values and send: retry with preconditions."
                        )
                    else:
                        guidance = (
                            "Expected result was not observed after executing steps.\n"
                            "Likely cause: data/state mismatch for this testcase (not parser/generation issue).\n"
                            "Next: confirm scenario data, then send: continue from current step."
                        )

                    send_progress("chat_response", guidance)
                    return {
                        **exploration,
                        "message": guidance,
                        "session_id": sid,
                        "state": self._session_state(session),
                    }
                return {**exploration, "session_id": sid, "state": self._session_state(session)}

            completion_response = self._post_navigation_response(session, user_message, exploration)
            send_progress("chat_response", completion_response)

            if intent["type"] == "navigate_and_generate":
                generation = self._generate_tests_from_locators(
                    session=session,
                    user_message=user_message,
                    workspace_path=workspace_path,
                    send_progress=send_progress,
                    framework=intent.get("framework", "Appium"),
                    language=intent.get("language", "Java"),
                    structure=intent.get("structure", "Maven POM"),
                    context_text=attachment_context,
                )
                result = {
                    "success": generation.get("success", False),
                    "type": "navigate_and_generate",
                    "exploration": exploration,
                    "generation": generation,
                    "message": completion_response,
                    "session_id": sid,
                    "state": self._session_state(session),
                }
                self._store_assistant_summary(session, result)
                return result

            result = {
                "success": True,
                "type": "navigation",
                **exploration,
                "message": completion_response,
                "session_id": sid,
                "state": self._session_state(session),
            }
            self._store_assistant_summary(session, result)
            return result

        if intent["type"] == "generate_code":
            generation = self._generate_tests_from_locators(
                session=session,
                user_message=user_message,
                workspace_path=workspace_path,
                send_progress=send_progress,
                framework=intent.get("framework", "Appium"),
                language=intent.get("language", "Java"),
                structure=intent.get("structure", "Maven POM"),
                context_text=attachment_context,
            )
            result = {
                "type": "generate_code",
                "session_id": sid,
                "state": self._session_state(session),
                **generation,
            }
            self._store_assistant_summary(session, result)
            return result

        response = self._dynamic_chat_response(user_message, session, attachment_context)
        send_progress("chat_response", response)
        return {
            "success": True,
            "type": "chat",
            "message": response,
            "session_id": sid,
            "state": self._session_state(session),
        }

    def _get_or_create_session(self, session_id: str) -> Dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "session_id": session_id,
                "history": [],
                "last_intent": None,
                "last_objective": "",
                "visited_xpaths": set(),
                "locators_file": None,
                "last_result": {},
                "agent_type": "balanced",
                "model": self.default_ollama_model,
                "context_mode": "workspace",
                "attached_files": [],
                "plan_steps": [],
                "current_plan_step": 0,
                "saved_locator_keys": set(),
                "plan_search_attempts": {},
                "recent_actions": [],
                "consecutive_failures": 0,
                "expected_outcomes": [],
                "autonomous_retry_count": 0,
            }
        return self.sessions[session_id]

    def _session_state(self, session: Dict) -> Dict:
        return {
            "agent_type": session.get("agent_type"),
            "model": session.get("model"),
            "context_mode": session.get("context_mode"),
            "last_intent": session.get("last_intent"),
            "locators_file": session.get("locators_file"),
            "attachments": session.get("attached_files", []),
        }

    def _detect_intent(self, message: str, session: Dict) -> Dict:
        message_lower = message.lower().strip()

        followup_words = {"continue", "continuw", "contine", "continuee", "next", "go on", "proceed", "keep going"}
        if any(word in message_lower for word in followup_words):
            if session.get("last_intent") in {"navigate", "navigate_and_generate"}:
                return {
                    "type": session["last_intent"],
                    "description": "Continue previous navigation objective",
                    "max_steps": max(3, self._steps_for_agent_type(session.get("agent_type", "balanced")) - 2),
                }

        has_nav = any(
            keyword in message_lower
            for keyword in [
                "navigate",
                "explore",
                "xplore",
                "tap",
                "click",
                "scroll",
                "screen",
                "ui",
                "open",
                "start",
                "place",
                "login",
            ]
        )

        has_generate = any(
            keyword in message_lower
            for keyword in [
                "generate",
                "genrete",
                "genrate",
                "gnerate",
                "create test",
                "cretae test",
                "test case",
                "test cases",
                "tset case",
                "automation",
                "appium",
                "selenium",
                "playwright",
                "typescript",
                "python",
                "java",
                "rest case",
                "tset",
            ]
        )

        if "help" in message_lower:
            return {"type": "help", "description": "Show capabilities"}

        if has_nav and has_generate:
            session["last_intent"] = "navigate_and_generate"
            session["last_objective"] = message
            return {
                "type": "navigate_and_generate",
                "description": "Explore app then generate tests",
                "framework": self._extract_framework(message),
                "language": self._extract_language(message),
                "structure": self._extract_structure(message),
                "max_steps": self._steps_for_agent_type(session.get("agent_type", "balanced")),
            }

        if has_nav:
            session["last_intent"] = "navigate"
            session["last_objective"] = message
            return {
                "type": "navigate",
                "description": "Conversational app navigation",
                "max_steps": self._steps_for_agent_type(session.get("agent_type", "balanced")),
            }

        if has_generate:
            session["last_intent"] = "generate_code"
            return {
                "type": "generate_code",
                "description": "Generate code from collected locators",
                "framework": self._extract_framework(message),
                "language": self._extract_language(message),
                "structure": self._extract_structure(message),
            }

        return {"type": "general_chat", "description": "General conversation"}

    def _is_recoverable_navigation_error(self, exploration: Dict) -> bool:
        error = str(exploration.get("error", "")).lower()
        return any(
            token in error
            for token in [
                "expected result not observed",
                "action execution failed",
                "no plan step executed",
                "no actionable ui elements found",
            ]
        )

    def _attempt_autonomous_recovery(
        self,
        session: Dict,
        send_progress: Callable,
        app_package: str,
        app_activity: str,
        attachment_context: str,
    ) -> bool:
        retry_count = int(session.get("autonomous_retry_count", 0))
        if retry_count >= 2:
            return False

        session["autonomous_retry_count"] = retry_count + 1
        send_progress("progress", f"🩹 Auto-heal attempt {session['autonomous_retry_count']}/2")

        current_step = self._current_plan_step_text(session)
        if current_step:
            screen_data = self.mcp_server.call_tool("explore_screen", {})
            if screen_data.get("success"):
                elements = screen_data.get("elements", [])
                candidate = self._match_element_to_objective(current_step + " " + attachment_context, elements, session)
                if candidate and candidate.get("xpath"):
                    click_result = self.mcp_server.call_tool(
                        "perform_action",
                        {"action": "click", "xpath": candidate.get("xpath"), "reason": "auto-heal rematch"},
                    )
                    if click_result.get("success"):
                        send_progress("success", "✅ Auto-heal matched and clicked fallback target")
                        return True

        relaunch = self.mcp_server.call_tool(
            "perform_action",
            {
                "action": "relaunch_app",
                "app_package": app_package,
                "app_activity": app_activity,
            },
        )
        if relaunch.get("success"):
            send_progress("success", "✅ Auto-heal relaunched app and will retry steps")
            return True

        send_progress("warning", f"⚠️ Auto-heal failed: {relaunch.get('error', 'unknown relaunch error')}")
        return False

    def _steps_for_agent_type(self, agent_type: str) -> int:
        if agent_type == "planner":
            return 10
        if agent_type == "executor":
            return 6
        return 8

    def _run_agent_loop(
        self,
        session: Dict,
        user_message: str,
        workspace_path: str,
        send_progress: Callable,
        max_steps: int,
        attachment_context: str,
    ) -> Dict:
        objective = user_message
        if any(token in user_message.lower() for token in ["continue", "next", "go on"]):
            objective = session.get("last_objective") or user_message

        locators_file = session.get("locators_file") or self._prepare_locators_file(workspace_path, objective)
        session["locators_file"] = locators_file

        if attachment_context:
            send_progress("progress", "📎 Using attached file context in planning")

        send_progress("progress", f"🧠 Agent objective: {objective}")

        steps_taken = []
        locators_collected = 0
        read_screen_failed = False
        read_screen_error = None
        action_failed = False
        action_error = None
        last_elements = []

        for idx in range(1, max_steps + 1):
            current_plan_step = self._current_plan_step_text(session)
            if current_plan_step:
                send_progress("progress", f"🪜 Target step: {current_plan_step}")

            screen_data = self.mcp_server.call_tool("explore_screen", {})
            if not screen_data.get("success"):
                read_screen_failed = True
                read_screen_error = screen_data.get("error") or "Unable to read current screen"
                send_progress("warning", f"⚠️ Unable to read current screen: {read_screen_error}")
                break

            elements = screen_data.get("elements", [])
            last_elements = elements
            send_progress("step", f"📱 Step {idx}/{max_steps}: found {len(elements)} elements")

            new_locators = self._save_screen_locators(session, locators_file, elements)
            locators_collected += new_locators

            next_action = self._decide_next_action(
                objective=objective,
                elements=elements,
                session=session,
                attachment_context=attachment_context,
                step_number=idx,
            )
            if not next_action:
                if current_plan_step:
                    send_progress("warning", f"⚠️ Could not find a reliable UI action for target step: {current_plan_step}")
                send_progress("progress", "✅ No better action found; stopping exploration")
                break

            action_name = next_action.get("action", "click")
            action_reason = next_action.get("reason") or "best available next move"
            send_progress("progress", f"🤔 Next action: {action_name} ({action_reason})")

            action_result = self.mcp_server.call_tool("perform_action", next_action)
            if not action_result.get("success"):
                retried = self._retry_failed_action(
                    next_action=next_action,
                    session=session,
                    objective=objective,
                    attachment_context=attachment_context,
                )
                if retried.get("success"):
                    action_result = retried
                    send_progress("progress", "♻️ Recovered with fallback strategy")

            if not action_result.get("success"):
                action_failed = True
                action_error = action_result.get("error", "unknown error")
                send_progress("warning", f"⚠️ Action failed: {action_error}")
                if current_plan_step:
                    send_progress("warning", f"⚠️ Blocked while executing plan step: {current_plan_step}")
                break

            if next_action.get("xpath"):
                session["visited_xpaths"].add(next_action["xpath"])

            steps_taken.append(next_action)
            if next_action.get("from_plan") and next_action.get("action") == "click":
                next_index = min(
                    session.get("current_plan_step", 0) + 1,
                    len(session.get("plan_steps", [])),
                )
                session["current_plan_step"] = next_index
                session.get("plan_search_attempts", {}).pop(str(next_index), None)
            reason = next_action.get("reason")
            if reason:
                send_progress("success", f"✅ Executed {action_name} ({reason})")
            else:
                send_progress("success", f"✅ Executed {action_name}")
            session["consecutive_failures"] = 0
            session.setdefault("recent_actions", []).append(action_name)
            session["recent_actions"] = session["recent_actions"][-8:]

        if read_screen_failed and not steps_taken:
            return {
                "success": False,
                "type": "navigation",
                "error": "Failed to read current screen",
                "details": read_screen_error,
                "steps_executed": 0,
                "locators_collected": locators_collected,
                "locators_file": locators_file,
                "steps": steps_taken,
            }

        if action_failed:
            return {
                "success": False,
                "type": "navigation",
                "error": "Action execution failed",
                "details": action_error,
                "steps_executed": len(steps_taken),
                "locators_collected": locators_collected,
                "locators_file": locators_file,
                "steps": steps_taken,
            }

        if session.get("plan_steps") and len(steps_taken) == 0:
            return {
                "success": False,
                "type": "navigation",
                "error": "No plan step executed",
                "details": "Plan steps were loaded but no actionable UI step could be completed on the current screen.",
                "steps_executed": 0,
                "locators_collected": locators_collected,
                "locators_file": locators_file,
                "steps": steps_taken,
            }

        if not steps_taken and locators_collected == 0:
            return {
                "success": False,
                "type": "navigation",
                "error": "No actionable UI elements found",
                "details": "Exploration ended without any actions or locators.",
                "steps_executed": 0,
                "locators_collected": 0,
                "locators_file": locators_file,
                "steps": steps_taken,
            }

        expected_outcomes = session.get("expected_outcomes") or []
        if expected_outcomes:
            verification = self._verify_expected_outcomes(expected_outcomes, last_elements)
            if verification.get("matched", 0) == 0:
                return {
                    "success": False,
                    "type": "navigation",
                    "error": "Expected result not observed",
                    "details": "Executed actions but none of the expected outcomes were observed on screen.",
                    "steps_executed": len(steps_taken),
                    "locators_collected": locators_collected,
                    "locators_file": locators_file,
                    "steps": steps_taken,
                    "expected_verification": verification,
                }

        return {
            "success": True,
            "steps_executed": len(steps_taken),
            "locators_collected": locators_collected,
            "locators_file": locators_file,
            "steps": steps_taken,
            "expected_verification": self._verify_expected_outcomes(session.get("expected_outcomes") or [], last_elements),
        }

    def _decide_next_action(
        self,
        objective: str,
        elements: List[Dict],
        session: Dict,
        attachment_context: str,
        step_number: int,
    ) -> Optional[Dict]:
        if not elements:
            return None

        llm_action = self._plan_next_action_with_llm(
            objective=objective,
            elements=elements,
            session=session,
            attachment_context=attachment_context,
            step_number=step_number,
        )
        if llm_action:
            return llm_action

        current_step = self._current_plan_step_text(session)
        if current_step:
            candidate = self._match_element_to_objective(current_step, elements, session)
            if candidate:
                return {
                    "action": "click",
                    "xpath": candidate.get("xpath"),
                    "reason": f"plan step match: {current_step}",
                    "from_plan": True,
                }
            step_index = str(session.get("current_plan_step", 0))
            attempts = session.setdefault("plan_search_attempts", {}).get(step_index, 0)
            if attempts < 3:
                session["plan_search_attempts"][step_index] = attempts + 1
                direction = "down" if attempts % 2 == 0 else "up"
                return {
                    "action": "scroll",
                    "direction": direction,
                    "reason": f"searching UI for plan step: {current_step}",
                    "from_plan": True,
                }

            # If screen is sparse, prefer trying one unseen clickable rather than over-scrolling.
            if len(elements) <= 4:
                for element in elements:
                    xpath = element.get("xpath")
                    if element.get("clickable") and xpath and xpath not in session["visited_xpaths"]:
                        return {
                            "action": "click",
                            "xpath": xpath,
                            "reason": "sparse screen fallback candidate",
                            "from_plan": True,
                        }
            return None

        candidate = self._match_element_to_objective(objective + " " + attachment_context, elements, session)
        if candidate:
            return {"action": "click", "xpath": candidate.get("xpath"), "reason": "heuristic objective match"}

        for element in elements:
            xpath = element.get("xpath")
            if element.get("clickable") and xpath and xpath not in session["visited_xpaths"]:
                return {"action": "click", "xpath": xpath, "reason": "first unseen clickable"}

        return None

    def _plan_next_action_with_llm(
        self,
        objective: str,
        elements: List[Dict],
        session: Dict,
        attachment_context: str,
        step_number: int,
    ) -> Optional[Dict]:
        model = session.get("model")

        compact_elements = []
        for idx, elem in enumerate(elements[:30]):
            compact_elements.append(
                {
                    "index": idx,
                    "text": elem.get("text"),
                    "resource_id": elem.get("resource_id"),
                    "id": elem.get("id"),
                    "accessibility_id": elem.get("accessibility_id"),
                    "clickable": elem.get("clickable"),
                    "xpath": elem.get("xpath"),
                }
            )

        prompt = (
            "You are a mobile UI automation planner. "
            "Choose the best next single action for this step. "
            "Return JSON only with keys: action, xpath, reason. "
            "Action must be one of click|scroll|back.\n"
            f"Objective: {objective}\n"
            f"Step number: {step_number}\n"
            f"Already visited xpaths count: {len(session.get('visited_xpaths', []))}\n"
            + (f"Attachment context:\n{attachment_context[:1200]}\n" if attachment_context else "")
            + "Elements:\n"
            + json.dumps(compact_elements, ensure_ascii=True)
        )

        response_text = self._run_model_prompt(prompt, model, max_tokens=500)
        if not response_text:
            return None

        parsed = self._extract_json_object(response_text)
        if not parsed:
            return None

        action = parsed.get("action")
        xpath = parsed.get("xpath")
        reason = parsed.get("reason", "llm plan")

        if action not in {"click", "scroll", "back"}:
            return None

        if action == "click" and not xpath:
            return None

        if action == "scroll":
            return {"action": "scroll", "reason": reason}
        if action == "back":
            return {"action": "back", "reason": reason}
        return {"action": "click", "xpath": xpath, "reason": reason}

    def _match_element_to_objective(self, objective: str, elements: List[Dict], session: Dict) -> Optional[Dict]:
        objective_lower = objective.lower()
        keywords = [w for w in re.split(r"\W+", objective_lower) if len(w) > 2]
        if "3 stripes" in objective_lower or "three stripes" in objective_lower:
            keywords.extend(["hamburger", "menu", "drawer", "nav", "navigation"])
        if "hamburger" in objective_lower:
            keywords.extend(["menu", "drawer", "nav", "navigation"])
        if "insights" in objective_lower:
            keywords.extend(["insight", "question", "sales"])
        keywords = list(dict.fromkeys(keywords))
        if not keywords:
            return None

        best = None
        best_score = 0

        for element in elements:
            if not element.get("clickable"):
                continue

            xpath = element.get("xpath")
            if not xpath or xpath in session["visited_xpaths"]:
                continue

            haystack = " ".join(
                [
                    str(element.get("text") or ""),
                    str(element.get("resource_id") or ""),
                    str(element.get("id") or ""),
                    str(element.get("accessibility_id") or ""),
                ]
            ).lower()

            score = sum(1 for k in keywords if k in haystack)

            # Add fuzzy similarity to tolerate text variation across UI labels.
            similarity = SequenceMatcher(None, objective_lower[:140], haystack[:140]).ratio()
            score += int(similarity * 3)

            # Strongly prefer likely menu/hamburger candidates for menu-opening steps.
            if any(token in objective_lower for token in ["3 stripes", "three stripes", "hamburger", "menu"]):
                if any(token in haystack for token in ["hamburger", "menu", "drawer", "navigation", "nav"]):
                    score += 3

            if element.get("text") and str(element.get("text")).strip():
                score += 1

            if score > best_score:
                best_score = score
                best = element

        return best if best_score > 0 else None

    def _retry_failed_action(
        self,
        next_action: Dict,
        session: Dict,
        objective: str,
        attachment_context: str,
    ) -> Dict:
        action = next_action.get("action")
        session["consecutive_failures"] = int(session.get("consecutive_failures", 0)) + 1

        if action == "click":
            # Recover from stale/missed target by re-reading screen and rematching.
            screen_data = self.mcp_server.call_tool("explore_screen", {})
            if screen_data.get("success"):
                elements = screen_data.get("elements", [])
                current_step = self._current_plan_step_text(session) or objective
                candidate = self._match_element_to_objective(current_step + " " + attachment_context, elements, session)
                if candidate and candidate.get("xpath"):
                    retry_action = {
                        "action": "click",
                        "xpath": candidate.get("xpath"),
                        "reason": "retry with rematched element",
                    }
                    return self.mcp_server.call_tool("perform_action", retry_action)

        if action == "scroll":
            # Retry scroll in opposite direction once before failing hard.
            original_direction = str(next_action.get("direction", "down")).lower()
            opposite = "up" if original_direction == "down" else "down"
            retry_action = {
                "action": "scroll",
                "direction": opposite,
                "reason": "retry opposite direction",
            }
            return self.mcp_server.call_tool("perform_action", retry_action)

        return {"success": False, "error": "Retry strategy could not recover"}

    def _save_screen_locators(self, session: Dict, locators_file: str, elements: List[Dict]) -> int:
        collected = 0
        for element in elements:
            if not (element.get("clickable") or element.get("text") or element.get("resource_id")):
                continue

            locator = {
                "timestamp": datetime.now().isoformat(),
                "text": element.get("text"),
                "resource_id": element.get("resource_id"),
                "type": element.get("type"),
                "xpath": element.get("xpath"),
                "clickable": element.get("clickable", False),
            }
            locator_key = self._locator_key(locator)
            if locator_key in session.get("saved_locator_keys", set()):
                continue
            result = self.mcp_server.call_tool("save_locator", {"file": locators_file, "locator": locator})
            if result.get("success"):
                session.setdefault("saved_locator_keys", set()).add(locator_key)
                collected += 1
        return collected

    def _locator_key(self, locator: Dict) -> str:
        return "|".join(
            [
                str(locator.get("resource_id") or ""),
                str(locator.get("text") or ""),
                str(locator.get("xpath") or ""),
            ]
        )

    def _current_plan_step_text(self, session: Dict) -> str:
        plan_steps = session.get("plan_steps") or []
        step_index = session.get("current_plan_step", 0)
        if 0 <= step_index < len(plan_steps):
            return plan_steps[step_index]
        return ""

    def _extract_plan_steps(self, context_text: str) -> List[str]:
        if not context_text:
            return []

        def section_marker(value: str) -> str:
            marker = value.strip().lower()
            marker = re.sub(r"^[#\-*\s]+", "", marker)
            marker = marker.replace("**", "")
            return marker.strip(" :")

        lowered = context_text.lower()
        if "**steps**" in lowered or "steps:" in lowered:
            steps = []
            in_steps_section = False
            for raw_line in context_text.splitlines():
                stripped = raw_line.strip()
                if not stripped:
                    continue
                marker = section_marker(stripped)
                if marker.startswith("steps"):
                    in_steps_section = True
                    continue
                if in_steps_section and (marker.startswith("expected") or marker.startswith("db validation") or marker.startswith("preconditions")):
                    in_steps_section = False
                    continue
                if not in_steps_section:
                    continue
                if re.match(r"^(step\s*\d+[:.-]|\d+[.)]|[-*])\s+", stripped, re.IGNORECASE):
                    cleaned = re.sub(r"^(step\s*\d+[:.-]|\d+[.)]|[-*])\s+", "", stripped, flags=re.IGNORECASE).strip()
                    cleaned = self._normalize_step_text(cleaned)
                    if cleaned and self._is_actionable_step(cleaned):
                        steps.append(cleaned)
            if steps:
                return self._dedupe_steps(steps)[:30]

        steps = []
        for line in context_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(token in stripped for token in ["package ", "import ", "public class", "private ", "caps.setCapability("]):
                continue
            if re.match(r"^(step\s*\d+[:.-]|\d+[.)]|[-*])\s+", stripped, re.IGNORECASE):
                cleaned = re.sub(r"^(step\s*\d+[:.-]|\d+[.)]|[-*])\s+", "", stripped, flags=re.IGNORECASE).strip()
                cleaned = self._normalize_step_text(cleaned)
                if cleaned and self._is_actionable_step(cleaned):
                    steps.append(cleaned)
        return self._dedupe_steps(steps)[:20]

    def _extract_expected_outcomes(self, context_text: str) -> List[str]:
        if not context_text:
            return []

        def section_marker(value: str) -> str:
            marker = value.strip().lower()
            marker = re.sub(r"^[#\-*\s]+", "", marker)
            marker = marker.replace("**", "")
            return marker.strip(" :")

        outcomes: List[str] = []
        in_expected = False
        for raw_line in context_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            marker = section_marker(stripped)
            if marker.startswith("expected"):
                in_expected = True
                continue
            if in_expected and (
                marker.startswith("db validation")
                or marker.startswith("preconditions")
                or marker.startswith("steps")
            ):
                in_expected = False
                continue
            if not in_expected:
                continue
            if re.match(r"^(\d+[.)]|[-*])\s+", stripped):
                cleaned = re.sub(r"^(\d+[.)]|[-*])\s+", "", stripped).strip()
                if len(cleaned) >= 4:
                    outcomes.append(cleaned)

        return outcomes[:40]

    def _verify_expected_outcomes(self, expected_outcomes: List[str], elements: List[Dict]) -> Dict:
        if not expected_outcomes:
            return {"matched": 0, "total": 0, "hits": []}

        haystack = " ".join(
            [
                str(e.get("text") or "") + " " + str(e.get("resource_id") or "") + " " + str(e.get("id") or "")
                for e in elements
            ]
        ).lower()

        hits = []
        matched = 0
        for outcome in expected_outcomes:
            tokens = [
                t
                for t in re.split(r"\W+", outcome.lower())
                if len(t) > 3 and t not in {"should", "must", "then", "user", "able"}
            ]
            is_hit = any(tok in haystack for tok in tokens[:4]) if tokens else False
            if is_hit:
                matched += 1
                hits.append(outcome)

        return {"matched": matched, "total": len(expected_outcomes), "hits": hits}

    def _dedupe_steps(self, steps: List[str]) -> List[str]:
        deduped: List[str] = []
        seen: set = set()
        for step in steps:
            normalized = re.sub(r"\s+", " ", step.strip().lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(step)
        return deduped

    def _normalize_step_text(self, step: str) -> str:
        normalized = re.sub(r"(?i)(enabled|disabled)(click|tap|open|select|enter)", r"\1 \2", step)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _is_actionable_step(self, step: str) -> bool:
        lower = step.lower()
        if "=" in lower and not any(k in lower for k in ["click", "tap", "open", "select", "enter", "start", "place", "login", "search", "menu"]):
            return False
        action_words = ["click", "tap", "open", "select", "enter", "start", "place", "login", "search", "menu", "hamburger", "call", "order"]
        return any(word in lower for word in action_words)

    def _generate_tests_from_locators(
        self,
        session: Dict,
        user_message: str,
        workspace_path: str,
        send_progress: Callable,
        framework: str,
        language: str,
        structure: str,
        context_text: str = "",
    ) -> Dict:
        locators_file = session.get("locators_file") or self._find_latest_locators(workspace_path)
        if not locators_file:
            send_progress("error", "❌ No locators found. Explore the app first.")
            return {"success": False, "error": "No locators file available"}

        send_progress("progress", f"✨ Generating {framework} {language} tests...")

        try:
            from agents.ai_code_generator_agent import AICodeGeneratorAgent

            generator = AICodeGeneratorAgent()
            instruction = (
                f"Generate {framework} tests in {language} using {structure}. "
                f"Base the tests on this objective: {user_message}"
            )

            result = generator.generate_test_code(
                user_instruction=instruction,
                test_plan_path=None,
                test_plan_content=context_text,
                locators_file=locators_file,
                workspace_path=workspace_path,
                progress_callback=send_progress,
            )

            saved_files = result.get("saved_files", []) if isinstance(result, dict) else []
            if saved_files:
                try:
                    generated_root = os.path.commonpath(saved_files)
                    send_progress("success", f"📁 Generated tests at: {generated_root}")
                except Exception:
                    pass
            return {"success": True, "locators_file": locators_file, "result": result}
        except Exception as exc:
            send_progress("error", f"❌ Code generation failed: {exc}")
            return {"success": False, "error": str(exc), "locators_file": locators_file}

    def _connect_device_mcp(self, device_name: str, app_package: str, app_activity: str) -> Dict:
        if not self.mcp_server:
            return {"success": False, "error": "MCP server unavailable"}
        result = self.mcp_server.call_tool(
            "connect_device",
            {
                "device_name": device_name,
                "app_package": app_package,
                "app_activity": app_activity,
            },
        )
        return result

    def _prepare_locators_file(self, workspace_path: str, description: str) -> str:
        locators_dir = os.path.join(workspace_path, "locators")
        os.makedirs(locators_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_desc = re.sub(r"[^a-zA-Z0-9]+", "_", description)[:40]
        return os.path.join(locators_dir, f"locators_{safe_desc}_{timestamp}.jsonl")

    def _find_latest_locators(self, workspace_path: str) -> Optional[str]:
        locators_dir = os.path.join(workspace_path, "locators")
        if not os.path.isdir(locators_dir):
            return None
        files = [name for name in os.listdir(locators_dir) if name.startswith("locators_")]
        if not files:
            return None
        latest = max(files, key=lambda name: os.path.getmtime(os.path.join(locators_dir, name)))
        return os.path.join(locators_dir, latest)

    def _build_attachment_context(self, attached_files: List[str]) -> str:
        snippets = []
        for path in attached_files[:5]:
            if not path or not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(1200)
                snippets.append(f"FILE: {os.path.basename(path)}\n{content}")
            except Exception:
                continue
        return "\n\n".join(snippets)

    def _extract_inline_context(self, user_message: str) -> (str, str):
        context_parts: List[str] = []
        cleaned_message = user_message

        selection_match = re.search(r"\[CONTEXT selection\]\s*(.*)", user_message, re.DOTALL)
        if selection_match:
            selected_text = selection_match.group(1).strip()
            if selected_text:
                context_parts.append("SELECTION CONTEXT:\n" + selected_text)
            cleaned_message = user_message[:selection_match.start()].strip()

        file_match = re.search(r"\[CONTEXT current_file=([^\]]+)\]", cleaned_message)
        if file_match:
            file_path = file_match.group(1).strip()
            cleaned_message = cleaned_message.replace(file_match.group(0), "").strip()
            if file_path and os.path.isfile(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        snippet = f.read(1600)
                    if snippet:
                        context_parts.append(f"CURRENT FILE: {os.path.basename(file_path)}\n{snippet}")
                except Exception:
                    pass

        return cleaned_message or user_message, "\n\n".join(context_parts)

    def _store_assistant_summary(self, session: Dict, result: Dict):
        summary = json.dumps(
            {
                "type": result.get("type"),
                "success": result.get("success"),
                "locators_file": result.get("locators_file") or result.get("exploration", {}).get("locators_file"),
            }
        )
        session["last_result"] = result
        session["history"].append(
            {
                "role": "assistant",
                "content": summary,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _extract_framework(self, message: str) -> str:
        msg = message.lower()
        if "playwright" in msg:
            return "Playwright"
        if "selenium" in msg:
            return "Selenium"
        if "cypress" in msg:
            return "Cypress"
        return "Appium"

    def _extract_language(self, message: str) -> str:
        msg = message.lower()
        if "python" in msg:
            return "Python"
        if "typescript" in msg:
            return "TypeScript"
        if "javascript" in msg:
            return "JavaScript"
        return "Java"

    def _extract_structure(self, message: str) -> str:
        msg = message.lower()
        if "maven" in msg or "pom" in msg:
            return "Maven POM"
        if "gradle" in msg:
            return "Gradle"
        if "page object" in msg:
            return "Page Object Model"
        return "Maven POM"

    def _help_text(self) -> str:
        return (
            "I can run as a real multi-turn copilot:\n"
            "1. Explore and act: Explore app and do login flow\n"
            "2. Continue session: continue\n"
            "3. Generate tests: now generate Appium Java tests\n"
            "4. Use attachments and context mode from the UI controls"
        )

    def _post_navigation_response(self, session: Dict, user_message: str, exploration: Dict) -> str:
        prompt = (
            "Summarize the navigation outcome as a natural copilot update.\n"
            f"User request: {user_message}\n"
            f"Steps executed: {exploration.get('steps_executed')}\n"
            f"Locators collected: {exploration.get('locators_collected')}\n"
            f"Locators file: {exploration.get('locators_file')}\n"
            "Use exactly 3 short lines in this format:\n"
            "What I did: ...\n"
            "What happened: ...\n"
            "Next best move: ..."
        )
        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=180)
        if response:
            return response.strip()
        steps = exploration.get("steps_executed", 0)
        locators = exploration.get("locators_collected", 0)
        locators_file = exploration.get("locators_file", "not available")
        return (
            f"What I did: I navigated the app toward your objective and executed {steps} action(s).\n"
            f"What happened: I captured {locators} locator(s) and saved them to {locators_file}.\n"
            "Next best move: Ask me to continue from this screen or generate tests from these locators."
        )

    def _dynamic_chat_response(self, user_message: str, session: Dict, attachment_context: str) -> str:
        prompt = self._build_chat_prompt(user_message, session, attachment_context)
        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=350)
        if response:
            return response.strip()

        if session.get("last_objective"):
            return (
                f"I understand: {user_message}.\n"
                f"Current objective in session: {session.get('last_objective')}.\n"
                "If you want, I can continue from the current app state or switch to a new task."
            )
        return (
            f"I understand: {user_message}.\n"
            "Tell me the app goal, and I will run it step-by-step with live action updates and clear failure reasons if blocked."
        )

    def _build_chat_prompt(self, user_message: str, session: Dict, attachment_context: str) -> str:
        history_lines = []
        for item in session.get("history", [])[-6:]:
            history_lines.append(f"{item.get('role', 'user')}: {item.get('content', '')}")

        return (
            "You are a high-quality real-time QA automation copilot.\n"
            "Style rules:\n"
            "- Sound natural, direct, and confident.\n"
            "- Do not overclaim; be explicit when blocked.\n"
            "- Use concrete next steps based on current state.\n"
            "- Keep the reply compact (4-8 lines).\n"
            "- Avoid generic assistant filler.\n"
            f"Agent type: {session.get('agent_type')}\n"
            f"Context mode: {session.get('context_mode')}\n"
            f"Last objective: {session.get('last_objective')}\n"
            "Conversation:\n"
            + "\n".join(history_lines)
            + "\n"
            + (f"Attachment context:\n{attachment_context}\n" if attachment_context else "")
            + f"Current user message: {user_message}\n"
            + "Respond in this structure:\n"
            + "1) Understanding\n"
            + "2) What I can do now\n"
            + "3) Best next command/message to send"
        )

    def _run_model_prompt(self, prompt: str, model: Optional[str], max_tokens: int = 300) -> Optional[str]:
        if self._is_gemini_model(model):
            response = self._run_gemini_prompt(prompt, model, max_tokens=max_tokens)
            if response:
                return response

        if self._is_claude_model(model):
            response = self._run_claude_prompt(prompt, model, max_tokens=max_tokens)
            if response:
                return response

        if self.use_ollama:
            selected_model = model if model and not self._is_gemini_model(model) and not self._is_claude_model(model) else self.default_ollama_model
            response = self._run_ollama_prompt(prompt, selected_model, max_tokens=max_tokens)
            if response:
                return response

        return None

    def _run_gemini_prompt(self, prompt: str, model: Optional[str], max_tokens: int = 300) -> Optional[str]:
        if not self.has_gemini:
            return None

        selected_model = model or "gemini-1.5-pro"
        aliases = {
            "gemini-pro": "gemini-1.5-pro",
            "gemini-flash": "gemini-1.5-flash",
        }
        selected_model = aliases.get(selected_model, selected_model)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens,
            },
        }

        try:
            response = requests.post(
                url,
                params={"key": self.gemini_api_key},
                json=payload,
                timeout=45,
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
                    return text.strip() if text else None
        except Exception:
            return None

        return None

    def _run_ollama_prompt(self, prompt: str, model: Optional[str], max_tokens: int = 300) -> Optional[str]:
        selected_model = model or self.default_ollama_model
        if not selected_model:
            return None
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=40,
            )
            if response.status_code == 200:
                return (response.json().get("response") or "").strip()
        except Exception:
            return None

        return None

    def _run_claude_prompt(self, prompt: str, model: Optional[str], max_tokens: int = 300) -> Optional[str]:
        if not self.has_anthropic:
            return None

        selected_model = model or "claude-3-5-sonnet-latest"
        aliases = {
            "claude-sonnet": "claude-3-5-sonnet-latest",
            "claude-haiku": "claude-3-5-haiku-latest",
        }
        selected_model = aliases.get(selected_model, selected_model)

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": selected_model,
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=45,
            )
            if response.status_code == 200:
                payload = response.json()
                parts = payload.get("content", [])
                text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text")
                return text.strip() if text else None
        except Exception:
            return None

        return None

    def _is_gemini_model(self, model: Optional[str]) -> bool:
        return bool(model and model.lower().startswith("gemini"))

    def _is_claude_model(self, model: Optional[str]) -> bool:
        return bool(model and model.lower().startswith("claude"))

    def _extract_json_object(self, text: str) -> Optional[Dict]:
        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None

        try:
            return json.loads(match.group())
        except Exception:
            return None
