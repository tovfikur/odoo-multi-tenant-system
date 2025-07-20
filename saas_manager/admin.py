from flask import Blueprint, render_template, flash, request, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, NumberRange
from .models import db, SaasUser, TenantUser, SubscriptionPlan, Report
from .utils import admin_required, track_errors
import json
from datetime import datetime

# Define the admin Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Form for creating/editing subscription plans
class SubscriptionPlanForm(FlaskForm):
    name = StringField('Plan Name', validators=[DataRequired(), ])
    price_per_month = FloatField('Price per Month ($)', validators=[DataRequired(), NumberRange(min=0)])
    features = TextAreaField('Features (JSON)', validators=[DataRequired()])
    max_apps = IntegerField('Max Applications', validators=[DataRequired(), NumberRange(min=1)])
    max_users = IntegerField('Max Users', validators=[DataRequired(), NumberRange(min=1)])

@admin_bp.route('/reports/user_tenants')
@admin_required
@track_errors('admin_user_tenants_report')
def user_tenants_report():
    """
    Generate and display a report showing all users and their associated tenants.
    Only accessible to admin users.
    """
    try:
        # Fetch all users from the database
        users = SaasUser.query.all()
        user_tenant_data = []

        # Compile data for each user and their tenants
        for user in users:
            tenants = [tu.tenant for tu in user.tenants]
            user_tenant_data.append({
                'user': user,
                'tenants': tenants
            })

        # Store the report in the database
        report_data = [
            {
                'user_id': data['user'].id,
                'username': data['user'].username,
                'email': data['user'].email,
                'tenants': [{'name': t.name, 'subdomain': t.subdomain} for t in data['tenants']]
            } for data in user_tenant_data
        ]
        report = Report(
            report_type='user_tenants',
            content=json.dumps(report_data),
            created_at=datetime.utcnow()
        )
        db.session.add(report)
        db.session.commit()

        return render_template('admin_user_tenants.html', user_tenant_data=user_tenant_data)
    except Exception as e:
        db.session.rollback()
        flash('Error generating report. Please try again.', 'error')
        return render_template('admin_user_tenants.html', user_tenant_data=[])

@admin_bp.route('/reports/stored')
@admin_required
@track_errors('admin_stored_reports')
def stored_reports():
    """
    Display all stored reports.
    """
    try:
        reports = Report.query.order_by(Report.created_at.desc()).all()
        return render_template('admin_stored_reports.html', reports=reports)
    except Exception as e:
        flash('Error loading stored reports. Please try again.', 'error')
        return render_template('admin_stored_reports.html', reports=[])

@admin_bp.route('/subscriptions', methods=['GET', 'POST'])
@admin_required
@track_errors('admin_subscriptions')
def manage_subscriptions():
    """
    Manage subscription plans (create, view).
    """
    form = SubscriptionPlanForm()
    if form.validate_on_submit():
        try:
            # Validate JSON features
            try:
                features = json.loads(form.features.data)
            except json.JSONDecodeError:
                flash('Features must be valid JSON.', 'error')
                return render_template('admin_subscriptions.html', form=form, plans=SubscriptionPlan.query.all())

            plan = SubscriptionPlan(
                name=form.name.data,
                price_per_month=form.price_per_month.data,
                features=features,
                max_apps=form.max_apps.data,
                max_users=form.max_users.data,
                is_active=True
            )
            db.session.add(plan)
            db.session.commit()
            flash(f'Subscription plan "{form.name.data}" created successfully.', 'success')
            return redirect(url_for('admin.manage_subscriptions'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating subscription plan. Please try again.', 'error')

    plans = SubscriptionPlan.query.all()
    return render_template('admin_subscriptions.html', form=form, plans=plans)

@admin_bp.route('/subscriptions/<int:plan_id>/toggle', methods=['POST'])
@admin_required
@track_errors('toggle_subscription')
def toggle_subscription(plan_id):
    """
    Toggle the active status of a subscription plan.
    """
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    try:
        plan.is_active = not plan.is_active
        db.session.commit()
        status = 'activated' if plan.is_active else 'deactivated'
        flash(f'Subscription plan "{plan.name}" {status} successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to toggle plan: {str(e)}', 'error')
    return redirect(url_for('admin.manage_subscriptions'))