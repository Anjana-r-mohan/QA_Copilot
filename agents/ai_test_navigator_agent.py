"""
AI Test Navigator Agent
Combines Claude AI with Appium to intelligently navigate through test flows
and collect locators based on test plan steps
"""

import json
import os
import time
import re
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import anthropic
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()


class AITestNavigatorAgent:
    """
    Uses Claude AI to understand test flows and navigate through app
    Collects locators at each step based on test plan
    """
    
    def __init__(self, ui_explorer_agent, anthropic_api_key: str = None):
        self.ui_explorer = ui_explorer_agent
        self.anthropic_api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')
        self.client = None
        self.use_ollama = False
        self.ollama_url = None
        self.collected_locators = {}
        self.locator_ids = set()
        self.navigation_history = []
        self.current_screen = None
        
        # Use the UI explorer's Ollama settings
        if ui_explorer_agent.use_ollama and ui_explorer_agent.ollama_url:
            self.use_ollama = True
            self.ollama_url = ui_explorer_agent.ollama_url
            print(f"✅ AI Navigator using Ollama at: {self.ollama_url}")
            return
        
        # Fallback to Anthropic if Ollama not available
        print("💡 AI Navigator: Attempting fallback to Anthropic Claude API...")
        if self.anthropic_api_key and not self.anthropic_api_key.startswith("sk-ant-api03"):
            try:
                self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
                print("✅ AI Navigator using Anthropic Claude API")
                return
            except Exception as e:
                print(f"⚠️  Anthropic API unavailable: {e}")

        
    def parse_test_plan(self, test_plan_path: str) -> List[Dict]:
        """Parse test plan markdown file"""
        test_cases = []
        
        with open(test_plan_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by test case headers (#### TC...)
        tc_pattern = r'#### (TC\d+): (.+?)\n'
        matches = list(re.finditer(tc_pattern, content))
        
        for i, match in enumerate(matches):
            tc_id = match.group(1)
            tc_name = match.group(2)
            
            # Get content until next test case or end
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            tc_content = content[start_pos:end_pos]
            
            # Extract steps
            steps = []
            steps_section = re.search(r'\*\*Steps\*\*:\n(.*?)\n\n', tc_content, re.DOTALL)
            if steps_section:
                step_lines = steps_section.group(1).strip().split('\n')
                for line in step_lines:
                    step_text = re.sub(r'^\d+\.\s*', '', line.strip())
                    if step_text:
                        steps.append(step_text)
            
            # Extract expected results
            expected = []
            expected_section = re.search(r'\*\*Expected Results\*\*:\n(.*?)\n\n', tc_content, re.DOTALL)
            if expected_section:
                expected_lines = expected_section.group(1).strip().split('\n')
                for line in expected_lines:
                    line = line.strip()
                    if line.startswith('- '):
                        expected.append(line[2:])
            
            test_cases.append({
                'id': tc_id,
                'name': tc_name,
                'steps': steps,
                'expected': expected
            })
        
        return test_cases
    
    def get_ai_navigation_plan(self, test_case: Dict, current_ui_elements: List[Dict]) -> Dict:
        """
        Use Claude to analyze test case and generate navigation plan
        
        Returns:
        {
            'steps': [
                {
                    'action': 'click',
                    'target': 'Login button',
                    'reason': 'Navigate to login screen',
                    'expected_element': 'username field'
                },
                ...
            ],
            'flow_summary': 'User logs in with credentials and verifies dashboard'
        }
        """
        
        if not self.client:
            return {
                "error": "Anthropic client not initialized",
                "message": "Set ANTHROPIC_API_KEY environment variable or pass api_key parameter"
            }
        
        # Format current UI elements for Claude
        ui_summary = self._format_ui_elements(current_ui_elements)
        
        prompt = f"""You are a QA automation expert. Analyze this test case and generate a step-by-step navigation plan.

TEST CASE: {test_case['id']} - {test_case['name']}

STEPS TO EXECUTE:
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(test_case['steps']))}

EXPECTED RESULTS:
{chr(10).join(f"- {exp}" for exp in test_case['expected'])}

CURRENT SCREEN UI ELEMENTS:
{ui_summary}

Generate a detailed navigation plan that:
1. Identifies which UI element to interact with for each step
2. Specifies the action (click, enter text, verify, etc.)
3. Predicts what screen/elements should appear after each action
4. Handles any conditional logic or error cases

Return as JSON with this structure:
{{
    "flow_summary": "Brief description of the test flow",
    "steps": [
        {{
            "step_number": 1,
            "action": "click|enter|verify|scroll|wait",
            "target_element": "Description of element to interact with",
            "target_locator_hint": "Keyword to find element (e.g., 'login', 'username')",
            "input_value": "Text to enter (if action is enter)",
            "expected_after_action": "What should appear after this action",
            "reason": "Why this action is needed"
        }}
    ],
    "potential_issues": ["List of potential issues to handle"],
    "locators_to_collect": ["List of important locators to save"]
}}"""

        try:
            if self.use_ollama:
                # Using Ollama via HTTP (local or cloud)
                try:
                    response = requests.post(
                        f'{self.ollama_url}/api/generate',
                        json={
                            'model': 'neural-chat',
                            'prompt': prompt,
                            'stream': False
                        },
                        timeout=30
                    )
                    if response.status_code == 200:
                        response_data = response.json()
                        response_text = response_data.get('response', '')
                    else:
                        return {"error": f"Ollama error: {response.status_code}"}
                except (requests.Timeout, requests.ConnectionError) as e:
                    return {"error": f"Ollama timeout/connection error: {e}"}
            else:
                # Using Anthropic API
                message = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2000,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                response_text = message.content[0].text
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
                return plan
            else:
                return {"error": "Could not parse AI response", "raw_response": response_text}
        
        except Exception as e:
            return {"error": str(e)}
    
    def _format_ui_elements(self, elements: List[Dict]) -> str:
        """Format UI elements for Claude prompt"""
        if not elements:
            return "No UI elements found"
        
        formatted = []
        for elem in elements[:20]:  # Limit to first 20 elements
            elem_desc = f"- {elem.get('type', 'View')}"
            
            if elem.get('text'):
                elem_desc += f": '{elem['text']}'"
            elif elem.get('resource_id'):
                elem_desc += f": {elem['resource_id'].split('/')[-1]}"
            
            if elem.get('clickable'):
                elem_desc += " [clickable]"
            
            formatted.append(elem_desc)
        
        if len(elements) > 20:
            formatted.append(f"... and {len(elements) - 20} more elements")
        
        return "\n".join(formatted)
    
    def find_element_by_hint(self, hint: str, ui_elements: List[Dict]) -> Optional[Dict]:
        """
        Find UI element using AI-generated hint
        
        Matches based on:
        - Resource ID contains hint
        - Text contains hint
        - Accessibility ID contains hint
        """
        hint_lower = hint.lower()
        keywords = hint_lower.split()
        
        best_match = None
        best_score = 0
        
        for elem in ui_elements:
            score = 0
            
            # Check resource_id
            if elem.get('resource_id'):
                resource_id_lower = elem['resource_id'].lower()
                for keyword in keywords:
                    if keyword in resource_id_lower:
                        score += 3
            
            # Check text
            if elem.get('text'):
                text_lower = elem['text'].lower()
                for keyword in keywords:
                    if keyword in text_lower:
                        score += 2
            
            # Check accessibility_id
            if elem.get('accessibility_id'):
                acc_id_lower = elem['accessibility_id'].lower()
                for keyword in keywords:
                    if keyword in acc_id_lower:
                        score += 2
            
            if score > best_score:
                best_score = score
                best_match = elem
        
        return best_match if best_score > 0 else None
    
    def execute_action(self, action: str, element: Optional[Dict], input_value: str = None) -> Dict:
        """
        Execute action on element using Appium
        
        Actions: click, enter, verify, scroll, wait
        """
        if not self.ui_explorer.driver:
            return {"success": False, "error": "Not connected to device"}
        
        try:
            if action == "click" and element:
                # Click element
                xpath = element.get('xpath')
                if xpath:
                    elem = self.ui_explorer.driver.find_element("xpath", xpath)
                    elem.click()
                    time.sleep(1)  # Wait for screen to load
                    return {"success": True, "action": "click", "element": element.get('text') or element.get('id')}
            
            elif action == "enter" and element and input_value:
                # Enter text
                xpath = element.get('xpath')
                if xpath:
                    elem = self.ui_explorer.driver.find_element("xpath", xpath)
                    elem.clear()
                    elem.send_keys(input_value)
                    time.sleep(0.5)
                    return {"success": True, "action": "enter", "element": element.get('text') or element.get('id'), "value": input_value}
            
            elif action == "verify" and element:
                # Verify element is visible
                xpath = element.get('xpath')
                if xpath:
                    elem = self.ui_explorer.driver.find_element("xpath", xpath)
                    is_displayed = elem.is_displayed()
                    return {"success": is_displayed, "action": "verify", "element": element.get('text') or element.get('id'), "visible": is_displayed}
            
            elif action == "scroll":
                # Scroll down
                self.ui_explorer.driver.swipe(285, 600, 285, 300, 500)
                time.sleep(0.5)
                return {"success": True, "action": "scroll"}
            
            elif action == "wait":
                # Wait for screen to load
                time.sleep(2)
                return {"success": True, "action": "wait"}
            
            return {"success": False, "error": f"Unknown action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e), "action": action}
    
    def add_locator(self, element: Dict, step_info: Dict):
        """Add locator to collection if not already present"""
        if not element:
            return False
        
        locator_id = element.get('resource_id') or element.get('text') or element.get('accessibility_id')
        
        if not locator_id or locator_id in self.locator_ids:
            return False
        
        self.locator_ids.add(locator_id)
        self.collected_locators[locator_id] = {
            'resource_id': element.get('resource_id'),
            'xpath': element.get('xpath'),
            'accessibility_id': element.get('accessibility_id'),
            'text': element.get('text'),
            'type': element.get('type'),
            'clickable': element.get('clickable'),
            'used_in_step': step_info.get('step_number'),
            'action': step_info.get('action')
        }
        
        return True
    
    def execute_test_case_with_ai(self, test_case: Dict, device_name: str = "127.0.0.1:6555",
                                   app_package: str = None, app_activity: str = None) -> Dict:
        """
        Execute single test case with AI navigation
        
        Returns:
        {
            'success': True,
            'test_case_id': 'TC001',
            'steps_executed': 5,
            'locators_collected': 12,
            'navigation_log': [...]
        }
        """
        print(f"\n{'='*70}")
        print(f"🤖 AI-Guided Test Execution: {test_case['id']} - {test_case['name']}")
        print(f"{'='*70}")
        
        # Connect to device
        print(f"\n📱 Connecting to device: {device_name}")
        connection = self.ui_explorer.connect_to_emulator(
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity
        )
        
        if not connection['success']:
            return {
                'success': False,
                'error': connection.get('error'),
                'test_case_id': test_case['id']
            }
        
        print(f"✅ Connected to {device_name}")
        
        # Explore initial screen
        print(f"\n📸 Exploring initial screen...")
        initial_screen = self.ui_explorer.explore_current_screen("InitialScreen")
        
        if not initial_screen.get('success'):
            self.ui_explorer.disconnect()
            return {
                'success': False,
                'error': 'Failed to explore initial screen',
                'test_case_id': test_case['id']
            }
        
        ui_elements = initial_screen.get('elements', [])
        print(f"✅ Found {len(ui_elements)} UI elements")
        
        # Get AI navigation plan
        print(f"\n🧠 Generating AI navigation plan...")
        plan = self.get_ai_navigation_plan(test_case, ui_elements)
        
        if 'error' in plan:
            print(f"⚠️  AI planning error: {plan['error']}")
            self.ui_explorer.disconnect()
            return {
                'success': False,
                'error': f"AI planning failed: {plan['error']}",
                'test_case_id': test_case['id']
            }
        
        print(f"✅ Plan generated: {plan.get('flow_summary', 'N/A')}")
        
        # Execute plan steps
        steps_executed = 0
        locators_collected = 0
        execution_log = []
        
        for step_plan in plan.get('steps', []):
            step_num = step_plan.get('step_number', steps_executed + 1)
            action = step_plan.get('action', 'unknown')
            target = step_plan.get('target_element', 'unknown')
            reason = step_plan.get('reason', '')
            
            print(f"\n{'─'*70}")
            print(f"Step {step_num}: {action.upper()} - {target}")
            print(f"Reason: {reason}")
            
            # Explore current screen
            screen_result = self.ui_explorer.explore_current_screen(f"Step{step_num}")
            if not screen_result.get('success'):
                print(f"⚠️  Could not explore screen")
                continue
            
            current_elements = screen_result.get('elements', [])
            print(f"Found {len(current_elements)} UI elements on screen")
            
            # Find target element
            target_hint = step_plan.get('target_locator_hint', target)
            target_element = self.find_element_by_hint(target_hint, current_elements)
            
            if target_element:
                print(f"✅ Found target element: {target_element.get('text') or target_element.get('id')}")
                
                # Add to locators if it's a clickable/interactive element
                if target_element.get('clickable') or action in ['click', 'enter']:
                    is_new = self.add_locator(target_element, step_plan)
                    if is_new:
                        locators_collected += 1
                        print(f"📍 New locator collected")
            else:
                print(f"⚠️  Target element not found: {target_hint}")
            
            # Execute action
            input_value = step_plan.get('input_value', None)
            action_result = self.execute_action(action, target_element, input_value)
            
            if action_result.get('success'):
                print(f"✅ Action executed successfully")
            else:
                print(f"⚠️  Action failed: {action_result.get('error')}")
            
            execution_log.append({
                'step': step_num,
                'action': action,
                'target': target,
                'result': action_result,
                'locator_collected': target_element is not None
            })
            
            steps_executed += 1
            time.sleep(0.5)
        
        # Disconnect
        self.ui_explorer.disconnect()
        
        # Save locators
        locators_file = self.save_locators(test_case['id'])
        
        print(f"\n{'='*70}")
        print(f"✅ Test Execution Complete!")
        print(f"{'='*70}")
        print(f"Steps Executed: {steps_executed}")
        print(f"Locators Collected: {locators_collected}")
        print(f"Locators File: {locators_file}")
        print(f"{'='*70}\n")
        
        return {
            'success': True,
            'test_case_id': test_case['id'],
            'test_case_name': test_case['name'],
            'steps_executed': steps_executed,
            'locators_collected': locators_collected,
            'locators_file': locators_file,
            'execution_log': execution_log,
            'ai_plan': plan,
            'locators': self.collected_locators
        }
    
    def execute_test_plan_with_ai(self, test_plan_path: str, device_name: str = "127.0.0.1:6555",
                                   app_package: str = None, app_activity: str = None) -> Dict:
        """
        Execute entire test plan with AI navigation
        """
        print(f"\n{'='*70}")
        print(f"🚀 AI-Guided Test Plan Execution")
        print(f"{'='*70}")
        
        # Parse test plan
        test_cases = self.parse_test_plan(test_plan_path)
        print(f"\n✅ Parsed {len(test_cases)} test cases from {test_plan_path}")
        
        results = []
        total_locators = 0
        
        for tc_idx, test_case in enumerate(test_cases, 1):
            print(f"\n\n{'#'*70}")
            print(f"# Test Case {tc_idx}/{len(test_cases)}")
            print(f"{'#'*70}")
            
            # Reset locators for each test case
            self.collected_locators = {}
            self.locator_ids = set()
            
            result = self.execute_test_case_with_ai(
                test_case,
                device_name=device_name,
                app_package=app_package,
                app_activity=app_activity
            )
            
            results.append(result)
            if result.get('success'):
                total_locators += result.get('locators_collected', 0)
        
        return {
            'success': True,
            'test_plan_path': test_plan_path,
            'test_cases_executed': len(test_cases),
            'total_locators_collected': total_locators,
            'results': results
        }
    
    def save_locators(self, test_case_id: str) -> str:
        """Save collected locators to file"""
        os.makedirs("locators", exist_ok=True)
        
        output_file = f"locators/{test_case_id}_locators.txt"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# Locators for: {test_case_id}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total unique locators: {len(self.collected_locators)}\n")
            f.write("\n" + "="*80 + "\n\n")
            
            for idx, (locator_id, locator) in enumerate(self.collected_locators.items(), 1):
                f.write(f"{idx}. {locator_id}\n")
                f.write(f"   Type: {locator.get('type')}\n")
                
                if locator.get('resource_id'):
                    f.write(f"   Resource ID: {locator['resource_id']}\n")
                
                if locator.get('xpath'):
                    f.write(f"   XPath: {locator['xpath']}\n")
                
                if locator.get('accessibility_id'):
                    f.write(f"   Accessibility ID: {locator['accessibility_id']}\n")
                
                if locator.get('text'):
                    f.write(f"   Text: {locator['text']}\n")
                
                f.write(f"   Clickable: {locator.get('clickable')}\n")
                f.write(f"   Used in Step: {locator.get('used_in_step')}\n")
                f.write(f"   Action: {locator.get('action')}\n")
                f.write("\n" + "-"*80 + "\n\n")
        
        return output_file
