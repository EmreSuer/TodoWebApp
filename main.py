from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from flask_migrate import Migrate
import secrets
import re
import dns.resolver
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
import os
from flask_apscheduler import APScheduler
import csv
import json
import io
import pandas as pd
from werkzeug.utils import secure_filename
import logging

# Load environment variables at the start of the application
load_dotenv()

# App Configuration
app = Flask(__name__)


# Database Configuration
#database_url = os.getenv('DATABASE_URL')
#if database_url and database_url.startswith('postgres://'):
    # Render uses 'postgres://' but SQLAlchemy needs 'postgresql://'
#   database_url = database_url.replace('postgres://', 'postgresql://', 1)
#   app.config['SQLALCHEMY_DATABASE_URI'] = database_url
#else:
#   app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'

import os

#app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///tasks.db')

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://todo_list_db_88z8_user:JJlkuTZm2hDNwBvcQYSVNb9STtuTNg9Z@dpg-cu0hqcdumphs7384bkog-a.oregon-postgres.render.com:5432/todo_list_db_88z8')


app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Mail Configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

print(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
logging.debug(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")


# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), unique=True)
    token_expiration = db.Column(db.DateTime)
    tasks = db.relationship('Task', backref='user', lazy=True)
    categories = db.relationship('Category', backref='user', lazy=True)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    deadline = db.Column(db.DateTime, nullable=True)
    reminder_sent = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(10), nullable=False, default='Medium')
    is_recurring = db.Column(db.Boolean, default=False)
    position = db.Column(db.Integer, default=0)
    completion_dates = db.relationship('TaskCompletionDate', backref='task', lazy=True)
    deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7), nullable=False, default='#000000')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tasks = db.relationship('Task', backref='category', lazy=True)


class TaskCompletionDate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    completion_date = db.Column(db.Date, nullable=False)

    # Ensure we don't have duplicate dates for the same task
    __table_args__ = (db.UniqueConstraint('task_id', 'completion_date'),)


# Helper Functions
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def verify_email_exists(email):
    try:
        domain = email.split('@')[1]
        dns.resolver.resolve(domain, 'MX')
        return True
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, IndexError):
        return False


def generate_verification_token():
    return secrets.token_urlsafe(32)


def send_verification_email(user):
    try:
        token = generate_verification_token()
        expiration = datetime.utcnow() + timedelta(hours=24)

        user.verification_token = token
        user.token_expiration = expiration
        db.session.commit()

        verification_url = url_for('verify_email', token=token, _external=True)

        msg = Message('Verify Your Email',
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[user.email])

        msg.body = f'''Please click the following link to verify your email:
{verification_url}

This link will expire in 24 hours.

If you did not register for this account, please ignore this email.
'''
        mail.send(msg)
        return True, None
    except Exception as e:
        return False, str(e)


def send_reminder_email(task, user):
    msg = Message('Task Reminder',
                  sender=app.config['MAIL_USERNAME'],
                  recipients=[user.email])

    status = "overdue" if task.is_overdue else "due soon"

    msg.body = f'''Hello {user.username},

This is a reminder that your task "{task.name}" is {status}.
Due date: {task.deadline.strftime('%Y-%m-%d')}

Task Details:
- Name: {task.name}
- Category: {task.category.name if task.category else 'Uncategorized'}
- Status: {"Overdue" if task.is_overdue else "Due Soon"}

Please complete this task as soon as possible.

Best regards,
Your Task Manager'''

    mail.send(msg)
    task.reminder_sent = True
    db.session.commit()


# Add this function to check and send reminders
def check_and_send_reminders():
    with app.app_context():
        current_time = datetime.utcnow()

        # Gets tasks that meet ALL these conditions:
        tasks = Task.query.filter_by(completed=False) \
            .filter(Task.deadline.isnot(None)) \
            .filter(Task.reminder_sent.is_(False)).all()

        for task in tasks:
            if (task.deadline < current_time or
                    current_time <= task.deadline <= (current_time + timedelta(days=1))):
                user = User.query.get(task.user_id)
                try:
                    send_reminder_email(task, user)
                except Exception as e:
                    pass


def calculate_progress_stats(tasks, period='all'):
    # Filter out deleted tasks first
    tasks = [t for t in tasks if not t.deleted]

    if not tasks:
        return {
            'completed': 0,
            'total': 0,
            'percentage': 0,
            'completed_high': 0,
            'completed_medium': 0,
            'completed_low': 0
        }

    current_date = datetime.utcnow()

    # Filter tasks based on period
    if period == 'month':
        tasks = [t for t in tasks if
                 (t.deadline and t.deadline.year == current_date.year and
                  t.deadline.month == current_date.month) or t.is_recurring]
    elif period == 'year':
        tasks = [t for t in tasks if
                 (t.deadline and t.deadline.year == current_date.year) or t.is_recurring]

    completed_tasks = 0
    completed_high = 0
    completed_medium = 0
    completed_low = 0

    # Calculate completions
    for task in tasks:
        is_completed = False
        if task.is_recurring:
            # For recurring tasks, check if completed today
            is_completed = any(cd.completion_date == current_date.date()
                               for cd in task.completion_dates)
        else:
            # For one-time tasks
            is_completed = task.completed

        if is_completed:
            completed_tasks += 1
            if task.priority == 'High':
                completed_high += 1
            elif task.priority == 'Medium':
                completed_medium += 1
            elif task.priority == 'Low':
                completed_low += 1

    total_tasks = len(tasks)
    percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return {
        'completed': completed_tasks,
        'total': total_tasks,
        'percentage': round(percentage, 1),
        'completed_high': completed_high,
        'completed_medium': completed_medium,
        'completed_low': completed_low
    }


def calculate_monthly_stats(tasks):
    current_date = datetime.utcnow()
    start_of_month = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

    # Filter tasks for current month - include all non-deleted tasks
    monthly_tasks = [t for t in tasks if not t.deleted]

    completed = 0
    active = 0
    overdue = 0

    # Calculate completed and active tasks
    for task in monthly_tasks:
        if task.is_recurring:
            # For recurring tasks, check if completed today
            if any(cd.completion_date == current_date.date() for cd in task.completion_dates):
                completed += 1
            else:
                active += 1
        else:
            # For one-time tasks
            if task.completed:
                completed += 1
            elif task.deadline and task.deadline < current_date:
                overdue += 1
            else:
                active += 1

    # Calculate completion rate based on all tasks
    total = len(monthly_tasks)
    completion_rate = round((completed / total * 100) if total > 0 else 0, 1)

    return {
        'completed': completed,
        'overdue': overdue,
        'active': active,
        'completion_rate': completion_rate
    }


# Add this helper function
def getContrastColor(hex_color):
    # Remove the # if present
    hex_color = hex_color.lstrip('#')

    # Convert to RGB
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Calculate luminance
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    # Return white for dark colors, black for light colors
    return '#ffffff' if luminance <= 0.5 else '#000000'


# Authentication Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))

        if not is_valid_email(email):
            flash('Invalid email format')
            return redirect(url_for('register'))

        if not verify_email_exists(email):
            flash('Invalid email domain. Please use a valid email address.')
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            email_verified=False
        )
        db.session.add(new_user)
        db.session.commit()

        try:
            success, error = send_verification_email(new_user)
            if success:
                flash('Registration successful! Please check your email to verify your account.')
            else:
                flash(f'Registration successful! However, there was an error sending the verification email: {error}')
        except Exception as e:
            flash(f'Registration successful! However, there was an error sending the verification email: {str(e)}')
            print(f"Error sending email: {e}")

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']

            user = User.query.filter_by(email=email).first()

            if user and check_password_hash(user.password, password):
                if not user.email_verified:
                    flash('Please verify your email before logging in.')
                    return redirect(url_for('login'))

                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('Invalid email or password')
    
        return render_template('login.html')
    except Exception as e:
        flash(f'An error occurred: {str(e)}')
        return redirect(url_for('login'))


@app.route('/debug')
def debug():
    return f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}"


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()

    if not user:
        flash('Invalid verification link')
        return redirect(url_for('login'))

    if datetime.utcnow() > user.token_expiration:
        flash('Verification link has expired. Please request a new one.')
        return redirect(url_for('login'))

    user.email_verified = True
    user.verification_token = None
    user.token_expiration = None
    db.session.commit()

    flash('Email verified successfully! You can now login.')
    return redirect(url_for('login'))


@app.route('/resend-verification')
def resend_verification():
    email = request.args.get('email')
    if not email:
        flash('Email address is required')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('No account found with that email address')
        return redirect(url_for('login'))

    if user.email_verified:
        flash('Email is already verified')
        return redirect(url_for('login'))

    try:
        send_verification_email(user)
        flash('Verification email has been resent')
    except Exception as e:
        flash('Error sending verification email')
        print(f"Error sending email: {e}")

    return redirect(url_for('login'))


# Task Routes
@app.route('/')
@login_required
def index():
    category_id = request.args.get('category', type=int, default=0)
    tasks_query = Task.query.filter_by(user_id=current_user.id, deleted=False)

    if category_id != 0:
        tasks_query = tasks_query.filter_by(category_id=category_id)

    tasks = tasks_query.order_by(
        Task.completed,
        Task.position,
        db.case(
            (Task.priority == 'High', 1),
            (Task.priority == 'Medium', 2),
            (Task.priority == 'Low', 3),
            else_=4
        ),
        Task.deadline.asc().nullslast()
    ).all()

    # Get all non-deleted tasks for progress calculation
    all_tasks = Task.query.filter_by(user_id=current_user.id, deleted=False).all()
    progress_stats = calculate_progress_stats(all_tasks)
    monthly_stats = calculate_monthly_stats(all_tasks)

    categories = Category.query.filter_by(user_id=current_user.id).all()

    current_time = datetime.utcnow()
    for task in tasks:
        task.is_overdue = False
        task.due_soon = False
        if task.deadline and not task.completed:
            task.is_overdue = task.deadline < current_time
            task.due_soon = current_time <= task.deadline <= (current_time + timedelta(days=1))

    return render_template('index.html',
                           tasks=tasks,
                           categories=categories,
                           selected_category=category_id,
                           current_time=current_time,
                           progress_stats=progress_stats,
                           monthly_stats=monthly_stats,
                           getContrastColor=getContrastColor)


@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    task_name = request.form['task']

    if len(task_name) > 120:
        return redirect(url_for('index'))

    category_id = request.form.get('category_id', type=int)
    deadline_str = request.form.get('deadline')
    priority = request.form.get('priority', 'Medium')
    is_recurring = request.form.get('is_recurring') == 'true'

    deadline = None
    if deadline_str and not is_recurring:
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d')

    new_task = Task(
        name=task_name,
        user_id=current_user.id,
        category_id=category_id,
        deadline=deadline,
        priority=priority,
        is_recurring=is_recurring
    )
    db.session.add(new_task)
    db.session.commit()

    if is_recurring:
        return redirect(url_for('yearly_view', task_id=new_task.id))
    return redirect(url_for('index'))


@app.route('/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return redirect(url_for('index'))

    task.deleted = True
    task.deleted_at = datetime.utcnow()
    db.session.commit()

    # Get updated progress stats for response
    all_tasks = Task.query.filter_by(user_id=current_user.id, deleted=False).all()
    progress_stats = calculate_progress_stats(all_tasks)

    flash('Task moved to trash')
    return redirect(url_for('index'))


@app.route('/toggle_complete/<int:task_id>')
@login_required
def toggle_complete(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return redirect(url_for('index'))

    if task.is_recurring:
        return redirect(url_for('yearly_view', task_id=task.id))
    else:
        task.completed = not task.completed
        db.session.commit()

    return redirect(url_for('index'))


# Category Routes
@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form['category_name']
    color = request.form['color']
    category = Category(name=name, color=color, user_id=current_user.id)
    db.session.add(category)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete_category/<int:category_id>')
@login_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    if category.user_id != current_user.id:
        return redirect(url_for('index'))

    Task.query.filter_by(category_id=category_id).update({Task.category_id: None})
    db.session.delete(category)
    db.session.commit()
    return redirect(url_for('index'))


# Add new route for toggling daily completion
@app.route('/toggle_daily_complete/<int:task_id>/<string:date>')
@login_required
def toggle_daily_complete(task_id, date):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return redirect(url_for('index'))

    completion_date = datetime.strptime(date, '%Y-%m-%d').date()

    existing_completion = TaskCompletionDate.query.filter_by(
        task_id=task_id,
        completion_date=completion_date
    ).first()

    if existing_completion:
        db.session.delete(existing_completion)
    else:
        new_completion = TaskCompletionDate(
            task_id=task_id,
            completion_date=completion_date
        )
        db.session.add(new_completion)

    db.session.commit()
    return redirect(url_for('yearly_view', task_id=task_id))


# Add new route for yearly view
@app.route('/yearly_view/<int:task_id>')
@login_required
def yearly_view(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return redirect(url_for('index'))

    completion_dates = {
        completion.completion_date
        for completion in task.completion_dates
    }

    year = 2025
    calendar_data = []
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    for month in range(1, 13):
        month_data = {
            'name': month_names[month - 1],
            'days': []
        }

        if month == 2:
            days_in_month = 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
        elif month in [4, 6, 9, 11]:
            days_in_month = 30
        else:
            days_in_month = 31

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            month_data['days'].append({
                'date': current_date,
                'completed': current_date in completion_dates
            })

        calendar_data.append(month_data)

    return render_template('yearly_view.html',
                           task=task,
                           calendar_data=calendar_data,
                           year=year)


# Add this new route for handling task reordering
@app.route('/reorder_tasks', methods=['POST'])
@login_required
def reorder_tasks():
    new_order = request.json
    for position, task_id in enumerate(new_order):
        task = Task.query.get(task_id)
        if task and task.user_id == current_user.id:
            task.position = position
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/update_description/<int:task_id>', methods=['POST'])
@login_required
def update_description(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    description = request.form.get('description', '')
    task.description = description
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/trash')
@login_required
def trash():
    deleted_tasks = Task.query.filter_by(
        user_id=current_user.id,
        deleted=True
    ).order_by(Task.deleted_at.desc()).all()

    return render_template('trash.html', tasks=deleted_tasks)


@app.route('/restore_task/<int:task_id>')
@login_required
def restore_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return redirect(url_for('trash'))

    task.deleted = False
    task.deleted_at = None
    db.session.commit()

    # Get updated progress stats for response
    all_tasks = Task.query.filter_by(user_id=current_user.id, deleted=False).all()
    progress_stats = calculate_progress_stats(all_tasks)

    flash('Task restored successfully')
    return redirect(url_for('trash'))


@app.route('/permanent_delete/<int:task_id>')
@login_required
def permanent_delete(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return redirect(url_for('trash'))

    # Delete completion dates first
    TaskCompletionDate.query.filter_by(task_id=task_id).delete()

    # Then delete the task
    db.session.delete(task)
    db.session.commit()
    flash('Task permanently deleted')
    return redirect(url_for('trash'))


@app.route('/update_task/<int:task_id>', methods=['POST'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    data = request.json
    task.name = data.get('name', task.name)
    task.priority = data.get('priority', task.priority)

    category_id = data.get('category_id')
    if category_id:
        category = Category.query.get(category_id)
        if category and category.user_id == current_user.id:
            task.category = category
    else:
        task.category = None

    db.session.commit()

    response_data = {
        'status': 'success',
        'category': {
            'id': task.category.id,
            'name': task.category.name,
            'color': task.category.color
        } if task.category else None
    }

    return jsonify(response_data)


scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


@scheduler.task('interval', id='check_reminders', hours=1)
def schedule_check_reminders():
    with app.app_context():
        check_and_send_reminders()


@app.route('/export_tasks/<format>')
@login_required
def export_tasks(format):
    tasks = Task.query.filter_by(user_id=current_user.id, deleted=False).all()

    # Prepare task data
    task_data = []
    for task in tasks:
        task_dict = {
            'name': task.name,
            'description': task.description,
            'completed': task.completed,
            'category': task.category.name if task.category else None,
            'deadline': task.deadline.strftime('%Y-%m-%d') if task.deadline else None,
            'priority': task.priority,
            'is_recurring': task.is_recurring
        }
        task_data.append(task_dict)

    if format == 'json':
        # Export as JSON
        output = io.StringIO()
        json.dump(task_data, output, indent=2)

        return Response(
            output.getvalue(),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment;filename=tasks.json'}
        )

    elif format == 'csv':
        # Export as CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=task_data[0].keys())
        writer.writeheader()
        writer.writerows(task_data)

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=tasks.csv'}
        )

    elif format == 'excel':
        # Export as Excel
        df = pd.DataFrame(task_data)
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='tasks.xlsx'
        )

    return redirect(url_for('index'))


@app.route('/import_tasks', methods=['POST'])
@login_required
def import_tasks():
    if 'file' not in request.files:
        flash('No file uploaded')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))

    try:
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()

        if file_ext not in ['json', 'csv', 'xlsx']:
            flash('Invalid file format. Please upload JSON, CSV, or Excel file.')
            return redirect(url_for('index'))

        # Process the file based on its format
        if file_ext == 'json':
            data = json.load(file)
        elif file_ext == 'csv':
            df = pd.read_csv(file)
            # Convert DataFrame to dict while handling date format
            data = df.replace({pd.NA: None}).to_dict('records')
        elif file_ext == 'xlsx':
            df = pd.read_excel(file)
            # Convert DataFrame to dict while handling date format
            data = df.replace({pd.NA: None}).to_dict('records')

        # Import tasks
        for task_data in data:
            # Get or create category if specified
            category = None
            if task_data.get('category'):
                category = Category.query.filter_by(
                    name=task_data['category'],
                    user_id=current_user.id
                ).first()
                if not category:
                    category = Category(
                        name=task_data['category'],
                        color='#000000',
                        user_id=current_user.id
                    )
                    db.session.add(category)
                    db.session.commit()

            # Handle deadline date
            deadline = None
            deadline_value = task_data.get('deadline')
            if deadline_value:
                try:
                    if isinstance(deadline_value, str):
                        deadline = datetime.strptime(deadline_value, '%Y-%m-%d')
                    elif isinstance(deadline_value, (pd.Timestamp, datetime)):
                        deadline = deadline_value
                    elif isinstance(deadline_value, float):
                        if not pd.isna(deadline_value):  # Check if it's not NaN
                            # Convert Excel date number to datetime
                            deadline = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + int(deadline_value) - 2)
                except (ValueError, TypeError):
                    # If date parsing fails, skip the deadline
                    deadline = None

            # Create new task
            new_task = Task(
                name=str(task_data['name']),  # Ensure name is string
                description=str(task_data.get('description', '')) if task_data.get('description') else None,
                completed=bool(task_data.get('completed', False)),
                user_id=current_user.id,
                category_id=category.id if category else None,
                deadline=deadline,
                priority=str(task_data.get('priority', 'Medium')),
                is_recurring=bool(task_data.get('is_recurring', False))
            )
            db.session.add(new_task)

        db.session.commit()
        flash('Tasks imported successfully')

    except Exception as e:
        flash(f'Error importing tasks: {str(e)}')

    return redirect(url_for('index'))


@app.route('/restore_all_tasks')
@login_required
def restore_all_tasks():
    # Restore all deleted tasks for the current user
    Task.query.filter_by(
        user_id=current_user.id,
        deleted=True
    ).update({
        'deleted': False,
        'deleted_at': None
    })

    db.session.commit()
    flash('All tasks restored successfully')
    return redirect(url_for('trash'))


@app.route('/permanent_delete_all')
@login_required
def permanent_delete_all():
    # Get all deleted tasks for the current user
    deleted_tasks = Task.query.filter_by(
        user_id=current_user.id,
        deleted=True
    ).all()

    # Delete completion dates for all tasks
    task_ids = [task.id for task in deleted_tasks]
    if task_ids:
        TaskCompletionDate.query.filter(
            TaskCompletionDate.task_id.in_(task_ids)
        ).delete(synchronize_session=False)

    # Delete all tasks
    for task in deleted_tasks:
        db.session.delete(task)

    db.session.commit()
    flash('All tasks in trash have been permanently deleted')
    return redirect(url_for('trash'))





if __name__ == "__main__":
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print(f"Database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    app.run(debug=True)
