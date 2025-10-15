#!/usr/bin/env python
"""
Smart Bug Triage System - Launcher Menu
=======================================
Choose how you want to run your Smart Bug Triage System.
"""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path.cwd()))

def show_menu():
    """Show the launcher menu."""
    print("🎯 SMART BUG TRIAGE SYSTEM LAUNCHER")
    print("=" * 50)
    print("Choose how you want to run the system:")
    print()
    print("1. 🚀 Start Complete Live Pipeline")
    print("   → Runs all agents with message queue")
    print("   → Monitors GitHub continuously")
    print("   → Production mode")
    print()
    print("2. 🧪 Run System Test/Demo")
    print("   → Tests all components")
    print("   → Shows real GitHub issues")
    print("   → Demonstrates AI assignment")
    print()
    print("3. 🔍 Test Individual Components")
    print("   → Test listener agent only")
    print("   → Test triage agent only")
    print("   → Test assignment logic")
    print()
    print("4. ❌ Exit")
    print()

def main():
    """Main launcher function."""
    while True:
        show_menu()
        choice = input("Enter your choice (1-4): ").strip()
        print()
        
        if choice == "1":
            print("🚀 Starting Complete Live Pipeline...")
            print("This will run the full system with all agents.")
            print("Press Ctrl+C to stop the system when running.")
            print()
            input("Press Enter to continue or Ctrl+C to cancel...")
            
            # Run the complete pipeline
            os.system("python start_complete_pipeline.py")
            
        elif choice == "2":
            print("🧪 Running System Test/Demo...")
            print("This will test the system with real GitHub issues.")
            print()
            
            # Run the test/demo
            os.system("python run_real_system_test.py")
            print()
            input("Press Enter to continue...")
            
        elif choice == "3":
            print("🔍 Individual Component Testing")
            print("-" * 30)
            print("a. Test all agents")
            print("b. Test triage agent")
            print("c. Test full system components")
            print()
            
            sub_choice = input("Enter your choice (a-c): ").strip().lower()
            
            if sub_choice == "a":
                os.system("python test_all_agents.py")
            elif sub_choice == "b":
                os.system("python test_full_system.py")
            elif sub_choice == "c":
                os.system("python test_complete_pipeline.py")
            else:
                print("Invalid choice")
            
            print()
            input("Press Enter to continue...")
            
        elif choice == "4":
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice. Please enter 1-4.")
            input("Press Enter to continue...")
        
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")