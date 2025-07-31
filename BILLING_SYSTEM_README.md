# Usage-Based Billing System for Odoo Multi-Tenant Platform

This document describes the comprehensive usage-based billing system implemented for the Odoo multi-tenant platform, where each tenant is called a "Panel".

## 🎯 System Overview

The billing system tracks actual panel uptime and automatically manages billing cycles, notifications, and payments based on usage rather than calendar time.

### Key Features

- **Usage-Based Billing**: Only counts active hours when panel database is running
- **Automatic Notifications**: 7-day reminders via support tickets
- **Auto-Deactivation**: Panels automatically disabled when billing limit reached
- **Payment Integration**: Ready-to-integrate payment gateway support
- **Admin Dashboard**: Comprehensive billing logs and management
- **Real-time UI**: Dashboard shows billing progress with visual indicators

## 📊 Billing Logic

### Billing Cycle Details
- **Duration**: 30 calendar days per cycle
- **Active Hours**: 12 billable hours per day (360 total hours per cycle)
- **Usage Tracking**: Hourly monitoring of database status
- **Deactivation**: Automatic when 360 hours consumed OR 30 days elapsed

### Hour Calculation
```
Total Hours per Cycle = 30 days × 12 hours = 360 hours
Daily Allowance = 12 active hours
Monitoring Frequency = Every hour
```

## 🗃️ Database Schema

### New Tables Created

1. **billing_cycles** - Tracks billing periods per tenant
2. **usage_tracking** - Hourly usage logs
3. **payment_history** - Payment records and transactions
4. **billing_notifications** - Notification tracking and support tickets

### Key Relationships
```
Tenant (1) → (N) BillingCycle
BillingCycle (1) → (N) UsageTracking
BillingCycle (1) → (N) PaymentHistory
BillingCycle (1) → (N) BillingNotification
```

## 🔔 Notification System

### 7-Day Reminder
- **Trigger**: When 84 hours (7 days) remain in cycle
- **Method**: Creates support ticket automatically
- **Message**: "Your current billing cycle will end in 7 days. Please renew to continue uninterrupted access."
- **UI Badge**: Shows warning indicator on panel card

### Expiry Notification
- **Trigger**: When panel auto-deactivated
- **Method**: Creates high-priority support ticket
- **Message**: "Your panel has been deactivated due to billing limit reached. Please make a payment to reactivate your service."

## 🔒 Auto-Deactivation Process

1. **Monitor**: Hourly check of usage vs. limit
2. **Trigger**: When `hours_used >= 360` or cycle expired
3. **Actions**:
   - Set `tenant.is_active = False`
   - Set `tenant.status = 'billing_expired'`
   - Mark `billing_cycle.auto_deactivated = True`
   - Create expiry notification
   - Disable database toggle in UI
   - Show "Pay to Renew" button

## 💳 Payment & Reactivation

### Payment Flow
1. User clicks "Pay to Renew" button
2. Redirected to payment page with billing summary
3. Select payment method (Stripe, PayPal, etc.)
4. Process payment through gateway
5. On success: Reactivate panel + create new billing cycle

### Reactivation Process
- `tenant.is_active = True`
- `tenant.status = 'active'`
- Create new 30-day billing cycle
- Reset hour counter to 0
- Update support tickets as "Paid"
- Enable panel controls

## 👀 Admin Panel Features

### Billing Logs Dashboard
- **View**: Complete billing history per panel
- **Filters**: By panel, date range, status
- **Data**: Creation date, payments, uptime, downtime, notifications
- **Export**: Download billing reports (planned)

### Detailed Panel View
- Billing cycle history
- Payment transaction logs
- Usage patterns (hourly logs)
- Notification history
- Real-time status

## 📅 Dashboard UI Updates

### Panel Card Enhancements
- **Progress Bar**: Visual billing usage indicator
- **Status Text**: "Billing: 9 days (108 hours) remaining"
- **Color Coding**: 
  - Green: < 60% used
  - Yellow: 60-80% used  
  - Red: > 80% used
- **Notification Badge**: Warning icon when reminder needed
- **Smart Buttons**: "Pay to Renew" replaces "Manage" when expired

### Real-time Updates
- Auto-refresh every 30 seconds
- AJAX loading of billing info
- Dynamic button switching
- Progress bar animations

## 🔄 Background Tasks

### Hourly CRON Job
```python
# Every hour:
- Check all active panels
- Record database status (active/inactive)
- Update billing cycle hours
- Send 7-day reminders if needed
- Auto-deactivate expired panels
```

### Monitoring Tasks
- Database connectivity checks
- Panel health verification
- Usage hour accumulation
- Notification dispatch

## 🚀 Installation & Setup

### 1. Database Migration
```bash
cd saas_manager
python database_migration.py
```

### 2. Install Dependencies
```bash
pip install schedule
```

### 3. Environment Variables
```env
BILLING_ENABLED=true
DEFAULT_PANEL_PRICE=50.00
BILLING_CURRENCY=USD
CRON_TOKEN=your-secure-random-token
```

### 4. Flask Integration
```python
from billing_routes import billing_bp
from cron_setup import start_billing_scheduler

app.register_blueprint(billing_bp)

with app.app_context():
    start_billing_scheduler()
```

### 5. Cron Setup (Optional)
```cron
# Backup hourly trigger
0 * * * * curl -X POST -H "X-Cron-Token: your-token" http://localhost:5000/billing/cron/hourly-tracking
```

## 🛠️ File Structure

```
saas_manager/
├── models.py                 # Added billing models
├── billing_service.py        # Core billing logic
├── billing_routes.py         # API endpoints
├── cron_setup.py            # Background scheduler
├── database_migration.py    # DB setup script
├── billing_integration.py   # Integration guide
├── templates/billing/
│   ├── payment.html         # Payment page
│   └── admin_logs.html      # Admin dashboard
└── templates/dashboard.html # Updated with billing UI
```

## 🔧 API Endpoints

### User Endpoints
- `GET /billing/panel/{id}/info` - Get billing info
- `GET /billing/panel/{id}/payment` - Payment page
- `POST /billing/panel/{id}/payment/process` - Process payment
- `GET /billing/notifications/{id}` - Get notifications
- `POST /billing/notifications/{id}/read` - Mark as read

### Admin Endpoints
- `GET /billing/admin/logs` - Billing logs dashboard
- `GET /billing/admin/tenant/{id}/billing` - Detailed view

### System Endpoints
- `POST /billing/cron/hourly-tracking` - Trigger tracking

## 🧪 Testing

### Manual Testing
```python
from billing_service import BillingService

billing = BillingService()

# Create billing cycle
cycle = billing.create_billing_cycle(tenant_id=1)

# Run tracking
billing.track_hourly_usage()

# Get info
info = billing.get_tenant_billing_info(tenant_id=1)
```

### Test Payment Flow
1. Create test tenant
2. Let it run past 360 hours (simulate)
3. Verify auto-deactivation
4. Test payment and reactivation

## 📊 Usage Examples

### Billing Progress Display
- "Billing: 15 days (180 hours) remaining"
- "Billing: 2 days (24 hours) remaining" ⚠️
- "Billing expired. Please renew." ❌

### Notification Messages
- 7-day reminder: Support ticket created
- Expiry notice: High-priority ticket
- Payment confirmation: Ticket marked as resolved

## 🔮 Future Enhancements

### Planned Features
- Multiple billing plans (basic, premium, enterprise)
- Custom billing cycles (weekly, monthly, quarterly)
- Usage analytics and forecasting
- Automated payment methods (subscription)
- Billing API for external integrations
- White-label billing portal

### Advanced Monitoring
- Real-time usage graphs
- Performance impact tracking
- Cost optimization recommendations
- Predictive billing alerts

## 🎉 Success Metrics

The billing system provides:
- ✅ Automatic usage tracking
- ✅ Fair pay-per-use pricing
- ✅ Proactive user notifications
- ✅ Seamless payment experience
- ✅ Complete admin visibility
- ✅ Reliable auto-management

## 🆘 Support & Troubleshooting

### Common Issues
1. **Billing not updating**: Check if scheduler is running
2. **Payment not processing**: Verify gateway configuration
3. **Panel not reactivating**: Check payment status in logs
4. **Notifications not sending**: Verify support ticket creation

### Debug Commands
```python
# Check scheduler status
from cron_setup import billing_scheduler
print(f"Scheduler running: {billing_scheduler.running}")

# Manual trigger
billing_scheduler.run_hourly_tracking()

# Check billing cycle
from models import BillingCycle
cycle = BillingCycle.query.filter_by(tenant_id=1, status='active').first()
print(f"Hours used: {cycle.hours_used}/360")
```

---

**🎯 The billing system is now fully operational and ready to manage your Odoo multi-tenant platform with fair, usage-based pricing!**
