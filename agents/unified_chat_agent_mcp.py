"""
Unified Chat Agent - Using Simple MCP Tool Structure
Orchestrates test execution via MCP tools with Ollama AI
"""

import os
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()


class UnifiedChatAgent:
    """
    Intelligent agent using simple MCP tool calls
    """
    
    def __init__(self, mcp_server=None):
        self.mcp_server = mcp_server
        self.conversation_history = []
        self.last_action_result = {}
        
        # AI backend - Use Ollama (local)
        self.ollama_model = None
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                if models:
                    self.ollama_model = models[0]['name']
                    print(f"✅ Using Ollama ({self.ollama_model}) for AI decisions")
        except:
            print("⚠️  Ollama not available - using rule-based fallback")
    
    def process_message(self, user_message: str, workspace_path: str,
                       device_name: str, app_package: str, app_activity: str,
                       progress_callback=None) -> Dict:
        """
        Main entry point - processes user messages
        """
        
        def send_progress(msg_type: str, message: str, data: dict = None):
            if progress_callback:
                progress_callback(msg_type, message, data)
        
        send_progress('understanding', f"🎯 Understanding: {user_message}")
        
        # Detect intent
        intent = self._detect_intent(user_message, workspace_path)
        send_progress('intent', f"💡 Intent: {intent['type']}")
        
        # Route to handler
        if intent['type'] == 'navigate_and_generate':
            return self._handle_navigate_and_generate(
                user_message, intent, workspace_path, device_name,
                app_package, app_activity, send_progress
            )
        
        elif intent['type'] == 'generate_code':
            return self._handle_code_generation(
                user_message, intent, workspace_path, send_progress
            )
        
        elif intent['type'] == 'file_search':
            return self._handle_file_search(
                user_message, intent, workspace_path, send_progress
            )
        
        elif intent['type'] == 'help':
            return self._handle_help(user_message, intent, workspace_path, send_progress)
        
        else:
            send_progress('chat_response', "I'm here to help! Try: 'Explore app based on test plan'")
            return {'success': True, 'type': 'chat'}
    
    def _detect_intent(self, message: str, workspace_path: str) -> Dict:
        """Detect user intent"""
        message_lower = message.lower()
        
        # File search
        if any(word in message_lower for word in ['cannot find', 'where are', "can't find", 'where is']):
            return {'type': 'file_search', 'description': 'Find files'}
        
        # Combined navigate + generate
        has_navigate = any(kw in message_lower for kw in ['explore', 'navigate', 'test plan', 'execute'])
        has_generate = any(kw in message_lower for kw in ['generate', 'create test', 'appium', 'selenium', 'playwright'])
        
        if has_navigate and has_generate:
            return {
                'type': 'navigate_and_generate',
                'description': 'Execute test plan and generate code',
                'framework': self._extract_framework(message),
                'language': self._extract_language(message),
                'structure': self._extract_structure(message)
            }
        
        # Just code generation
        if has_generate:
            return {
                'type': 'generate_code',
                'description': 'Generate test code',
                'framework': self._extract_framework(message),
                'language': self._extract_language(message),
                'structure': self._extract_structure(message)
            }
        
        # Help
        if any(kw in message_lower for kw in ['help', 'how to', 'what is']):
            return {'type': 'help', 'description': 'Provide help'}
        
        return {'type': 'general_chat', 'description': 'General conversation'}
    
    def _handle_navigate_and_generate(self, message: str, intent: Dict,
                                      workspace_path: str, device_name: str,
                                      app_package: str, app_activity: str,
                                      send_progress) -> Dict:
        """
        Main handler: Execute test plan via MCP tools, then generate code
        """
        
        if not self.mcp_server:
            send_progress('error', "❌ MCP server not available")
            return {'success': False, 'error': 'MCP server not available'}
        
        # Step 1: Connect device
        send_progress('progress', "🔌 Connecting to device via MCP...")
        try:
            result = self.mcp_server.call_tool("connect_device", {
                "device_name": device_name,
                "app_package": app_package,
                "app_activity": app_activity
            })
            
            if not result.get('success'):
                send_progress('error', f"❌ Failed to connect")
                return {'success': False, 'error': 'Connection failed'}
            
            send_progress('success', f"✅ Connected to device: {device_name}")
        except Exception as e:
            send_progress('error', f"❌ Connection error: {str(e)}")
            return {'success': False, 'error': str(e)}
        
        # Step 2: Find and parse test plan
        send_progress('progress', "📋 Executing test plan intelligently with MCP...")
        
        test_plan_path = self._find_latest_test_plan(workspace_path)
        if not test_plan_path:
            send_progress('error', "❌ No test plan found")
            return {'success': False, 'error': 'No test plan found'}
        
        with open(test_plan_path, 'r') as f:
            test_plan_content = f.read()
        
        # Parse steps from test plan
        steps = self._parse_test_plan(test_plan_content)
        send_progress('progress', f"📋 Found {len(steps)} test steps")
        
        # Step 3: Execute each step
        locators_file = self._prepare_locators_file(workspace_path, test_plan_path)
        locators_collected = 0
        
        for idx, step_text in enumerate(steps, 1):
            send_progress('progress', f"⚙️  Step {idx}/{len(steps)}: {step_text[:50]}...")
            
            try:
                # Get current screen
                screen_data = self.mcp_server.call_tool("explore_screen", {})
                
                # Ask AI what to do
                action = self._decide_action_with_ai(step_text, screen_data)
                
                if action:
                    # Perform action
                    self.mcp_server.call_tool("perform_action", action)
                    
                    # Save locator if applicable
                    if action.get('xpath'):
                        locator = {
                            'step': step_text,
                            'action': action.get('action'),
                            'xpath': action.get('xpath'),
                            'value': action.get('value', '')
                        }
                        self.mcp_server.call_tool("save_locator", {
                            'file': locators_file,
                            'locator': locator
                        })
                        locators_collected += 1
                
            except Exception as e:
                send_progress('warning', f"⚠️  Step {idx} failed: {str(e)}")
                continue
        
        send_progress('success', f"✅ Test execution complete: {len(steps)} steps, {locators_collected} locators")
        
        # Step 4: Generate code
        send_progress('progress', "✨ Generating test code...")
        
        try:
            from agents.ai_code_generator_agent import AICodeGeneratorAgent
            code_generator = AICodeGeneratorAgent()
            
            instruction = f"Generate {intent['framework']} tests in {intent['language']} with {intent['structure']} structure"
            
            gen_result = code_generator.generate_test_code(
                user_instruction=instruction,
                test_plan_path=test_plan_path,
                locators_file=locators_file,
                workspace_path=workspace_path,
                progress_callback=send_progress
            )
            
            send_progress('complete', "🎉 Complete!")
            
            return {
                'success': True,
                'type': 'navigate_and_generate',
                'steps_executed': len(steps),
                'locators_collected': locators_collected,
                'locators_file': locators_file,
                'generation': gen_result
            }
            
        except Exception as e:
            send_progress('error', f"❌ Code generation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _decide_action_with_ai(self, step_text: str, screen_data: Dict) -> Optional[Dict]:
        """
        Use AI (Ollama preferred) to decide what action to take
        """
        
        elements = screen_data.get('elements', [])
        elements_summary = self._summarize_elements(elements[:15])
        
        prompt = f"""You are a mobile test automation expert.

TEST STEP: "{step_text}"

CURRENT SCREEN ELEMENTS:
{elements_summary}

Decide what action to take. Respond with JSON ONLY:

{{"action": "click", "xpath": "//android.widget.Button[@text='Login']"}}
{{"action": "enter", "xpath": "//android.widget.EditText[@resource-id='username']", "value": "testuser"}}
{{"action": "scroll"}}

Choose click/enter/scroll based on the step."""
        
        # Try Ollama first (local, always works)
        if self.ollama_model:
            try:
                response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={'model': self.ollama_model, 'prompt': prompt, 'stream': False},
                    timeout=30
                )
                if response.status_code == 200:
                    ai_response = response.json().get('response', '')
                    print(f"🤖 Ollama response: {ai_response[:100]}...")
                    
                    # Extract JSON
                    json_match = re.search(r'\{[^}]+\}', ai_response)
                    if json_match:
                        action = json.loads(json_match.group())
                        print(f"✅ Parsed action: {action}")
                        return action
            except Exception as e:
                print(f"⚠️  Ollama decision failed: {e}")
        
        # Fallback: Simple rule-based
        print(f"⚠️  Using rule-based fallback for: {step_text[:50]}")
        return self._fallback_action(step_text, elements)
    
    def _fallback_action(self, step_text: str, elements: List) -> Optional[Dict]:
        """Rule-based fallback when AI unavailable"""
        step_lower = step_text.lower()
        
        # Find clickable element
        if any(kw in step_lower for kw in ['click', 'tap', 'press', 'select']):
            for elem in elements:
                if elem.get('clickable'):
                    xpath = self._element_to_xpath(elem)
                    return {'action': 'click', 'xpath': xpath}
        
        # Find input field
        elif any(kw in step_lower for kw in ['enter', 'input', 'type']):
            for elem in elements:
                if 'EditText' in elem.get('class', ''):
                    xpath = self._element_to_xpath(elem)
                    return {'action': 'enter', 'xpath': xpath, 'value': 'testvalue'}
        
        # Scroll
        elif 'scroll' in step_lower:
            return {'action': 'scroll'}
        
        return None
    
    def _summarize_elements(self, elements: List) -> str:
        """Summarize elements for AI"""
        lines = []
        for elem in elements[:15]:
            text = elem.get('text', '')
            res_id = elem.get('resource-id', '')
            cls = elem.get('class', '').split('.')[-1]
            clickable = elem.get('clickable', False)
            
            if text or res_id:
                lines.append(f"- {cls}: text='{text}' id='{res_id}' clickable={clickable}")
        
        return '\n'.join(lines) if lines else "No interactive elements found"
    
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
    
    def _parse_test_plan(self, content: str) -> List[str]:
        """Parse test plan to extract steps"""
        steps = []
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Numbered steps: "1. Step text"
            if re.match(r'^\d+\.\s+', line):
                step_text = re.sub(r'^\d+\.\s+', '', line)
                if len(step_text) > 5:  # Ignore short lines
                    steps.append(step_text)
            
            # Bulleted: "- Step text"
            elif line.startswith(('- ', '* ')):
                step_text = line[2:].strip()
                if len(step_text) > 5:
                    steps.append(step_text)
        
        return steps
    
    def _prepare_locators_file(self, workspace_path: str, test_plan_path: str) -> str:
        """Create locators file path"""
        locators_dir = os.path.join(workspace_path, 'locators')
        os.makedirs(locators_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        test_name = os.path.basename(test_plan_path).replace('.md', '')
        filename = f"locators_{test_name}_{timestamp}.jsonl"
        
        return os.path.join(locators_dir, filename)
    
    def _find_latest_test_plan(self, workspace_path: str) -> Optional[str]:
        """Find most recent test plan"""
        test_plans_dir = os.path.join(workspace_path, 'test_plans')
        if not os.path.exists(test_plans_dir):
            return None
        
        files = [f for f in os.listdir(test_plans_dir) if f.endswith('.md')]
        if not files:
            return None
        
        latest = max(files, key=lambda f: os.path.getmtime(os.path.join(test_plans_dir, f)))
        return os.path.join(test_plans_dir, latest)
    
    def _extract_framework(self, message: str) -> str:
        """Extract test framework from message"""
        message_lower = message.lower()
        
        if 'playwright' in message_lower:
            return 'Playwright'
        elif 'selenium' in message_lower:
            return 'Selenium'
        elif 'cypress' in message_lower:
            return 'Cypress'
        else:
            return 'Appium'
    
    def _extract_language(self, message: str) -> str:
        """Extract programming language"""
        message_lower = message.lower()
        
        if 'python' in message_lower:
            return 'Python'
        elif 'typescript' in message_lower:
            return 'TypeScript'
        elif 'javascript' in message_lower:
            return 'JavaScript'
        else:
            return 'Java'
    
    def _extract_structure(self, message: str) -> str:
        """Extract project structure"""
        message_lower = message.lower()
        
        if 'maven' in message_lower or 'pom' in message_lower:
            return 'Maven POM'
        elif 'gradle' in message_lower:
            return 'Gradle'
        else:
            return 'Standard'
    
    def _handle_code_generation(self, message: str, intent: Dict,
                                workspace_path: str, send_progress) -> Dict:
        """Handle code generation only"""
        from agents.ai_code_generator_agent import AICodeGeneratorAgent
        code_generator = AICodeGeneratorAgent()
        
        locators_file = self._find_latest_locators(workspace_path)
        test_plan_file = self._find_latest_test_plan(workspace_path)
        
        result = code_generator.generate_test_code(
            user_instruction=message,
            test_plan_path=test_plan_file,
            locators_file=locators_file,
            workspace_path=workspace_path,
            progress_callback=send_progress
        )
        
        return {'success': True, 'type': 'generate_code', 'result': result}
    
    def _handle_file_search(self, message: str, intent: Dict,
                           workspace_path: str, send_progress) -> Dict:
        """Help find generated files"""
        gen_dir = os.path.join(workspace_path, 'generated_tests')
        if os.path.exists(gen_dir):
            subdirs = [d for d in os.listdir(gen_dir) if os.path.isdir(os.path.join(gen_dir, d))]
            if subdirs:
                latest_dir = max(subdirs)
                full_path = os.path.join(gen_dir, latest_dir)
                send_progress('chat_response', f"📂 Your tests are here:\n{full_path}")
                return {'success': True, 'type': 'file_search', 'location': full_path}
        
        send_progress('chat_response', "I haven't generated files yet. Say: 'Explore app and generate tests'")
        return {'success': True, 'type': 'chat'}
    
    def _handle_help(self, message: str, intent: Dict, workspace_path: str, send_progress) -> Dict:
        """Provide help"""
        help_text = """
🤖 I'm ScriptSherpa - your AI QA assistant!

Try:
• "Explore app based on test plan and generate Appium tests"
• "Generate Playwright tests in TypeScript"
• "Where are my generated files?"

I'll navigate your app, collect locators, and generate test code!
"""
        send_progress('chat_response', help_text)
        return {'success': True, 'type': 'help'}
    
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
