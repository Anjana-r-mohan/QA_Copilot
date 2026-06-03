"""
Test Executor Agent
Executes test cases step by step and collects locators
"""

import os
import re
import time
from typing import List, Dict, Set
from datetime import datetime


class TestExecutorAgent:
    """
    Executes test plan steps and collects unique locators
    """
    
    def __init__(self, ui_explorer_agent):
        self.ui_explorer = ui_explorer_agent
        self.collected_locators = {}  # {locator_id: locator_data}
        self.locator_ids = set()  # For quick duplicate checking
        
    def parse_test_plan(self, test_plan_path: str) -> List[Dict]:
        """
        Parse test plan markdown file and extract test cases
        """
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
                    # Remove step number (1. 2. etc.)
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
    
    def identify_action_and_element(self, step: str) -> Dict:
        """
        Parse step text to identify action and target element
        
        Examples:
        - "Enter username" → action: enter, element: username
        - "Click Login button" → action: click, element: login button
        - "Verify user logged in" → action: verify, element: user status
        """
        step_lower = step.lower()
        
        action = None
        element = None
        
        # Identify action
        if any(word in step_lower for word in ['enter', 'type', 'input', 'fill']):
            action = 'enter'
        elif any(word in step_lower for word in ['click', 'tap', 'press', 'select']):
            action = 'click'
        elif any(word in step_lower for word in ['verify', 'check', 'validate', 'assert']):
            action = 'verify'
        elif any(word in step_lower for word in ['open', 'launch', 'navigate', 'go to']):
            action = 'navigate'
        elif any(word in step_lower for word in ['scroll', 'swipe']):
            action = 'scroll'
        else:
            action = 'interact'
        
        # Extract element name (everything after action word)
        for keyword in ['enter', 'type', 'click', 'tap', 'press', 'verify', 'check', 'open', 'select']:
            if keyword in step_lower:
                parts = step_lower.split(keyword, 1)
                if len(parts) > 1:
                    element = parts[1].strip()
                    # Clean up common words
                    element = element.replace('the ', '').replace('button', '').replace('field', '').strip()
                    break
        
        if not element:
            element = step_lower
        
        return {
            'action': action,
            'element': element,
            'original_step': step
        }
    
    def find_matching_locator(self, element_name: str, ui_elements: List[Dict]) -> Dict:
        """
        Find UI element that matches the step description
        
        Matching logic:
        - Check resource_id contains element name
        - Check text matches element name
        - Check accessibility_id matches
        - Check type matches (Button, EditText, etc.)
        """
        element_name_lower = element_name.lower()
        
        # Remove common words
        keywords = element_name_lower.replace('button', '').replace('field', '').replace('the', '').strip().split()
        
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
            
            # Check type
            elem_type = elem.get('type', '').lower()
            if 'button' in element_name_lower and 'button' in elem_type:
                score += 1
            if any(word in element_name_lower for word in ['field', 'input', 'text']) and 'edit' in elem_type:
                score += 1
            
            if score > best_score:
                best_score = score
                best_match = elem
        
        return best_match if best_score > 0 else None
    
    def add_locator(self, element: Dict, step_info: Dict):
        """
        Add locator to collection if not already present
        """
        if not element:
            return False
        
        # Create unique ID for this locator
        locator_id = element.get('resource_id') or element.get('text') or element.get('accessibility_id')
        
        if not locator_id or locator_id in self.locator_ids:
            return False  # Already collected
        
        # Add to collection
        self.locator_ids.add(locator_id)
        self.collected_locators[locator_id] = {
            'resource_id': element.get('resource_id'),
            'xpath': element.get('xpath'),
            'accessibility_id': element.get('accessibility_id'),
            'text': element.get('text'),
            'type': element.get('type'),
            'clickable': element.get('clickable'),
            'used_in_step': step_info['original_step'],
            'action': step_info['action']
        }
        
        return True  # New locator added
    
    def execute_test_plan(self, test_plan_path: str, device_name: str = "127.0.0.1:6555",
                          app_package: str = None, app_activity: str = None) -> Dict:
        """
        Execute test plan and collect locators
        
        Returns:
        {
            'success': True,
            'test_cases_executed': 5,
            'total_steps': 25,
            'unique_locators_collected': 15,
            'locators_file': 'locators_test_plan_name.txt'
        }
        """
        print(f"\n🚀 Starting Test Execution")
        print(f"📄 Test Plan: {test_plan_path}")
        print("=" * 60)
        
        # Parse test plan
        test_cases = self.parse_test_plan(test_plan_path)
        print(f"\n✅ Parsed {len(test_cases)} test cases")
        
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
                'message': 'Failed to connect to device'
            }
        
        print(f"✅ Connected to {device_name}")
        
        total_steps = 0
        new_locators = 0
        
        # Execute each test case
        for tc_idx, tc in enumerate(test_cases, 1):
            print(f"\n{'='*60}")
            print(f"Test Case {tc_idx}/{len(test_cases)}: {tc['id']} - {tc['name']}")
            print(f"{'='*60}")
            
            # Execute each step
            for step_idx, step in enumerate(tc['steps'], 1):
                print(f"\n  Step {step_idx}: {step}")
                total_steps += 1
                
                # Identify action and element
                step_info = self.identify_action_and_element(step)
                print(f"    → Action: {step_info['action']}, Element: {step_info['element']}")
                
                # Explore current screen
                screen_result = self.ui_explorer.explore_current_screen(f"{tc['id']}_Step{step_idx}")
                
                if not screen_result.get('success'):
                    print(f"    ⚠️  Could not explore screen: {screen_result.get('error')}")
                    continue
                
                ui_elements = screen_result.get('elements', [])
                print(f"    → Found {len(ui_elements)} UI elements")
                
                # Find matching locator
                matching_element = self.find_matching_locator(step_info['element'], ui_elements)
                
                if matching_element:
                    # Add to collection
                    is_new = self.add_locator(matching_element, step_info)
                    if is_new:
                        new_locators += 1
                        print(f"    ✅ New locator collected: {matching_element.get('resource_id') or matching_element.get('text')}")
                    else:
                        print(f"    ℹ️  Locator already collected (skipped)")
                else:
                    print(f"    ⚠️  No matching element found for: {step_info['element']}")
                
                # Small delay between steps
                time.sleep(0.5)
        
        # Disconnect
        self.ui_explorer.disconnect()
        
        # Save locators to file
        locators_file = self.save_locators(test_plan_path)
        
        print(f"\n{'='*60}")
        print(f"✅ Test Execution Complete!")
        print(f"{'='*60}")
        print(f"Test Cases Executed: {len(test_cases)}")
        print(f"Total Steps: {total_steps}")
        print(f"Unique Locators Collected: {len(self.collected_locators)}")
        print(f"Locators File: {locators_file}")
        print(f"{'='*60}\n")
        
        return {
            'success': True,
            'test_cases_executed': len(test_cases),
            'total_steps': total_steps,
            'unique_locators_collected': len(self.collected_locators),
            'locators_file': locators_file,
            'locators': self.collected_locators
        }
    
    def save_locators(self, test_plan_path: str) -> str:
        """
        Save collected locators to .txt file with same base name as test plan
        """
        # Get base name from test plan
        base_name = os.path.splitext(os.path.basename(test_plan_path))[0]
        output_file = f"locators/{base_name}_locators.txt"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# Locators collected from: {test_plan_path}\n")
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
                f.write(f"   Used in: {locator.get('used_in_step')}\n")
                f.write(f"   Action: {locator.get('action')}\n")
                f.write("\n" + "-"*80 + "\n\n")
        
        print(f"💾 Locators saved to: {output_file}")
        return output_file


def demo_test_executor():
    """Demo the test executor agent"""
    from ui_explorer_agent import UIExplorerAgent
    
    print("🧪 Test Executor Agent Demo")
    print("=" * 60)
    
    # Initialize agents
    ui_explorer = UIExplorerAgent()
    executor = TestExecutorAgent(ui_explorer)
    
    # Execute test plan
    result = executor.execute_test_plan(
        test_plan_path='test_plans/test_plan_sample.md',
        device_name='127.0.0.1:6555',
        app_package='co.bizom.apps',
        app_activity='.android.MainActivity'
    )
    
    if result['success']:
        print(f"\n✅ Success!")
        print(f"   Locators file: {result['locators_file']}")
    else:
        print(f"\n❌ Failed: {result.get('error')}")


if __name__ == "__main__":
    demo_test_executor()
