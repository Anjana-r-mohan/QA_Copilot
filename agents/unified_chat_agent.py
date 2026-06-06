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

    def reset_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        return self.sessions.pop(session_id, None) is not None

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
        selected_model = model or session.get("model") or "gemini-3-flash-preview"

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
            session["step_results"] = []
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

        if intent["type"] == "connect":
            send_progress("progress", "🔌 Connecting to device...")
            connection = self._connect_device_mcp(device_name, app_package, app_activity)
            if not connection.get("success"):
                connect_error = connection.get("error") or connection.get("message") or "Failed to connect device via MCP"
                send_progress("warning", f"⚠️ Device connect failed: {connect_error}")
                return {
                    "success": False,
                    "type": "connect",
                    "error": "Failed to connect device via MCP",
                    "details": connect_error,
                    "session_id": sid,
                    "state": self._session_state(session),
                }

            target_device = device_name or "configured device"
            send_progress("success", f"✅ Connected to {target_device}")
            snapshot = self.mcp_server.call_tool("explore_screen", {}) if self.mcp_server else {"success": False}
            elements = snapshot.get("elements", []) if isinstance(snapshot, dict) else []
            preview = []
            for element in elements[:8]:
                text = (element.get("text") or "").strip()
                content_desc = (element.get("content-desc") or "").strip()
                label = text or content_desc
                if label:
                    preview.append(label)

            summary = "\n".join(f"- {item}" for item in preview) if preview else "- Screen loaded (no labeled elements detected yet)"
            facts = (
                f"Connected to {target_device}. "
                f"Screen has {len(elements)} element(s). "
                f"Visible labels: {', '.join(preview[:6]) if preview else 'none detected'}."
            )
            response = self._conversational_wrap(facts, user_message, session) or (
                f"Connected to **{target_device}**. I can see {len(elements)} element(s) on screen.\n\n"
                f"Key elements:\n{summary}\n\n"
                "What would you like to do? I can explore, navigate, or run a test plan."
            )
            session["history"].append({"role": "assistant", "content": response})
            send_progress("chat_response", response)
            return {
                "success": True,
                "type": "connect",
                "message": response,
                "session_id": sid,
                "state": self._session_state(session),
            }

        if intent["type"] == "explore":
            send_progress("progress", "🔌 Connecting to device...")
            connection = self._connect_device_mcp(device_name, app_package, app_activity)
            if not connection.get("success"):
                connect_error = connection.get("error") or connection.get("message") or "Failed to connect device via MCP"
                send_progress("warning", f"⚠️ Device connect failed: {connect_error}")
                return {
                    "success": False,
                    "type": "explore",
                    "error": "Failed to connect device via MCP",
                    "details": connect_error,
                    "session_id": sid,
                    "state": self._session_state(session),
                }

            send_progress("progress", "🔎 Reading current screen...")
            snapshot = self.mcp_server.call_tool("explore_screen", {}) if self.mcp_server else {"success": False}
            if not snapshot.get("success"):
                screen_error = snapshot.get("error") or "Unable to read screen"
                return {
                    "success": False,
                    "type": "explore",
                    "error": "Failed to explore current screen",
                    "details": screen_error,
                    "session_id": sid,
                    "state": self._session_state(session),
                }

            elements = snapshot.get("elements", []) if isinstance(snapshot, dict) else []
            preview = []
            for element in elements[:12]:
                label = (element.get("text") or element.get("content-desc") or "").strip()
                if label:
                    preview.append(label)

            summary = "\n".join(f"- {item}" for item in preview) if preview else "- No labeled elements found"
            facts = (
                f"Screen has {len(elements)} element(s). "
                f"Visible labels: {', '.join(preview[:8]) if preview else 'none detected'}."
            )
            response = self._conversational_wrap(facts, user_message, session) or (
                f"I found **{len(elements)}** elements on the current screen.\n\n"
                f"Here's what's visible:\n{summary}\n\n"
                "I can tap on any of these, navigate deeper, or generate a test plan from this screen."
            )
            session["history"].append({"role": "assistant", "content": response})
            send_progress("chat_response", response)
            return {
                "success": True,
                "type": "explore",
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
                # Step validation failure — LLM already explained to user via chat_response
                if exploration.get("error") == "step_validation_failed":
                    return {
                        **exploration,
                        "message": exploration.get("llm_explanation", exploration.get("details", "")),
                        "session_id": sid,
                        "state": self._session_state(session),
                    }

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

            # Check if any step validations failed — don't generate broken tests
            # Only look at the FINAL result for each step_index (retries add duplicates)
            step_results = session.get("step_results", [])
            final_by_step = {}
            for r in step_results:
                final_by_step[r.get("step_index")] = r
            failed_steps = [r for r in final_by_step.values() if not r.get("passed")]

            completion_response = self._post_navigation_response(session, user_message, exploration)
            send_progress("chat_response", completion_response)

            if intent["type"] == "navigate_and_generate":
                if failed_steps:
                    send_progress("warning", f"⚠️ Skipping test generation — {len(failed_steps)} step(s) failed validation")
                    fail_summary = self._llm_explain_skip_codegen(session, failed_steps)
                    send_progress("chat_response", fail_summary)
                    result = {
                        "success": False,
                        "type": "navigate_and_generate",
                        "exploration": exploration,
                        "generation": {"success": False, "reason": "Steps failed validation"},
                        "message": fail_summary,
                        "session_id": sid,
                        "state": self._session_state(session),
                    }
                    self._store_assistant_summary(session, result)
                    return result

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

                # Build a final conversational wrap-up covering BOTH navigation and code gen
                gen_result = generation.get("result", {}) if isinstance(generation.get("result"), dict) else {}
                saved_files = gen_result.get("saved_files", [])
                gen_success = generation.get("success", False)

                # Deduplicate step results for summary
                final_by_step = {}
                for r in session.get("step_results", []):
                    final_by_step[r.get("step_index")] = r
                passed_count = sum(1 for r in final_by_step.values() if r.get("passed"))
                total_validated = len(final_by_step)
                steps_executed = exploration.get("steps_executed", 0)
                locators_count = exploration.get("locators_collected", 0)

                wrap_prompt = (
                    f"I just finished a complete QA automation run for the user. Here's what happened:\n\n"
                    f"1. Ran through the app: {steps_executed} actions, {passed_count}/{total_validated} test steps passed\n"
                    f"2. Collected {locators_count} locators from the screens I visited\n"
                    f"3. Code generation: {'succeeded' if gen_success else 'failed'}"
                    + (f", created {len(saved_files)} files" if saved_files else "")
                    + (f"\n   Files: {', '.join(os.path.basename(f) for f in saved_files[:5])}" if saved_files else "")
                    + f"\n\nThe user originally asked: \"{user_message}\"\n\n"
                    "Give them a natural, engaging summary — like you're wrapping up and handing off. "
                    "Mention the key results, where the files are, and what they can do next "
                    "(review the tests, run them, ask you to tweak something). Keep it 4-6 sentences."
                )
                final_message = self._run_model_prompt(wrap_prompt, session.get("model"), max_tokens=400)
                if not final_message:
                    final_message = completion_response
                else:
                    final_message = final_message.strip()

                result = {
                    "success": generation.get("success", False),
                    "type": "navigate_and_generate",
                    "exploration": exploration,
                    "generation": generation,
                    "message": final_message,
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
                "model": "gemini-3-flash-preview",
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
                "step_results": [],
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

        # Quick followup check
        followup_words = {"continue", "continuw", "contine", "continuee", "next", "go on", "proceed", "keep going", "retry", "skip", "skip and continue"}
        if any(word in message_lower for word in followup_words):
            prev = session.get("last_intent")
            prev_obj = session.get("last_objective", "")
            if prev in {"navigate", "navigate_and_generate"}:
                result = {
                    "type": prev,
                    "description": f"Continue: {prev_obj}",
                    "max_steps": self._steps_for_agent_type(session.get("agent_type", "balanced")),
                }
                if prev == "navigate_and_generate":
                    result["framework"] = self._extract_framework(prev_obj)
                    result["language"] = self._extract_language(prev_obj)
                    result["structure"] = self._extract_structure(prev_obj)
                return result
            if prev and prev_obj:
                # Default to navigate_and_generate for any previous objective involving tests
                inferred = "navigate_and_generate" if any(kw in prev_obj.lower() for kw in ["generate", "test", "code", "java", "maven"]) else "navigate"
                session["last_intent"] = inferred
                result = {
                    "type": inferred,
                    "description": f"Continue: {prev_obj}",
                    "max_steps": self._steps_for_agent_type(session.get("agent_type", "balanced")),
                }
                if inferred == "navigate_and_generate":
                    result["framework"] = self._extract_framework(prev_obj)
                    result["language"] = self._extract_language(prev_obj)
                    result["structure"] = self._extract_structure(prev_obj)
                return result

        if "help" in message_lower and len(message_lower) < 20:
            return {"type": "help", "description": "Show capabilities"}

        # ── LLM-powered intent detection (with retry) ──
        llm_intent = self._detect_intent_with_llm(message, session)
        if not llm_intent:
            import time
            time.sleep(1)
            llm_intent = self._detect_intent_with_llm(message, session)
        if llm_intent:
            return llm_intent

        # LLM unavailable — default to navigate_and_generate for action-like messages
        if any(kw in message_lower for kw in ["test", "execute", "explore", "generate", "run", "plan", "locator"]):
            session["last_intent"] = "navigate_and_generate"
            session["last_objective"] = message
            return {
                "type": "navigate_and_generate",
                "description": "Explore app and generate tests (LLM unavailable, defaulting)",
                "framework": self._extract_framework(message),
                "language": self._extract_language(message),
                "structure": self._extract_structure(message),
                "max_steps": self._steps_for_agent_type(session.get("agent_type", "balanced")),
            }
        return {"type": "general_chat", "description": "General conversation"}

    def _detect_intent_with_llm(self, message: str, session: Dict) -> Optional[Dict]:
        """Use Gemini to understand user intent."""
        history_summary = ""
        for item in session.get("history", [])[-4:]:
            history_summary += f"{item.get('role', 'user')}: {item.get('content', '')[:100]}\n"

        last_obj = session.get("last_objective", "none")
        has_locators = bool(session.get("locators_file"))

        prompt = (
            "Hey, you're a QA copilot helping me figure out what the user wants to do. "
            "Read their message and tell me — in your own words — what they're asking for.\n\n"
            f"Their message: \"{message}\"\n"
            f"What we were doing before: {last_obj}\n"
            f"Already have locators saved: {'yes' if has_locators else 'no'}\n"
            + (f"Recent conversation:\n{history_summary}\n" if history_summary else "")
            + "\nHere's what I can do:\n"
            "- **connect** — just hook up to a device/emulator, nothing else\n"
            "- **explore** — look at the current screen, read what's there, no tapping\n"
            "- **navigate** — interact with the app (tap buttons, scroll, go through flows) but no code\n"
            "- **navigate_and_generate** — run through the app AND write test code afterward (this is the most common one)\n"
            "- **generate_code** — write test code from locators we already captured\n"
            "- **general_chat** — they're just asking a question, not requesting an action\n\n"
            "Which one fits best? Just tell me naturally — mention the intent name somewhere in your answer."
        )

        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=100)
        if not response:
            return None

        response_lower = response.strip().lower().replace(" ", "_").replace("-", "_")
        description = response.strip()

        # Scan the response for intent keywords — order matters (most specific first)
        intent_type = None
        intent_priorities = [
            "navigate_and_generate",
            "generate_code",
            "navigate",
            "explore",
            "connect",
            "general_chat",
        ]
        for candidate in intent_priorities:
            if candidate in response_lower:
                intent_type = candidate
                break
        if not intent_type:
            # Fallback: look for clue words
            clues = response.strip().lower()
            if any(w in clues for w in ["execute", "run", "test plan", "generate", "java", "maven"]):
                intent_type = "navigate_and_generate"
            elif any(w in clues for w in ["tap", "click", "scroll", "interact"]):
                intent_type = "navigate"
            elif any(w in clues for w in ["look at", "see what", "read", "screen"]):
                intent_type = "explore"
            elif any(w in clues for w in ["device", "emulator", "attach"]):
                intent_type = "connect"
            else:
                intent_type = "navigate_and_generate"  # safe default

        valid_intents = {"connect", "explore", "navigate", "navigate_and_generate", "generate_code", "general_chat"}

        result = {"type": intent_type, "description": description}

        if intent_type in {"navigate", "navigate_and_generate"}:
            result["max_steps"] = self._steps_for_agent_type(session.get("agent_type", "balanced"))
            session["last_intent"] = intent_type
            session["last_objective"] = message
        if intent_type in {"navigate_and_generate", "generate_code"}:
            result["framework"] = self._extract_framework(message)
            result["language"] = self._extract_language(message)
            result["structure"] = self._extract_structure(message)
        if intent_type == "generate_code":
            session["last_intent"] = "generate_code"
        if intent_type == "connect":
            session["last_intent"] = "connect"
            session["last_objective"] = message
        if intent_type == "explore":
            session["last_intent"] = "explore"
            session["last_objective"] = message

        return result

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

        session["step_results"] = []
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
                completed_step_idx = session.get("current_plan_step", 0)
                completed_step_text = current_plan_step
                next_index = min(
                    completed_step_idx + 1,
                    len(session.get("plan_steps", [])),
                )
                session["current_plan_step"] = next_index
                session.get("plan_search_attempts", {}).pop(str(next_index), None)

                # --- LLM-driven per-step outcome validation ---
                expected_outcomes = session.get("expected_outcomes") or []
                if expected_outcomes and completed_step_idx < len(expected_outcomes):
                    expected = expected_outcomes[completed_step_idx]
                    post_screen = self.mcp_server.call_tool("explore_screen", {})
                    if post_screen.get("success"):
                        post_elements = post_screen.get("elements", [])
                        step_result = self._validate_step_outcome_with_llm(
                            step_text=completed_step_text or "",
                            expected_outcome=expected,
                            elements=post_elements,
                            session=session,
                        )
                        passed = step_result.get("passed", False)
                        reason_text = step_result.get("reason", "")
                        step_record = {
                            "step_index": completed_step_idx + 1,
                            "step": completed_step_text,
                            "expected": expected,
                            "passed": passed,
                            "reason": reason_text,
                        }
                        session.setdefault("step_results", []).append(step_record)

                        if passed:
                            send_progress("success", f"✅ Step {completed_step_idx + 1} PASSED — {reason_text}")
                        else:
                            send_progress("warning", f"❌ Step {completed_step_idx + 1} FAILED — Expected: {expected}")
                            # Let LLM decide what to do next
                            recovery = self._llm_decide_recovery(
                                step_text=completed_step_text or "",
                                expected_outcome=expected,
                                failure_reason=reason_text,
                                elements=post_elements,
                                session=session,
                                remaining_steps=max_steps - idx,
                            )
                            decision = recovery.get("decision", "stop")
                            explanation = recovery.get("explanation", "")
                            send_progress("progress", f"🤖 LLM decision: {explanation}")

                            if decision == "retry":
                                send_progress("progress", "🔄 Retrying this step...")
                                session["current_plan_step"] = completed_step_idx
                                continue
                            elif decision == "skip":
                                send_progress("progress", f"⏭️ Skipping to next step...")
                                continue
                            elif decision == "stop":
                                send_progress("chat_response", explanation)
                                return {
                                    "success": False,
                                    "type": "navigation",
                                    "error": "step_validation_failed",
                                    "failed_step_index": completed_step_idx + 1,
                                    "failed_step": completed_step_text,
                                    "expected_outcome": expected,
                                    "actual_reason": reason_text,
                                    "llm_explanation": explanation,
                                    "details": f"Step {completed_step_idx + 1} failed validation",
                                    "steps_executed": len(steps_taken),
                                    "locators_collected": locators_collected,
                                    "locators_file": locators_file,
                                    "steps": steps_taken,
                                    "step_results": session.get("step_results", []),
                                }

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
        step_results = session.get("step_results", [])
        if expected_outcomes:
            verification = self._verify_expected_outcomes(expected_outcomes, last_elements)
            # Only look at the FINAL result for each step (retries add duplicates)
            final_by_step = {}
            for r in step_results:
                final_by_step[r.get("step_index")] = r
            failed_steps = [r for r in final_by_step.values() if not r.get("passed")]
            if verification.get("matched", 0) == 0 and not step_results:
                return {
                    "success": False,
                    "type": "navigation",
                    "error": "Expected result not observed",
                    "details": "Executed actions but none of the expected outcomes were observed on screen.",
                    "steps_executed": len(steps_taken),
                    "locators_collected": locators_collected,
                    "locators_file": locators_file,
                    "steps": steps_taken,
                    "step_results": step_results,
                    "expected_verification": verification,
                }

        return {
            "success": True,
            "steps_executed": len(steps_taken),
            "locators_collected": locators_collected,
            "locators_file": locators_file,
            "steps": steps_taken,
            "step_results": step_results,
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
        current_plan_step = self._current_plan_step_text(session)

        compact_elements = []
        for idx, elem in enumerate(elements[:30]):
            compact_elements.append(
                {
                    "index": idx,
                    "text": elem.get("text"),
                    "resource_id": elem.get("resource_id") or elem.get("id"),
                    "clickable": elem.get("clickable"),
                    "xpath": elem.get("xpath"),
                }
            )

        elements_text = "\n".join(
            f"  [{e['index']}] \"{e.get('text') or ''}\" (id={e.get('resource_id') or ''}, clickable={e.get('clickable')})"
            for e in compact_elements
        )

        prompt = (
            "You are controlling a mobile app. Look at the screen elements and tell me "
            "what you would do next to accomplish the goal.\n\n"
            + (f"Current test step: {current_plan_step}\n" if current_plan_step else "")
            + f"Goal: {objective}\n"
            + (f"\nTest plan:\n{attachment_context[:600]}\n" if attachment_context else "")
            + f"\nScreen elements:\n{elements_text}\n\n"
            "Tell me which element to click (by its number), or if I should scroll or go back. "
            "Explain your reasoning briefly."
        )

        response = self._run_model_prompt(prompt, model, max_tokens=200)
        if not response:
            return None

        response_lower = response.lower()
        has_plan = bool(current_plan_step)

        # Extract action from natural language
        if "scroll" in response_lower and "click" not in response_lower:
            return {"action": "scroll", "reason": response.strip()[:200], "from_plan": has_plan}
        if "go back" in response_lower or "press back" in response_lower or "navigate back" in response_lower:
            return {"action": "back", "reason": response.strip()[:200], "from_plan": has_plan}

        # Find element index mentioned in response
        # Look for patterns like [3], element 3, #3, index 3, number 3
        index_match = re.search(r'\[(\d+)\]|element\s*(\d+)|#(\d+)|index\s*(\d+)|number\s*(\d+)', response_lower)
        if not index_match:
            # Try just the first standalone number in context of clicking
            if "click" in response_lower or "tap" in response_lower:
                num_match = re.search(r'\b(\d+)\b', response)
                if num_match:
                    index_match = num_match

        if index_match:
            # Get the first non-None group
            idx_str = next((g for g in index_match.groups() if g is not None), None) if hasattr(index_match, 'groups') and len(index_match.groups()) > 1 else index_match.group(1)
            try:
                elem_index = int(idx_str)
                if 0 <= elem_index < len(compact_elements):
                    xpath = compact_elements[elem_index].get("xpath")
                    if xpath:
                        return {"action": "click", "xpath": xpath, "reason": response.strip()[:200], "from_plan": has_plan}
            except (ValueError, TypeError):
                pass

        # If LLM mentioned an element by name, try to match it
        for elem in compact_elements:
            elem_text = (elem.get("text") or "").lower()
            elem_id = (elem.get("resource_id") or "").lower()
            if elem_text and len(elem_text) > 2 and elem_text in response_lower and elem.get("clickable"):
                xpath = elem.get("xpath")
                if xpath and xpath not in session.get("visited_xpaths", set()):
                    return {"action": "click", "xpath": xpath, "reason": response.strip()[:200], "from_plan": has_plan}
            if elem_id and len(elem_id) > 3 and elem_id in response_lower and elem.get("clickable"):
                xpath = elem.get("xpath")
                if xpath and xpath not in session.get("visited_xpaths", set()):
                    return {"action": "click", "xpath": xpath, "reason": response.strip()[:200], "from_plan": has_plan}

        return None

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

    def _validate_step_outcome_with_llm(
        self,
        step_text: str,
        expected_outcome: str,
        elements: List[Dict],
        session: Dict,
    ) -> Dict:
        """Use LLM to assess whether a plan step's expected outcome is met on screen."""
        screen_texts = [
            str(e.get("text") or "") for e in elements[:40] if e.get("text")
        ]
        screen_summary = ", ".join(screen_texts[:30]) if screen_texts else "(no visible text)"

        prompt = (
            "I just performed a test step on a mobile app. Take a look at what's on screen "
            "and tell me — did it work?\n\n"
            f"What I did: {step_text}\n"
            f"What we expected to see: {expected_outcome}\n"
            f"What's actually on screen: {screen_summary}\n\n"
            "Be generous — if the action happened (menu opened, screen changed, button was tapped), "
            "that counts as working even if not every detail is visible yet. "
            "Only say it failed if the screen is clearly wrong or the action obviously didn't happen.\n\n"
            "Tell me naturally — did it pass or fail, and why?"
        )

        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=150)
        if not response:
            haystack = " ".join(screen_texts).lower()
            tokens = [t for t in re.split(r"\W+", expected_outcome.lower()) if len(t) > 3 and t not in {"should", "must", "then", "user", "able", "will", "verify", "check"}]
            hit = any(tok in haystack for tok in tokens[:5]) if tokens else False
            return {"passed": hit, "reason": "keyword match (LLM unavailable)"}

        response_lower = response.strip().lower()
        # Detect pass/fail from natural language — look for positive/negative signals
        fail_signals = ["fail", "didn't work", "did not work", "not there", "wrong screen",
                        "doesn't match", "does not match", "missing", "not visible",
                        "wasn't found", "was not found", "no sign of", "not present"]
        pass_signals = ["pass", "worked", "looks good", "success", "it did", "yes",
                        "matches", "can see", "is visible", "is there", "opened",
                        "showing", "appears", "found", "present", "correct"]

        fail_score = sum(1 for s in fail_signals if s in response_lower)
        pass_score = sum(1 for s in pass_signals if s in response_lower)
        passed = pass_score >= fail_score  # ties go to pass (be generous)

        reason = response.strip()
        # Clean up any PASS/FAIL prefix if the LLM still used it
        for prefix in ["pass", "fail"]:
            if response_lower.startswith(prefix):
                reason = response.strip()[len(prefix):].strip(" .:—-\n") or response.strip()
                break
        return {"passed": passed, "reason": reason}

    def _llm_decide_recovery(
        self,
        step_text: str,
        expected_outcome: str,
        failure_reason: str,
        elements: List[Dict],
        session: Dict,
        remaining_steps: int,
    ) -> Dict:
        """Let the LLM decide what to do when a step's expected outcome is not met."""
        screen_texts = [str(e.get("text") or "") for e in elements[:30] if e.get("text")]
        screen_summary = ", ".join(screen_texts[:20]) if screen_texts else "(no visible text)"

        step_results_so_far = session.get("step_results", [])
        results_summary = ""
        for r in step_results_so_far:
            status = "PASS" if r.get("passed") else "FAIL"
            results_summary += f"\n  Step {r.get('step_index')}: {status} — {r.get('reason', '')}"

        plan_steps = session.get("plan_steps", [])
        total_steps = len(plan_steps)
        current_idx = session.get("current_plan_step", 0)

        prompt = (
            f"Hey, I just tried to do this step but it didn't pass validation:\n\n"
            f"Step: \"{step_text}\"\n"
            f"Expected: \"{expected_outcome}\"\n"
            f"What happened: {failure_reason}\n"
            f"What's on screen now: {screen_summary}\n"
            f"Progress: {current_idx}/{total_steps} steps done, {remaining_steps} attempts left\n"
            + (f"Previous results: {results_summary}\n" if results_summary else "")
            + "\nWhat should I do? Tell me in your own words — should I:\n"
            "- **retry** it (maybe the screen needs a moment to load, or I should scroll)\n"
            "- **skip** this step and move on to the next one\n"
            "- **stop** entirely (only if something is really broken — wrong screen, app crashed)\n\n"
            "Lean toward retrying when you're not sure. Tell me what you think is happening "
            "and what I should try."
        )

        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=500)
        if response:
            response_lower = response.strip().lower()
            # Look for decision keywords anywhere in the response, not just at the start
            decision = "retry"  # Default to retry — always give it another chance
            for line in response_lower.split("\n"):
                line_stripped = line.strip()
                if "retry" in line_stripped:
                    decision = "retry"
                    break
                elif "skip" in line_stripped:
                    decision = "skip"
                    break
                elif "stop" in line_stripped and any(w in line_stripped for w in ["stop", "cannot proceed", "critical", "wrong screen", "blocked"]):
                    decision = "stop"
                    break
            # Use the full response as explanation
            explanation = response.strip()
            # Strip the keyword from the start if present for cleaner display
            for kw in ["retry", "skip", "stop"]:
                if explanation.lower().startswith(kw):
                    explanation = explanation[len(kw):].strip(" .:—-\n")
                    break
            return {"decision": decision, "explanation": explanation or response.strip()}

        # Fallback: stop with a template message
        return {
            "decision": "stop",
            "explanation": (
                f"I ran step **\"{step_text}\"** but the expected outcome wasn't met.\n\n"
                f"**Expected:** {expected_outcome}\n"
                f"**What I saw:** {failure_reason}\n\n"
                "This could mean:\n"
                "- The app feature isn't enabled for this user/account\n"
                "- A configuration or data setup is missing\n"
                "- The screen didn't load correctly\n\n"
                "Would you like me to **retry this step**, **skip and continue**, or do you need to adjust something first?"
            ),
        }

    def _llm_explain_skip_codegen(self, session: Dict, failed_steps: List[Dict]) -> str:
        """Let LLM explain why test generation was skipped due to failed steps."""
        failures_text = ""
        for r in failed_steps:
            failures_text += f"\n- Step {r.get('step_index')}: \"{r.get('step')}\" — Expected: \"{r.get('expected')}\" — {r.get('reason', 'no details')}"

        prompt = (
            "Hey, so a few test steps didn't go as expected, and I've decided not to generate "
            "test code just yet — writing tests from broken steps would give you unreliable code.\n\n"
            f"Here's what went wrong:{failures_text}\n\n"
            "Tell the user what happened in a friendly, clear way. Explain which steps failed "
            "and why, why you're holding off on code generation, what they might want to check or fix, "
            "and that you're ready to retry whenever they are. "
            "You can also offer to generate tests anyway if they want to."
        )

        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=300)
        if response:
            return response.strip()

        # Fallback
        summary = "**I'm holding off on generating test code** because some steps didn't pass validation:\n"
        for r in failed_steps:
            summary += f"\n❌ **Step {r.get('step_index')}**: Expected \"{r.get('expected')}\" — {r.get('reason', '')}"
        summary += "\n\nGenerating tests from failed steps would produce unreliable code. "
        summary += "Please check the app state/configuration and say **retry** when ready, "
        summary += "or say **generate anyway** if you want tests regardless."
        return summary

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
            "I'm your QA automation copilot. Here's what I can do:\n\n"
            "- **Explore the app** — I'll connect to your device and scan the screen\n"
            "- **Execute flows** — Tell me a goal like \"do the login flow\" and I'll navigate step by step\n"
            "- **Generate tests** — I can create Appium Java test cases from the screens I've explored\n"
            "- **Continue** — Just say \"continue\" to pick up where we left off\n\n"
            "Try something like: *\"Connect to the device and explore the home screen\"*"
        )

    def _post_navigation_response(self, session: Dict, user_message: str, exploration: Dict) -> str:
        steps = exploration.get("steps_executed", 0)
        locators = exploration.get("locators_collected", 0)
        locators_file = exploration.get("locators_file", "not available")
        file_name = locators_file.split("/")[-1] if locators_file and locators_file != "not available" else None

        # Build step results summary — only final result per step
        step_results = session.get("step_results", [])
        final_by_step = {}
        for r in step_results:
            final_by_step[r.get("step_index")] = r
        step_summary = ""
        if final_by_step:
            passed = sum(1 for r in final_by_step.values() if r.get("passed"))
            failed = sum(1 for r in final_by_step.values() if not r.get("passed"))
            step_summary = f"\nOut of {len(final_by_step)} test steps: {passed} passed, {failed} failed."
            for idx in sorted(final_by_step.keys()):
                r = final_by_step[idx]
                status = "passed" if r.get("passed") else "failed"
                step_summary += f"\n- Step {idx}: {status} — {r.get('reason', '')}"

        prompt = (
            f"I just finished running through the app for the user. Tell them how it went — "
            f"be natural, like you're chatting with a colleague.\n\n"
            f"What they asked: {user_message}\n"
            f"What I did: Performed {steps} action(s) on the app, captured {locators} locator(s)"
            + (f", saved them to {file_name}" if file_name else "")
            + "."
            + step_summary
            + "\n\nGive a quick, friendly summary (3-5 sentences). "
            "Mention what passed, what failed if anything, and what's next."
        )
        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=300)
        if response:
            return response.strip()

        # Fallback template
        summary = f"All done! I went through **{steps}** actions on the app and picked up **{locators}** locators"
        summary += f" (saved to `{file_name}`)" if file_name else ""
        summary += "."
        if final_by_step:
            passed = sum(1 for r in final_by_step.values() if r.get("passed"))
            failed = sum(1 for r in final_by_step.values() if not r.get("passed"))
            summary += f"\n\n**Results:** {passed} passed, {failed} failed."
            for idx in sorted(final_by_step.keys()):
                r = final_by_step[idx]
                icon = "✅" if r.get("passed") else "❌"
                summary += f"\n{icon} Step {idx}: {r.get('reason', 'no details')}"
            if failed > 0:
                summary += "\n\nA few steps didn't go as expected — might want to check the app state or data setup."
        else:
            summary += "\n\nWant me to keep exploring, or should I generate test cases from what I've got?"
        return summary

    def _conversational_wrap(self, facts: str, user_message: str, session: Dict) -> Optional[str]:
        """Use the LLM to rewrite dry facts into a natural copilot response."""
        prompt = (
            f"Hey, the user said: \"{user_message}\"\n\n"
            f"Here's what I know: {facts}\n\n"
            "Turn this into a natural, friendly response — like you're chatting with them. "
            "Keep it short (3-5 sentences), be direct, and suggest what to do next."
        )
        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=200)
        return response.strip() if response else None

    def _dynamic_chat_response(self, user_message: str, session: Dict, attachment_context: str) -> str:
        prompt = self._build_chat_prompt(user_message, session, attachment_context)
        response = self._run_model_prompt(prompt, session.get("model"), max_tokens=350)
        if response:
            return response.strip()

        if session.get("last_objective"):
            return (
                f"Got it. We were working on: *{session.get('last_objective')}*.\n\n"
                "I can pick up from the current screen, or you can give me a new task."
            )
        return (
            "Tell me what you'd like to do — for example, *\"explore the home screen\"* or "
            "*\"run the login flow and generate tests\"*. I'll handle it step by step."
        )

    def _build_chat_prompt(self, user_message: str, session: Dict, attachment_context: str) -> str:
        history_lines = []
        for item in session.get("history", [])[-6:]:
            history_lines.append(f"{item.get('role', 'user')}: {item.get('content', '')}")

        return (
            "You're a QA automation copilot chatting with a tester in VS Code. "
            "Talk naturally — like a helpful colleague, not a robot.\n"
            "Be direct, confident, and specific. If you're blocked, say so honestly.\n"
            "Keep replies short (4-8 lines). Suggest concrete next steps.\n\n"
            f"What we're working on: {session.get('last_objective', 'nothing yet')}\n"
            f"Agent mode: {session.get('agent_type')}\n"
            "Recent conversation:\n"
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
        # Always try Gemini first — it's the primary LLM
        if self.has_gemini:
            response = self._run_gemini_prompt(prompt, model, max_tokens=max_tokens)
            if response:
                return response

        # Claude as secondary
        if self.has_anthropic:
            response = self._run_claude_prompt(prompt, model, max_tokens=max_tokens)
            if response:
                return response

        return None

    def _run_gemini_prompt(self, prompt: str, model: Optional[str], max_tokens: int = 300) -> Optional[str]:
        if not self.has_gemini:
            return None

        selected_model = model or "gemini-3-flash-preview"
        aliases = {
            "gemini-pro": "gemini-1.5-pro",
            "gemini-flash": "gemini-3-flash-preview",
            "gemini-2.0-flash": "gemini-3-flash-preview",
            "gemini-2.0-flash-lite": "gemini-3-flash-preview",
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
                timeout=20,
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
                    return text.strip() if text else None
            else:
                import logging
                logging.warning(f"Gemini API error {response.status_code}: {response.text[:200]}")
        except Exception as e:
            import logging
            logging.warning(f"Gemini API exception: {e}")
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
                return (response.json().get("response") or "").strip() or None
            else:
                import logging
                logging.warning(f"Ollama error {response.status_code}: {response.text[:200]}")
        except Exception as e:
            import logging
            logging.warning(f"Ollama exception: {e}")
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
                timeout=20,
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
        # Strip markdown code blocks
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
        text = text.rstrip('`').strip()

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
