"""
AI Code Generator Agent
Truly intelligent test code generation based on user instructions
Uses AI to understand requirements and generate appropriate test code
"""

import os
import json
import re
import requests
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class AICodeGeneratorAgent:
    """
    AI-powered test code generator
    Generates test code based on natural language instructions
    Adapts to any framework: Playwright, Selenium, Appium, etc.
    """
    
    def __init__(self):
        self.use_groq = False
        self.use_ollama = False
        self.ollama_url = None
        
        # Try Ollama first (local, free)
        print("🤖 Initializing AI Code Generator...")
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            if response.status_code == 200:
                self.use_ollama = True
                self.ollama_url = 'http://localhost:11434'
                print("✅ Using Ollama (Local AI)")
                return
        except:
            pass
        
        print("⚠️  No AI backend available")
    
    def generate_test_code(self, user_instruction: str, test_plan_path: str = None,
                          test_plan_content: str = None,
                          locators_file: str = None, workspace_path: str = None,
                          progress_callback=None) -> Dict:
        """
        Generate test code based on user's natural language instruction
        
        Args:
            user_instruction: Natural language instruction from user
            test_plan_path: Optional path to test plan file
            locators_file: Optional path to locators file
            workspace_path: Workspace for saving generated code
            progress_callback: Optional callback for progress updates
        
        Returns:
            Dict with generated code and metadata
        """
        
        def send_progress(msg_type: str, message: str, data: dict = None):
            if progress_callback:
                progress_callback(msg_type, message, data)
            print(message)
        
        send_progress('understanding', f"🎯 Understanding your request: {user_instruction}")
        
        # Load test plan if provided
        loaded_test_plan_content = test_plan_content
        if test_plan_path and os.path.exists(test_plan_path):
            send_progress('progress', f"📋 Reading test plan...")
            with open(test_plan_path, 'r', encoding='utf-8') as f:
                loaded_test_plan_content = f.read()
            send_progress('success', f"✅ Test plan loaded ({len(loaded_test_plan_content)} chars)")
        elif loaded_test_plan_content:
            send_progress('success', f"✅ Context plan loaded ({len(loaded_test_plan_content)} chars)")
        
        # Load locators if provided
        locators_content = None
        if locators_file and os.path.exists(locators_file):
            send_progress('progress', f"🔍 Reading locators...")
            with open(locators_file, 'r', encoding='utf-8') as f:
                locators_content = f.read()
            send_progress('success', f"✅ Locators loaded")
        
        # Analyze user instruction to determine framework and structure
        send_progress('progress', f"🧠 Analyzing your requirements...")
        analysis = self._analyze_instruction(user_instruction)
        
        send_progress('intent', f"📊 Detected: {analysis['framework']} with {analysis['language']}")
        send_progress('intent', f"📦 Structure: {analysis['structure']}")
        
        # Generate code using AI
        send_progress('progress', f"✨ Generating test code...")
        
        generated_code = self._generate_with_ai(
            user_instruction=user_instruction,
            test_plan=loaded_test_plan_content,
            locators=locators_content,
            analysis=analysis,
            progress_callback=send_progress
        )
        
        # Save generated code
        if workspace_path and generated_code:
            send_progress('progress', f"💾 Saving generated code...")
            saved_files = self._save_generated_code(
                generated_code,
                workspace_path,
                analysis
            )
            send_progress('success', f"✅ Saved {len(saved_files)} file(s)")
        else:
            saved_files = []
        
        send_progress('complete', f"🎉 Test code generation complete!", {
            'framework': analysis['framework'],
            'language': analysis['language'],
            'files_generated': len(saved_files)
        })
        
        return {
            'success': True,
            'framework': analysis['framework'],
            'language': analysis['language'],
            'structure': analysis['structure'],
            'generated_code': generated_code,
            'saved_files': saved_files
        }
    
    def _analyze_instruction(self, instruction: str) -> Dict:
        """
        Analyze user instruction to determine framework, language, and structure
        """
        instruction_lower = instruction.lower()
        
        # Detect framework
        framework = 'Appium'  # Default
        if 'playwright' in instruction_lower:
            framework = 'Playwright'
        elif 'selenium' in instruction_lower:
            framework = 'Selenium'
        elif 'cypress' in instruction_lower:
            framework = 'Cypress'
        elif 'testng' in instruction_lower:
            framework = 'TestNG'
        elif 'junit' in instruction_lower:
            framework = 'JUnit'
        elif 'pytest' in instruction_lower:
            framework = 'Pytest'
        
        # Detect language
        language = 'Java'  # Default
        if 'python' in instruction_lower:
            language = 'Python'
        elif 'typescript' in instruction_lower or re.search(r'\bts\b', instruction_lower):
            language = 'TypeScript'
        elif 'javascript' in instruction_lower or re.search(r'\bjs\b', instruction_lower):
            language = 'JavaScript'
        elif 'kotlin' in instruction_lower:
            language = 'Kotlin'
        
        # Detect structure
        structure = 'Simple'
        if 'maven' in instruction_lower or 'pom' in instruction_lower:
            structure = 'Maven'
        elif 'gradle' in instruction_lower:
            structure = 'Gradle'
        elif 'npm' in instruction_lower or 'package.json' in instruction_lower:
            structure = 'NPM'
        elif 'bdd' in instruction_lower or 'cucumber' in instruction_lower:
            structure = 'BDD-Cucumber'
        elif 'page object' in instruction_lower or 'pom pattern' in instruction_lower:
            structure = 'Page Object Model'
        
        return {
            'framework': framework,
            'language': language,
            'structure': structure,
            'instruction': instruction
        }
    
    def _generate_with_ai(self, user_instruction: str, test_plan: str = None,
                         locators: str = None, analysis: Dict = None,
                         progress_callback=None) -> Dict:
        """
        Use AI to generate test code based on all inputs
        """

        if (
            analysis
            and analysis.get('framework') == 'Appium'
            and analysis.get('language') == 'Java'
            and analysis.get('structure') in {'Maven', 'Maven POM', 'Simple'}
        ):
            return self._generate_appium_java_maven(test_plan, locators, analysis)
        
        # Build comprehensive prompt
        prompt = self._build_generation_prompt(
            user_instruction, test_plan, locators, analysis
        )
        
        if progress_callback:
            progress_callback('progress', f"🤖 AI is generating code...")
        
        # Generate with AI
        if self.use_ollama:
            return self._generate_with_ollama(prompt, analysis, progress_callback)
        else:
            # Fallback to template-based generation
            return self._generate_with_template(analysis, test_plan, locators)
    
    def _build_generation_prompt(self, instruction: str, test_plan: str,
                                 locators: str, analysis: Dict) -> str:
        """
        Build comprehensive prompt for AI code generation
        """
        
        prompt = f"""You are an expert test automation engineer. Generate production-ready test code based on the user's requirements.

USER'S INSTRUCTION:
{instruction}

DETECTED REQUIREMENTS:
- Framework: {analysis['framework']}
- Language: {analysis['language']}
- Structure: {analysis['structure']}

"""
        
        if test_plan:
            # Include first 2000 chars of test plan
            prompt += f"""
TEST PLAN:
{test_plan[:2000]}
{"..." if len(test_plan) > 2000 else ""}

"""
        
        if locators:
            # Include first 3000 chars of locators
            prompt += f"""
COLLECTED UI LOCATORS:
{locators[:3000]}
{"..." if len(locators) > 3000 else ""}

"""
        
        prompt += """
REQUIREMENTS:
1. Generate COMPLETE, RUNNABLE test code
2. Follow best practices for the specified framework
3. Include proper imports and dependencies
4. Add meaningful comments
5. Handle waits and synchronization properly
6. Include assertion statements
7. Follow the project structure requested
8. Make code maintainable and scalable

OUTPUT FORMAT:
Return a JSON object with this structure:
{
    "files": [
        {
            "path": "relative/path/to/file.ext",
            "content": "full file content here",
            "description": "brief description"
        }
    ],
    "dependencies": ["list", "of", "dependencies"],
    "setup_instructions": "How to run the tests",
    "notes": "Any important notes"
}

Generate comprehensive, production-ready code now.
"""
        
        return prompt
    
    def _generate_with_ollama(self, prompt: str, analysis: Dict,
                             progress_callback=None) -> Dict:
        """Generate code using Ollama"""
        
        try:
            response = requests.post(
                f'{self.ollama_url}/api/generate',
                json={
                    'model': 'codellama',  # Use CodeLlama for code generation
                    'prompt': prompt,
                    'stream': False
                },
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get('response', '')
                
                # Parse JSON response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    generated = json.loads(json_match.group())
                    return generated
            
            # Fallback
            return self._generate_with_template(analysis, None, None)
            
        except Exception as e:
            print(f"⚠️  Ollama generation failed: {e}")
            return self._generate_with_template(analysis, None, None)
    
    def _generate_with_template(self, analysis: Dict, test_plan: str,
                                locators: str) -> Dict:
        """
        Fallback: Generate code using templates
        """
        
        framework = analysis['framework']
        language = analysis['language']
        structure = analysis['structure']

        if framework == 'Appium' and language == 'Java' and structure in {'Maven', 'Maven POM', 'Simple'}:
            return self._generate_appium_java_maven(test_plan, locators, analysis)
        
        if framework == 'Playwright' and language == 'TypeScript':
            return self._generate_playwright_typescript()
        elif framework == 'Selenium' and language == 'Java':
            return self._generate_selenium_java()
        else:
            return self._generate_appium_java()
    
    def _generate_playwright_typescript(self) -> Dict:
        """Generate Playwright TypeScript template"""
        
        return {
            "files": [
                {
                    "path": "tests/login.spec.ts",
                    "content": """import { test, expect } from '@playwright/test';

test.describe('Login Tests', () => {
  test('should login successfully with valid credentials', async ({ page }) => {
    await page.goto('https://example.com/login');
    
    await page.fill('[data-testid="email"]', 'user@example.com');
    await page.fill('[data-testid="password"]', 'password123');
    await page.click('[data-testid="login-button"]');
    
    await expect(page).toHaveURL('/dashboard');
    await expect(page.locator('[data-testid="welcome-message"]')).toBeVisible();
  });
});
""",
                    "description": "Login test suite"
                },
                {
                    "path": "playwright.config.ts",
                    "content": """import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'https://example.com',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
""",
                    "description": "Playwright configuration"
                }
            ],
            "dependencies": ["@playwright/test"],
            "setup_instructions": "Run: npm install && npx playwright test",
            "notes": "Generated Playwright TypeScript project"
        }
    
    def _generate_selenium_java(self) -> Dict:
        """Generate Selenium Java template"""
        
        return {
            "files": [
                {
                    "path": "src/test/java/tests/LoginTest.java",
                    "content": """package tests;

import org.testng.annotations.Test;
import org.testng.Assert;
import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;

public class LoginTest {
    
    @Test
    public void testLogin() {
        WebDriver driver = new ChromeDriver();
        
        try {
            driver.get("https://example.com/login");
            
            driver.findElement(By.id("email")).sendKeys("user@example.com");
            driver.findElement(By.id("password")).sendKeys("password123");
            driver.findElement(By.id("loginButton")).click();
            
            String currentUrl = driver.getCurrentUrl();
            Assert.assertTrue(currentUrl.contains("dashboard"), "Login failed");
            
        } finally {
            driver.quit();
        }
    }
}
""",
                    "description": "Login test class"
                },
                {
                    "path": "pom.xml",
                    "content": """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    
    <groupId>com.example</groupId>
    <artifactId>selenium-tests</artifactId>
    <version>1.0.0</version>
    
    <dependencies>
        <dependency>
            <groupId>org.seleniumhq.selenium</groupId>
            <artifactId>selenium-java</artifactId>
            <version>4.15.0</version>
        </dependency>
        <dependency>
            <groupId>org.testng</groupId>
            <artifactId>testng</artifactId>
            <version>7.8.0</version>
        </dependency>
    </dependencies>
</project>
""",
                    "description": "Maven POM file"
                }
            ],
            "dependencies": ["selenium-java", "testng"],
            "setup_instructions": "Run: mvn clean test",
            "notes": "Generated Selenium Java Maven project"
        }
    
    def _generate_appium_java(self) -> Dict:
        """Generate Appium Java template"""
        
        return {
            "files": [
                {
                    "path": "src/test/java/tests/MobileTest.java",
                    "content": """package tests;

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.remote.DesiredCapabilities;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

import java.net.URL;

public class MobileTest {
    private AppiumDriver driver;
    
    @BeforeMethod
    public void setup() throws Exception {
        DesiredCapabilities caps = new DesiredCapabilities();
        caps.setCapability("platformName", "Android");
        caps.setCapability("deviceName", "emulator-5554");
        caps.setCapability("app", "/path/to/app.apk");
        
        driver = new AndroidDriver(new URL("http://localhost:4723"), caps);
    }
    
    @Test
    public void testAppLaunch() {
        // Test implementation
        System.out.println("App launched successfully");
    }
    
    @AfterMethod
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
}
""",
                    "description": "Mobile test class"
                }
            ],
            "dependencies": ["appium-java-client", "testng"],
            "setup_instructions": "Run: mvn clean test",
            "notes": "Generated Appium Java project"
        }

    def _generate_appium_java_maven(self, test_plan: str, locators: str, analysis: Dict) -> Dict:
        steps = self._extract_test_steps(test_plan or analysis.get('instruction', ''))
        parsed_locators = self._parse_locators(locators)
        locator_map = self._build_locator_map(parsed_locators)

        test_class = self._build_appium_java_test_class(steps, locator_map)
        pom_xml = self._build_appium_maven_pom()
        base_test = self._build_base_test_java()

        return {
            "files": [
                {
                    "path": "pom.xml",
                    "content": pom_xml,
                    "description": "Maven project file for Appium Java execution"
                },
                {
                    "path": "src/test/java/tests/BaseMobileTest.java",
                    "content": base_test,
                    "description": "Shared Appium setup and teardown"
                },
                {
                    "path": "src/test/java/tests/GeneratedMobileFlowTest.java",
                    "content": test_class,
                    "description": "Generated mobile test flow based on provided steps and collected locators"
                }
            ],
            "dependencies": ["appium-java-client", "selenium-java", "testng"],
            "setup_instructions": "mvn clean test",
            "notes": f"Generated from {len(steps)} planned step(s) and {len(parsed_locators)} locator record(s)."
        }

    def _extract_test_steps(self, text: str) -> List[str]:
        if not text:
            return []

        lowered = text.lower()
        if "**steps**" in lowered or "steps:" in lowered:
            section_steps = []
            in_steps_section = False
            for raw_line in text.splitlines():
                candidate = raw_line.strip()
                if not candidate:
                    continue
                marker = candidate.lower()
                if marker.startswith("**steps**") or marker.startswith("steps:"):
                    in_steps_section = True
                    continue
                if in_steps_section and (marker.startswith("**expected") or marker.startswith("expected") or marker.startswith("**db validation") or marker.startswith("db validation") or marker.startswith("**preconditions") or marker.startswith("preconditions")):
                    in_steps_section = False
                    continue
                if not in_steps_section:
                    continue
                if re.match(r'^(step\s*\d+[:.-]|\d+\.|[-*])\s+', candidate, re.IGNORECASE):
                    cleaned = re.sub(r'^(step\s*\d+[:.-]|\d+\.|[-*])\s+', '', candidate, flags=re.IGNORECASE).strip()
                    cleaned = self._normalize_step_text(cleaned)
                    if cleaned and self._is_actionable_step(cleaned):
                        section_steps.append(cleaned)
            if section_steps:
                return self._dedupe_steps(section_steps)[:40]

        if any(token in text for token in ["package ", "import ", "public class", "private ", "caps.setCapability("]):
            text = "\n".join(
                line for line in text.splitlines()
                if re.match(r'^(\d+\.|[-*]|step\s*\d+[:.-])\s+', line.strip(), re.IGNORECASE)
            )
            if not text.strip():
                return []

        steps = []
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if re.match(r'^(step\s*\d+[:.-]|\d+\.|[-*])\s+', candidate, re.IGNORECASE):
                cleaned = re.sub(r'^(step\s*\d+[:.-]|\d+\.|[-*])\s+', '', candidate, flags=re.IGNORECASE).strip()
                cleaned = self._normalize_step_text(cleaned)
                if cleaned and self._is_actionable_step(cleaned):
                    steps.append(cleaned)
        if steps:
            return self._dedupe_steps(steps)

        sentence_parts = re.split(r'\bthen\b|,', text, flags=re.IGNORECASE)
        fallback_steps = [self._normalize_step_text(part.strip()) for part in sentence_parts if len(part.strip()) > 8 and self._is_actionable_step(part.strip())]
        return self._dedupe_steps(fallback_steps)[:8]

    def _dedupe_steps(self, steps: List[str]) -> List[str]:
        deduped = []
        seen = set()
        for step in steps:
            normalized = re.sub(r'\s+', ' ', step.strip().lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(step)
        return deduped

    def _normalize_step_text(self, step: str) -> str:
        normalized = re.sub(r'(?i)(enabled|disabled)(click|tap|open|select|enter)', r'\1 \2', step)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _is_actionable_step(self, step: str) -> bool:
        lower = step.lower()
        if '=' in lower and not any(k in lower for k in ['click', 'tap', 'open', 'select', 'enter', 'start', 'place', 'login', 'search', 'menu']):
            return False
        action_words = ['click', 'tap', 'open', 'select', 'enter', 'start', 'place', 'login', 'search', 'menu', 'hamburger', 'call', 'order']
        return any(word in lower for word in action_words)

    def _parse_locators(self, locators: str) -> List[Dict]:
        parsed = []
        if not locators:
            return parsed
        for line in locators.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    parsed.append(item)
            except Exception:
                continue
        return parsed

    def _build_locator_map(self, locators: List[Dict]) -> Dict[str, Dict]:
        locator_map = {}
        for locator in locators:
            tokens = [
                str(locator.get('text') or '').strip(),
                str(locator.get('resource_id') or '').strip(),
                str(locator.get('type') or '').strip(),
            ]
            for token in tokens:
                if not token:
                    continue
                for part in re.split(r'[^a-zA-Z0-9]+', token.lower()):
                    if len(part) > 2 and part not in locator_map:
                        locator_map[part] = locator
        return locator_map

    def _build_appium_java_test_class(self, steps: List[str], locator_map: Dict[str, Dict]) -> str:
        if not steps:
            steps = ["Launch the app", "Inspect visible UI and continue with the target flow"]

        body_lines = []
        for index, step in enumerate(steps, start=1):
            locator = self._find_locator_for_step(step, locator_map)
            escaped_step = step.replace('"', '\\"')
            body_lines.append(f'        // Step {index}: {escaped_step}')
            if locator:
                locator_expr = self._java_locator_expression(locator)
                body_lines.append(f'        waitForVisible({locator_expr});')
                if locator.get('clickable'):
                    body_lines.append(f'        driver.findElement({locator_expr}).click();')
                else:
                    body_lines.append(f'        System.out.println("Verified step {index}: {escaped_step}");')
            else:
                body_lines.append(f'        System.out.println("TODO Step {index}: {escaped_step}");')
            body_lines.append('')

        return f'''package tests;

import org.openqa.selenium.By;
import org.testng.annotations.Test;

public class GeneratedMobileFlowTest extends BaseMobileTest {{

    @Test
    public void executeGeneratedFlow() {{
{chr(10).join(body_lines).rstrip()}
    }}
}}
'''

    def _find_locator_for_step(self, step: str, locator_map: Dict[str, Dict]) -> Optional[Dict]:
        keywords = [token for token in re.split(r'[^a-zA-Z0-9]+', step.lower()) if len(token) > 2]
        synonym_map = {
            'hamburger': ['menu', 'icon'],
            'stripes': ['menu'],
            'three': ['menu'],
            'call': ['call', 'start'],
            'order': ['order', 'place'],
        }
        for keyword in keywords:
            if keyword in locator_map:
                return locator_map[keyword]
            for synonym in synonym_map.get(keyword, []):
                if synonym in locator_map:
                    return locator_map[synonym]
        return None

    def _java_locator_expression(self, locator: Dict) -> str:
        resource_id = locator.get('resource_id')
        text = locator.get('text')
        xpath = locator.get('xpath')
        accessibility_id = locator.get('accessibility_id')

        if resource_id:
            return f'By.id("{resource_id}")'
        if accessibility_id:
            return f'By.xpath("//*[@content-desc=\\"{accessibility_id}\\"]")'
        if text:
            return f'By.xpath("//*[@text=\\"{text}\\"]")'
        return f'By.xpath("{xpath or "//*"}")'

    def _build_base_test_java(self) -> str:
        return '''package tests;

import io.appium.java_client.AppiumDriver;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.By;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.remote.DesiredCapabilities;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;

import java.net.URL;
import java.time.Duration;

public class BaseMobileTest {
    protected AppiumDriver driver;
    protected WebDriverWait wait;

    @BeforeMethod
    public void setup() throws Exception {
        DesiredCapabilities caps = new DesiredCapabilities();
        caps.setCapability("platformName", "Android");
        caps.setCapability("deviceName", System.getProperty("deviceName", "127.0.0.1:6555"));
        caps.setCapability("automationName", "UiAutomator2");
        caps.setCapability("appPackage", System.getProperty("appPackage", "co.bizom.apps"));
        caps.setCapability("appActivity", System.getProperty("appActivity", ".android.MainActivity"));
        caps.setCapability("noReset", true);

        driver = new AndroidDriver(new URL(System.getProperty("appiumUrl", "http://localhost:4723")), caps);
        wait = new WebDriverWait(driver, Duration.ofSeconds(15));
    }

    protected WebElement waitForVisible(By by) {
        return wait.until(ExpectedConditions.visibilityOfElementLocated(by));
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
}
'''

    def _build_appium_maven_pom(self) -> str:
        return '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.bizom.generated</groupId>
    <artifactId>script-sherpa-mobile-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.appium</groupId>
            <artifactId>java-client</artifactId>
            <version>9.2.2</version>
        </dependency>
        <dependency>
            <groupId>org.seleniumhq.selenium</groupId>
            <artifactId>selenium-java</artifactId>
            <version>4.21.0</version>
        </dependency>
        <dependency>
            <groupId>org.testng</groupId>
            <artifactId>testng</artifactId>
            <version>7.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <suiteXmlFiles></suiteXmlFiles>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
'''
    
    def _save_generated_code(self, generated_code: Dict, workspace_path: str,
                            analysis: Dict) -> List[str]:
        """
        Save generated code files to workspace
        """
        
        saved_files = []

        # Reuse a stable project folder so code is incrementally updated.
        output_dir = os.path.join(workspace_path, "generated_tests")
        os.makedirs(output_dir, exist_ok=True)
        project_dir = os.path.join(output_dir, f"{analysis['framework']}_current")
        os.makedirs(project_dir, exist_ok=True)

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save each file
        for file_info in generated_code.get('files', []):
            file_path = os.path.join(project_dir, file_info['path'])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            content_to_write = file_info['content']
            file_name = os.path.basename(file_path)

            # Preserve existing scaffolding once created.
            if os.path.exists(file_path) and file_name in {"BaseMobileTest.java", "pom.xml"}:
                print(f"ℹ️ Reusing existing: {file_path}")
                saved_files.append(file_path)
                continue

            if os.path.exists(file_path) and file_name == "GeneratedMobileFlowTest.java":
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing = f.read()
                content_to_write = self._merge_generated_test(existing, file_info['content'], run_id)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content_to_write)
            
            saved_files.append(file_path)
            print(f"✅ Saved: {file_path}")
        
        # Save README with setup instructions
        readme_path = os.path.join(project_dir, "README.md")
        readme_content = f"""# Generated Test Project

**Framework**: {analysis['framework']}
**Language**: {analysis['language']}
**Structure**: {analysis['structure']}
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Dependencies

{chr(10).join(f'- {dep}' for dep in generated_code.get('dependencies', []))}

## Setup Instructions

```bash
{generated_code.get('setup_instructions', 'See framework documentation')}
```

## Notes

{generated_code.get('notes', 'No additional notes')}

## Files Generated

{chr(10).join(f'- {file["path"]} - {file["description"]}' for file in generated_code.get('files', []))}
"""
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        saved_files.append(readme_path)
        print(f"✅ Saved: {readme_path}")
        
        return saved_files

    def _merge_generated_test(self, existing_content: str, new_content: str, run_id: str) -> str:
        method_match = re.search(
            r"@Test\s+public void executeGeneratedFlow\(\) \{([\s\S]*?)\n\s*\}\n\s*\}",
            new_content,
        )
        if not method_match:
            return existing_content

        method_body = method_match.group(1).rstrip()
        method_name = f"executeGeneratedFlow_{run_id}"
        new_method = (
            "\n    @Test\n"
            f"    public void {method_name}() {{\n"
            f"{method_body}\n"
            "    }\n"
        )

        insert_at = existing_content.rfind("}")
        if insert_at == -1:
            return existing_content
        return existing_content[:insert_at] + new_method + "\n" + existing_content[insert_at:]


def demo():
    """Demo the AI Code Generator"""
    
    agent = AICodeGeneratorAgent()
    
    print("\n" + "="*70)
    print("🚀 AI Code Generator Agent Demo")
    print("="*70 + "\n")
    
    # Example 1: Playwright
    print("Example 1: Generate Playwright tests")
    result = agent.generate_test_code(
        user_instruction="Generate Playwright tests in TypeScript with proper structure",
        workspace_path="."
    )
    print(f"✅ Generated {len(result['saved_files'])} files")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    demo()
