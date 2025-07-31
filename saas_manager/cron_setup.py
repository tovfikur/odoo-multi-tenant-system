# Background Task Setup for Billing System
import schedule
import time
import threading
import logging
from datetime import datetime
from billing_service import BillingService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BillingScheduler:
    """Handles scheduled billing tasks"""
    
    def __init__(self):
        self.billing_service = BillingService()
        self.running = False
        self.scheduler_thread = None
    
    def start_scheduler(self):
        """Start the background scheduler"""
        if self.running:
            logger.warning("Scheduler is already running")
            return
        
        # Schedule hourly usage tracking
        schedule.every().hour.do(self.run_hourly_tracking)
        
        # Schedule daily maintenance at 2 AM
        schedule.every().day.at("02:00").do(self.run_daily_maintenance)
        
        # Schedule weekly reports on Sunday at 6 AM
        schedule.every().sunday.at("06:00").do(self.run_weekly_reports)
        
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Billing scheduler started successfully")
    
    def stop_scheduler(self):
        """Stop the background scheduler"""
        self.running = False
        schedule.clear()
        logger.info("Billing scheduler stopped")
    
    def _run_scheduler(self):
        """Internal method to run the scheduler loop"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                time.sleep(60)  # Continue running even if there's an error
    
    def run_hourly_tracking(self):
        """Run hourly usage tracking"""
        try:
            logger.info("Starting hourly billing tracking job")
            self.billing_service.track_hourly_usage()
            logger.info("Completed hourly billing tracking job")
        except Exception as e:
            logger.error(f"Error in hourly tracking job: {str(e)}")
    
    def run_daily_maintenance(self):
        """Run daily maintenance tasks"""
        try:
            logger.info("Starting daily billing maintenance")
            
            # Add any daily maintenance tasks here
            # For example: cleanup old usage logs, generate reports, etc.
            
            logger.info("Completed daily billing maintenance")
        except Exception as e:
            logger.error(f"Error in daily maintenance: {str(e)}")
    
    def run_weekly_reports(self):
        """Generate weekly billing reports"""
        try:
            logger.info("Starting weekly billing reports")
            
            # Add weekly report generation here
            # For example: send usage summaries to admins
            
            logger.info("Completed weekly billing reports")
        except Exception as e:
            logger.error(f"Error in weekly reports: {str(e)}")

# Global scheduler instance
billing_scheduler = BillingScheduler()

def start_billing_scheduler():
    """Start the billing scheduler (call this from your main app)"""
    billing_scheduler.start_scheduler()

def stop_billing_scheduler():
    """Stop the billing scheduler"""
    billing_scheduler.stop_scheduler()

# Manual trigger functions for testing
def trigger_hourly_tracking():
    """Manually trigger hourly tracking (for testing)"""
    billing_scheduler.run_hourly_tracking()

def trigger_daily_maintenance():
    """Manually trigger daily maintenance (for testing)"""
    billing_scheduler.run_daily_maintenance()

if __name__ == "__main__":
    # For testing purposes
    print("Starting billing scheduler for testing...")
    start_billing_scheduler()
    
    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping billing scheduler...")
        stop_billing_scheduler()
