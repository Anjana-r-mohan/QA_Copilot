"""
Agent Router
Central Brain
"""

from enum import Enum


class IntentType(Enum):
    EXPLORE_APP = "explore_app"
    EXECUTE_TEST_PLAN = "execute_test_plan"
    GENERATE_CODE = "generate_code"
    ANALYZE_CODEBASE = "analyze_codebase"
    GENERAL_CHAT = "general_chat"


class AgentRouter:

    @staticmethod
    def detect_intent(message: str):

        msg = message.lower()

        if any(word in msg for word in [
            "execute",
            "run test",
            "test plan",
            "run testcase",
            "execute testcase"
        ]):
            return IntentType.EXECUTE_TEST_PLAN

        if any(word in msg for word in [
            "generate code",
            "create framework",
            "generate automation",
            "generate test"
        ]):
            return IntentType.GENERATE_CODE

        if any(word in msg for word in [
            "explore",
            "navigate",
            "open screen",
            "click",
            "find element",
            "inspect"
        ]):
            return IntentType.EXPLORE_APP

        if any(word in msg for word in [
            "analyze repo",
            "analyze project",
            "analyze codebase",
            "scan framework"
        ]):
            return IntentType.ANALYZE_CODEBASE

        return IntentType.GENERAL_CHAT