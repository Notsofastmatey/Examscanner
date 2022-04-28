from app import app, db
import os
import json
import git
import hashlib
import hmac
from flask import send_from_directory, render_template, flash, redirect, url_for, request, abort
from app.forms import LoginForm,RegistrationForm, PaperForm
from flask_login import current_user, login_user, logout_user, login_required
from app.models import User, Paper
from werkzeug.urls import url_parse
from werkzeug.utils import secure_filename

@app.route('/')
@app.route('/index')
@login_required
def index():
    papers = [
    { 
        'author': {'username': 'Susan'}, 
        'paper_name': 'Y11 Mock Exam' 
    },
    { 
        'author': {'username': 'Susan'}, 
        'paper_name': 'Y7 Winter Exam'  
    }
]
    return render_template("index.html", title='Home Page', papers=papers)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route('/crop')
@login_required
def crop():
    return render_template('crop.html', title='Crop Paper')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/user/<username>', methods=['GET', 'POST'])
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    papers=user.papers.all()
    form = PaperForm()
    if form.validate_on_submit():
        uploaded_file = request.files['file']
        filename = secure_filename(uploaded_file.filename)
        if filename != '':
            file_ext = os.path.splitext(filename)[1]
            #if file_ext not in app.config['UPLOAD_EXTENSIONS'] or \
                    #file_ext != uploaded_file.stream:
                #flash('Invalid file type. Only PDF files are accepted.')
                #abort(400)
        myPath = os.path.join(app.config['UPLOAD_PATH'],current_user.get_id())
        if os.path.isdir(myPath)==False:
            os.mkdir(myPath)
        uploaded_file.save(os.path.join(app.config['UPLOAD_PATH'],current_user.get_id(), filename))
        paper = Paper(paper_name=form.paper.data, author=current_user, filename = filename)
        db.session.add(paper)
        db.session.commit()
        flash('Your paper has been added to the database.')
        return redirect(url_for('user', username=user.username)) 

    return render_template('user.html', user=user, form=form, papers=papers)


@app.route('/uploads/<filename>')
@login_required
def upload(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_PATH'], current_user.get_id()), filename)

@app.route('/showPDF')
@login_required
def showPDF():
    return render_template('showPDF.html')