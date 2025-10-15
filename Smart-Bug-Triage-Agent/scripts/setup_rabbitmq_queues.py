#!/usr/bin/env python
"""
Setup RabbitMQ queues and exchanges for Smart Bug Triage.
Run this script to create the required message queues.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pika
from smart_bug_triage.config.settings import SystemConfig


def setup_rabbitmq():
    """Set up RabbitMQ exchanges and queues."""
    print("🐰 Setting up RabbitMQ queues for Smart Bug Triage...")
    
    try:
        # Load configuration
        config = SystemConfig.from_env()
        
        # Connect to RabbitMQ
        credentials = pika.PlainCredentials(
            config.message_queue.username,
            config.message_queue.password
        )
        
        parameters = pika.ConnectionParameters(
            host=config.message_queue.host,
            port=config.message_queue.port,
            virtual_host=config.message_queue.virtual_host,
            credentials=credentials
        )
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        print(f"✅ Connected to RabbitMQ at {config.message_queue.host}:{config.message_queue.port}")
        
        # Create exchange
        exchange_name = config.message_queue.exchange_name
        channel.exchange_declare(
            exchange=exchange_name,
            exchange_type='topic',
            durable=True
        )
        print(f"✅ Created exchange: {exchange_name}")
        
        # Create queues
        queues_to_create = [
            ("bug_triage.new_bugs", "new_bugs"),
            ("bug_triage.triaged_bugs", "triaged_bugs"), 
            ("bug_triage.assignments", "assignments"),
            ("bug_triage.notifications", "notifications"),
            ("manual_review", "manual_review")
        ]
        
        for queue_name, routing_key in queues_to_create:
            # Declare queue
            channel.queue_declare(queue=queue_name, durable=True)
            
            # Bind queue to exchange
            channel.queue_bind(
                exchange=exchange_name,
                queue=queue_name,
                routing_key=routing_key
            )
            
            print(f"✅ Created queue: {queue_name} (routing: {routing_key})")
        
        # Close connection
        connection.close()
        
        print("\n🎉 RabbitMQ setup completed successfully!")
        print("\n📋 Created queues:")
        print("   📥 bug_triage.new_bugs - Incoming bug reports")
        print("   📤 bug_triage.triaged_bugs - Classified bugs for assignment")
        print("   👥 bug_triage.assignments - Bug assignments to developers")
        print("   📢 bug_triage.notifications - System notifications")
        print("   🔍 manual_review - Low-confidence bugs for manual review")
        print("\n🚀 The Triage Agent can now process messages!")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to setup RabbitMQ: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Make sure RabbitMQ is running: brew services start rabbitmq")
        print("2. Check RabbitMQ management UI: http://localhost:15672 (guest/guest)")
        print("3. Verify environment variables in .env file")
        return False


if __name__ == "__main__":
    success = setup_rabbitmq()
    sys.exit(0 if success else 1)