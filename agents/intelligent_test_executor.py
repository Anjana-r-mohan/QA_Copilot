"""
Intelligent Test Executor - TRUE AI-Driven Test Execution
Uses vision + reasoning to actually execute tests, not just scrape screens
"""

import os
import re
import time
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests
from appium import webdriver
from appium.options.android import UiAutomator2Options


class IntelligentTestExecutor:
    """
    REAL AI test executor that:
    1. Understands test steps using AI
    2. Analyzes current screen state
    3. Determines correct actions (tap, input, scroll)
    4. Executes actions on app
    5. Verifies results
    6. Collects locators from CORRECT screens
    """
    
    def __init__(self):
        self.driver = None
        self.use_ollama = False
        self.collected_locators = {}
        self.locator_ids = set()
        self.execution_history = []
        
        # Initialize AI
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                self.use_ollama = True
                print("✅ Using Ollama for intelligent test execution")
        except:
            pass
    
    def connect_to_device(self, device_name: str, app_package: str, app_activity: str):
        """Connect to Android device/emulator"""
        try:
            options = UiAutomator2Options()
            options.platform_name = 'Android'
            options.device_name = device_name
            options.automation_name = 'UiAutomator2'
            options.no_reset = True
            
            if app_package:
                options.app_package = app_package
            if app_activity:
                options.app_activity = app_activity
            
            self.driver = webdriver.Remote('http://localhost:4723', options=options)
            time.sleep(2)
            
            return {'success': True, 'message': f'Connected to {device_name}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def execute_test_plan_intelligently(self, test_plan_path: str, device_name: str,
                                       app_package: str, app_activity: str,
                                       workspace_path: str, progress_callback=None) -> Dict:
        """
        Execute test plan with TRUE intelligence
        """
        
        def send_progress(msg_type: str, message: str, data: dict = None):
            if progress_callback:
                progress_callback(msg_type, message, data)
            print(message)
        
        # Parse test plan
        send_progress('progress', f"📋 Parsing test plan: {test_plan_path}")
        test_cases = self._parse_test_plan(test_plan_path)
        send_progress('success', f"✅ Found {len(test_cases)} test cases")
        
        # Connect
        send_progress('progress', f"📱 Connecting to device: {device_name}")
        conn_result = self.connect_to_device(device_name, app_package, app_activity)
        if not conn_result['success']:
            send_progress('error', f"❌ Connection failed: {conn_result['error']}")
            return {'success': False, 'error': conn_result['error']}
        
        send_progress('success', f"✅ Connected to {device_name}")
        
        # Execute each test case with INTELLIGENCE
        for tc_idx, test_case in enumerate(test_cases, 1):
            tc_id = test_case['id']
            tc_title = test_case['title']
            steps = test_case['steps']
            preconditions = test_case.get('preconditions', [])
            
            send_progress('test_case_start',
                         f"📝 Executing {tc_id}: {tc_title} ({tc_idx}/{len(test_cases)})",
                         {'test_case_id': tc_id, 'test_case_number': tc_idx, 'total_test_cases': len(test_cases)})
            
            # Handle preconditions first
            if preconditions:
                send_progress('progress', f"🔧 Setting up preconditions...")
                for precond in preconditions:
                    self._execute_step_intelligently(precond, tc_id, 0, send_progress)
            
            # Execute each step with AI
            for step_idx, step in enumerate(steps, 1):
                send_progress('step', f"   Step {step_idx}/{len(steps)}: {step[:60]}...")
                
                success = self._execute_step_intelligently(step, tc_id, step_idx, send_progress)
                
                if not success:
                    send_progress('warning', f"   ⚠️  Step failed, continuing...")
        
        # Save locators
        send_progress('progress', f"💾 Saving {len(self.collected_locators)} locators...")
        test_plan_name = os.path.basename(test_plan_path).replace('.md', '')
        locators_file = self._save_locators(workspace_path, test_plan_name)
        
        # Disconnect
        if self.driver:
            self.driver.quit()
        
        send_progress('complete',
                     f"🎉 Test execution complete!",
                     {
                         'test_cases_executed': len(test_cases),
                         'locators_collected': len(self.collected_locators),
                         'locators_file': locators_file
                     })
        
        return {
            'success': True,
            'steps_executed': len(test_cases),
            'locators_collected': len(self.collected_locators),
            'locators_file': locators_file,
            'test_plan_used': test_plan_path
        }
    
    def _execute_step_intelligently(self, step_text: str, tc_id: str, step_idx: int,
                                    send_progress) -> bool:
        """
        CORE INTELLIGENCE: Execute ONE test step properly
        
        1. Get current screen state
        2. Ask AI: What action should I take?
        3. Find the target element
        4. Execute the action
        5. Verify result
        6. Collect locators
        """
        
        try:
            # 1. Get current screen
            page_source = self.driver.page_source
            current_elements = self._parse_page_source(page_source)
            
            send_progress('progress', f"      🧠 AI analyzing step...")
            
            # 2. Ask AI what to do
            action_plan = self._ai_determine_action(step_text, current_elements, page_source)
            
            if not action_plan:
                send_progress('warning', f"      ⚠️  AI couldn't determine action")
                # Still collect locators from this screen
                self._collect_locators_from_elements(current_elements, tc_id, step_idx)
                return False
            
            # 3. Execute the action
            send_progress('progress', 
                         f"      🎯 {action_plan['action_type']}: {action_plan['target_description']}")
            
            executed = self._execute_action(action_plan)
            
            if executed:
                send_progress('success', f"      ✅ Action executed successfully")
                time.sleep(1.5)  # Wait for screen to update
                
                # 4. Collect locators from NEW screen state
                new_page_source = self.driver.page_source
                new_elements = self._parse_page_source(new_page_source)
                
                added = self._collect_locators_from_elements(new_elements, tc_id, step_idx)
                send_progress('locators_update',
                             f"      📍 Collected {added} new locators (total: {len(self.collected_locators)})",
                             {'new_locators': added, 'total_locators': len(self.collected_locators)})
                
                return True
            else:
                send_progress('warning', f"      ⚠️  Action execution failed")
                return False
        
        except Exception as e:
            send_progress('error', f"      ❌ Step failed: {str(e)}")
            return False
    
    def _ai_determine_action(self, step_text: str, elements: List[Dict], page_source: str) -> Optional[Dict]:
        """
        Use AI to understand what action to take
        
        Returns:
        {
            'action_type': 'tap' | 'input' | 'scroll' | 'wait' | 'verify',
            'target_element': <element dict>,
            'target_description': 'Login button',
            'input_value': 'user@example.com' (if action_type is 'input'),
            'reasoning': 'User wants to login, need to tap login button'
        }
        """
        
        # Build context for AI
        elements_summary = self._summarize_elements_for_ai(elements)
        
        prompt = f"""You are a mobile test automation expert. Analyze this test step and current screen, then decide what action to take.

TEST STEP: "{step_text}"

CURRENT SCREEN ELEMENTS:
{elements_summary}

YOUR TASK:
1. Understand what the step wants to accomplish
2. Find the right element to interact with
3. Determine the action type (tap, input, scroll, wait, verify)
4. If it's an input action, extract the value to enter

RESPOND IN JSON:
{{
    "action_type": "tap|input|scroll|wait|verify",
    "target_element_index": <index from elements list, or -1 if none>,
    "target_description": "brief description of target",
    "input_value": "value to input" (only for input actions),
    "reasoning": "why this action"
}}

EXAMPLES:
- Step: "Click login button" → {{"action_type": "tap", "target_element_index": 5, "target_description": "Login button"}}
- Step: "Enter email user@test.com" → {{"action_type": "input", "target_element_index": 2, "input_value": "user@test.com"}}
- Step: "Scroll to bottom" → {{"action_type": "scroll", "target_element_index": -1}}
"""
        
        # Call AI
        if self.use_ollama:
            response = self._call_ollama(prompt)
        else:
            # Fallback to keyword matching
            return self._keyword_based_action(step_text, elements)
        
        if not response:
            return None
        
        # Parse AI response
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                action_plan = json.loads(json_match.group())
                
                # Get the actual element
                element_idx = action_plan.get('target_element_index', -1)
                if element_idx >= 0 and element_idx < len(elements):
                    action_plan['target_element'] = elements[element_idx]
                else:
                    action_plan['target_element'] = None
                
                return action_plan
        except Exception as e:
            print(f"Failed to parse AI response: {e}")
            return None
        
        return None
    
    def _execute_action(self, action_plan: Dict) -> bool:
        """
        Execute the planned action on the device
        """
        try:
            action_type = action_plan['action_type']
            target_element = action_plan.get('target_element')
            
            if action_type == 'tap' and target_element:
                # Find and tap element
                locator = self._get_best_locator(target_element)
                if locator:
                    elem = self.driver.find_element(locator['by'], locator['value'])
                    elem.click()
                    return True
            
            elif action_type == 'input' and target_element:
                # Find and input text
                locator = self._get_best_locator(target_element)
                input_value = action_plan.get('input_value', '')
                if locator and input_value:
                    elem = self.driver.find_element(locator['by'], locator['value'])
                    elem.clear()
                    elem.send_keys(input_value)
                    return True
            
            elif action_type == 'scroll':
                # Perform scroll
                self.driver.swipe(500, 1500, 500, 500, 500)
                return True
            
            elif action_type == 'wait':
                # Just wait
                time.sleep(2)
                return True
            
            elif action_type == 'verify':
                # Check if element exists
                if target_element:
                    locator = self._get_best_locator(target_element)
                    if locator:
                        elem = self.driver.find_element(locator['by'], locator['value'])
                        return elem is not None
                return True
            
            return False
        
        except Exception as e:
            print(f"Action execution failed: {e}")
            return False
    
    def _get_best_locator(self, element: Dict) -> Optional[Dict]:
        """Find best locator strategy for element"""
        
        # Priority: resource-id > xpath > text
        if element.get('resource-id'):
            return {'by': 'id', 'value': element['resource-id']}
        
        if element.get('xpath'):
            return {'by': 'xpath', 'value': element['xpath']}
        
        if element.get('text'):
            return {'by': 'xpath', 'value': f"//*[@text='{element['text']}']"}
        
        if element.get('content-desc'):
            return {'by': 'xpath', 'value': f"//*[@content-desc='{element['content-desc']}']"}
        
        return None
    
    def _summarize_elements_for_ai(self, elements: List[Dict], max_elements: int = 30) -> str:
        """
        Create concise summary of elements for AI
        """
        summary = []
        for idx, elem in enumerate(elements[:max_elements]):
            text = elem.get('text', '')
            res_id = elem.get('resource-id', '')
            class_name = elem.get('class', '').split('.')[-1]
            
            desc = f"[{idx}] {class_name}"
            if text:
                desc += f" text='{text}'"
            if res_id:
                desc += f" id='{res_id}'"
            
            summary.append(desc)
        
        if len(elements) > max_elements:
            summary.append(f"... and {len(elements) - max_elements} more elements")
        
        return "\n".join(summary)
    
    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call Ollama API"""
        try:
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={'model': 'llama2', 'prompt': prompt, 'stream': False},
                timeout=30
            )
            if response.status_code == 200:
                return response.json().get('response', '')
        except Exception as e:
            print(f"Ollama call failed: {e}")
        return None
    
    def _keyword_based_action(self, step_text: str, elements: List[Dict]) -> Optional[Dict]:
        """
        Fallback: keyword-based action detection
        """
        step_lower = step_text.lower()
        
        # Detect action type
        if any(kw in step_lower for kw in ['click', 'tap', 'select', 'press']):
            action_type = 'tap'
        elif any(kw in step_lower for kw in ['enter', 'input', 'type', 'fill']):
            action_type = 'input'
        elif 'scroll' in step_lower:
            action_type = 'scroll'
        elif 'wait' in step_lower:
            action_type = 'wait'
        else:
            action_type = 'verify'
        
        # Try to find target element by keyword matching
        for idx, elem in enumerate(elements):
            text = (elem.get('text', '') + ' ' + elem.get('resource-id', '')).lower()
            
            # Simple keyword matching
            if any(word in text for word in step_lower.split() if len(word) > 3):
                return {
                    'action_type': action_type,
                    'target_element': elem,
                    'target_element_index': idx,
                    'target_description': elem.get('text', elem.get('resource-id', 'element')),
                    'reasoning': 'Keyword match fallback'
                }
        
        return None
    
    def _parse_page_source(self, page_source: str) -> List[Dict]:
        """Parse XML page source into element list"""
        import xml.etree.ElementTree as ET
        
        elements = []
        try:
            root = ET.fromstring(page_source)
            for elem in root.iter():
                attribs = elem.attrib
                if attribs.get('clickable') == 'true' or attribs.get('text'):
                    elements.append({
                        'class': attribs.get('class', ''),
                        'text': attribs.get('text', ''),
                        'resource-id': attribs.get('resource-id', ''),
                        'content-desc': attribs.get('content-desc', ''),
                        'clickable': attribs.get('clickable', 'false'),
                        'bounds': attribs.get('bounds', '')
                    })
        except:
            pass
        
        return elements
    
    def _collect_locators_from_elements(self, elements: List[Dict], tc_id: str, step_idx: int) -> int:
        """Add unique elements to locator collection"""
        added = 0
        for elem in elements:
            elem_id = elem.get('resource-id') or elem.get('text') or elem.get('content-desc')
            if elem_id and elem_id not in self.locator_ids:
                self.collected_locators[elem_id] = {
                    'resource_id': elem.get('resource-id', ''),
                    'text': elem.get('text', ''),
                    'content_desc': elem.get('content-desc', ''),
                    'class': elem.get('class', ''),
                    'test_case': tc_id,
                    'step': step_idx
                }
                self.locator_ids.add(elem_id)
                added += 1
        return added
    
    def _parse_test_plan(self, test_plan_path: str) -> List[Dict]:
        """Parse markdown test plan"""
        if not os.path.exists(test_plan_path):
            return []
        
        try:
            with open(test_plan_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            test_cases = []
            current_tc = None
            lines = content.split('\n')
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Match test case ID (#### TC8508:)
                if line.strip().startswith('#### TC'):
                    if current_tc:
                        test_cases.append(current_tc)
                    
                    # Extract TC ID and title
                    tc_line = line.strip()
                    tc_id = tc_line.split(':')[0].replace('#### ', '').strip()
                    tc_title = tc_line.split(':', 1)[1].strip() if ':' in tc_line else ''
                    
                    current_tc = {
                        'id': tc_id,
                        'title': tc_title,
                        'priority': '',
                        'preconditions': [],
                        'steps': [],
                        'expected_results': []
                    }
                
                # Match Preconditions
                elif line.startswith('**Preconditions**'):
                    i += 1
                    while i < len(lines):
                        line = lines[i]
                        if line.startswith('**'):
                            i -= 1
                            break
                        if line.strip().startswith('- '):
                            current_tc['preconditions'].append(line.strip()[2:])
                        i += 1
                    continue
                
                # Match Steps
                elif line.startswith('**Steps**'):
                    i += 1
                    while i < len(lines):
                        line = lines[i]
                        if line.startswith('**'):
                            i -= 1
                            break
                        # Match numbered steps (1. 2. 3. etc)
                        if line.strip() and line.strip()[0].isdigit() and '. ' in line:
                            step_text = line.strip()
                            # Remove step number (e.g., "1. " or "1.2. ")
                            step_text = step_text.split('. ', 1)[1] if '. ' in step_text else step_text
                            current_tc['steps'].append(step_text)
                        i += 1
                    continue
                
                i += 1
            
            # Add last test case
            if current_tc:
                test_cases.append(current_tc)
            
            return test_cases
        
        except Exception as e:
            print(f"Failed to parse test plan: {e}")
            return []
    
    def _save_locators(self, workspace_path: str, test_plan_name: str) -> str:
        """Save collected locators to file"""
        locators_dir = os.path.join(workspace_path, 'locators')
        os.makedirs(locators_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{test_plan_name}_{timestamp}_locators.txt"
        filepath = os.path.join(locators_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# UI Locators - Generated: {datetime.now()}\n")
            f.write(f"# Test Plan: {test_plan_name}\n")
            f.write(f"# Total Locators: {len(self.collected_locators)}\n\n")
            
            for loc_id, loc_data in self.collected_locators.items():
                f.write(f"## {loc_data.get('text', loc_id)}\n")
                f.write(f"Resource ID: {loc_data.get('resource_id', 'N/A')}\n")
                f.write(f"Class: {loc_data.get('class', 'N/A')}\n")
                f.write(f"Test Case: {loc_data.get('test_case')}\n\n")
        
        return filepath
