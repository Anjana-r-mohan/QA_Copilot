"""
Appium Driver Manager
Manages Appium WebDriver connection and provides clean interface for tools
"""

import time
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
from appium import webdriver
from appium.options.android import UiAutomator2Options


class AppiumDriverManager:
    """
    Manages Appium driver connection and provides tool interface
    """
    
    def __init__(self):
        self.driver = None
        self.connected_device = None
    
    def connect(self, device_name: str, app_package: Optional[str] = None,
                app_activity: Optional[str] = None) -> Dict:
        """Connect to device"""
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

            base_url = os.getenv("APPIUM_SERVER_URL", "http://localhost:4723").strip().rstrip("/")
            candidate_urls = [base_url]
            if not base_url.endswith("/wd/hub"):
                candidate_urls.append(base_url + "/wd/hub")

            last_error = None
            for url in candidate_urls:
                try:
                    self.driver = webdriver.Remote(url, options=options)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc

            if self.driver is None:
                raise last_error or Exception("Unable to create Appium session")

            self.connected_device = device_name
            time.sleep(2)
            
            return {
                'success': True,
                'connected': True,
                'device_name': device_name
            }
        except Exception as e:
            return {
                'success': False,
                'connected': False,
                'error': str(e),
                'message': "Failed to connect to Appium. Check APPIUM_SERVER_URL or Appium server status."
            }
    
    def disconnect(self) -> Dict:
        """Disconnect from device"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                self.connected_device = None
                return {'success': True, 'disconnected': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        return {'success': True, 'message': 'Not connected'}
    
    def get_screen_state(self) -> Dict:
        """Get current screen state"""
        if not self.driver:
            raise Exception("Not connected to device")
        
        try:
            page_source = self.driver.page_source
            elements = self._parse_page_source(page_source)
            
            return {
                'page_source': page_source,
                'elements': elements,
                'element_count': len(elements)
            }
        except Exception as e:
            raise Exception(f"Failed to get screen state: {e}")
    
    def tap_element(self, locator_type: str, locator_value: str) -> Dict:
        """Tap an element"""
        if not self.driver:
            raise Exception("Not connected to device")
        
        try:
            # Map locator types
            by_map = {
                'id': 'id',
                'xpath': 'xpath',
                'text': 'xpath'
            }
            
            by = by_map.get(locator_type, 'xpath')
            
            # For text, construct xpath
            if locator_type == 'text':
                locator_value = f"//*[@text='{locator_value}']"
                by = 'xpath'
            
            element = self.driver.find_element(by, locator_value)
            element.click()
            time.sleep(1)
            
            return {
                'success': True,
                'tapped': True,
                'locator': f"{locator_type}={locator_value}"
            }
        except Exception as e:
            raise Exception(f"Failed to tap element: {e}")
    
    def input_text(self, locator_type: str, locator_value: str, text: str) -> Dict:
        """Input text into element"""
        if not self.driver:
            raise Exception("Not connected to device")
        
        try:
            by_map = {
                'id': 'id',
                'xpath': 'xpath',
                'text': 'xpath'
            }
            
            by = by_map.get(locator_type, 'xpath')
            
            if locator_type == 'text':
                locator_value = f"//*[@text='{locator_value}']"
                by = 'xpath'
            
            element = self.driver.find_element(by, locator_value)
            element.clear()
            element.send_keys(text)
            time.sleep(0.5)
            
            return {
                'success': True,
                'input_completed': True,
                'text': text
            }
        except Exception as e:
            raise Exception(f"Failed to input text: {e}")
    
    def scroll(self, direction: str = 'down') -> Dict:
        """Scroll the screen"""
        if not self.driver:
            raise Exception("Not connected to device")
        
        try:
            # Get screen size
            size = self.driver.get_window_size()
            width = size['width']
            height = size['height']
            
            # Calculate coordinates
            start_x = width // 2
            start_y = int(height * 0.7) if direction == 'down' else int(height * 0.3)
            end_y = int(height * 0.3) if direction == 'down' else int(height * 0.7)
            
            # Perform swipe
            self.driver.swipe(start_x, start_y, start_x, end_y, 500)
            time.sleep(1)
            
            return {
                'success': True,
                'scrolled': True,
                'direction': direction
            }
        except Exception as e:
            raise Exception(f"Failed to scroll: {e}")
    
    def _parse_page_source(self, page_source: str) -> List[Dict]:
        """Parse XML page source into element list"""
        elements = []
        
        try:
            root = ET.fromstring(page_source)
            
            for elem in root.iter():
                attribs = elem.attrib
                
                # Only include relevant elements
                if attribs.get('clickable') == 'true' or attribs.get('text') or attribs.get('content-desc'):
                    elements.append({
                        'class': attribs.get('class', ''),
                        'text': attribs.get('text', ''),
                        'resource-id': attribs.get('resource-id', ''),
                        'content-desc': attribs.get('content-desc', ''),
                        'clickable': attribs.get('clickable', 'false') == 'true',
                        'enabled': attribs.get('enabled', 'false') == 'true',
                        'bounds': attribs.get('bounds', '')
                    })
        except Exception as e:
            print(f"Failed to parse page source: {e}")
        
        return elements
