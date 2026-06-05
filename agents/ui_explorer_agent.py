"""
UI Explorer Agent
Intelligent agent that navigates through app flows and collects locators
Uses AI to understand user intent and guide navigation
"""

import json
import os
import requests
from typing import Dict, List, Optional
from datetime import datetime
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class UIExplorerAgent:
    """
    Intelligent UI Explorer that navigates based on user commands
    Uses AI to understand intent and guide navigation
    Collects locators as it navigates
    """
    
    def __init__(self):
        self.ui_elements = []
        self.driver = None
        self.appium_available = self._check_appium_available()
        self.collected_locators = {}
        self.locator_ids = set()
        self.navigation_log = []
        self.use_groq = False
        self.use_ollama = False
        self.ollama_url = None
        
        # Check for cloud Ollama first
        cloud_ollama_url = os.getenv('CLOUD_OLLAMA_URL', '').strip()
        if cloud_ollama_url:
            print(f"🌩️  Attempting Cloud Ollama at: {cloud_ollama_url}")
            try:
                response = requests.get(f'{cloud_ollama_url}/api/tags', timeout=10)
                if response.status_code == 200:
                    self.use_ollama = True
                    self.ollama_url = cloud_ollama_url
                    print("✅ Using Cloud Ollama (Remote GPU)")
                    return
                else:
                    print(f"⚠️  Cloud Ollama returned {response.status_code}")
            except Exception as e:
                print(f"⚠️  Cloud Ollama not available: {e}")
        
        # Try Ollama FIRST (local, no API key needed, unlimited usage)
        print("🤖 Initializing with Ollama (Local AI)...")
        try:
            # Test if Ollama server is running via HTTP
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                self.use_ollama = True
                self.ollama_url = 'http://localhost:11434'
                print("✅ Using Ollama (Local AI) - Connected via HTTP")
                return
            else:
                print(f"⚠️  Ollama not responding: {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("⚠️  Ollama server not running at http://localhost:11434")
        except Exception as e:
            print(f"⚠️  Ollama connection failed: {e}")
        
        print("❌ WARNING: No AI backend available. Ollama initialization failed.")
    
    def _check_appium_available(self) -> bool:
        """Check if Appium Python client is available"""
        try:
            from appium import webdriver
            return True
        except ImportError:
            print("⚠️  Appium Python client not installed. Install with: pip install Appium-Python-Client")
            return False
        
    def connect_to_emulator(self, device_name: str = "127.0.0.1:6555", 
                            app_package: str = "co.bizom.apps", 
                            app_activity: str = "co.bizom.apps.android.MainActivity",
                            platform: str = "android") -> Dict:
        """
        Connect to real emulator via Appium
        
        Args:
            device_name: Device name (e.g., 'emulator-5554' or '192.168.56.101:5555')
            app_package: Android app package (e.g., 'com.bizom')
            app_activity: Android app activity (e.g., '.MainActivity')
            platform: 'android' or 'ios'
        """
        if not self.appium_available:
            return {
                "success": False,
                "error": "Appium Python client not installed",
                "message": "Install with: pip install Appium-Python-Client"
            }
        
        try:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options
            
            if platform.lower() == "android":
                options = UiAutomator2Options()
                options.platform_name = "Android"
                options.device_name = device_name
                options.automation_name = "UiAutomator2"
                
                # If app package provided, launch specific app
                if app_package:
                    options.app_package = app_package
                    if app_activity:
                        options.app_activity = app_activity
                    options.no_reset = True
                    options.full_reset = False
                    # Force app to launch
                    options.auto_launch = True
                    # Skip settings app requirement
                    options.skip_server_installation = False
                    options.skip_logcat_capture = True
                else:
                    # No app specified - just connect to device
                    options.no_reset = True
                    options.full_reset = False
                    options.skip_logcat_capture = True
                    # Skip settings app requirement
                    options.skip_server_installation = True
                
                # Connect to Appium server
                appium_base_url = os.getenv('APPIUM_SERVER_URL', 'http://localhost:4723').strip().rstrip('/')
                candidate_urls = [appium_base_url]
                if not appium_base_url.endswith('/wd/hub'):
                    candidate_urls.append(appium_base_url + '/wd/hub')

                last_error = None
                for candidate_url in candidate_urls:
                    try:
                        self.driver = webdriver.Remote(candidate_url, options=options)
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc

                if self.driver is None:
                    raise last_error or Exception('Unable to create Appium session')
                
                return {
                    "success": True,
                    "device": device_name,
                    "platform": platform,
                    "status": "connected",
                    "message": f"Connected to {device_name}"
                }
            else:
                return {
                    "success": False,
                    "error": "iOS not yet implemented",
                    "message": "Currently only Android is supported"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to connect: {str(e)}",
                "workaround": [
                    "0. If Appium runs on a custom URL, set APPIUM_SERVER_URL in .env",
                    "1. Manually open your app on the emulator",
                    "2. Navigate to the screen you want to explore",
                    "3. Call explore-ui again - it will explore the current screen",
                    "4. Make sure device is connected: adb devices"
                ]
            }
    
    def explore_current_screen(self, screen_name: str = "CurrentScreen") -> Dict:
        """
        Extract UI elements from current screen using Appium
        """
        if not self.driver:
            return {
                "success": False,
                "error": "Not connected to emulator",
                "message": "Call connect_to_emulator() first"
            }
        
        try:
            # Check if session is still valid
            try:
                self.driver.current_activity
            except Exception as session_error:
                # Session expired, need to reconnect
                return {
                    "success": False,
                    "error": "Session expired",
                    "message": "Appium session expired. Please try again.",
                    "session_error": str(session_error)
                }
            
            # Get page source for debugging
            page_source = self.driver.page_source
            
            # Find all elements
            elements = self.driver.find_elements(by="xpath", value="//*")
            
            ui_elements = []
            for elem in elements:
                try:
                    # Extract element attributes
                    resource_id = elem.get_attribute("resource-id")
                    class_name = elem.get_attribute("class") or elem.get_attribute("className")
                    text = elem.text
                    content_desc = elem.get_attribute("content-desc")
                    clickable = elem.get_attribute("clickable") == "true"
                    enabled = elem.get_attribute("enabled") == "true"
                    bounds = elem.get_attribute("bounds")
                    
                    # Clean up null/empty values
                    resource_id = resource_id if resource_id and resource_id != "null" else None
                    class_name = class_name if class_name and class_name != "null" else None
                    text = text if text and text.strip() and text != "null" else None
                    content_desc = content_desc if content_desc and content_desc != "null" else None
                    bounds = bounds if bounds and bounds != "null" else None
                    
                    # Skip elements with no useful identifiers
                    if not resource_id and not text and not content_desc:
                        continue
                    
                    # Skip generic container elements without identifiers
                    if not resource_id and not text and not content_desc and not clickable:
                        continue
                    
                    # Generate XPath
                    xpath = self._generate_xpath(resource_id, class_name, text, content_desc)
                    
                    # Extract simple ID from resource-id
                    simple_id = resource_id.split("/")[-1] if resource_id and "/" in resource_id else resource_id
                    
                    ui_elements.append({
                        "id": simple_id or text or content_desc or "unknown",
                        "type": class_name.split(".")[-1] if class_name and "." in class_name else (class_name or "View"),
                        "text": text,
                        "resource_id": resource_id,
                        "xpath": xpath,
                        "accessibility_id": content_desc,
                        "bounds": bounds,
                        "clickable": clickable,
                        "enabled": enabled
                    })
                    
                except Exception as e:
                    # Skip elements that can't be processed
                    continue
            
            return {
                "success": True,
                "screen": screen_name,
                "platform": "android",
                "timestamp": datetime.now().isoformat(),
                "elements_count": len(ui_elements),
                "elements": ui_elements
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to explore screen: {str(e)}"
            }
    
    def _generate_xpath(self, resource_id: str, class_name: str, text: str, content_desc: str) -> str:
        """Generate XPath locator for element"""
        if resource_id:
            return f"//*[@resource-id='{resource_id}']"
        elif text:
            return f"//*[@text='{text}']"
        elif content_desc:
            return f"//*[@content-desc='{content_desc}']"
        elif class_name:
            return f"//{class_name}"
        else:
            return "//*"
    
    def explore_screen(self, screen_name: str, platform: str = "android") -> Dict:
        """
        Explore a screen and extract UI elements
        Uses real Appium connection if available, otherwise returns error
        """
        if self.driver:
            # Use real Appium connection
            return self.explore_current_screen(screen_name)
        else:
            return {
                "success": False,
                "error": "Not connected to emulator",
                "message": "Call connect_to_emulator() first to extract real UI elements",
                "screen": screen_name,
                "platform": platform
            }
    
    def explore_app(self, screens: List[str] = None, platform: str = "android", 
                    device_name: str = "emulator-5554",
                    app_package: str = None,
                    app_activity: str = None) -> Dict:
        """
        Explore multiple screens in the app
        
        Args:
            screens: List of screen names (optional, will explore current screen if None)
            platform: 'android' or 'ios'
            device_name: Device identifier
            app_package: App package name (Android)
            app_activity: App activity (Android)
        """
        # Always disconnect old session and create fresh connection
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        # Connect to emulator with fresh session
        connection = self.connect_to_emulator(device_name, app_package, app_activity, platform)
        if not connection["success"]:
            return connection
        
        all_elements = []
        screen_data = {}
        
        if screens:
            # Explore specified screens (just explore current screen for each)
            for screen in screens:
                result = self.explore_current_screen(screen)
                if result.get("success"):
                    screen_data[screen] = result
                    all_elements.extend(result['elements'])
                else:
                    screen_data[screen] = result
        else:
            # Explore current screen only
            result = self.explore_current_screen("CurrentScreen")
            if result.get("success"):
                screen_data["CurrentScreen"] = result
                all_elements.extend(result['elements'])
            else:
                # Disconnect on failure
                self.disconnect()
                return result
        
        # Save to file
        if all_elements:
            self.save_ui_elements(all_elements, platform)
        
        # Keep session alive for potential follow-up requests
        # Don't disconnect here - let it be reused or timeout naturally
        
        return {
            "success": True,
            "platform": platform,
            "screens_explored": len(screen_data),
            "total_elements": len(all_elements),
            "screens": screen_data
        }
    
    def save_ui_elements(self, elements: List[Dict], platform: str):
        """Save UI elements to JSON file"""
        os.makedirs("data", exist_ok=True)
        
        output_file = f"data/ui_elements_{platform}.json"
        
        with open(output_file, 'w') as f:
            json.dump({
                "platform": platform,
                "timestamp": datetime.now().isoformat(),
                "elements": elements
            }, f, indent=2)
        
        print(f"✅ UI elements saved: {output_file}")
        return output_file
    
    def get_locator_strategies(self, element: Dict) -> Dict:
        """
        Get all possible locator strategies for an element
        """
        strategies = {}
        
        if element.get('resource_id'):
            strategies['id'] = element['resource_id']
        
        if element.get('xpath'):
            strategies['xpath'] = element['xpath']
        
        if element.get('accessibility_id'):
            strategies['accessibility_id'] = element['accessibility_id']
        
        if element.get('text'):
            strategies['text'] = element['text']
        
        return strategies
    
    def disconnect(self):
        """Disconnect from emulator"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                return {"success": True, "message": "Disconnected from emulator"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": True, "message": "Not connected"}

    def _parse_test_plan(self, test_plan_path: str) -> Dict:
        """
        Parse markdown test plan to extract test cases and steps
        Returns structured dict with test cases
        """
        if not os.path.exists(test_plan_path):
            return {
                "success": False,
                "error": f"Test plan not found: {test_plan_path}"
            }
        
        try:
            with open(test_plan_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            test_cases = []
            current_tc = None
            current_section = None
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
                    current_section = None
                
                # Match Priority
                elif line.startswith('**Priority**'):
                    if current_tc:
                        priority = line.split(':', 1)[1].strip().replace('**', '') if ':' in line else ''
                        current_tc['priority'] = priority
                
                # Match Preconditions
                elif line.startswith('**Preconditions**'):
                    current_section = 'preconditions'
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
                    current_section = 'steps'
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
                
                # Match Expected Results
                elif line.startswith('**Expected Results**'):
                    current_section = 'expected_results'
                    i += 1
                    while i < len(lines):
                        line = lines[i]
                        if line.startswith('**'):
                            i -= 1
                            break
                        if line.strip().startswith('- '):
                            current_tc['expected_results'].append(line.strip()[2:])
                        i += 1
                    continue
                
                i += 1
            
            # Add last test case
            if current_tc:
                test_cases.append(current_tc)
            
            return {
                "success": True,
                "test_cases": test_cases,
                "total": len(test_cases)
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse test plan: {str(e)}"
            }

    def execute_test_plan(self, test_plan_path: str, device_name: str = "127.0.0.1:6555",
                         app_package: str = None, app_activity: str = None,
                         workspace_path: str = None, progress_callback=None) -> Dict:
        """
        Execute test plan step-by-step, collecting ALL unique locators across all test cases
        Generates ONE locator file for the entire test plan with deduplication
        
        Args:
            progress_callback: Optional function(msg_type, message, data) for progress updates
        """
        
        def send_progress(msg_type: str, message: str, data: dict = None):
            """Send progress update if callback provided"""
            if progress_callback:
                progress_callback(msg_type, message, data)
            # Also print to console
            if msg_type == 'progress':
                print(message)
        
        # Parse test plan
        send_progress('progress', f"📋 Parsing test plan: {test_plan_path}")
        parse_result = self._parse_test_plan(test_plan_path)
        
        if not parse_result.get('success'):
            send_progress('error', f"❌ Failed to parse test plan: {parse_result.get('error')}")
            return {
                "success": False,
                "error": parse_result.get('error'),
                "message": "Failed to parse test plan"
            }
        
        test_cases = parse_result.get('test_cases', [])
        send_progress('success', f"✅ Found {len(test_cases)} test cases", {'total_test_cases': len(test_cases)})
        
        # Connect to device once
        send_progress('progress', f"📱 Connecting to device: {device_name}")
        connection = self.connect_to_emulator(device_name, app_package, app_activity)
        
        if not connection['success']:
            send_progress('error', f"❌ Failed to connect: {connection.get('error')}")
            return {
                'success': False,
                'error': connection.get('error'),
                'message': connection.get('message')
            }
        
        send_progress('success', f"✅ Connected to {device_name}")
        
        # Initialize SINGLE locator collection for entire test plan
        self.collected_locators = {}
        self.locator_ids = set()
        all_navigation_logs = []
        
        # Execute each test case and accumulate locators
        for tc_idx, test_case in enumerate(test_cases, 1):
            tc_id = test_case.get('id', f'TC{tc_idx}')
            tc_title = test_case.get('title', f'Test Case {tc_idx}')
            steps = test_case.get('steps', [])
            
            send_progress('test_case_start', 
                         f"📝 Executing {tc_id}: {tc_title} ({tc_idx}/{len(test_cases)})",
                         {
                             'test_case_id': tc_id,
                             'test_case_number': tc_idx,
                             'total_test_cases': len(test_cases),
                             'total_steps': len(steps),
                             'locators_so_far': len(self.collected_locators)
                         })
            
            # Execute each step
            for step_idx, step in enumerate(steps, 1):
                send_progress('step', f"   Step {step_idx}/{len(steps)}: {step[:50]}...", 
                            {'step_number': step_idx, 'total_steps': len(steps)})
                
                # Explore current screen and collect ALL elements
                screen_result = self.explore_current_screen(f"{tc_id}_Step{step_idx}")
                if not screen_result.get('success'):
                    send_progress('warning', f"   ⚠️  Could not explore screen")
                    continue
                
                current_elements = screen_result.get('elements', [])
                send_progress('elements_found', f"   Found {len(current_elements)} UI elements",
                            {'elements_count': len(current_elements)})
                
                # Add ALL unique elements from this screen to locators
                new_locators_count = 0
                for element in current_elements:
                    # Create unique ID for this element
                    element_id = element.get('resource_id') or element.get('text') or element.get('content_desc')
                    if element_id and element_id not in self.locator_ids:
                        self._add_locator(element, {
                            'test_case': tc_id,
                            'step': step_idx,
                            'action': 'available',
                            'description': step
                        })
                        new_locators_count += 1
                
                duplicates_skipped = len(current_elements) - new_locators_count
                send_progress('locators_update', 
                            f"   ✅ Added {new_locators_count} new locators (total: {len(self.collected_locators)})",
                            {
                                'new_locators': new_locators_count,
                                'duplicates_skipped': duplicates_skipped,
                                'total_locators': len(self.collected_locators)
                            })
                
                # Now determine and execute action for this step
                try:
                    action_plan = self._get_action_from_step(step, current_elements)
                    
                    if action_plan and action_plan.get('target_element'):
                        target_element = action_plan['target_element']
                        action = action_plan.get('action', 'click')
                        
                        print(f"   🎯 Action: {action} on {target_element.get('text') or target_element.get('resource_id')}")
                        
                        # Execute action
                        try:
                            if action == "click" and target_element.get('xpath'):
                                xpath = target_element['xpath']
                                elem = self.driver.find_element("xpath", xpath)
                                elem.click()
                                print(f"   ✅ Action executed")
                                time.sleep(1)
                        except Exception as e:
                            print(f"   ⚠️  Action failed: {str(e)}")
                    else:
                        print(f"   ⚠️  Could not determine action for step")
                
                except Exception as e:
                    print(f"   ⚠️  Error processing step: {str(e)}")
        
        # Save ALL collected locators to ONE file for the entire test plan
        send_progress('progress', f"💾 Saving all {len(self.collected_locators)} unique locators to file...")
        test_plan_name = os.path.basename(test_plan_path).replace('.md', '')
        locators_file = self._save_locators_to_workspace(
            workspace_path,
            f"TestPlan_{test_plan_name}"
        )
        
        # Disconnect
        self.disconnect()
        
        send_progress('complete', 
                     f"✅ Test Plan Execution Complete! Collected {len(self.collected_locators)} unique locators",
                     {
                         'test_cases_executed': len(test_cases),
                         'total_locators': len(self.collected_locators),
                         'locators_file': locators_file
                     })
        
        # Return format compatible with plugin expectations
        return {
            'success': True,
            'command': 'test plan execution',
            'steps_executed': len(test_cases),  # Plugin expects this key
            'locators_collected': len(self.collected_locators),  # Plugin expects this key
            'locators_file': locators_file,  # Plugin expects this key
            'test_plan_path': test_plan_path,
            'test_cases_executed': len(test_cases),
            'total_test_cases': len(test_cases)
        }

    def _get_action_from_step(self, step_text: str, ui_elements: List[Dict]) -> Optional[Dict]:
        """
        Use AI to determine action and target element from step text
        """
        try:
            if not self.use_ollama:
                # Fallback to keyword matching
                return self._get_action_by_keyword(step_text, ui_elements)
            
            # Try Ollama first
            if self.use_ollama:
                prompt = f"""
Analyze this test step and determine what action to perform and which UI element to interact with.

Step: {step_text}

Available UI Elements:
{json.dumps([{'resource_id': e.get('resource_id'), 'text': e.get('text'), 'type': e.get('type')} for e in ui_elements[:20]], indent=2)}

Respond in JSON format:
{{
  "action": "click|enter|scroll|swipe|back",
  "target_description": "brief description of target element",
  "confidence": 0.0-1.0
}}
"""
                response = requests.post(
                    f'{self.ollama_url}/api/generate' if self.ollama_url else 'http://localhost:11434/api/generate',
                    json={
                        'model': 'neural-chat',
                        'prompt': prompt,
                        'stream': False
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    response_text = result.get('response', '')
                    
                    # Parse JSON from response
                    try:
                        import re
                        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                        if json_match:
                            action_data = json.loads(json_match.group())
                            action = action_data.get('action', 'click')
                            target_desc = action_data.get('target_description', '')
                            
                            # Find matching element
                            target_element = self._find_element_for_action(target_desc, action, ui_elements)
                            if target_element:
                                return {
                                    'action': action,
                                    'target_element': target_element,
                                    'confidence': action_data.get('confidence', 0.5)
                                }
                    except:
                        pass
            
            # Fallback to keyword matching
            return self._get_action_by_keyword(step_text, ui_elements)
        
        except Exception as e:
            print(f"Error in _get_action_from_step: {str(e)}")
            return self._get_action_by_keyword(step_text, ui_elements)

    def _get_action_by_keyword(self, step_text: str, ui_elements: List[Dict]) -> Optional[Dict]:
        """
        Simple keyword-based action determination
        """
        step_lower = step_text.lower()
        
        # Determine action type
        action = 'click'
        if 'enter' in step_lower or 'type' in step_lower or 'input' in step_lower:
            action = 'enter'
        elif 'scroll' in step_lower:
            action = 'scroll'
        elif 'swipe' in step_lower:
            action = 'swipe'
        
        # Find target element
        for element in ui_elements:
            # Safely get text and resource_id (handle None values)
            text = element.get('text') or element.get('resource_id') or ''
            resource_id = element.get('resource_id') or ''
            element_text = (str(text) + ' ' + str(resource_id)).lower()
            
            # Simple matching
            words = step_lower.split()
            for word in words:
                if len(word) > 3 and word in element_text:
                    return {
                        'action': action,
                        'target_element': element,
                        'confidence': 0.6
                    }
        
        # Default: return first clickable element
        for element in ui_elements:
            if element.get('clickable'):
                return {
                    'action': action,
                    'target_element': element,
                    'confidence': 0.3
                }
        
        return None
    
    
    def navigate_based_on_intent_with_progress(self, user_command: str, device_name: str = "127.0.0.1:6555",
                                               app_package: str = None, app_activity: str = None,
                                               workspace_path: str = None, progress_callback=None) -> Dict:
        """
        Navigate with progress callbacks for real-time UI updates
        """
        # Same logic as navigate_based_on_intent but with progress updates
        if not self.use_ollama:
            if progress_callback:
                progress_callback('error', "❌ AI client not initialized")
            return {
                "success": False,
                "error": "AI client not initialized",
                "message": "Ollama is not available"
            }
        
        # Check if user is asking to execute test plan
        user_command_lower = user_command.lower()
        has_test_plan_keyword = any(keyword in user_command_lower for keyword in ['test plan', 'generated test', 'testplan', 'test case', 'test cases'])
        has_test_plan_file = '[TEST_PLAN:' in user_command
        
        if has_test_plan_keyword or has_test_plan_file:
            if progress_callback:
                progress_callback('intent', "🎯 Detected: Test Plan Execution Mode")
            
            # Try to extract test plan path from metadata first
            test_plan_path = None
            if has_test_plan_file:
                # Extract path from [TEST_PLAN: /path/to/file]
                import re
                match = re.search(r'\[TEST_PLAN:\s*([^\]]+)\]', user_command)
                if match:
                    test_plan_path = match.group(1).strip()
                    if progress_callback:
                        progress_callback('progress', f"📋 Found test plan: {os.path.basename(test_plan_path)}")
            
            # If no metadata, find latest test plan
            if not test_plan_path:
                if not workspace_path:
                    workspace_path = os.getcwd()
                
                test_plans_dir = os.path.join(workspace_path, 'test_plans')
                if not os.path.exists(test_plans_dir):
                    if progress_callback:
                        progress_callback('error', f"❌ Test plans directory not found: {test_plans_dir}")
                    return {
                        "success": False,
                        "error": "Test plans directory not found",
                        "message": f"No test plans directory at {test_plans_dir}"
                    }
                
                # Get latest test plan
                test_plans = sorted([f for f in os.listdir(test_plans_dir) if f.endswith('.md')])
                if not test_plans:
                    if progress_callback:
                        progress_callback('error', f"❌ No test plans found in {test_plans_dir}")
                    return {
                        "success": False,
                        "error": "No test plans found",
                        "message": f"No markdown test plans in {test_plans_dir}"
                    }
                
                test_plan_path = os.path.join(test_plans_dir, test_plans[-1])
                if progress_callback:
                    progress_callback('progress', f"📋 Using latest test plan: {os.path.basename(test_plan_path)}")
            
            # Execute test plan with progress
            return self.execute_test_plan(
                test_plan_path,
                device_name,
                app_package,
                app_activity,
                workspace_path,
                progress_callback
            )
        
        # For free-form navigation, use original method
        return self.navigate_based_on_intent(
            user_command, device_name, app_package, app_activity, workspace_path
        )
    
    def navigate_based_on_intent(self, user_command: str, device_name: str = "127.0.0.1:6555",
                                  app_package: str = None, app_activity: str = None,
                                  workspace_path: str = None) -> Dict:
        """
        Navigate through app based on user intent using AI
        Understands natural language commands like "explore pjp screen and do start call and place an order"
        Also detects test plan execution requests
        """
        
        if not self.use_ollama:
            return {
                "success": False,
                "error": "AI client not initialized",
                "message": "Ollama is not available"
            }
        
        # Check if user is asking to execute test plan
        user_command_lower = user_command.lower()
        has_test_plan_keyword = any(keyword in user_command_lower for keyword in ['test plan', 'generated test', 'testplan', 'test case', 'test cases'])
        has_test_plan_file = '[TEST_PLAN:' in user_command
        
        if has_test_plan_keyword or has_test_plan_file:
            print(f"\n🎯 Detected test plan execution request")
            
            # Try to extract test plan path from metadata first
            test_plan_path = None
            if has_test_plan_file:
                # Extract path from [TEST_PLAN: /path/to/file]
                import re
                match = re.search(r'\[TEST_PLAN:\s*([^\]]+)\]', user_command)
                if match:
                    test_plan_path = match.group(1).strip()
                    print(f"📋 Found test plan in metadata: {test_plan_path}")
            
            # If no metadata, find latest test plan
            if not test_plan_path:
                if not workspace_path:
                    workspace_path = os.getcwd()
                
                test_plans_dir = os.path.join(workspace_path, 'test_plans')
                if not os.path.exists(test_plans_dir):
                    return {
                        "success": False,
                        "error": "Test plans directory not found",
                        "message": f"No test plans directory at {test_plans_dir}"
                    }
                
                # Get latest test plan
                test_plans = sorted([f for f in os.listdir(test_plans_dir) if f.endswith('.md')])
                if not test_plans:
                    return {
                        "success": False,
                        "error": "No test plans found",
                        "message": f"No markdown test plans in {test_plans_dir}"
                    }
                
                test_plan_path = os.path.join(test_plans_dir, test_plans[-1])
                print(f"📋 Using latest test plan: {test_plan_path}")
            
            # Execute test plan
            return self.execute_test_plan(
                test_plan_path,
                device_name,
                app_package,
                app_activity,
                workspace_path
            )
        
        # Original navigation logic for free-form commands
        # Connect to device
        print(f"\n📱 Connecting to device: {device_name}")
        connection = self.connect_to_emulator(device_name, app_package, app_activity)
        
        if not connection['success']:
            # Device connection failed - return helpful message
            return {
                'success': False,
                'error': connection.get('error'),
                'message': connection.get('message'),
                'solutions': [
                    f"1. Ensure device/emulator is running at {device_name}",
                    "2. Check: adb devices",
                    "3. Verify Appium is running on port 4723",
                    "4. Check device address setting"
                ]
            }
        
        print(f"✅ Connected to {device_name}")
        
        # Initialize navigation
        self.collected_locators = {}
        self.locator_ids = set()
        self.navigation_log = []
        
        # Explore initial screen
        print(f"\n📸 Exploring initial screen...")
        initial_screen = self.explore_current_screen("InitialScreen")
        
        if not initial_screen.get('success'):
            self.disconnect()
            return {
                'success': False,
                'error': 'Failed to explore initial screen',
                'message': initial_screen.get('error')
            }
        
        ui_elements = initial_screen.get('elements', [])
        print(f"✅ Found {len(ui_elements)} UI elements on initial screen")
        
        # Get AI to generate navigation steps
        print(f"\n🧠 Analyzing your command: '{user_command}'")
        navigation_plan = self._generate_navigation_steps(user_command, ui_elements)
        
        if 'error' in navigation_plan:
            print(f"⚠️  Navigation plan error: {navigation_plan['error']}")
            self.disconnect()
            return {
                'success': False,
                'error': 'Failed to generate navigation plan',
                'message': navigation_plan['error']
            }
        
        print(f"✅ Navigation plan generated")
        print(f"   Flow: {navigation_plan.get('flow_summary', 'N/A')}")
        print(f"   Steps: {len(navigation_plan.get('steps', []))}")
        
        # Execute navigation steps
        step_count = 0
        for step in navigation_plan.get('steps', []):
            step_count += 1
            action = step.get('action', 'unknown')
            target = step.get('target', 'unknown')
            
            print(f"\n{'─'*70}")
            print(f"Step {step_count}: {action.upper()} - {target}")
            
            # Explore current screen
            screen_result = self.explore_current_screen(f"Step{step_count}")
            if not screen_result.get('success'):
                print(f"⚠️  Could not explore screen")
                continue
            
            current_elements = screen_result.get('elements', [])
            print(f"Found {len(current_elements)} UI elements")
            
            # Find and execute action
            target_element = self._find_element_for_action(target, action, current_elements)
            
            if target_element:
                print(f"✅ Found target element: {target_element.get('text') or target_element.get('id')}")
                
                # Collect locator
                self._add_locator(target_element, step)
                
                # Execute action
                try:
                    if action == "click" and target_element.get('xpath'):
                        xpath = target_element['xpath']
                        elem = self.driver.find_element("xpath", xpath)
                        elem.click()
                        print(f"✅ Clicked: {target_element.get('text')}")
                        time.sleep(1)
                    
                    elif action == "enter" and target_element.get('xpath'):
                        xpath = target_element['xpath']
                        elem = self.driver.find_element("xpath", xpath)
                        input_text = step.get('input', '')
                        elem.clear()
                        elem.send_keys(input_text)
                        print(f"✅ Entered text: {input_text}")
                        time.sleep(0.5)
                    
                    self.navigation_log.append({
                        'step': step_count,
                        'action': action,
                        'target': target,
                        'success': True
                    })
                    
                except Exception as e:
                    print(f"⚠️  Failed to execute action: {str(e)}")
                    self.navigation_log.append({
                        'step': step_count,
                        'action': action,
                        'target': target,
                        'success': False,
                        'error': str(e)
                    })
            else:
                print(f"⚠️  Could not find target element: {target}")
                self.navigation_log.append({
                    'step': step_count,
                    'action': action,
                    'target': target,
                    'success': False,
                    'error': 'Element not found'
                })
        
        # Save locators to workspace
        locators_file = self._save_locators_to_workspace(workspace_path, user_command)
        
        # Disconnect
        self.disconnect()
        
        print(f"\n{'='*70}")
        print(f"✅ Navigation Complete!")
        print(f"{'='*70}")
        print(f"Steps executed: {step_count}")
        print(f"Locators collected: {len(self.collected_locators)}")
        print(f"Locators file: {locators_file}")
        print(f"{'='*70}\n")
        
        return {
            'success': True,
            'command': user_command,
            'steps_executed': step_count,
            'locators_collected': len(self.collected_locators),
            'locators_file': locators_file,
            'navigation_log': self.navigation_log,
            'locators': self.collected_locators
        }
    
    def _generate_navigation_steps(self, user_command: str, ui_elements: List[Dict]) -> Dict:
        """Generate navigation steps using Ollama."""
        
        if not self.use_ollama:
            return {"error": "AI client not available"}
        
        # Format UI elements for prompt
        ui_summary = self._format_ui_elements_for_ai(ui_elements)
        
        prompt = f"""You are a mobile app automation expert. Analyze the user's command and generate navigation steps.

USER COMMAND: "{user_command}"

CURRENT SCREEN UI ELEMENTS:
{ui_summary}

Generate a step-by-step navigation plan. For each step, identify:
1. The action to perform (click, enter, verify, scroll, wait)
2. The target element to interact with
3. Any input to enter
4. Expected outcome

Return as JSON with this structure:
{{
    "flow_summary": "Brief description of what needs to happen",
    "steps": [
        {{
            "step": 1,
            "action": "click|enter|verify|scroll|wait",
            "target": "Description of element to interact with",
            "input": "Text to enter if action is enter",
            "expected": "What should happen after this action",
            "reason": "Why this action is needed"
        }}
    ],
    "expected_flow": "Description of the complete expected flow"
}}"""

        try:
            # Using Ollama via HTTP with timeout (local or cloud)
            try:
                response = requests.post(
                    f'{self.ollama_url}/api/generate',
                    json={
                        'model': 'neural-chat',
                        'prompt': prompt,
                        'stream': False
                    },
                    timeout=30  # Short timeout
                )
                if response.status_code == 200:
                    response_data = response.json()
                    response_text = response_data.get('response', '')
                else:
                    # Fallback to keyword matching
                    return self._generate_steps_by_keyword_matching(user_command, ui_elements)
            except (requests.Timeout, requests.ConnectionError):
                # Fallback to keyword matching
                return self._generate_steps_by_keyword_matching(user_command, ui_elements)
            
            # Extract JSON
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
                return plan
            else:
                return self._generate_steps_by_keyword_matching(user_command, ui_elements)
        
        except Exception as e:
            print(f"⚠️  Navigation planning error: {e}")
            return self._generate_steps_by_keyword_matching(user_command, ui_elements)
    
    def _generate_steps_by_keyword_matching(self, user_command: str, ui_elements: List[Dict]) -> Dict:
        """Fallback: Generate steps using keyword matching when AI is unavailable"""
        
        print("💡 Using intelligent keyword matching for navigation...")
        
        keywords = user_command.lower().split()
        steps = []
        step_num = 1
        
        # Common app actions
        actions_map = {
            'start': {'action': 'click', 'keywords': ['start', 'begin', 'initiate']},
            'call': {'action': 'click', 'keywords': ['call', 'dial', 'star']},  # Added 'star' typo
            'order': {'action': 'click', 'keywords': ['order', 'purchase', 'place']},
            'sale': {'action': 'click', 'keywords': ['sale', 'sell']},
            'explore': {'action': 'scroll', 'keywords': ['explore', 'browse']},
        }
        
        # Find matching actions
        matched_actions = []
        for keyword in keywords:
            for action_key, action_info in actions_map.items():
                if keyword in action_info['keywords']:
                    matched_actions.append(action_key)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_actions = []
        for action in matched_actions:
            if action not in seen:
                seen.add(action)
                unique_actions.append(action)
        
        # Generate steps for each action
        for action_key in unique_actions:
            action_info = actions_map[action_key]
            steps.append({
                'step': step_num,
                'action': action_info['action'],
                'target': f"{action_key} element",
                'expected': f"{action_key} action completed",
                'reason': f"User requested to {action_key}"
            })
            step_num += 1
        
        # If no specific actions found, just scroll/explore
        if not steps:
            steps.append({
                'step': 1,
                'action': 'scroll',
                'target': 'Scroll down',
                'expected': 'Screen scrolls',
                'reason': 'Explore the screen'
            })
        
        return {
            'flow_summary': f"User command: {user_command}",
            'steps': steps,
            'expected_flow': 'Smart keyword-based navigation'
        }
    
    def _find_element_for_action(self, target_desc: str, action: str, elements: List[Dict]) -> Optional[Dict]:
        """Find UI element that matches target description"""
        
        target_lower = target_desc.lower()
        keywords = target_lower.split()
        
        best_match = None
        best_score = 0
        
        for elem in elements:
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
            
            # Prefer clickable elements for click actions
            if action == "click" and elem.get('clickable'):
                score += 1
            
            if score > best_score:
                best_score = score
                best_match = elem
        
        return best_match if best_score > 0 else None
    
    def _add_locator(self, element: Dict, step_info: Dict):
        """Add locator to collection if not already present (deduplication across entire test plan)"""
        
        if not element:
            return False
        
        # Create unique ID for this element (resource_id is most reliable)
        locator_id = element.get('resource_id') or element.get('text') or element.get('accessibility_id')
        
        # Skip if no valid ID or already collected
        if not locator_id or locator_id in self.locator_ids:
            return False
        
        # Add to deduplication set
        self.locator_ids.add(locator_id)
        
        # Store comprehensive locator information
        self.collected_locators[locator_id] = {
            'resource_id': element.get('resource_id'),
            'xpath': element.get('xpath'),
            'accessibility_id': element.get('accessibility_id'),
            'text': element.get('text'),
            'content_desc': element.get('content_desc'),
            'type': element.get('type'),
            'clickable': element.get('clickable'),
            'enabled': element.get('enabled'),
            'focusable': element.get('focusable'),
            'bounds': element.get('bounds'),
            'test_case': step_info.get('test_case', 'N/A'),  # Which test case found this
            'step': step_info.get('step', 'N/A'),
            'action': step_info.get('action', 'available')
        }
        
        return True
    
    def _format_ui_elements_for_ai(self, elements: List[Dict]) -> str:
        """Format UI elements for AI prompt"""
        
        if not elements:
            return "No UI elements found"
        
        formatted = []
        for elem in elements[:30]:  # Limit to first 30
            elem_desc = f"- {elem.get('type', 'View')}"
            
            if elem.get('text'):
                elem_desc += f": '{elem['text']}'"
            elif elem.get('resource_id'):
                resource_name = elem['resource_id'].split('/')[-1]
                elem_desc += f": {resource_name}"
            
            if elem.get('clickable'):
                elem_desc += " [clickable]"
            
            formatted.append(elem_desc)
        
        if len(elements) > 30:
            formatted.append(f"... and {len(elements) - 30} more elements")
        
        return "\n".join(formatted)
    
    def _save_locators_to_workspace(self, workspace_path: str = None, user_command: str = "") -> str:
        """Save collected locators to workspace folder with comprehensive information"""
        
        if not workspace_path:
            workspace_path = os.getcwd()
        
        # Create locators directory in workspace
        locators_dir = os.path.join(workspace_path, "locators")
        os.makedirs(locators_dir, exist_ok=True)
        
        # Generate filename from command
        if user_command:
            # Clean command for filename
            filename_base = "".join(c if c.isalnum() else "_" for c in user_command[:50])
        else:
            filename_base = "explored_ui"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(locators_dir, f"{filename_base}_{timestamp}_locators.txt")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# UI Element Locators\n")
            f.write(f"# Source: {user_command}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total Unique Elements: {len(self.collected_locators)}\n")
            f.write(f"# Deduplication: Applied across all test cases\n")
            f.write("\n" + "="*80 + "\n\n")
            
            for idx, (locator_id, locator) in enumerate(self.collected_locators.items(), 1):
                f.write(f"{idx}. {locator_id}\n")
                f.write(f"   Element Type: {locator.get('type', 'Unknown')}\n")
                
                if locator.get('resource_id'):
                    f.write(f"   Resource ID: {locator['resource_id']}\n")
                
                if locator.get('xpath'):
                    f.write(f"   XPath: {locator['xpath']}\n")
                
                if locator.get('accessibility_id'):
                    f.write(f"   Accessibility ID: {locator['accessibility_id']}\n")
                
                if locator.get('content_desc'):
                    f.write(f"   Content Description: {locator['content_desc']}\n")
                
                if locator.get('text'):
                    f.write(f"   Text: {locator['text']}\n")
                
                if locator.get('bounds'):
                    f.write(f"   Bounds: {locator['bounds']}\n")
                
                f.write(f"   Clickable: {locator.get('clickable', False)}\n")
                f.write(f"   Enabled: {locator.get('enabled', False)}\n")
                f.write(f"   Focusable: {locator.get('focusable', False)}\n")
                f.write(f"   Found in Test Case: {locator.get('test_case', 'N/A')}\n")
                f.write(f"   Step: {locator.get('step', 'N/A')}\n")
                f.write(f"   Usage: {locator.get('action', 'available')}\n")
                f.write("\n" + "-"*80 + "\n\n")
        
        print(f"✅ Locators saved to: {output_file}")
        return output_file
    
    def take_screenshot(self, filename: str = None) -> Dict:
        """Take screenshot of current screen"""
        if not self.driver:
            return {"success": False, "error": "Not connected to emulator"}
        
        try:
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            os.makedirs("screenshots", exist_ok=True)
            filepath = os.path.join("screenshots", filename)
            
            self.driver.save_screenshot(filepath)
            
            return {
                "success": True,
                "filepath": filepath,
                "message": f"Screenshot saved: {filepath}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def demo_ui_explorer():
    """Demo the UI Explorer agent with real Appium connection"""
    
    print("📱 UI Explorer Agent - Real Appium Connection")
    print("=" * 60)
    
    agent = UIExplorerAgent()
    
    # Check Appium availability
    if not agent.appium_available:
        print("\n Appium Python client not installed")
        print("   Install with: pip install Appium-Python-Client")
        print("\n   Then:")
        print("   1. Start Appium server: appium")
        print("   2. Start emulator (Genymotion or Android Studio)")
        print("   3. Connect device: adb devices")
        print("   4. Run this script again")
        return
    
    print("\n✅ Appium Python client available")
    
    # Connect to emulator
    print("\n1. Connecting to emulator...")
    print("   Make sure:")
    print("   - Appium server is running (http://localhost:4723)")
    print("   - Emulator is running (adb devices)")
    
    connection = agent.connect_to_emulator(
        device_name="emulator-5554",  # Change to your device
        # app_package="com.bizom",    # Uncomment if you want to launch specific app
        # app_activity=".MainActivity"
    )
    
    if not connection["success"]:
        print(f"\n Connection failed: {connection.get('error')}")
        print("\nTroubleshooting:")
        for tip in connection.get('troubleshooting', []):
            print(f"   {tip}")
        return
    
    print(f"    {connection['message']}")
    
    # Explore current screen
    print("\n2. Exploring current screen...")
    result = agent.explore_current_screen("CurrentScreen")
    
    if not result.get("success"):
        print(f"    Failed: {result.get('error')}")
        agent.disconnect()
        return
    
    print(f"    Found {result['elements_count']} UI elements")
    
    # Show sample elements
    print("\n3. Sample UI elements:")
    for element in result['elements'][:5]:  # Show first 5
        print(f"\n   {element['type']}: {element['text'] or element['id']}")
        print(f"      ID: {element['resource_id']}")
        print(f"      XPath: {element['xpath']}")
    
    if result['elements_count'] > 5:
        print(f"\n   ... and {result['elements_count'] - 5} more elements")
    
    # Save elements
    print("\n4. Saving UI elements...")
    agent.save_ui_elements(result['elements'], "android")
    
    # Take screenshot
    print("\n5. Taking screenshot...")
    screenshot = agent.take_screenshot()
    if screenshot["success"]:
        print(f"    {screenshot['message']}")
    
    # Disconnect
    print("\n6. Disconnecting...")
    agent.disconnect()
    print("   ✅ Disconnected")
    
    print("\n" + "=" * 60)
    print("UI Explorer Demo Complete!")
    print(f"\nExtracted {result['elements_count']} real UI elements from emulator")
    print("Check: data/ui_elements_android.json")


if __name__ == "__main__":
    demo_ui_explorer()
