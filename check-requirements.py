#!/usr/bin/env python3
"""
Check if all required dependencies are installed
"""

import subprocess
import sys
from pathlib import Path

def check_python_package(package_name):
    """Check if a Python package is installed"""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def check_requirements_file(requirements_path):
    """Check requirements.txt file"""
    if not Path(requirements_path).exists():
        print(f"❌ {requirements_path} not found")
        return False
    
    print(f"📋 Checking {requirements_path}...")
    
    with open(requirements_path, 'r') as f:
        requirements = f.read().strip().split('\n')
    
    missing = []
    for req in requirements:
        if req.strip() and not req.startswith('#'):
            # Extract package name (before ==, >=, etc.)
            package_name = req.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
            
            if not check_python_package(package_name):
                missing.append(package_name)
    
    if missing:
        print(f"❌ Missing packages: {', '.join(missing)}")
        return False
    else:
        print(f"✅ All packages installed")
        return True

def check_node_dependencies():
    """Check if Node.js dependencies are installed"""
    frontend_path = Path("front")
    if not frontend_path.exists():
        print("❌ Frontend directory not found")
        return False
    
    node_modules = frontend_path / "node_modules"
    if not node_modules.exists():
        print("❌ Node.js dependencies not installed")
        print("   Run: cd front && npm install")
        return False
    
    print("✅ Node.js dependencies installed")
    return True

def main():
    """Check all requirements"""
    print("🔍 Checking KubeMinder Requirements")
    print("=" * 40)
    
    # Check Python requirements
    python_requirements = [
        "backend/api_gateway/requirements.txt",
        "agents/planner/requirements.txt", 
        "agents/collaborator/requirements.txt",
        "agents/actor/requirements.txt",
        "agents/learner/requirements.txt"
    ]
    
    python_ok = True
    for req_file in python_requirements:
        if not check_requirements_file(req_file):
            python_ok = False
    
    # Check Node.js dependencies
    node_ok = check_node_dependencies()
    
    # Summary
    print("\n" + "=" * 40)
    if python_ok and node_ok:
        print("🎉 All requirements are satisfied!")
        print("\n🚀 You can now run: npm start")
        return 0
    else:
        print("⚠️  Some requirements are missing.")
        print("\n📝 To install missing requirements:")
        print("   Python: pip install -r [requirements.txt]")
        print("   Node.js: cd front && npm install")
        return 1

if __name__ == "__main__":
    sys.exit(main())
