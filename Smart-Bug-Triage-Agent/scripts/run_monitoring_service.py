#!/usr/bin/env python
"""Script to run the monitoring service."""

import sys
import signal
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from smart_bug_triage.monitoring.monitoring_service import monitoring_service
from smart_bug_triage.utils.logging import get_logger


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger = get_logger(__name__)
    logger.info(f"Received signal {signum}, shutting down monitoring service...")
    monitoring_service.stop()
    sys.exit(0)


def main():
    """Main function to run the monitoring service."""
    logger = get_logger(__name__)
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("Starting Smart Bug Triage Monitoring Service")
        
        # Start the monitoring service
        monitoring_service.start()
        
        # Print initial status
        print("\n" + "="*60)
        print("Smart Bug Triage Monitoring Service")
        print("="*60)
        print(f"Service started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Check interval: {monitoring_service.check_interval} seconds")
        print("Press Ctrl+C to stop")
        print("="*60)
        
        # Print initial system status
        status = monitoring_service.get_system_status()
        if 'error' not in status:
            print(f"\nSystem Health Score: {status['system_health'].get('overall_health_score', 0):.1f}/100")
            print(f"Status: {status['system_health'].get('status', 'Unknown')}")
            print(f"Active Alerts: {status['active_alerts_count']}")
            
            if status.get('critical_alerts'):
                print("\nCRITICAL ALERTS:")
                for alert in status['critical_alerts']:
                    print(f"  - {alert['alert_name']}: {alert['message']}")
        
        print("\nMonitoring service is running...")
        
        # Keep the main thread alive
        while monitoring_service.is_running:
            time.sleep(60)  # Print status every minute
            
            # Print periodic status updates
            try:
                status = monitoring_service.get_system_status()
                if 'error' not in status:
                    health_score = status['system_health'].get('overall_health_score', 0)
                    alerts_count = status['active_alerts_count']
                    
                    print(f"[{time.strftime('%H:%M:%S')}] "
                          f"Health: {health_score:.1f}/100, "
                          f"Alerts: {alerts_count}")
                    
                    # Show critical alerts
                    if status.get('critical_alerts'):
                        for alert in status['critical_alerts']:
                            print(f"  CRITICAL: {alert['alert_name']}")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Error getting status: {status.get('error')}")
                    
            except Exception as e:
                logger.error(f"Error printing status: {str(e)}")
    
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1
    finally:
        # Ensure service is stopped
        if monitoring_service.is_running:
            monitoring_service.stop()
        logger.info("Monitoring service stopped")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())