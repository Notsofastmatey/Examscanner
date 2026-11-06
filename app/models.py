from app import db, login
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    papers = db.relationship('Paper', backref='author', lazy='dynamic')
    courses = db.relationship('Course', backref='author', lazy='dynamic')

    def __repr__(self):
        return '<User {}>'.format(self.username)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_name = db.Column(db.String(140))
    filename = db.Column(db.String(300))
    created_time = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    page_count = db.Column(db.Integer)
    mark_scheme_filename = db.Column(db.String(300))
    layout_filename = db.Column(db.String(300))     # optional scan of the printed paper
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    course = db.relationship('Course')
    questions = db.relationship('Question', backref='paper', lazy='dynamic',
                                order_by='Question.position', cascade='all, delete-orphan')
    regions = db.relationship('Region', backref='paper', lazy='dynamic',
                              cascade='all, delete-orphan')
    batches = db.relationship('Batch', backref='paper', lazy='dynamic', cascade='all, delete-orphan')
    scripts = db.relationship('Script', backref='paper', lazy='dynamic', order_by='Script.number')

    def __repr__(self):
            return '<Paper {}>'.format(self.paper_name)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('paper.id'), index=True)
    label = db.Column(db.String(20))
    position = db.Column(db.Integer, default=0)
    max_mark = db.Column(db.Integer)
    mark_scheme = db.Column(db.Text)
    guidance = db.Column(db.Text)
    class_comment = db.Column(db.Text)      # feedback on this question for the whole class
    topic = db.Column(db.String(20))        # a topic code from the paper's course, e.g. 1.1.1
    regions = db.relationship('Region', backref='question', lazy='dynamic',
                              cascade='all, delete-orphan')

    def __repr__(self):
        return '<Question {}>'.format(self.label)

    def to_dict(self):
        return {'id': self.id, 'label': self.label, 'max_mark': self.max_mark,
                'topic': self.topic or '', 'regions': self.regions.count()}

# A course (a specification, or a scheme of work) and its topics. Questions are tagged
# with topic codes so student reports can group marks and point to revision material.
# Everything subject-specific lives here, so any subject can bring its own.
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(140))            # e.g. OCR GCSE Computer Science (J277)
    subject = db.Column(db.String(80))          # e.g. Computer Science
    sections = db.Column(db.JSON)               # {"1": "Computer systems", ...} keyed by the code's first part
    topic_note = db.Column(db.Text)             # shown to students under the topic table
    resource_name = db.Column(db.String(80))    # e.g. Craig'n'Dave
    resource_url = db.Column(db.String(300))    # where to find all of them
    topics = db.relationship('Topic', backref='course', lazy='dynamic', order_by='Topic.position',
                             cascade='all, delete-orphan')

class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), index=True)
    position = db.Column(db.Integer, default=0)
    code = db.Column(db.String(20))
    name = db.Column(db.String(140))
    revise = db.Column(db.JSON)                 # ["what to revise", ...]
    videos = db.Column(db.JSON)                 # [["title", "url"], ...]

# A box drawn on the master paper. Coordinates are fractions (0-1) of the page
# size so they apply to scans at any resolution. kind is 'answer' or 'name'.
class Region(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('paper.id'), index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=True)
    kind = db.Column(db.String(10), default='answer')
    page = db.Column(db.Integer)
    x = db.Column(db.Float)
    y = db.Column(db.Float)
    w = db.Column(db.Float)
    h = db.Column(db.Float)

    def to_dict(self):
        return {'id': self.id, 'question_id': self.question_id, 'kind': self.kind,
                'page': self.page, 'x': self.x, 'y': self.y, 'w': self.w, 'h': self.h}

# One uploaded scan of a pile of scripts
class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('paper.id'), index=True)
    filename = db.Column(db.String(300))
    created_time = db.Column(db.DateTime, default=datetime.utcnow)
    scripts = db.relationship('Script', backref='batch', lazy='dynamic', cascade='all, delete-orphan')

# One student's script. Markers only ever see its number, never the name.
class Script(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'), index=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('paper.id'), index=True)
    number = db.Column(db.Integer)
    student_name = db.Column(db.String(120))
    comment = db.Column(db.Text)            # overall feedback for this student
    answers = db.relationship('Answer', backref='script', lazy='dynamic', cascade='all, delete-orphan')

    def total(self):
        return sum(a.mark or 0 for a in self.answers)

# A student's answer to one question, cropped from their scan.
# ink is how much writing there is, used to spot blank answers.
class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), index=True)
    mark = db.Column(db.Integer)
    comment = db.Column(db.Text)
    ink = db.Column(db.Float)
    blank = db.Column(db.Boolean, default=False)
    # The marker's ticks, [[x, y], ...] as fractions of the answer image. Just for the marker: not counted.
    ticks = db.Column(db.JSON)
    question = db.relationship('Question')

    def to_dict(self):
        return {'id': self.id, 'script': self.script.number, 'mark': self.mark,
                'comment': self.comment or '', 'blank': bool(self.blank), 'ticks': self.ticks or []}

@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))