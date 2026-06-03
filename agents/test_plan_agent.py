"""
Test Plan Agent
Analyzes CSV file with manual test cases and creates structured test plan
"""

import csv
import os
from typing import List, Dict
from datetime import datetime


class TestPlanAgent:
    """
    Converts manual test cases from CSV into structured test plan
    """
    
    def __init__(self):
        self.test_cases = []
        self.features = {}
        
    def parse_csv(self, csv_path: str) -> List[Dict]:
        """
        Parse CSV file with test cases
        
        Supports multiple CSV formats:
        - Standard: Test ID, Feature, Test Case Name, Steps, Expected Result, Priority, Platform
        - QA Touch: Case code, Module Name, Title, Steps, ExpectedResult, Priorities, Precondition
        """
        test_cases = []
        
        # Try different encodings
        encodings = ['utf-8-sig', 'utf-8', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    headers = reader.fieldnames
                    
                    for row in reader:
                        # Detect format and map fields
                        if 'Case code' in headers or 'Case Key' in headers:
                            # QA Touch format
                            test_id = row.get('Case code', '') or row.get('Case Key', '') or ''
                            feature = row.get('Module Name', '') or 'General'
                            name = row.get('Title', '') or ''
                            steps_text = row.get('Steps', '') or ''
                            expected = row.get('ExpectedResult', '') or ''
                            priority = row.get('Priorities', 'Medium') or 'Medium'
                            precondition = row.get('Precondition', '') or ''
                        else:
                            # Standard format
                            test_id = row.get('Test ID', '') or ''
                            feature = row.get('Feature', '') or 'General'
                            name = row.get('Test Case Name', '') or ''
                            steps_text = row.get('Steps', '') or ''
                            expected = row.get('Expected Result', '') or ''
                            priority = row.get('Priority', 'Medium') or 'Medium'
                            precondition = row.get('Precondition', '') or ''
                        
                        # Skip empty rows
                        if not test_id and not name:
                            continue
                        
                        # Map priority names
                        priority_map = {
                            'critical': 'High',
                            'high': 'High',
                            'major': 'High',
                            'medium': 'Medium',
                            'normal': 'Medium',
                            'minor': 'Low',
                            'low': 'Low',
                            'trivial': 'Low'
                        }
                        priority = priority_map.get(priority.lower(), priority)
                        
                        test_case = {
                            'id': test_id,
                            'feature': feature,
                            'name': name,
                            'steps': steps_text.split('\n') if steps_text else [],
                            'expected': expected,
                            'priority': priority,
                            'platform': row.get('Platform', 'Both') or 'Both',
                            'precondition': precondition
                        }
                        test_cases.append(test_case)
                
                break  # Success, exit loop
            except Exception as e:
                if encoding == encodings[-1]:
                    raise  # Re-raise if last encoding fails
                continue
        
        self.test_cases = test_cases
        return test_cases
    
    def group_by_feature(self) -> Dict:
        """Group test cases by feature"""
        features = {}
        
        for tc in self.test_cases:
            feature = tc['feature']
            if feature not in features:
                features[feature] = []
            features[feature].append(tc)
        
        self.features = features
        return features
    
    def analyze_dependencies(self) -> Dict:
        """Analyze test dependencies and prerequisites"""
        dependencies = {}
        
        for tc in self.test_cases:
            # Check if test requires login
            steps_text = ' '.join(tc['steps']).lower()
            
            deps = []
            if 'login' in steps_text and tc['feature'] != 'Login':
                deps.append('Login')
            if 'profile' in steps_text and tc['feature'] != 'Profile':
                deps.append('Profile')
            
            if deps:
                dependencies[tc['id']] = deps
        
        return dependencies
    
    def generate_test_plan(self, output_path: str = None, csv_filename: str = None, workspace_path: str = None):
        """Generate structured test plan in exact Playwright format"""
        
        # Generate unique filename based on CSV name or timestamp
        if output_path is None:
            # Determine base directory
            if workspace_path and os.path.exists(workspace_path):
                base_dir = os.path.join(workspace_path, 'test_plans')
            else:
                base_dir = 'test_plans'
            
            os.makedirs(base_dir, exist_ok=True)
            
            if csv_filename:
                # Use CSV filename without extension
                base_name = os.path.splitext(os.path.basename(csv_filename))[0]
                output_path = os.path.join(base_dir, f'test_plan_{base_name}.md')
            else:
                # Use timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = os.path.join(base_dir, f'test_plan_{timestamp}.md')
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Header
            f.write(f"# Test Plan - Generated from CSV\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            
            # Test cases by feature (Playwright style)
            for feature_idx, (feature, test_cases) in enumerate(self.features.items(), 1):
                # Use "General" if feature is empty
                feature_name = feature if feature else "General"
                    
                f.write(f"### {feature_idx}. {feature_name}\n\n")
                
                for tc in test_cases:
                    # Test case header
                    f.write(f"#### {tc['id']}: {tc['name']}\n\n")
                    
                    # Priority
                    priority_map = {'High': 'P1', 'Medium': 'P2', 'Low': 'P3'}
                    priority = priority_map.get(tc['priority'], 'P2')
                    f.write(f"**Priority**: {priority}  \n\n")
                    
                    # Preconditions
                    f.write("**Preconditions**:\n")
                    if tc.get('precondition'):
                        # Use precondition from CSV
                        precond_lines = tc['precondition'].split('\n')
                        for line in precond_lines:
                            if line.strip():
                                f.write(f"- {line.strip()}\n")
                    else:
                        # Default preconditions
                        f.write(f"- User has valid credentials\n")
                        if tc['feature'] != 'Login' and 'login' not in tc['name'].lower():
                            f.write(f"- User is logged in\n")
                        f.write(f"- Application is accessible\n")
                    f.write("\n")
                    
                    # Steps
                    f.write("**Steps**:\n")
                    for i, step in enumerate(tc['steps'], 1):
                        if step.strip():
                            f.write(f"{i}. {step.strip()}\n")
                    f.write("\n")
                    
                    # Expected Results
                    f.write("**Expected Results**:\n")
                    if tc['expected']:
                        # Split expected result into bullet points if it contains multiple items
                        expected_lines = tc['expected'].split('\n')
                        if len(expected_lines) > 1:
                            for line in expected_lines:
                                if line.strip():
                                    f.write(f"- {line.strip()}\n")
                        else:
                            f.write(f"- {tc['expected']}\n")
                    else:
                        f.write(f"- Test completes successfully\n")
                    f.write("\n")
                    
                    # DB Validation
                    f.write("**DB Validation**:\n")
                    f.write("```sql\n")
                    f.write(f"-- Verify {tc['name']}\n")
                    f.write(f"-- Add specific SQL query for validation\n")
                    f.write("SELECT * FROM relevant_table WHERE condition;\n")
                    f.write("```\n\n")
                    
                    f.write("---\n\n")
            
            f.write(f"**End of Test Plan**\n")
        
        print(f" Test plan generated: {output_path}")
        return output_path


def demo_test_plan_agent():
    """Demo the test plan agent with sample CSV"""
    
    # Create sample CSV
    sample_csv = """Test ID,Feature,Test Case Name,Steps,Expected Result,Priority,Platform
TC001,Login,Valid Login,1. Open app
2. Enter valid email
3. Enter valid password
4. Click Login,User logged in successfully,High,Both
TC002,Login,Invalid Login,1. Open app
2. Enter invalid email
3. Enter password
4. Click Login,Error message displayed,High,Both
TC003,Profile,View Profile,1. Login to app
2. Navigate to Profile
3. View profile details,Profile details displayed,Medium,Both
TC004,Profile,Edit Profile,1. Login to app
2. Navigate to Profile
3. Click Edit
4. Update name
5. Save,Profile updated successfully,Medium,Both
TC005,Dashboard,View Dashboard,1. Login to app
2. View dashboard,Dashboard loaded with data,High,Both"""
    
    os.makedirs('test_plans', exist_ok=True)
    csv_path = 'test_plans/sample_test_cases.csv'
    
    with open(csv_path, 'w') as f:
        f.write(sample_csv)
    
    print("📋 Test Plan Agent Demo")
    print("=" * 60)
    
    # Initialize agent
    agent = TestPlanAgent()
    
    # Parse CSV
    print(f"\n1. Parsing CSV: {csv_path}")
    test_cases = agent.parse_csv(csv_path)
    print(f"    Found {len(test_cases)} test cases")
    
    # Group by feature
    print("\n2. Grouping by feature")
    features = agent.group_by_feature()
    for feature, tcs in features.items():
        print(f"   - {feature}: {len(tcs)} test cases")
    
    # Analyze dependencies
    print("\n3. Analyzing dependencies")
    deps = agent.analyze_dependencies()
    print(f"    Found {len(deps)} test dependencies")
    
    # Generate test plan
    print("\n4. Generating test plan")
    output_path = agent.generate_test_plan()
    
    print("\n" + "=" * 60)
    print(" Test Plan Agent Demo Complete!")
    print(f"\nGenerated file: {output_path}")
    print("\nNext steps:")
    print("1. Review test_plan.md")
    print("2. Run Codebase Explorer to analyze Bizom KMM repo")
    print("3. Run UI Explorer to extract locators")
    print("4. Generate automated tests")


if __name__ == "__main__":
    demo_test_plan_agent()
