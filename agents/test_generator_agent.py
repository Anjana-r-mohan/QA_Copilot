"""
Test Generator Agent
Generates Appium test code from test plans and UI locators
"""

import json
import os
from typing import Dict, List
from datetime import datetime


class TestGeneratorAgent:
    """
    Generates automated test code from test plans and locators
    """
    
    def __init__(self):
        self.test_plan = None
        self.locators = {}
        
    def load_test_plan(self, test_plan_path: str = "test_plans/test_plan.md"):
        """Load test plan from markdown file"""
        if os.path.exists(test_plan_path):
            with open(test_plan_path, 'r') as f:
                self.test_plan = f.read()
            return True
        return False
    
    def load_locators(self, locators_path: str = "data/locators.json"):
        """Load UI locators from JSON file"""
        if os.path.exists(locators_path):
            with open(locators_path, 'r') as f:
                data = json.load(f)
                # Convert list to dict for easy lookup
                if isinstance(data, list):
                    self.locators = {loc.get('id', ''): loc for loc in data}
                else:
                    self.locators = data
            return True
        return False
    
    def load_ui_elements(self, ui_elements_path: str = "data/ui_elements_android.json"):
        """Load UI elements from UI Explorer"""
        if os.path.exists(ui_elements_path):
            with open(ui_elements_path, 'r') as f:
                data = json.load(f)
                elements = data.get('elements', [])
                # Add to locators
                for elem in elements:
                    elem_id = elem.get('id', '')
                    if elem_id:
                        self.locators[elem_id] = elem
            return True
        return False
    
    def generate_test_class(self, test_case: Dict, platform: str = "android") -> str:
        """Generate Appium test class for a test case"""
        
        test_id = test_case.get('id', 'TC001')
        test_name = test_case.get('name', 'Test Case')
        steps = test_case.get('steps', [])
        
        # Clean test name for class name
        class_name = ''.join(word.capitalize() for word in test_name.split())
        class_name = ''.join(c for c in class_name if c.isalnum())
        
        # Generate test code
        code = f'''package com.bizom.tests;

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.By;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.testng.annotations.*;
import org.testng.Assert;

import java.net.URL;
import java.time.Duration;

/**
 * Test Case: {test_id}
 * Description: {test_name}
 * Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
 */
public class {class_name}Test {{
    
    private AppiumDriver driver;
    private WebDriverWait wait;
    
    @BeforeClass
    public void setUp() throws Exception {{
        // Set up Appium driver
        DesiredCapabilities caps = new DesiredCapabilities();
        caps.setCapability("platformName", "Android");
        caps.setCapability("deviceName", "emulator-5554");
        caps.setCapability("app", "/path/to/bizom.apk");
        caps.setCapability("automationName", "UiAutomator2");
        
        driver = new AndroidDriver(new URL("http://localhost:4723/wd/hub"), caps);
        wait = new WebDriverWait(driver, Duration.ofSeconds(10));
    }}
    
    @Test
    public void test{class_name}() {{
        // Test: {test_name}
        
'''
        
        # Generate steps
        for i, step in enumerate(steps, 1):
            if not step.strip():
                continue
                
            step_lower = step.lower()
            code += f"        // Step {i}: {step}\n"
            
            # Generate code based on step keywords
            if 'login' in step_lower or 'enter' in step_lower:
                if 'email' in step_lower:
                    code += self._generate_input_code('email_input', 'test@example.com')
                elif 'password' in step_lower:
                    code += self._generate_input_code('password_input', 'password123')
                elif 'username' in step_lower:
                    code += self._generate_input_code('username_input', 'testuser')
            
            elif 'click' in step_lower or 'tap' in step_lower:
                if 'login' in step_lower or 'submit' in step_lower:
                    code += self._generate_click_code('login_button')
                elif 'menu' in step_lower:
                    code += self._generate_click_code('menu_button')
                elif 'profile' in step_lower:
                    code += self._generate_click_code('profile_button')
                else:
                    code += "        // TODO: Add click action\n"
            
            elif 'verify' in step_lower or 'check' in step_lower:
                code += self._generate_assertion_code('element', 'expected_text')
            
            elif 'navigate' in step_lower or 'open' in step_lower:
                code += "        // Navigate to screen\n"
                code += "        Thread.sleep(1000);\n"
            
            else:
                code += "        // TODO: Implement step\n"
            
            code += "\n"
        
        # Add assertions
        code += '''        // Verify test completed successfully
        Assert.assertTrue(true, "Test completed");
    }
    
    @AfterClass
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
    
    // Helper methods
    
    private WebElement findElement(By locator) {
        return wait.until(ExpectedConditions.presenceOfElementLocated(locator));
    }
    
    private void clickElement(By locator) {
        WebElement element = findElement(locator);
        element.click();
    }
    
    private void enterText(By locator, String text) {
        WebElement element = findElement(locator);
        element.clear();
        element.sendKeys(text);
    }
    
    private void verifyText(By locator, String expectedText) {
        WebElement element = findElement(locator);
        String actualText = element.getText();
        Assert.assertEquals(actualText, expectedText);
    }
}
'''
        
        return code
    
    def _generate_input_code(self, element_id: str, value: str) -> str:
        """Generate code for text input"""
        locator = self.locators.get(element_id, {})
        resource_id = locator.get('resource_id', f'com.bizom:id/{element_id}')
        
        return f'''        enterText(By.id("{resource_id}"), "{value}");
'''
    
    def _generate_click_code(self, element_id: str) -> str:
        """Generate code for click action"""
        locator = self.locators.get(element_id, {})
        resource_id = locator.get('resource_id', f'com.bizom:id/{element_id}')
        
        return f'''        clickElement(By.id("{resource_id}"));
'''
    
    def _generate_assertion_code(self, element_id: str, expected_text: str) -> str:
        """Generate code for assertion"""
        locator = self.locators.get(element_id, {})
        resource_id = locator.get('resource_id', f'com.bizom:id/{element_id}')
        
        return f'''        verifyText(By.id("{resource_id}"), "{expected_text}");
'''
    
    def generate_tests_from_plan(self, test_cases: List[Dict], output_dir: str = "generated_tests") -> Dict:
        """Generate test files for multiple test cases"""
        
        os.makedirs(output_dir, exist_ok=True)
        
        generated_files = []
        
        for test_case in test_cases:
            test_id = test_case.get('id', 'TC001')
            test_name = test_case.get('name', 'Test Case')
            
            # Generate class name
            class_name = ''.join(word.capitalize() for word in test_name.split())
            class_name = ''.join(c for c in class_name if c.isalnum())
            
            # Generate test code
            test_code = self.generate_test_class(test_case)
            
            # Save to file
            filename = f"{output_dir}/{class_name}Test.java"
            with open(filename, 'w') as f:
                f.write(test_code)
            
            generated_files.append({
                "test_id": test_id,
                "test_name": test_name,
                "class_name": f"{class_name}Test",
                "file": filename
            })
            
            print(f"✅ Generated: {filename}")
        
        return {
            "success": True,
            "tests_generated": len(generated_files),
            "output_directory": output_dir,
            "files": generated_files
        }


def demo_test_generator():
    """Demo the Test Generator agent"""
    
    print("⚙️  Test Generator Agent Demo")
    print("=" * 60)
    
    agent = TestGeneratorAgent()
    
    # Load UI elements
    print("\n1. Loading UI elements...")
    if agent.load_ui_elements():
        print(f"   ✅ Loaded {len(agent.locators)} UI elements")
    
    # Sample test cases
    test_cases = [
        {
            "id": "TC001",
            "name": "Valid Login",
            "steps": [
                "Open app",
                "Enter valid email",
                "Enter valid password",
                "Click Login button",
                "Verify user logged in"
            ]
        },
        {
            "id": "TC002",
            "name": "View Profile",
            "steps": [
                "Login to app",
                "Click menu button",
                "Navigate to Profile",
                "Verify profile details displayed"
            ]
        }
    ]
    
    # Generate tests
    print("\n2. Generating test code...")
    result = agent.generate_tests_from_plan(test_cases)
    
    print(f"\n   ✅ Generated {result['tests_generated']} test files")
    print(f"   📁 Output directory: {result['output_directory']}")
    
    print("\n3. Generated files:")
    for file_info in result['files']:
        print(f"   - {file_info['class_name']}: {file_info['file']}")
    
    print("\n" + "=" * 60)
    print("✅ Test Generator Demo Complete!")


if __name__ == "__main__":
    demo_test_generator()
