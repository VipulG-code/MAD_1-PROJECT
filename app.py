from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from models import db, User, Company, Student, PlacementDrive, Application
from datetime import datetime, date
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'placement-portal-iitm-mad1-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///placement_portal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'resumes')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── Role decorators ────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def company_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'company':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ─── DB initialisation ──────────────────────────────────────────────────────

def create_tables():
    db.create_all()
    if not User.query.filter_by(role='admin').first():
        admin = User(
            username='admin',
            email='admin@placement.edu',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Default admin created  ➜  username: admin | password: admin123")


# ─── Auth ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Your account has been deactivated.', 'danger')
                return redirect(url_for('login'))
            if user.role == 'company':
                company = Company.query.filter_by(user_id=user.id).first()
                if company:
                    if company.is_blacklisted:
                        flash('Your company account has been blacklisted.', 'danger')
                        return redirect(url_for('login'))
                    if company.approval_status != 'approved':
                        flash('Your company registration is pending admin approval.', 'warning')
                        return redirect(url_for('login'))
            if user.role == 'student':
                student = Student.query.filter_by(user_id=user.id).first()
                if student and student.is_blacklisted:
                    flash('Your account has been blacklisted.', 'danger')
                    return redirect(url_for('login'))
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif current_user.role == 'company':
        return redirect(url_for('company_dashboard'))
    elif current_user.role == 'student':
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/register/student', methods=['GET', 'POST'])
def register_student():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        roll_number = request.form.get('roll_number', '').strip()
        branch = request.form.get('branch', '').strip()
        cgpa = request.form.get('cgpa', '').strip()
        phone = request.form.get('phone', '').strip()

        if not all([username, email, password, full_name, roll_number]):
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('register_student'))
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('register_student'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register_student'))
        if Student.query.filter_by(roll_number=roll_number).first():
            flash('Roll number already registered.', 'danger')
            return redirect(url_for('register_student'))

        user = User(
            username=username, email=email,
            password_hash=generate_password_hash(password),
            role='student', is_active=True
        )
        db.session.add(user)
        db.session.flush()
        student = Student(
            user_id=user.id, full_name=full_name,
            roll_number=roll_number, branch=branch,
            cgpa=float(cgpa) if cgpa else None, phone=phone
        )
        db.session.add(student)
        db.session.commit()
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register_student.html')


@app.route('/register/company', methods=['GET', 'POST'])
def register_company():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        company_name = request.form.get('company_name', '').strip()
        hr_contact = request.form.get('hr_contact', '').strip()
        website = request.form.get('website', '').strip()
        description = request.form.get('description', '').strip()

        if not all([username, email, password, company_name]):
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('register_company'))
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('register_company'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register_company'))
        if Company.query.filter_by(company_name=company_name).first():
            flash('Company name already registered.', 'danger')
            return redirect(url_for('register_company'))

        user = User(
            username=username, email=email,
            password_hash=generate_password_hash(password),
            role='company', is_active=True
        )
        db.session.add(user)
        db.session.flush()
        company = Company(
            user_id=user.id, company_name=company_name,
            hr_contact=hr_contact, website=website,
            description=description, approval_status='pending'
        )
        db.session.add(company)
        db.session.commit()
        flash('Company registered! Awaiting admin approval before you can log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register_company.html')


# ─── Admin ──────────────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    total_students = Student.query.count()
    total_companies = Company.query.filter_by(approval_status='approved').count()
    total_drives = PlacementDrive.query.count()
    total_applications = Application.query.count()
    pending_companies = Company.query.filter_by(approval_status='pending').count()
    pending_drives = PlacementDrive.query.filter_by(status='pending').count()
    recent_applications = (Application.query
                           .order_by(Application.application_date.desc())
                           .limit(8).all())
    return render_template('admin/dashboard.html',
                           total_students=total_students,
                           total_companies=total_companies,
                           total_drives=total_drives,
                           total_applications=total_applications,
                           pending_companies=pending_companies,
                           pending_drives=pending_drives,
                           recent_applications=recent_applications)


@app.route('/admin/companies')
@login_required
@admin_required
def admin_companies():
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    query = Company.query
    if search:
        query = query.filter(Company.company_name.ilike(f'%{search}%'))
    if status_filter:
        query = query.filter(Company.approval_status == status_filter)
    companies = query.order_by(Company.created_at.desc()).all()
    return render_template('admin/companies.html', companies=companies,
                           search=search, status_filter=status_filter)


@app.route('/admin/company/<int:company_id>')
@login_required
@admin_required
def admin_company_detail(company_id):
    company = Company.query.get_or_404(company_id)
    drives = PlacementDrive.query.filter_by(company_id=company_id).order_by(PlacementDrive.created_at.desc()).all()
    return render_template('admin/company_detail.html', company=company, drives=drives)


@app.route('/admin/company/<int:company_id>/approve')
@login_required
@admin_required
def admin_approve_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.approval_status = 'approved'
    db.session.commit()
    flash(f'"{company.company_name}" has been approved.', 'success')
    return redirect(url_for('admin_companies'))


@app.route('/admin/company/<int:company_id>/reject')
@login_required
@admin_required
def admin_reject_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.approval_status = 'rejected'
    db.session.commit()
    flash(f'"{company.company_name}" has been rejected.', 'warning')
    return redirect(url_for('admin_companies'))


@app.route('/admin/company/<int:company_id>/blacklist')
@login_required
@admin_required
def admin_blacklist_company(company_id):
    company = Company.query.get_or_404(company_id)
    company.is_blacklisted = not company.is_blacklisted
    db.session.commit()
    action = 'blacklisted' if company.is_blacklisted else 'unblacklisted'
    flash(f'"{company.company_name}" has been {action}.', 'warning')
    return redirect(url_for('admin_companies'))


@app.route('/admin/company/<int:company_id>/delete')
@login_required
@admin_required
def admin_delete_company(company_id):
    company = Company.query.get_or_404(company_id)
    for drive in company.drives:
        Application.query.filter_by(drive_id=drive.id).delete()
        db.session.delete(drive)
    user = User.query.get(company.user_id)
    db.session.delete(company)
    if user:
        db.session.delete(user)
    db.session.commit()
    flash('Company and all associated data deleted.', 'success')
    return redirect(url_for('admin_companies'))


@app.route('/admin/students')
@login_required
@admin_required
def admin_students():
    search = request.args.get('search', '').strip()
    query = Student.query.join(User)
    if search:
        query = query.filter(
            db.or_(
                Student.full_name.ilike(f'%{search}%'),
                Student.roll_number.ilike(f'%{search}%'),
                Student.phone.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    students = query.order_by(Student.created_at.desc()).all()
    return render_template('admin/students.html', students=students, search=search)


@app.route('/admin/student/<int:student_id>')
@login_required
@admin_required
def admin_student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    applications = (Application.query.filter_by(student_id=student_id)
                    .order_by(Application.application_date.desc()).all())
    return render_template('admin/student_detail.html', student=student, applications=applications)


@app.route('/admin/student/<int:student_id>/blacklist')
@login_required
@admin_required
def admin_blacklist_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_blacklisted = not student.is_blacklisted
    db.session.commit()
    action = 'blacklisted' if student.is_blacklisted else 'unblacklisted'
    flash(f'"{student.full_name}" has been {action}.', 'warning')
    return redirect(url_for('admin_students'))


@app.route('/admin/student/<int:student_id>/delete')
@login_required
@admin_required
def admin_delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    Application.query.filter_by(student_id=student_id).delete()
    user = User.query.get(student.user_id)
    db.session.delete(student)
    if user:
        db.session.delete(user)
    db.session.commit()
    flash('Student deleted successfully.', 'success')
    return redirect(url_for('admin_students'))


@app.route('/admin/drives')
@login_required
@admin_required
def admin_drives():
    status_filter = request.args.get('status', '').strip()
    query = PlacementDrive.query
    if status_filter:
        query = query.filter(PlacementDrive.status == status_filter)
    drives = query.order_by(PlacementDrive.created_at.desc()).all()
    return render_template('admin/drives.html', drives=drives, status_filter=status_filter)


@app.route('/admin/drive/<int:drive_id>/approve')
@login_required
@admin_required
def admin_approve_drive(drive_id):
    drive = PlacementDrive.query.get_or_404(drive_id)
    drive.status = 'approved'
    db.session.commit()
    flash(f'Drive "{drive.job_title}" approved.', 'success')
    return redirect(url_for('admin_drives'))


@app.route('/admin/drive/<int:drive_id>/reject')
@login_required
@admin_required
def admin_reject_drive(drive_id):
    drive = PlacementDrive.query.get_or_404(drive_id)
    drive.status = 'rejected'
    db.session.commit()
    flash(f'Drive "{drive.job_title}" rejected.', 'warning')
    return redirect(url_for('admin_drives'))


@app.route('/admin/drive/<int:drive_id>/close')
@login_required
@admin_required
def admin_close_drive(drive_id):
    drive = PlacementDrive.query.get_or_404(drive_id)
    drive.status = 'closed'
    db.session.commit()
    flash(f'Drive "{drive.job_title}" closed.', 'info')
    return redirect(url_for('admin_drives'))


@app.route('/admin/applications')
@login_required
@admin_required
def admin_applications():
    applications = (Application.query
                    .order_by(Application.application_date.desc()).all())
    return render_template('admin/applications.html', applications=applications)


# ─── Company ────────────────────────────────────────────────────────────────

@app.route('/company/dashboard')
@login_required
@company_required
def company_dashboard():
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    drives = PlacementDrive.query.filter_by(company_id=company.id).order_by(PlacementDrive.created_at.desc()).all()
    drives_with_counts = [(d, Application.query.filter_by(drive_id=d.id).count()) for d in drives]
    return render_template('company/dashboard.html', company=company, drives_with_counts=drives_with_counts)


@app.route('/company/drive/create', methods=['GET', 'POST'])
@login_required
@company_required
def company_create_drive():
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    if company.approval_status != 'approved':
        flash('Admin approval required before creating placement drives.', 'warning')
        return redirect(url_for('company_dashboard'))
    if request.method == 'POST':
        job_title = request.form.get('job_title', '').strip()
        job_description = request.form.get('job_description', '').strip()
        eligibility_criteria = request.form.get('eligibility_criteria', '').strip()
        package = request.form.get('package', '').strip()
        location = request.form.get('location', '').strip()
        deadline_str = request.form.get('application_deadline', '')
        if not job_title or not deadline_str:
            flash('Job title and deadline are required.', 'danger')
            return redirect(url_for('company_create_drive'))
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
        drive = PlacementDrive(
            company_id=company.id,
            job_title=job_title,
            job_description=job_description,
            eligibility_criteria=eligibility_criteria,
            package=package,
            location=location,
            application_deadline=deadline,
            status='pending'
        )
        db.session.add(drive)
        db.session.commit()
        flash('Placement drive submitted for admin approval.', 'success')
        return redirect(url_for('company_dashboard'))
    return render_template('company/create_drive.html', company=company)


@app.route('/company/drive/<int:drive_id>/edit', methods=['GET', 'POST'])
@login_required
@company_required
def company_edit_drive(drive_id):
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    drive = PlacementDrive.query.filter_by(id=drive_id, company_id=company.id).first_or_404()
    if request.method == 'POST':
        drive.job_title = request.form.get('job_title', drive.job_title).strip()
        drive.job_description = request.form.get('job_description', drive.job_description)
        drive.eligibility_criteria = request.form.get('eligibility_criteria', drive.eligibility_criteria)
        drive.package = request.form.get('package', drive.package)
        drive.location = request.form.get('location', drive.location)
        deadline_str = request.form.get('application_deadline', '')
        if deadline_str:
            drive.application_deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
        drive.status = 'pending'
        db.session.commit()
        flash('Drive updated and resubmitted for approval.', 'success')
        return redirect(url_for('company_dashboard'))
    return render_template('company/edit_drive.html', drive=drive)


@app.route('/company/drive/<int:drive_id>/delete')
@login_required
@company_required
def company_delete_drive(drive_id):
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    drive = PlacementDrive.query.filter_by(id=drive_id, company_id=company.id).first_or_404()
    Application.query.filter_by(drive_id=drive_id).delete()
    db.session.delete(drive)
    db.session.commit()
    flash('Drive deleted.', 'success')
    return redirect(url_for('company_dashboard'))


@app.route('/company/drive/<int:drive_id>/close')
@login_required
@company_required
def company_close_drive(drive_id):
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    drive = PlacementDrive.query.filter_by(id=drive_id, company_id=company.id).first_or_404()
    drive.status = 'closed'
    db.session.commit()
    flash('Drive closed.', 'info')
    return redirect(url_for('company_dashboard'))


@app.route('/company/drive/<int:drive_id>/applications')
@login_required
@company_required
def company_drive_applications(drive_id):
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    drive = PlacementDrive.query.filter_by(id=drive_id, company_id=company.id).first_or_404()
    applications = Application.query.filter_by(drive_id=drive_id).all()
    return render_template('company/drive_applications.html', drive=drive, applications=applications)


@app.route('/company/application/<int:app_id>/update', methods=['POST'])
@login_required
@company_required
def company_update_application(app_id):
    application = Application.query.get_or_404(app_id)
    company = Company.query.filter_by(user_id=current_user.id).first_or_404()
    # Verify ownership
    PlacementDrive.query.filter_by(id=application.drive_id, company_id=company.id).first_or_404()
    new_status = request.form.get('status')
    if new_status in ['applied', 'shortlisted', 'selected', 'rejected']:
        application.status = new_status
        db.session.commit()
        flash('Application status updated.', 'success')
    return redirect(url_for('company_drive_applications', drive_id=application.drive_id))


# ─── Student ─────────────────────────────────────────────────────────────────

@app.route('/student/dashboard')
@login_required
@student_required
def student_dashboard():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    approved_drives = (PlacementDrive.query.filter_by(status='approved')
                       .order_by(PlacementDrive.created_at.desc()).all())
    my_applications = (Application.query.filter_by(student_id=student.id)
                       .order_by(Application.application_date.desc()).all())
    applied_drive_ids = {app.drive_id for app in my_applications}
    return render_template('student/dashboard.html',
                           student=student,
                           approved_drives=approved_drives,
                           my_applications=my_applications,
                           applied_drive_ids=applied_drive_ids,
                           today=date.today())


@app.route('/student/drives')
@login_required
@student_required
def student_drives():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    drives = (PlacementDrive.query.filter_by(status='approved')
              .order_by(PlacementDrive.created_at.desc()).all())
    applied_drive_ids = {app.drive_id for app in Application.query.filter_by(student_id=student.id).all()}
    return render_template('student/drives.html', drives=drives,
                           applied_drive_ids=applied_drive_ids, today=date.today())


@app.route('/student/drive/<int:drive_id>')
@login_required
@student_required
def student_drive_detail(drive_id):
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    drive = PlacementDrive.query.get_or_404(drive_id)
    if drive.status != 'approved':
        flash('This placement drive is not available.', 'warning')
        return redirect(url_for('student_drives'))
    existing_app = Application.query.filter_by(student_id=student.id, drive_id=drive_id).first()
    return render_template('student/drive_detail.html', drive=drive,
                           existing_app=existing_app, today=date.today())


@app.route('/student/drive/<int:drive_id>/apply', methods=['POST'])
@login_required
@student_required
def student_apply(drive_id):
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    if student.is_blacklisted:
        flash('Your account is blacklisted. You cannot apply.', 'danger')
        return redirect(url_for('student_drives'))
    drive = PlacementDrive.query.get_or_404(drive_id)
    if drive.status != 'approved':
        flash('This drive is not accepting applications.', 'warning')
        return redirect(url_for('student_drives'))
    if drive.application_deadline < date.today():
        flash('The application deadline has passed.', 'warning')
        return redirect(url_for('student_drive_detail', drive_id=drive_id))
    if Application.query.filter_by(student_id=student.id, drive_id=drive_id).first():
        flash('You have already applied for this drive.', 'warning')
        return redirect(url_for('student_drive_detail', drive_id=drive_id))
    cover_letter = request.form.get('cover_letter', '')
    application = Application(
        student_id=student.id,
        drive_id=drive_id,
        cover_letter=cover_letter,
        status='applied'
    )
    db.session.add(application)
    db.session.commit()
    flash('Application submitted successfully!', 'success')
    return redirect(url_for('student_applications'))


@app.route('/student/applications')
@login_required
@student_required
def student_applications():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    applications = (Application.query.filter_by(student_id=student.id)
                    .order_by(Application.application_date.desc()).all())
    return render_template('student/applications.html', applications=applications, student=student)


@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
@student_required
def student_profile():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        student.full_name = request.form.get('full_name', student.full_name).strip()
        student.branch = request.form.get('branch', student.branch)
        cgpa = request.form.get('cgpa', '').strip()
        student.cgpa = float(cgpa) if cgpa else student.cgpa
        student.phone = request.form.get('phone', student.phone)
        current_user.email = request.form.get('email', current_user.email)
        # Resume upload
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"resume_{student.id}_{file.filename}")
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                student.resume_filename = filename
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('student_profile'))
    return render_template('student/profile.html', student=student)


# ─── Error handlers ─────────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(debug=True)
