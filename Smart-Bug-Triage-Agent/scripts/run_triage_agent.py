#!/usr/bin/env python
"""
Run the Smart Bug Triage Agent.
This script starts the triage agent with proper configuration.
"""

import os
import sys
import signal
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from smart_bug_triage.agents.triage_agent import TriageAgent
from smart_bug_triage.config.settings import SystemConfig


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"\n🛑 Received signal {signum}, shutting down...")
    global agent
    if agent:
        agent.stop()
    sys.exit(0)


def main():
    """Run the triage agent."""
    global agent
    agent = None
    
    print("🚀 Starting Smart Bug Triage Agent...")
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load configuration
        config = SystemConfig.from_env()
        
        # Validate configuration (skip GitHub token requirement for Triage Agent)
        errors = []
        
        # Validate database settings
        if not config.database.host:
            errors.append("Database host is required")
        if not config.database.database:
            errors.append("Database name is required")
        
        # Validate message queue settings
        if not config.message_queue.host:
            errors.append("Message queue host is required")
        
        if errors:
            print("❌ Configuration validation failed!")
            for error in errors:
                print(f"   - {error}")
            print("Please check your environment variables.")
            return False
        
        # Create and configure triage agent
        triage_config = {
            'database': {
                'url': f"postgresql://{config.database.username}:{config.database.password}@{config.database.host}:{config.database.port}/{config.database.database}"
            },
            'message_queue': config.message_queue.__dict__,
            'triage': {
                'confidence_threshold': float(os.getenv('TRIAGE_CONFIDENCE_THRESHOLD', '0.7')),
                'manual_review_queue': os.getenv('TRIAGE_MANUAL_REVIEW_QUEUE', 'manual_review'),
                'processing_timeout': float(os.getenv('TRIAGE_PROCESSING_TIMEOUT', '30.0'))
            }
        }
        
        # Initialize agent
        agent = TriageAgent("triage_agent_main", triage_config)
        
        # Start agent
        if agent.start():
            print("✅ Triage Agent started successfully!")
            print("📊 Agent Status:", agent.get_status())
            print("🔄 Processing bug reports... (Press Ctrl+C to stop)")
            
            # Keep running until interrupted
            try:
                while True:
                    time.sleep(10)
                    
                    # Print periodic status updates
                    status = agent.get_status()
                    if status['is_healthy']:
                        stats = agent.get_processing_stats()
                        print(f"📈 Processed: {stats['total_processed']}, "
                              f"Success Rate: {stats['success_rate']:.1%}, "
                              f"Manual Review: {stats['manual_review_rate']:.1%}")
                    else:
                        print("⚠️  Agent health check failed!")
                        
            except KeyboardInterrupt:
                print("\n🛑 Shutdown requested by user")
                
        else:
            print("❌ Failed to start Triage Agent!")
            return False
            
    except Exception as e:
        print(f"❌ Error running triage agent: {e}")
        return False
    finally:
        if agent:
            print("🔄 Stopping agent...")
            agent.stop()
            print("✅ Agent stopped successfully")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)