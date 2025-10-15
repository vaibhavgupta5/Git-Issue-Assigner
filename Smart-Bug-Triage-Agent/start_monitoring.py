#!/usr/bin/env python
"""
Start Smart Bug Triage Monitoring System

This script starts your Smart Bug Triage system in monitoring mode.
"""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path.cwd()))

def main():
    """Start the monitoring system."""
    print("🚀 Starting Smart Bug Triage Monitoring System")
    print("=" * 50)
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check GitHub token
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ GITHUB_TOKEN not found in environment")
        print("💡 Make sure your .env file contains: GITHUB_TOKEN=your_token_here")
        return 1
    
    print("✅ GitHub token found")
    print("✅ Environment loaded")
    
    # Import and start the system
    try:
        from run_simple_system import SimpleBugTriageSystem
        
        print("\n🔧 Initializing Smart Bug Triage System...")
        system = SimpleBugTriageSystem()
        
        print("🚀 Starting monitoring...")
        print("💡 The system will check for new issues every 60 seconds")
        print("🛑 Press Ctrl+C to stop\n")
        
        # Start the system
        system.start()
        
    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Error starting system: {e}")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)