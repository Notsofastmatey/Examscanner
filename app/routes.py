from app import app, db
import os
from urllib.parse import urlsplit
from flask import send_from_directory, send_file, render_template, flash, redirect, url_for, request, abort, jsonify
from app.forms import LoginForm,RegistrationForm, PaperForm
from flask_login import current_user, login_user, logout_user, login_required
from app.models import User, Paper, Question, Region
from app.papers import prepare_paper, paper_dir, mark_scheme_image
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
        if not next_page or urlsplit(next_page).netloc != '':
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
            if file_ext not in app.config['UPLOAD_EXTENSIONS']:
                flash('Invalid file type. Only PDF files are accepted.')
                abort(400)
        myPath = os.path.join(app.config['UPLOAD_PATH'],current_user.get_id())
        os.makedirs(myPath, exist_ok=True)
        uploaded_file.save(os.path.join(app.config['UPLOAD_PATH'],current_user.get_id(), filename))
        paper = Paper(paper_name=form.paper.data, author=current_user, filename = filename)
        db.session.add(paper)
        db.session.commit()
        flash('Your paper has been added to the database.')
        try:
            for message in prepare_paper(paper):
                flash(message)
        except Exception:
            app.logger.exception('Could not prepare paper %s', paper.id)
            db.session.rollback()
            flash('The paper was saved, but it could not be read automatically.')
        return redirect(url_for('paper_template', id=paper.id))

    return render_template('user.html', user=user, form=form, papers=papers)


@app.route('/uploads/<filename>')
@login_required
def upload(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_PATH'], current_user.get_id()), filename)



def own_paper(id):
    paper = db.get_or_404(Paper, id)
    if paper.author != current_user:
        abort(404)
    return paper

def own_question(id):
    question = db.get_or_404(Question, id)
    own_paper(question.paper_id)
    return question

@app.route('/paper/<int:id>')
@login_required
def paper_template(id):
    paper = own_paper(id)
    return render_template('template.html', title=paper.paper_name, paper=paper,
                           questions=paper.questions.all())

@app.route('/paper/<int:id>/page/<int:n>')
@login_required
def paper_page(id, n):
    paper = own_paper(id)
    return send_from_directory(paper_dir(paper), 'page-{}.png'.format(n))

@app.route('/question/<int:id>/markscheme')
@login_required
def question_mark_scheme(id):
    question = own_question(id)
    path = mark_scheme_image(question)
    if not os.path.exists(path):
        abort(404)
    return send_file(path)

@app.route('/paper/<int:id>/data')
@login_required
def paper_data(id):
    paper = own_paper(id)
    return jsonify(questions=[q.to_dict() for q in paper.questions],
                   regions=[r.to_dict() for r in paper.regions])

@app.route('/paper/<int:id>/regions', methods=['POST'])
@login_required
def add_region(id):
    paper = own_paper(id)
    data = request.get_json()
    kind = 'name' if data.get('kind') == 'name' else 'answer'
    question = own_question(data['question_id']) if kind == 'answer' else None
    if kind == 'name':
        Region.query.filter_by(paper_id=paper.id, kind='name').delete()
    region = Region(paper=paper, question=question, kind=kind, page=int(data['page']),
                    **{k: float(data[k]) for k in ('x', 'y', 'w', 'h')})
    db.session.add(region)
    db.session.commit()
    return jsonify(region.to_dict())

@app.route('/region/<int:id>', methods=['POST', 'DELETE'])
@login_required
def edit_region(id):
    region = db.get_or_404(Region, id)
    own_paper(region.paper_id)
    if request.method == 'DELETE':
        db.session.delete(region)
    else:
        data = request.get_json()
        for k in ('x', 'y', 'w', 'h'):
            setattr(region, k, float(data[k]))
    db.session.commit()
    return jsonify(ok=True)

@app.route('/paper/<int:id>/questions', methods=['POST'])
@login_required
def add_question(id):
    paper = own_paper(id)
    data = request.get_json()
    question = Question(paper=paper, label=data['label'][:20], max_mark=data.get('max_mark') or None,
                        position=paper.questions.count())
    db.session.add(question)
    db.session.commit()
    return jsonify(question.to_dict())

@app.route('/question/<int:id>', methods=['POST', 'DELETE'])
@login_required
def edit_question(id):
    question = own_question(id)
    if request.method == 'DELETE':
        db.session.delete(question)
    else:
        data = request.get_json()
        if 'label' in data:
            question.label = data['label'][:20]
        if 'max_mark' in data:
            question.max_mark = data['max_mark'] or None
    db.session.commit()
    return jsonify(ok=True)

@app.route('/showPDF')
@login_required
def showPDF():
    return render_template('showPDF.html')