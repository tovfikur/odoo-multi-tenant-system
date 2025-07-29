# Standard library imports
import asyncio
import hashlib
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal

# Third-party imports
import requests
from flask import url_for, redirect, flash, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

# Local application imports
from db import db
from models import Tenant, SaasUser, SubscriptionPlan, TenantUser, CredentialAccess, WorkerInstance, PaymentTransaction
from utils import error_tracker, track_errors, generate_random_alphanumeric, logger

# SSLCommerz Sandbox Credentials
SSLCOMMERZ_STORE_ID = "kendr686995fcc52be"
SSLCOMMERZ_STORE_PASSWORD = "kendr686995fcc52be@ssl"
SSLCOMMERZ_SESSION_API = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
SSLCOMMERZ_VALIDATION_API = "https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php"

def run_async_in_background(coro):
    """Helper function to run an async coroutine in the background."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


# Enhanced payment success handler specifically for unified registration
@staticmethod
@track_errors('handle_unified_payment_success')
def handle_unified_payment_success(tenant_id, transaction_id, validation_id=None):
    """Enhanced payment success handler for unified registration flow"""
    try:
        if BillingService.validate_payment(transaction_id, tenant_id, validation_id):
            # Update transaction status to SUCCESS
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id,
                tenant_id=tenant_id
            ).first()
            
            if transaction:
                transaction.status = 'SUCCESS'
                transaction.updated_at = datetime.utcnow()
                db.session.commit()

            # Get tenant and user for activation
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found for payment success")
                flash('Payment successful, but tenant not found. Please contact support.', 'error')
                return redirect(url_for('dashboard'))

            # Activate the user account (was set to inactive during unified registration)
            user = SaasUser.query.get(transaction.user_id)
            if user and not user.is_active:
                user.is_active = True
                user.email_verified = True  # Auto-verify on successful payment
                db.session.commit()
                logger.info(f"Activated user {user.username} after successful payment")

            if tenant.status == 'pending':
                logger.info(f"Payment successful for tenant {tenant.name}. Creating Odoo database.")
                
                # Get plan modules
                subscription_plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
                plan_modules = subscription_plan.modules if subscription_plan and subscription_plan.modules else []
                
                # Import create_database function
                try:
                    from app import create_database
                    from flask import current_app
                    
                    # Create database in background after successful payment
                    executor = ThreadPoolExecutor(max_workers=1)
                    executor.submit(
                        run_async_in_background, 
                        create_database(
                            tenant.database_name, 
                            tenant.admin_username, 
                            tenant.get_admin_password(), 
                            plan_modules,
                            current_app._get_current_object()  # Pass app instance
                        )
                    )
                    executor.shutdown(wait=False)
                    
                    # Update tenant status to 'creating' to indicate database creation is in progress
                    tenant.status = 'creating'
                    db.session.commit()
                    
                    logger.info(f"Database creation initiated for tenant {tenant.name}")
                    
                    # Send welcome email (if email service is configured)
                    try:
                        BillingService.send_welcome_email(user, tenant)
                    except Exception as email_error:
                        logger.warning(f"Failed to send welcome email: {email_error}")
                    
                except ImportError as e:
                    logger.error(f"Failed to import create_database function: {e}")
                    flash('Payment successful, but database creation failed to start. Please contact support.', 'warning')
                except Exception as e:
                    logger.error(f"Failed to start database creation: {e}")
                    flash('Payment successful, but database creation failed to start. Please contact support.', 'warning')
            
            flash('Payment successful! Your Odoo instance is being created and will be ready shortly. Check your email for login credentials.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Payment validation failed.', 'error')
            return redirect(url_for('unified_register'))

    except Exception as e:
        error_tracker.log_error(e, {
            'tenant_id': tenant_id,
            'transaction_id': transaction_id,
            'validation_id': validation_id,
            'function': 'handle_unified_payment_success'
        })
        flash('Error processing payment success.', 'error')
        return redirect(url_for('dashboard'))

@staticmethod
@track_errors('send_welcome_email')
def send_welcome_email(user, tenant):
    """Send welcome email with login credentials and setup instructions"""
    try:
        # This is a placeholder for email functionality
        # You can integrate with services like SendGrid, Mailgun, or AWS SES
        
        logger.info(f"Would send welcome email to {user.email} for tenant {tenant.subdomain}")
        
        # Email content would include:
        # - Welcome message
        # - Odoo instance URL: https://{tenant.subdomain}.{domain}
        # - Login credentials (encrypted or temporary)
        # - Setup guide links
        # - Support contact information
        
        return True
        
    except Exception as e:
        error_tracker.log_error(e, {
            'user_id': user.id,
            'tenant_id': tenant.id,
            'function': 'send_welcome_email'
        })
        return False

@staticmethod
@track_errors('handle_unified_payment_fail')
def handle_unified_payment_fail(tenant_id, transaction_id):
    """Enhanced payment failure handler for unified registration"""
    try:
        # Update transaction status first
        transaction = PaymentTransaction.query.filter_by(
            transaction_id=transaction_id,
            tenant_id=tenant_id
        ).first()

        if transaction:
            transaction.status = 'FAILED'
            transaction.updated_at = datetime.utcnow()

            # Deactivate the user account
            user = SaasUser.query.get(transaction.user_id)
            if user:
                user.is_active = False
                logger.info(f"Deactivated user {user.username} due to payment failure")

            db.session.commit()

        # Get tenant for cleanup
        tenant = Tenant.query.get(tenant_id)
        
        if tenant:
            logger.info(f"Payment failed for tenant {tenant.name} (ID: {tenant_id}). Cleaning up tenant record.")
            
            try:
                # Update worker tenant count
                workers = WorkerInstance.query.filter(WorkerInstance.current_tenants > 0).all()
                for worker in workers:
                    if worker.current_tenants > 0:
                        worker.current_tenants -= 1
                        logger.info(f"Decremented tenant count for worker {worker.name}")
                
                # Delete tenant-related records in proper order
                TenantUser.query.filter_by(tenant_id=tenant_id).delete()
                logger.info(f"Deleted TenantUser records for tenant {tenant_id}")
                
                # Delete credential access logs if any
                CredentialAccess.query.filter_by(tenant_id=tenant_id).delete()
                logger.info(f"Deleted CredentialAccess records for tenant {tenant_id}")
                
                # Don't delete the user account in unified registration
                # Just keep it inactive so they can try again
                
                # Delete the tenant itself
                db.session.delete(tenant)
                db.session.commit()
                logger.info(f"Successfully deleted tenant {tenant.name} (ID: {tenant_id})")
                
                flash('Payment failed. Please try registering again or contact support if you continue having issues.', 'error')
                
            except Exception as cleanup_error:
                db.session.rollback()
                logger.error(f"Error during tenant cleanup: {cleanup_error}")
                error_tracker.log_error(cleanup_error, {
                    'tenant_id': tenant_id,
                    'transaction_id': transaction_id,
                    'cleanup_phase': 'tenant_deletion'
                })
                flash('Payment failed. There was an issue cleaning up. Please contact support.', 'error')
        else:
            logger.warning(f"Tenant {tenant_id} not found during payment failure cleanup")
            flash('Payment failed.', 'error')

        return redirect(url_for('unified_register'))

    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {
            'tenant_id': tenant_id,
            'transaction_id': transaction_id,
            'function': 'handle_unified_payment_fail'
        })
        flash('Error processing payment failure. Please contact support.', 'error')
        return redirect(url_for('unified_register'))


# Add these routes to your register_billing_routes function in billing.py

def register_unified_billing_routes(app, csrf=None):
    """Register unified registration billing routes"""
    
    @app.route('/billing/unified/<int:tenant_id>/success', methods=['GET', 'POST'])
    @csrf.exempt
    @track_errors('unified_payment_success_route')
    def unified_payment_success(tenant_id):
        logger.debug(f"Unified Success Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        
        transaction_id = request.form.get('tran_id') or request.form.get('value_d')
        validation_id = request.form.get('val_id')
        logger.debug(f"Extracted Parameters: transaction_id={transaction_id}, validation_id={validation_id}")

        if not validation_id:
            logger.error(f"No validation ID in query params for unified registration: {request.args.to_dict()}")
            flash('Invalid payment validation. Please contact support.', 'error')
            return redirect(url_for('unified_register'))

        if not transaction_id:
            transaction = PaymentTransaction.query.filter_by(
                tenant_id=tenant_id,
                status='PENDING'
            ).order_by(PaymentTransaction.created_at.desc()).first()
            if transaction:
                transaction_id = transaction.transaction_id
                logger.info(f"Fallback: Using latest pending transaction {transaction_id} for tenant {tenant_id}")
            else:
                logger.error(f"No transaction ID and no pending transaction for tenant {tenant_id}")
                flash('Invalid transaction. Please contact support.', 'error')
                return redirect(url_for('unified_register'))

        return BillingService.handle_unified_payment_success(tenant_id, transaction_id, validation_id)

    @app.route('/billing/unified/<int:tenant_id>/fail', methods=['GET', 'POST'])
    @csrf.exempt
    @track_errors('unified_payment_fail_route')
    def unified_payment_fail(tenant_id):
        logger.debug(f"Unified Fail Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        
        transaction_id = (request.args.get('tran_id') or 
                         request.args.get('value_d') or 
                         request.form.get('tran_id') or 
                         request.form.get('value_d'))
        
        logger.debug(f"Extracted Parameter: transaction_id={transaction_id}")

        if not transaction_id:
            logger.error(f"No transaction ID in unified payment fail callback")
            # Try to find and clean up pending tenant anyway
            try:
                tenant = Tenant.query.get(tenant_id)
                if tenant and tenant.status == 'pending':
                    logger.warning(f"Cleaning up pending tenant {tenant_id} even without transaction_id")
                    return BillingService.handle_unified_payment_fail(tenant_id, None)
            except Exception as e:
                logger.error(f"Error in unified payment fail fallback cleanup: {e}")
            
            flash('Payment failed. Please try again.', 'error')
            return redirect(url_for('unified_register'))
        
        return BillingService.handle_unified_payment_fail(tenant_id, transaction_id)

    @app.route('/billing/unified/<int:tenant_id>/cancel', methods=['GET', 'POST'])
    @csrf.exempt
    @track_errors('unified_payment_cancel_route')
    def unified_payment_cancel(tenant_id):
        logger.debug(f"Unified Cancel Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        transaction_id = request.args.get('tran_id') or request.args.get('value_d')
        logger.debug(f"Extracted Parameter: transaction_id={transaction_id}")

        if not transaction_id:
            logger.error(f"No transaction ID in unified payment cancel callback")
            flash('Payment was cancelled.', 'warning')
            return redirect(url_for('unified_register'))
        
        # Handle cancellation similar to failure for unified registration
        return BillingService.handle_unified_payment_fail(tenant_id, transaction_id)


class BillingService:
    """Service class to handle billing and payment operations with SSLCommerz"""

    # Enhanced payment initiation for unified registration
    @staticmethod
    @track_errors('initiate_unified_payment')
    def initiate_unified_payment(tenant_id, user_id, plan):
        """Initiate payment specifically for unified registration flow"""
        try:
            tenant = Tenant.query.get_or_404(tenant_id)
            user = SaasUser.query.get_or_404(user_id)

            if tenant.status != 'pending':
                raise ValueError(f"Tenant {tenant.subdomain} is not in pending status")

            plan_obj = SubscriptionPlan.query.filter_by(name=plan, is_active=True).first()
            if not plan_obj:
                raise ValueError(f"Invalid or inactive plan: {plan}")
            amount = plan_obj.price

            transaction_id = f"UNIFIED-{uuid.uuid4().hex[:16]}"
            domain = os.environ.get('DOMAIN', 'khudroo.com')
            protocol = request.scheme  # Gets 'http' or 'https' from current request
            
            # Use unified-specific URLs
            success_url = f"{protocol}://{domain}{url_for('unified_payment_success', tenant_id=tenant_id)}"
            fail_url = f"{protocol}://{domain}{url_for('unified_payment_fail', tenant_id=tenant_id)}"
            cancel_url = f"{protocol}://{domain}{url_for('unified_payment_cancel', tenant_id=tenant_id)}"
            ipn_url = f"{protocol}://{domain}/billing/ipn"

            # Prepare SSLCommerz payment request
            payload = {
                'store_id': SSLCOMMERZ_STORE_ID,
                'store_passwd': SSLCOMMERZ_STORE_PASSWORD,
                'total_amount': str(Decimal(str(amount))),
                'currency': 'BDT',
                'tran_id': transaction_id,
                'success_url': success_url,
                'fail_url': fail_url,
                'cancel_url': cancel_url,
                'ipn_url': ipn_url,
                'emi_option': 0,
                'cus_name': user.full_name or user.username,
                'cus_email': user.email,
                'cus_add1': user.company or 'Bangladesh',
                'cus_add2': '',
                'cus_city': 'N/A',
                'cus_postcode': 'N/A',
                'cus_country': 'Bangladesh',
                'cus_phone': 'N/A',
                'shipping_method': 'NO',
                'product_name': f"{plan} Plan - {tenant.name}",
                'product_category': 'SaaS-Registration',
                'product_profile': 'general',
                'num_of_item': 1,
                'value_a': str(tenant_id),  # Store tenant_id for IPN
                'value_b': str(user_id),
                'value_c': plan,
                'value_d': transaction_id
            }

            logger.info(f"Initiating unified payment for tenant {tenant_id}, transaction {transaction_id}")
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            BillingService._log_sslcommerz_request('POST', SSLCOMMERZ_SESSION_API, headers, payload)

            response = requests.post(SSLCOMMERZ_SESSION_API, data=payload, headers=headers, timeout=30)
            BillingService._log_sslcommerz_response(response)
            response_data = response.json()

            if response.status_code != 200 or response_data.get('status') != 'SUCCESS':
                logger.error(f"Unified payment initiation failed: {response_data.get('failedreason', 'Unknown error')}")
                raise Exception(f"Payment initiation failed: {response_data.get('failedreason', 'Unknown error')}")

            # Store transaction in database
            transaction = PaymentTransaction(
                transaction_id=transaction_id,
                validation_id=response_data.get('val_id'),
                tenant_id=tenant_id,
                user_id=user_id,
                amount=amount,
                status='PENDING',
                response_data=str(response_data)[:2000]
            )
            db.session.add(transaction)
            db.session.commit()

            logger.info(f"Unified payment initiated successfully for transaction {transaction_id}, val_id={response_data.get('val_id')}")
            return response_data.get('GatewayPageURL')

        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'user_id': user_id,
                'plan': plan,
                'function': 'initiate_unified_payment'
            })
            raise

    @staticmethod
    def _log_sslcommerz_request(method, url, headers, payload=None):
        """Log the full outgoing request to SSLCommerz"""
        safe_payload = {k: '[REDACTED]' if k == 'store_passwd' else v for k, v in (payload or {}).items()}
        log_data = {
            'method': method,
            'url': url,
            'headers': headers or {},
            'parameters': safe_payload
        }
        logger.debug(f"SSLCommerz Outgoing Request:\n"
                     f"  Method: {method}\n"
                     f"  URL: {url}\n"
                     f"  Headers: {json.dumps(headers or {}, indent=2)}\n"
                     f"  Parameters: {json.dumps(safe_payload, indent=2)}")

    @staticmethod
    def _log_sslcommerz_response(response):
        """Log the full response from SSLCommerz"""
        try:
            body = response.json() if response.headers.get('Content-Type', '').startswith('application/json') else response.text
        except ValueError:
            body = response.text
        log_data = {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'body': body
        }
        logger.debug(f"SSLCommerz Response:\n"
                     f"  Status Code: {response.status_code}\n"
                     f"  Headers: {json.dumps(dict(response.headers), indent=2)}\n"
                     f"  Body: {json.dumps(body, indent=2) if isinstance(body, dict) else body}")

    @staticmethod
    def _sort_keys(data_dict):
        """Sort dictionary keys for hash generation"""
        return [(key, data_dict[key]) for key in sorted(data_dict.keys())]

    @staticmethod
    @track_errors('initiate_payment')
    def initiate_payment(tenant_id, user_id, plan):
        """Initiate a payment for a tenant based on the subscription plan"""
        try:
            tenant = Tenant.query.get_or_404(tenant_id)
            user = SaasUser.query.get_or_404(user_id)

            if tenant.status != 'pending':
                raise ValueError(f"Tenant {tenant.subdomain} is not in pending status")

            plan_obj = SubscriptionPlan.query.filter_by(name=plan, is_active=True).first()
            if not plan_obj:
                raise ValueError(f"Invalid or inactive plan: {plan}")
            amount = plan_obj.price
            if not amount:
                raise ValueError(f"Invalid plan: {plan}")

            transaction_id = f"TXN-{uuid.uuid4().hex[:16]}"
            domain = os.environ.get('DOMAIN', 'khudroo.com')
            protocol = request.scheme  # Gets 'http' or 'https' from current request
            success_url = f"{protocol}://{domain}{url_for('payment_success', tenant_id=tenant_id)}"
            fail_url = f"{protocol}://{domain}{url_for('payment_fail', tenant_id=tenant_id)}"
            cancel_url = f"{protocol}://{domain}{url_for('payment_cancel', tenant_id=tenant_id)}"
            ipn_url = f"{protocol}://{domain}/billing/ipn"

            # Prepare SSLCommerz payment request
            payload = {
                'store_id': SSLCOMMERZ_STORE_ID,
                'store_passwd': SSLCOMMERZ_STORE_PASSWORD,
                'total_amount': str(Decimal(str(amount))),
                'currency': 'BDT',
                'tran_id': transaction_id,
                'success_url': success_url,
                'fail_url': fail_url,
                'cancel_url': cancel_url,
                'ipn_url': ipn_url,
                'emi_option': 0,
                'cus_name': user.username,
                'cus_email': user.email,
                'cus_add1': 'Bangladesh',
                'cus_add2': '',
                'cus_city': 'N/A',
                'cus_postcode': 'N/A',
                'cus_country': 'Bangladesh',
                'cus_phone': 'N/A',
                'shipping_method': 'NO',
                'product_name': f"{plan} Plan Subscription",
                'product_category': 'SaaS-odoo',
                'product_profile': 'general',
                'num_of_item': 1,
                'value_a': generate_random_alphanumeric(),
                'value_b': str(user_id),
                'value_c': plan,
                'value_d': transaction_id
            }

            logger.info(f"Initiating payment for tenant {tenant_id}, transaction {transaction_id}")
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            BillingService._log_sslcommerz_request('POST', SSLCOMMERZ_SESSION_API, headers, payload)

            response = requests.post(SSLCOMMERZ_SESSION_API, data=payload, headers=headers, timeout=30)
            BillingService._log_sslcommerz_response(response)
            response_data = response.json()

            if response.status_code != 200 or response_data.get('status') != 'SUCCESS':
                logger.error(f"Payment initiation failed: {response_data.get('failedreason', 'Unknown error')}")
                raise Exception(f"Payment initiation failed: {response_data.get('failedreason', 'Unknown error')}")

            # Store transaction in database
            transaction = PaymentTransaction(
                transaction_id=transaction_id,
                validation_id=response_data.get('val_id'),
                tenant_id=tenant_id,
                user_id=user_id,
                amount=amount,
                status='PENDING',
                response_data=str(response_data)[:2000]
            )
            db.session.add(transaction)
            db.session.commit()

            logger.info(f"Payment initiated successfully for transaction {transaction_id}, val_id={response_data.get('val_id')}")
            return response_data.get('GatewayPageURL')

        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'user_id': user_id,
                'plan': plan,
                'function': 'initiate_payment'
            })
            raise

    @staticmethod
    @track_errors('validate_payment')
    def validate_payment(transaction_id, tenant_id, validation_id=None):
        """Validate payment status with SSLCommerz"""
        try:
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id,
                tenant_id=tenant_id
            ).first()

            if not transaction:
                logger.error(f"Transaction {transaction_id} not found for tenant {tenant_id}")
                return False
            if transaction.validation_id and validation_id != transaction.validation_id:
                logger.error(f"Validation ID mismatch for transaction {transaction_id} (expected {transaction.validation_id}, got {validation_id})")
                return False
            return True

        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'transaction_id': transaction_id,
                'tenant_id': tenant_id,
                'function': 'validate_payment'
            })
            return False

    @staticmethod
    @track_errors('validate_ipn_hash')
    def validate_ipn_hash(ipn_data):
        """Validate IPN hash as per SSLCommerz requirements"""
        try:
            if 'verify_key' not in ipn_data or 'verify_sign' not in ipn_data:
                logger.error(f"Missing verify_key or verify_sign in IPN data:\n"
                             f"  Data: {json.dumps(ipn_data, indent=2)}")
                return False

            check_params = {}
            verify_key = ipn_data['verify_key'].split(',')
            for key in verify_key:
                if key in ipn_data:
                    check_params[key] = ipn_data[key]

            store_pass = SSLCOMMERZ_STORE_PASSWORD.encode()
            store_pass_hash = hashlib.md5(store_pass).hexdigest()
            check_params['store_passwd'] = store_pass_hash
            check_params = BillingService._sort_keys(check_params)

            sign_string = ''
            for key, value in check_params:
                sign_string += f"{key}={value}&"
            sign_string = sign_string.rstrip('&')
            sign_string_hash = hashlib.md5(sign_string.encode()).hexdigest()

            if sign_string_hash == ipn_data['verify_sign']:
                logger.info(f"IPN hash validation successful for transaction {ipn_data.get('tran_id')}")
                return True
            logger.error(f"IPN hash validation failed. Expected: {sign_string_hash}, Received: {ipn_data['verify_sign']}")
            return False

        except Exception as e:
            error_tracker.log_error(e, {
                'function': 'validate_ipn_hash',
                'ipn_data': {k: '[REDACTED]' if k == 'store_passwd' else v for k, v in ipn_data.items()}
            })
            return False

    @staticmethod
    @track_errors('handle_payment_success')
    def handle_payment_success(tenant_id, transaction_id, validation_id=None):
        """Handle successful payment callback and create database"""
        try:
            if BillingService.validate_payment(transaction_id, tenant_id, validation_id):
                # Update transaction status to SUCCESS
                transaction = PaymentTransaction.query.filter_by(
                    transaction_id=transaction_id,
                    tenant_id=tenant_id
                ).first()
                
                if transaction:
                    transaction.status = 'SUCCESS'
                    transaction.updated_at = datetime.utcnow()
                    db.session.commit()

                # Get tenant and create database NOW (after successful payment)
                tenant = Tenant.query.get(tenant_id)
                if tenant and tenant.status == 'pending':
                    logger.info(f"Payment successful for tenant {tenant.name}. Creating Odoo database.")
                    
                    # Get plan modules
                    subscription_plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
                    plan_modules = subscription_plan.modules if subscription_plan.modules else []
                    
                    # Import create_database function
                    try:
                        from app import create_database
                        from flask import current_app
                        
                        # Create database in background after successful payment
                        executor = ThreadPoolExecutor(max_workers=1)
                        executor.submit(
                            run_async_in_background, 
                            create_database(
                                tenant.database_name, 
                                tenant.admin_username, 
                                tenant.get_admin_password(), 
                                plan_modules,
                                current_app._get_current_object()  # Pass app instance
                            )
                        )
                        executor.shutdown(wait=False)
                        
                        # Update tenant status to 'creating' to indicate database creation is in progress
                        tenant.status = 'creating'
                        db.session.commit()
                        
                        logger.info(f"Database creation initiated for tenant {tenant.name}")
                        
                    except ImportError as e:
                        logger.error(f"Failed to import create_database function: {e}")
                        flash('Payment successful, but database creation failed to start. Please contact support.', 'warning')
                    except Exception as e:
                        logger.error(f"Failed to start database creation: {e}")
                        flash('Payment successful, but database creation failed to start. Please contact support.', 'warning')
                
                flash('Payment successful! Your Odoo instance is being created and will be ready shortly.', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Payment validation failed.', 'error')
                return redirect(url_for('dashboard'))

        except Exception as e:
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'transaction_id': transaction_id,
                'validation_id': validation_id,
                'function': 'handle_payment_success'
            })
            flash('Error processing payment success.', 'error')
            return redirect(url_for('dashboard'))

    @staticmethod
    @track_errors('handle_payment_fail')
    def handle_payment_fail(tenant_id, transaction_id):
        """Handle failed payment callback with tenant cleanup (no database created yet)"""
        try:
            # Update transaction status first
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id,
                tenant_id=tenant_id
            ).first()

            if transaction:
                transaction.status = 'FAILED'
                transaction.updated_at = datetime.utcnow()
                db.session.commit()

            # Get tenant for cleanup - NOTE: No database was created yet, so only clean up tenant record
            tenant = Tenant.query.get(tenant_id)
            
            if tenant:
                logger.info(f"Payment failed for tenant {tenant.name} (ID: {tenant_id}). Cleaning up tenant record.")
                
                try:
                    # Update worker tenant count if applicable (decrement since we're removing the tenant)
                    workers = WorkerInstance.query.filter(WorkerInstance.current_tenants > 0).all()
                    for worker in workers:
                        if worker.current_tenants > 0:
                            worker.current_tenants -= 1
                            logger.info(f"Decremented tenant count for worker {worker.name}")
                    
                    # Delete tenant-related records in proper order
                    TenantUser.query.filter_by(tenant_id=tenant_id).delete()
                    logger.info(f"Deleted TenantUser records for tenant {tenant_id}")
                    
                    # Delete credential access logs if any
                    CredentialAccess.query.filter_by(tenant_id=tenant_id).delete()
                    logger.info(f"Deleted CredentialAccess records for tenant {tenant_id}")
                    
                    # Delete payment transactions for this tenant
                    PaymentTransaction.query.filter_by(tenant_id=tenant_id).delete()
                    logger.info(f"Deleted PaymentTransaction records for tenant {tenant_id}")
                    
                    # Delete the tenant itself
                    db.session.delete(tenant)
                    db.session.commit()
                    logger.info(f"Successfully deleted tenant {tenant.name} (ID: {tenant_id})")
                    
                    flash('Payment failed. The tenant registration has been cancelled.', 'error')
                    
                except Exception as cleanup_error:
                    db.session.rollback()
                    logger.error(f"Error during tenant cleanup: {cleanup_error}")
                    error_tracker.log_error(cleanup_error, {
                        'tenant_id': tenant_id,
                        'transaction_id': transaction_id,
                        'cleanup_phase': 'tenant_deletion'
                    })
                    flash('Payment failed. There was an issue cleaning up. Please contact support.', 'error')
            else:
                logger.warning(f"Tenant {tenant_id} not found during payment failure cleanup")
                flash('Payment failed.', 'error')

            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'transaction_id': transaction_id,
                'function': 'handle_payment_fail'
            })
            flash('Error processing payment failure. Please contact support.', 'error')
            return redirect(url_for('dashboard'))

    @staticmethod
    @track_errors('handle_payment_cancel')
    def handle_payment_cancel(tenant_id, transaction_id):
        """Handle cancelled payment callback with tenant cleanup"""
        try:
            # Update transaction status first
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id,
                tenant_id=tenant_id
            ).first()

            if transaction:
                transaction.status = 'CANCELLED'
                transaction.updated_at = datetime.utcnow()
                db.session.commit()

            # Same cleanup as payment fail since no database was created
            tenant = Tenant.query.get(tenant_id)
            
            if tenant:
                logger.info(f"Payment cancelled for tenant {tenant.name} (ID: {tenant_id}). Cleaning up tenant record.")
                
                try:
                    # Update worker tenant count
                    workers = WorkerInstance.query.filter(WorkerInstance.current_tenants > 0).all()
                    for worker in workers:
                        if worker.current_tenants > 0:
                            worker.current_tenants -= 1
                    
                    # Delete tenant-related records
                    TenantUser.query.filter_by(tenant_id=tenant_id).delete()
                    CredentialAccess.query.filter_by(tenant_id=tenant_id).delete()
                    PaymentTransaction.query.filter_by(tenant_id=tenant_id).delete()
                    db.session.delete(tenant)
                    db.session.commit()
                    
                    flash('Payment was cancelled. The tenant registration has been cancelled.', 'warning')
                    
                except Exception as cleanup_error:
                    db.session.rollback()
                    logger.error(f"Error during tenant cleanup after cancellation: {cleanup_error}")
                    flash('Payment cancelled. There was an issue cleaning up. Please contact support.', 'warning')
            else:
                flash('Payment was cancelled.', 'warning')

            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'transaction_id': transaction_id,
                'function': 'handle_payment_cancel'
            })
            flash('Error processing payment cancellation.', 'error')
            return redirect(url_for('dashboard'))

def register_billing_routes(app, csrf=None):
    """Register billing-related routes with the Flask app"""
    @app.route('/billing/<int:tenant_id>/pay', methods=['POST'])
    @login_required
    @track_errors('initiate_payment_route')
    def initiate_payment_route(tenant_id):
        from app import verify_tenant_access  # Move import here
        try:
            tenant = Tenant.query.get_or_404(tenant_id)
            if not verify_tenant_access(current_user.id, tenant_id):
                flash('Access denied to this tenant.', 'error')
                return redirect(url_for('dashboard'))

            payment_url = BillingService.initiate_payment(
                tenant_id=tenant_id,
                user_id=current_user.id,
                plan=tenant.plan
            )
            return redirect(payment_url)

        except Exception as e:
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'user_id': current_user.id,
                'function': 'initiate_payment_route'
            })
            flash('Failed to initiate payment. Please try again.', 'error')
            return redirect(url_for('dashboard'))

    @app.route('/billing/<int:tenant_id>/success', methods=['GET', 'POST'])
    @csrf.exempt
    @track_errors('payment_success_route')
    def payment_success(tenant_id):
        logger.debug(f"Success Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        
        transaction_id = request.form.get('tran_id') or request.form.get('value_d')
        validation_id = request.form.get('val_id')
        logger.debug(f"Extracted Parameters: transaction_id={transaction_id}, validation_id={validation_id}")

        if not validation_id:
            logger.error(
                f"No validation ID in query params: {request.args.to_dict()}, "
                f"for tenant {tenant_id}"
            )
            flash('Invalid validation ID. Please contact support.', 'error')
            return redirect(url_for('dashboard'))
        else:
            transaction = PaymentTransaction.query.filter_by(
                tenant_id=tenant_id
            ).first()
            if transaction:
                logger.info(f"Found transaction with validation ID {validation_id} for tenant {tenant_id}")
                transaction_id = transaction.transaction_id
            else:
                logger.error(
                    f"No transaction found with validation ID {validation_id} for tenant {tenant_id}"
                )
                flash('Invalid validation ID. Payment is being processed via notification.', 'warning')
                return redirect(url_for('dashboard'))

        if not transaction_id:
            transaction = PaymentTransaction.query.filter_by(
                tenant_id=tenant_id,
                status='PENDING'
            ).order_by(PaymentTransaction.created_at.desc()).first()
            if transaction:
                transaction_id = transaction.transaction_id
                logger.info(f"Fallback: Using latest pending transaction {transaction_id} for tenant {tenant_id}")
            else:
                logger.error(f"No transaction ID in query params: {request.args.to_dict()}, and no pending transaction for tenant {tenant_id}")
                flash('Invalid transaction ID. Payment is being processed via notification.', 'warning')
                return redirect(url_for('dashboard'))

        return BillingService.handle_payment_success(tenant_id, transaction_id, validation_id)

    @app.route('/billing/<int:tenant_id>/fail', methods=['GET', 'POST'])
    @csrf.exempt
    @track_errors('payment_fail_route')
    def payment_fail(tenant_id):
        logger.debug(f"Fail Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        
        # Get transaction ID from either args or form data
        transaction_id = (request.args.get('tran_id') or 
                         request.args.get('value_d') or 
                         request.form.get('tran_id') or 
                         request.form.get('value_d'))
        
        logger.debug(f"Extracted Parameter: transaction_id={transaction_id}")

        if not transaction_id:
            logger.error(f"No transaction ID in request. Args: {request.args.to_dict()}, Form: {request.form.to_dict()}")
            
            # Even without transaction_id, clean up pending tenant
            try:
                tenant = Tenant.query.get(tenant_id)
                if tenant and tenant.status == 'pending':
                    logger.warning(f"Cleaning up pending tenant {tenant_id} even without transaction_id")
                    return BillingService.handle_payment_fail(tenant_id, None)
            except Exception as e:
                logger.error(f"Error in fallback cleanup: {e}")
            
            flash('Payment failed. Invalid transaction information.', 'error')
            return redirect(url_for('dashboard'))
        
        return BillingService.handle_payment_fail(tenant_id, transaction_id)

    @app.route('/billing/<int:tenant_id>/cancel', methods=['GET', 'POST'])
    @csrf.exempt
    @track_errors('payment_cancel_route')
    def payment_cancel(tenant_id):
        logger.debug(f"Cancel Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        transaction_id = request.args.get('tran_id') or request.args.get('value_d')
        logger.debug(f"Extracted Parameter: transaction_id={transaction_id}")

        if not transaction_id:
            logger.error(f"No transaction ID in query params: {request.args.to_dict()}")
            # Clean up pending tenant even without transaction_id
            try:
                tenant = Tenant.query.get(tenant_id)
                if tenant and tenant.status == 'pending':
                    return BillingService.handle_payment_cancel(tenant_id, None)
            except Exception as e:
                logger.error(f"Error in cancel cleanup: {e}")
            
            flash('Invalid transaction ID.', 'error')
            return redirect(url_for('dashboard'))
        
        return BillingService.handle_payment_cancel(tenant_id, transaction_id)

    @app.route('/billing/ipn', methods=['POST'])
    @csrf.exempt
    @track_errors('ipn_route')
    def ipn():
        """Handle IPN (Instant Payment Notification) from SSLCommerz"""
        logger.debug(f"IPN Request Received:\n"
                     f"  Method: {request.method}\n"
                     f"  URL: {request.url}\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}\n"
                     f"  Headers: {json.dumps(dict(request.headers), indent=2)}\n"
                     f"  Remote Address: {request.remote_addr}\n"
                     f"  User Agent: {request.user_agent}")
        try:
            data = request.form.to_dict()
            transaction_id = data.get('tran_id') or data.get('value_d')
            validation_id = data.get('val_id')
            tenant_id = int(data.get('value_a')) if data.get('value_a').isdigit() else None
            logger.debug(f"IPN Extracted Parameters: transaction_id={transaction_id}, validation_id={validation_id}, tenant_id={tenant_id}")

            if not transaction_id or not tenant_id:
                logger.error(f"Invalid IPN data:\n"
                             f"  Data: {json.dumps(data, indent=2)}")
                return jsonify({'status': 'error', 'message': 'Invalid transaction or tenant ID'}), 400

            if not BillingService.validate_ipn_hash(data):
                logger.error(f"IPN hash validation failed for transaction {transaction_id}")
                return jsonify({'status': 'error', 'message': 'Invalid IPN hash'}), 400

            # For IPN success, also trigger database creation
            if data.get('status') == 'VALID':
                try:
                    BillingService.handle_payment_success(tenant_id, transaction_id, validation_id)
                    logger.info(f"IPN triggered database creation for transaction {transaction_id}, tenant {tenant_id}")
                except Exception as e:
                    logger.error(f"IPN database creation failed: {e}")

            if BillingService.validate_payment(transaction_id, tenant_id, validation_id):
                logger.info(f"IPN validated for transaction {transaction_id}, tenant {tenant_id}")
                return jsonify({'status': 'success'}), 200
            else:
                logger.error(f"IPN validation failed for transaction {transaction_id}")
                return jsonify({'status': 'error', 'message': 'Validation failed'}), 400

        except Exception as e:
            error_tracker.log_error(e, {
                'function': 'ipn',
                'data': {k: '[REDACTED]' if k == 'store_passwd' else v for k, v in request.form.to_dict().items()}
            })
            return jsonify({'status': 'error', 'message': 'IPN processing failed'}), 500
    
    @staticmethod
    @track_errors('update_tenant_status_to_failed')
    def _update_tenant_status_to_failed(db_name, error_message, app=None):
        """Update tenant status to failed when database creation fails"""
        try:
            from models import Tenant
            from flask import current_app
            app_to_use = app if app else current_app
            
            # Create application context for background thread
            with app_to_use.app_context():
                tenant = Tenant.query.filter_by(database_name=db_name).first()
                if tenant:
                    tenant.status = 'failed'
                    db.session.commit()
                    logger.error(f"Updated tenant {tenant.id} status to failed: {error_message}")
                else:
                    logger.error(f"Could not find tenant with database_name {db_name} to update to failed status")
        except Exception as e:
            logger.error(f"Failed to update tenant status to failed: {e}")
            error_tracker.log_error(e, {'database_name': db_name, 'error_message': error_message})