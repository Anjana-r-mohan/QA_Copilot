"""
Codebase Explorer Agent
Analyzes Bizom KMM repository to understand features, flows, and extract locators
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
import subprocess


class CodebaseExplorerAgent:
    """
    Explores KMM codebase to extract features, flows, and UI elements
    """
    
    def __init__(self, repo_path: str = None):
        self.repo_path = repo_path
        self.features = {}
        self.locators = []
        self.screens = {}
        
    def clone_repo(self, repo_url: str, target_path: str = './bizom_kmm'):
        """Clone Bitbucket repository"""
        print(f"📥 Cloning repository: {repo_url}")
        
        if os.path.exists(target_path):
            print(f"   ⚠️  Repository already exists at {target_path}")
            self.repo_path = target_path
            return target_path
        
        try:
            subprocess.run(['git', 'clone', repo_url, target_path], check=True)
            self.repo_path = target_path
            print(f"   ✅ Repository cloned to {target_path}")
            return target_path
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Failed to clone repository: {e}")
            return None
    
    def analyze_android_code(self, android_path: str) -> Dict:
        """Analyze Android code for screens and locators"""
        print(f"\n📱 Analyzing Android code: {android_path}")
        
        screens = {}
        locators = []
        
        if not os.path.exists(android_path):
            print(f"   ⚠️  Path not found: {android_path}")
            return {'screens': screens, 'locators': locators}
        
        # Find all Kotlin/Java files
        for root, dirs, files in os.walk(android_path):
            for file in files:
                if file.endswith(('.kt', '.java')):
                    file_path = os.path.join(root, file)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Extract screen info
                        if 'Activity' in file or 'Fragment' in file:
                            screen_info = self._extract_android_screen(file_path, content)
                            if screen_info:
                                screens[screen_info['name']] = screen_info
                                locators.extend(screen_info['locators'])
                    
                    except Exception as e:
                        print(f"   ⚠️  Error reading {file}: {e}")
        
        print(f"   ✅ Found {len(screens)} screens, {len(locators)} locators")
        return {'screens': screens, 'locators': locators}
    
    def analyze_ios_code(self, ios_path: str) -> Dict:
        """Analyze iOS code for screens and locators"""
        print(f"\n📱 Analyzing iOS code: {ios_path}")
        
        screens = {}
        locators = []
        
        if not os.path.exists(ios_path):
            print(f"   ⚠️  Path not found: {ios_path}")
            return {'screens': screens, 'locators': locators}
        
        # Find all Swift files
        for root, dirs, files in os.walk(ios_path):
            for file in files:
                if file.endswith('.swift'):
                    file_path = os.path.join(root, file)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Extract screen info
                        if 'ViewController' in file or 'View' in file:
                            screen_info = self._extract_ios_screen(file_path, content)
                            if screen_info:
                                screens[screen_info['name']] = screen_info
                                locators.extend(screen_info['locators'])
                    
                    except Exception as e:
                        print(f"   ⚠️  Error reading {file}: {e}")
        
        print(f"   ✅ Found {len(screens)} screens, {len(locators)} locators")
        return {'screens': screens, 'locators': locators}
    
    def _extract_android_screen(self, file_path: str, content: str) -> Optional[Dict]:
        """Extract screen information from Android file"""
        # Extract class name
        class_match = re.search(r'class\s+(\w+)', content)
        if not class_match:
            return None
        
        class_name = class_match.group(1)
        
        # Extract UI element IDs
        locators = []
        id_matches = re.findall(r'R\.id\.(\w+)', content)
        for element_id in set(id_matches):
            locators.append({
                'screen': class_name,
                'element': element_id,
                'platform': 'android',
                'type': 'id',
                'value': element_id,
                'file': file_path
            })
        
        # Extract methods (potential actions)
        methods = re.findall(r'fun\s+(\w+)\s*\(|void\s+(\w+)\s*\(', content)
        method_names = [m[0] or m[1] for m in methods]
        
        return {
            'name': class_name,
            'platform': 'android',
            'file': file_path,
            'locators': locators,
            'methods': method_names,
            'type': 'Activity' if 'Activity' in class_name else 'Fragment'
        }
    
    def _extract_ios_screen(self, file_path: str, content: str) -> Optional[Dict]:
        """Extract screen information from iOS file"""
        # Extract class name
        class_match = re.search(r'class\s+(\w+)', content)
        if not class_match:
            return None
        
        class_name = class_match.group(1)
        
        # Extract UI elements
        locators = []
        
        # IBOutlets
        outlets = re.findall(r'@IBOutlet.*?(\w+):', content)
        for outlet in set(outlets):
            locators.append({
                'screen': class_name,
                'element': outlet,
                'platform': 'ios',
                'type': 'outlet',
                'value': outlet,
                'file': file_path
            })
        
        # Accessibility IDs
        accessibility_ids = re.findall(r'accessibilityIdentifier\s*=\s*"(\w+)"', content)
        for acc_id in set(accessibility_ids):
            locators.append({
                'screen': class_name,
                'element': acc_id,
                'platform': 'ios',
                'type': 'accessibilityId',
                'value': acc_id,
                'file': file_path
            })
        
        # Extract methods
        methods = re.findall(r'func\s+(\w+)\s*\(', content)
        
        return {
            'name': class_name,
            'platform': 'ios',
            'file': file_path,
            'locators': locators,
            'methods': methods,
            'type': 'ViewController' if 'ViewController' in class_name else 'View'
        }
    
    def save_feature_map(self, output_path: str = 'data/feature_map.json'):
        """Save feature map to JSON"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        feature_map = {
            'features': self.features,
            'screens': self.screens,
            'total_locators': len(self.locators)
        }
        
        with open(output_path, 'w') as f:
            json.dump(feature_map, f, indent=2)
        
        print(f"\n💾 Feature map saved: {output_path}")
        return output_path
    
    def save_locators(self, output_path: str = 'data/locators.json'):
        """Save locators to JSON"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.locators, f, indent=2)
        
        print(f"💾 Locators saved: {output_path}")
        return output_path
    
    def explore_repository(self, repo_path: str = None):
        """Main method to explore entire repository"""
        if repo_path:
            self.repo_path = repo_path
        
        if not self.repo_path:
            print("❌ No repository path provided")
            return
        
        print("=" * 60)
        print("🔍 Codebase Explorer Agent")
        print("=" * 60)
        print(f"\nRepository: {self.repo_path}")
        
        # Analyze Android
        android_path = os.path.join(self.repo_path, 'androidApp')
        if not os.path.exists(android_path):
            android_path = os.path.join(self.repo_path, 'android')
        
        android_results = self.analyze_android_code(android_path)
        
        # Analyze iOS
        ios_path = os.path.join(self.repo_path, 'iosApp')
        if not os.path.exists(ios_path):
            ios_path = os.path.join(self.repo_path, 'ios')
        
        ios_results = self.analyze_ios_code(ios_path)
        
        # Combine results
        self.screens = {**android_results['screens'], **ios_results['screens']}
        self.locators = android_results['locators'] + ios_results['locators']
        
        # Save results
        self.save_feature_map()
        self.save_locators()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Summary")
        print("=" * 60)
        print(f"Total Screens: {len(self.screens)}")
        print(f"Total Locators: {len(self.locators)}")
        print(f"Android Screens: {len(android_results['screens'])}")
        print(f"iOS Screens: {len(ios_results['screens'])}")
        
        return {
            'screens': self.screens,
            'locators': self.locators
        }


def demo_codebase_explorer():
    """Demo the codebase explorer with sample project"""
    print("🔍 Codebase Explorer Agent Demo")
    print("=" * 60)
    
    # Use the sample project we created earlier
    agent = CodebaseExplorerAgent()
    
    # Explore sample project
    results = agent.explore_repository('./sample_projects')
    
    print("\n✅ Codebase Explorer Demo Complete!")
    print("\nGenerated files:")
    print("- data/feature_map.json")
    print("- data/locators.json")


if __name__ == "__main__":
    demo_codebase_explorer()
