import os
import uuid
import logging
import requests
import json
import hashlib
from decimal import Decimal
from datetime import datetime
from flask import url_for, redirect, flash, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db import db  # Import db from db.py
from utils import error_tracker, track_errors, logger  # Import error_tracker and logger from utils.py
from models import Tenant, SaasUser, SubscriptionPlan  # Import models

# SSLCommerz Sandbox Credentials
SSLCOMMERZ_STORE_ID = "kendr686995fcc52be"
SSLCOMMERZ_STORE_PASSWORD = "kendr686995fcc52be@ssl"
SSLCOMMERZ_SESSION_API = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
SSLCOMMERZ_VALIDATION_API = "https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php"

class PaymentTransaction(db.Model):
    """Model to store payment transaction details"""
    __tablename__ = 'payment_transactions'
    
    id = Column(Integer, primary_key=True)
    transaction_id = Column(String(100), unique=True, nullable=False)
    validation_id = Column(String(100), nullable=True)  # Store val_id from SSLCommerz
    tenant_id = Column(Integer, nullable=False)  # Just an integer, no foreign key
    user_id = Column(Integer, ForeignKey('saas_users.id'), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default='BDT')
    status = Column(String(50), default='PENDING')
    payment_method = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    response_data = Column(String(2000))  # Store raw response from SSLCommerz
    
    # Relationship with user (keeping this one)
    user = relationship('SaasUser', backref='payment_transactions')
    
    # NO tenant relationship - removed completely
    
    def get_tenant(self):
        """Get the associated tenant by manual lookup"""
        # Import here to avoid circular imports
        from models import Tenant
        return Tenant.query.get(self.tenant_id)
    
    def get_tenant_name(self):
        """Helper method to get tenant name safely"""
        tenant = self.get_tenant()
        return tenant.name if tenant else f"Unknown Tenant (ID: {self.tenant_id})"
    
    def __repr__(self):
        return f"<PaymentTransaction {self.transaction_id} - {self.status}>"

class BillingService:
    """Service class to handle billing and payment operations with SSLCommerz"""

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
            domain = os.environ.get('DOMAIN', 'localhost:8000')
            success_url = f"http://{domain}{url_for('payment_success', tenant_id=tenant_id)}"
            fail_url = f"http://{domain}{url_for('payment_fail', tenant_id=tenant_id)}"
            cancel_url = f"http://{domain}{url_for('payment_cancel', tenant_id=tenant_id)}"
            ipn_url = f"http://{domain}/billing/ipn"

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
                'product_category': 'SaaS',
                'product_profile': 'general',
                'num_of_item': 1,
                'value_a': str(tenant_id),
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

            val_id = validation_id or transaction.validation_id
            if not val_id:
                logger.error(f"No validation ID available for transaction {transaction_id}")
                return False

            payload = {
                'val_id': val_id,
                'store_id': SSLCOMMERZ_STORE_ID,
                'store_passwd': SSLCOMMERZ_STORE_PASSWORD,
                'format': 'json'
            }

            headers = {'Accept': 'application/json'}
            BillingService._log_sslcommerz_request('GET', SSLCOMMERZ_VALIDATION_API, headers, payload)
            response = requests.get(SSLCOMMERZ_VALIDATION_API, params=payload, headers=headers, timeout=30)
            BillingService._log_sslcommerz_response(response)
            validation_data = response.json()

            if response.status_code == 200 and validation_data.get('status') == 'VALIDATED':
                transaction.status = 'COMPLETED'
                transaction.response_data = str(validation_data)[:2000]
                transaction.updated_at = datetime.utcnow()

                tenant = Tenant.query.get(tenant_id)
                tenant.status = 'active'
                tenant.updated_at = datetime.utcnow()

                db.session.commit()
                logger.info(f"Payment validated and tenant {tenant_id} activated for transaction {transaction_id}")
                return True
            else:
                transaction.status = 'FAILED'
                transaction.response_data = str(validation_data)[:2000]
                db.session.commit()
                logger.error(f"Payment validation failed for transaction {transaction_id}: {validation_data.get('error', 'Unknown error')}")
                return False

        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'transaction_id': transaction_id,
                'tenant_id': tenant_id,
                'validation_id': val_id,
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
        """Handle successful payment callback"""
        try:
            if BillingService.validate_payment(transaction_id, tenant_id, validation_id):
                flash('Payment processing. Tenant will be activated soon.', 'success')
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
        """Handle failed payment callback"""
        try:
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id,
                tenant_id=tenant_id
            ).first()

            if transaction:
                transaction.status = 'FAILED'
                transaction.updated_at = datetime.utcnow()
                db.session.commit()

            flash('Payment failed. Please try again.', 'error')
            return redirect(url_for('dashboard'))

        except Exception as e:
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'transaction_id': transaction_id,
                'function': 'handle_payment_fail'
            })
            flash('Error processing payment failure.', 'error')
            return redirect(url_for('dashboard'))

    @staticmethod
    @track_errors('handle_payment_cancel')
    def handle_payment_cancel(tenant_id, transaction_id):
        """Handle cancelled payment callback"""
        try:
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id,
                tenant_id=tenant_id
            ).first()

            if transaction:
                transaction.status = 'CANCELLED'
                transaction.updated_at = datetime.utcnow()
                db.session.commit()

            flash('Payment was cancelled.', 'warning')
            return redirect(url_for('dashboard'))

        except Exception as e:
            error_tracker.log_error(e, {
                'tenant_id': tenant_id,
                'transaction_id': transaction_id,
                'function': 'handle_payment_cancel'
            })
            flash('Error processing payment cancellation.', 'error')
            return redirect(url_for('dashboard'))

def register_billing_routes(app):
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
    @track_errors('payment_success_route')
    def payment_success(tenant_id):
        logger.debug(f"Success Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        transaction_id = request.args.get('tran_id') or request.args.get('value_d')
        validation_id = request.args.get('val_id')
        logger.debug(f"Extracted Parameters: transaction_id={transaction_id}, validation_id={validation_id}")

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
    @track_errors('payment_fail_route')
    def payment_fail(tenant_id):
        logger.debug(f"Fail Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        transaction_id = request.args.get('tran_id') or request.args.get('value_d')
        logger.debug(f"Extracted Parameter: transaction_id={transaction_id}")

        if not transaction_id:
            logger.error(f"No transaction ID in query params: {request.args.to_dict()}")
            flash('Invalid transaction ID.', 'error')
            return redirect(url_for('dashboard'))
        return BillingService.handle_payment_fail(tenant_id, transaction_id)

    @app.route('/billing/<int:tenant_id>/cancel', methods=['GET', 'POST'])
    @track_errors('payment_cancel_route')
    def payment_cancel(tenant_id):
        logger.debug(f"Cancel Callback Received:\n"
                     f"  Query Params: {json.dumps(request.args.to_dict(), indent=2)}\n"
                     f"  Form Data: {json.dumps(request.form.to_dict(), indent=2)}")
        transaction_id = request.args.get('tran_id') or request.args.get('value_d')
        logger.debug(f"Extracted Parameter: transaction_id={transaction_id}")

        if not transaction_id:
            logger.error(f"No transaction ID in query params: {request.args.to_dict()}")
            flash('Invalid transaction ID.', 'error')
            return redirect(url_for('dashboard'))
        return BillingService.handle_payment_cancel(tenant_id, transaction_id)

    @app.route('/billing/ipn', methods=['POST'])
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