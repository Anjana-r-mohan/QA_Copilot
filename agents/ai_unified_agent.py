"""
TRUE AI Unified Agent - Natural Language Understanding + MCP Orchestration
Understands any user request, explores app intelligently, generates tests
"""

import os
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()


class AIUnifiedAgent:
    """
    TRUE AI agent - understands natural language, explores freely via MCP
    """
    
    def __init__(self, mcp_server=None):
        self.mcp_server = mcp_server
        self.ollama_model = None
        self.conversation_memory = []  # Remember what we've done
        
        # Connect to Ollama
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                if models:
                    self.ollama_model = models[0]['name']
                    print(f"✅ AI Agent using Ollama ({self.ollama_model})")
        except:
            print("⚠️  Ollama not available")
    
    def process_message(self, user_message: str, workspace_path: str,
                       device_name: str, app_package: str, app_activity: str,
                       progress_callback=None) -> Dict:
        """
        Main entry - TRUE AI understanding of any request
        """
        
        def send_progress(msg_type: str, message: str, data: dict = None):
            if progress_callback:
                progress_callback(msg_type, message, data)
        
        send_progress('understanding', f"🧠 AI Understanding: {user_message}")
        
        # Use AI to understand user intent
        intent = self._ai_understand_intent(user_message)
        
        send_progress('intent', f"💡 {intent['description']}")
        
        # Connect to device
        send_progress('progress', "🔌 Connecting to device...")
        if not self._connect_device(device_name, app_package, app_activity):
            send_progress('error', "❌ Failed to connect")
            return {'success': False, 'error': 'Connection failed'}
        
        send_progress('success', f"✅ Connected to {device_name}")
        
        # Execute based on intent
        if intent['type'] == 'explore_and_generate':
            return self._intelligent_explore_and_generate(
                intent, workspace_path, user_message, send_progress
            )
        
        elif intent['type'] == 'just_explore':
            return self._intelligent_explore(
                intent, workspace_path, send_progress
            )
        
        elif intent['type'] == 'generate_only':
            return self._generate_from_existing(
                intent, workspace_path, send_progress
            )
        
        else:
            send_progress('chat_response', "I understand! Let me help you explore and generate tests.")
            return {'success': True, 'type': 'chat'}
    
    def _ai_understand_intent(self, user_message: str) -> Dict:
        """
        Use AI (Ollama) to understand ANY user request
        """
        
        prompt = f"""You are a QA automation assistant. Understand this user request and respond with JSON.

USER REQUEST: "{user_message}"

Determine:
1. What does user want? (explore app, generate tests, both, help)
2. Any specific actions mentioned? (start call, place order, login, etc.)
3. What framework/language for tests? (Appium, Selenium, Playwright, Java, Python, TypeScript)

Respond ONLY with JSON:
{{
    "type": "explore_and_generate|just_explore|generate_only|help",
    "description": "Brief description of what user wants",
    "actions": ["start call", "place order"],
    "framework": "Appium",
    "language": "Java",
    "structure": "Maven POM"
}}

Examples:
- "explore app, start call and place order, generate appium tests" → {{"type": "explore_and_generate", "actions": ["start call", "place order"], "framework": "Appium"}}
- "just navigate the app and collect locators" → {{"type": "just_explore", "actions": []}}
- "generate selenium python tests" → {{"type": "generate_only", "framework": "Selenium", "language": "Python"}}
"""
        
        if self.ollama_model:
            try:
                response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={'model': self.ollama_model, 'prompt': prompt, 'stream': False},
                    timeout=30
                )
                if response.status_code == 200:
                    ai_response = response.json().get('response', '')
                    
                    # Extract JSON
                    json_match = re.search(r'\{[^{}]*"type"[^{}]*\}', ai_response, re.DOTALL)
                    if json_match:
                        intent = json.loads(json_match.group())
                        print(f"✅ AI understood: {intent['type']} - {intent.get('description', '')}")
                        return intent
            except Exception as e:
                print(f"⚠️  AI understanding failed: {e}")
        
        # Fallback: keyword-based
        return self._fallback_intent(user_message)
    
    def _fallback_intent(self, message: str) -> Dict:
        """Fallback when AI unavailable"""
        message_lower = message.lower()
        
        has_explore = any(kw in message_lower for kw in ['explore', 'navigate', 'start', 'place', 'do'])
        has_generate = any(kw in message_lower for kw in ['generate', 'create test', 'test code'])
        
        if has_explore and has_generate:
            return {
                'type': 'explore_and_generate',
                'description': 'Explore app and generate tests',
                'actions': [],
                'framework': 'Appium',
                'language': 'Java',
                'structure': 'Maven POM'
            }
        elif has_explore:
            return {
                'type': 'just_explore',
                'description': 'Explore app and collect locators',
                'actions': [],
                'framework': 'Appium'
            }
        else:
            return {
                'type': 'generate_only',
                'description': 'Generate tests from existing locators',
                'framework': 'Appium',
                'language': 'Java',
                'structure': 'Standard'
            }
    
    def _connect_device(self, device_name: str, app_package: str, app_activity: str) -> bool:
        """Connect to device via MCP"""
        if not self.mcp_server:
            return False
        
        try:
            result = self.mcp_server.call_tool("connect_device", {
                "device_name": device_name,
                "app_package": app_package,
                "app_activity": app_activity
            })
            return result.get('success', False)
        except:
            return False
    
    def _intelligent_explore_and_generate(self, intent: Dict, workspace_path: str,
                                          user_message: str, send_progress) -> Dict:
        """
        MAIN FLOW: Intelligently explore app + generate tests
        """
        
        send_progress('progress', "🤖 Starting intelligent exploration...")
        
        # Prepare locators file
        locators_file = self._prepare_locators_file(workspace_path, user_message)
        
        # Extract actions from user message or intent
        actions = intent.get('actions', [])
        
        if actions:
            # User specified actions like "start call", "place order"
            send_progress('progress', f"🎯 Will perform: {', '.join(actions)}")
            locators_collected = self._execute_user_actions(actions, locators_file, send_progress)
        else:
            # Free exploration - let AI navigate intelligently
            send_progress('progress', "🔍 Free exploration mode - AI will navigate intelligently")
            locators_collected = self._free_intelligent_exploration(locators_file, send_progress)
        
        send_progress('success', f"✅ Exploration complete: {locators_collected} locators collected")
        
        # Generate tests
        send_progress('progress', "✨ Generating test code...")
        
        try:
            from agents.ai_code_generator_agent import AICodeGeneratorAgent
            code_generator = AICodeGeneratorAgent()
            
            instruction = f"Generate {intent.get('framework', 'Appium')} tests in {intent.get('language', 'Java')} with {intent.get('structure', 'Maven POM')} structure based on: {user_message}"
            
            gen_result = code_generator.generate_test_code(
                user_instruction=instruction,
                test_plan_path=None,  # No test plan needed!
                locators_file=locators_file,
                workspace_path=workspace_path,
                progress_callback=send_progress
            )
            
            send_progress('complete', f"🎉 Complete! {locators_collected} locators, tests generated")
            
            return {
                'success': True,
                'type': 'explore_and_generate',
                'locators_collected': locators_collected,
                'locators_file': locators_file,
                'generation': gen_result
            }
            
        except Exception as e:
            send_progress('error', f"❌ Code generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'locators_collected': locators_collected,
                'locators_file': locators_file
            }
    
    def _execute_user_actions(self, actions: List[str], locators_file: str,
                             send_progress) -> int:
        """
        Execute specific actions mentioned by user
        AI finds relevant elements and executes
        """
        
        locators_collected = 0
        
        for action in actions:
            send_progress('progress', f"⚙️  Performing: {action}")
            
            # Get current screen
            screen_data = self.mcp_server.call_tool("explore_screen", {})
            elements = screen_data.get('elements', [])
            
            # Ask AI how to perform this action
            action_plan = self._ai_decide_how_to_perform_action(action, elements)
            
            if action_plan:
                # Execute via MCP
                try:
                    self.mcp_server.call_tool("perform_action", action_plan)
                    
                    # Save locator
                    if action_plan.get('xpath'):
                        locator = {
                            'user_action': action,
                            'mcp_action': action_plan.get('action'),
                            'xpath': action_plan.get('xpath'),
                            'value': action_plan.get('value', ''),
                            'timestamp': datetime.now().isoformat()
                        }
                        self.mcp_server.call_tool("save_locator", {
                            'file': locators_file,
                            'locator': locator
                        })
                        locators_collected += 1
                        
                        send_progress('success', f"✅ {action} - locator saved")
                except Exception as e:
                    send_progress('warning', f"⚠️  {action} failed: {str(e)}")
            else:
                send_progress('warning', f"⚠️  Couldn't figure out how to: {action}")
        
        return locators_collected
    
    def _ai_decide_how_to_perform_action(self, user_action: str, elements: List) -> Optional[Dict]:
        """
        AI decides how to perform a user action like "start call" or "place order"
        """
        
        elements_summary = self._summarize_elements(elements[:20])
        
        prompt = f"""You are controlling a mobile app. The user wants you to: "{user_action}"

CURRENT SCREEN ELEMENTS:
{elements_summary}

Find the element that matches this action and decide what to do. Respond with JSON ONLY:

{{"action": "click", "xpath": "//android.widget.Button[@text='Start Call']"}}
{{"action": "enter", "xpath": "//android.widget.EditText[@resource-id='phone']", "value": "1234567890"}}
{{"action": "scroll"}}

Be smart - match button text/IDs to the user's intent.
"""
        
        if self.ollama_model:
            try:
                response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={'model': self.ollama_model, 'prompt': prompt, 'stream': False},
                    timeout=30
                )
                if response.status_code == 200:
                    ai_response = response.json().get('response', '')
                    
                    json_match = re.search(r'\{[^}]+\}', ai_response)
                    if json_match:
                        return json.loads(json_match.group())
            except:
                pass
        
        # Fallback: find clickable element
        for elem in elements:
            text = elem.get('text', '').lower()
            if user_action.lower() in text or any(word in text for word in user_action.lower().split()):
                return {
                    'action': 'click',
                    'xpath': self._element_to_xpath(elem)
                }
        
        return None
    
    def _free_intelligent_exploration(self, locators_file: str, send_progress) -> int:
        """
        Free exploration - AI navigates intelligently without specific instructions
        Clicks interesting buttons, explores screens, collects locators
        """
        
        locators_collected = 0
        max_screens = 10  # Explore up to 10 screens
        visited_screens = set()
        
        send_progress('progress', f"🔍 Free exploration: will visit up to {max_screens} screens")
        
        for screen_num in range(1, max_screens + 1):
            # Get current screen
            screen_data = self.mcp_server.call_tool("explore_screen", {})
            elements = screen_data.get('elements', [])
            
            # Create screen fingerprint
            screen_id = self._screen_fingerprint(elements)
            if screen_id in visited_screens:
                send_progress('progress', f"📍 Screen {screen_num}: Already visited, backing up")
                # Go back
                try:
                    self.mcp_server.call_tool("perform_action", {"action": "back"})
                except:
                    break
                continue
            
            visited_screens.add(screen_id)
            send_progress('progress', f"📱 Screen {screen_num}/{max_screens}: {len(elements)} elements")
            
            # Collect all clickable elements on this screen
            for elem in elements:
                if elem.get('clickable') or elem.get('text'):
                    locator = {
                        'screen': screen_num,
                        'text': elem.get('text', ''),
                        'resource_id': elem.get('resource-id', ''),
                        'class': elem.get('class', ''),
                        'clickable': elem.get('clickable', False),
                        'xpath': self._element_to_xpath(elem),
                        'timestamp': datetime.now().isoformat()
                    }
                    self.mcp_server.call_tool("save_locator", {
                        'file': locators_file,
                        'locator': locator
                    })
                    locators_collected += 1
            
            send_progress('success', f"✅ Screen {screen_num}: {locators_collected} total locators")
            
            # AI decides what to click next
            next_action = self._ai_decide_next_exploration_action(elements)
            
            if next_action:
                try:
                    self.mcp_server.call_tool("perform_action", next_action)
                    send_progress('progress', f"➡️  Navigating to next screen...")
                except:
                    send_progress('warning', "⚠️  Navigation failed, trying another")
            else:
                # No more interesting elements, done
                break
        
        return locators_collected
    
    def _ai_decide_next_exploration_action(self, elements: List) -> Optional[Dict]:
        """AI decides which element to click next during free exploration"""
        
        # Find clickable elements
        clickable = [e for e in elements if e.get('clickable')]
        
        if not clickable:
            return None
        
        # Prefer buttons/meaningful elements
        for elem in clickable:
            text = elem.get('text', '').lower()
            if text and len(text) > 2:  # Has meaningful text
                return {
                    'action': 'click',
                    'xpath': self._element_to_xpath(elem)
                }
        
        # Click first clickable
        if clickable:
            return {
                'action': 'click',
                'xpath': self._element_to_xpath(clickable[0])
            }
        
        return None
    
    def _screen_fingerprint(self, elements: List) -> str:
        """Create unique ID for screen to avoid revisiting"""
        texts = sorted([e.get('text', '') for e in elements if e.get('text')])
        return hash(tuple(texts[:10]))  # Use top 10 text elements
    
    def _intelligent_explore(self, intent: Dict, workspace_path: str, send_progress) -> Dict:
        """Just explore, don't generate"""
        locators_file = self._prepare_locators_file(workspace_path, "exploration")
        locators_collected = self._free_intelligent_exploration(locators_file, send_progress)
        
        send_progress('complete', f"🎉 Exploration complete: {locators_collected} locators")
        
        return {
            'success': True,
            'type': 'just_explore',
            'locators_collected': locators_collected,
            'locators_file': locators_file
        }
    
    def _generate_from_existing(self, intent: Dict, workspace_path: str, send_progress) -> Dict:
        """Generate tests from existing locators"""
        from agents.ai_code_generator_agent import AICodeGeneratorAgent
        code_generator = AICodeGeneratorAgent()
        
        locators_file = self._find_latest_locators(workspace_path)
        
        if not locators_file:
            send_progress('error', "❌ No locators found. Explore app first!")
            return {'success': False, 'error': 'No locators found'}
        
        result = code_generator.generate_test_code(
            user_instruction=f"Generate {intent.get('framework', 'Appium')} tests",
            test_plan_path=None,
            locators_file=locators_file,
            workspace_path=workspace_path,
            progress_callback=send_progress
        )
        
        return {'success': True, 'type': 'generate_only', 'result': result}
    
    def _summarize_elements(self, elements: List) -> str:
        """Summarize elements for AI"""
        lines = []
        for elem in elements:
            text = elem.get('text', '')
            res_id = elem.get('resource-id', '')
            cls = elem.get('class', '').split('.')[-1]
            clickable = elem.get('clickable', False)
            
            if text or res_id or clickable:
                lines.append(f"- {cls}: text='{text}' id='{res_id}' clickable={clickable}")
        
        return '\n'.join(lines[:15]) if lines else "No interactive elements"
    
    def _element_to_xpath(self, elem: Dict) -> str:
        """Convert element to XPath"""
        res_id = elem.get('resource-id', '')
        text = elem.get('text', '')
        cls = elem.get('class', '')
        
        if res_id:
            return f"//*[@resource-id='{res_id}']"
        elif text:
            return f"//*[@text='{text}']"
        elif cls:
            return f"//{cls}"
        else:
            return "//*"
    
    def _prepare_locators_file(self, workspace_path: str, description: str) -> str:
        """Create locators file"""
        locators_dir = os.path.join(workspace_path, 'locators')
        os.makedirs(locators_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_desc = re.sub(r'[^a-zA-Z0-9]+', '_', description)[:30]
        filename = f"locators_{safe_desc}_{timestamp}.jsonl"
        
        return os.path.join(locators_dir, filename)
    
    def _find_latest_locators(self, workspace_path: str) -> Optional[str]:
        """Find most recent locators file"""
        locators_dir = os.path.join(workspace_path, 'locators')
        if not os.path.exists(locators_dir):
            return None
        
        files = [f for f in os.listdir(locators_dir) if f.startswith('locators_')]
        if not files:
            return None
        
        latest = max(files, key=lambda f: os.path.getmtime(os.path.join(locators_dir, f)))
        return os.path.join(locators_dir, latest)
