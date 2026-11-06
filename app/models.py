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
    questions = db.relationship('Question', backref='paper', lazy='dynamic',
                                order_by='Question.position', cascade='all, delete-orphan')
    regions = db.relationship('Region', backref='paper', lazy='dynamic',
                              cascade='all, delete-orphan')

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
    regions = db.relationship('Region', backref='question', lazy='dynamic',
                              cascade='all, delete-orphan')

    def __repr__(self):
        return '<Question {}>'.format(self.label)

    def to_dict(self):
        return {'id': self.id, 'label': self.label, 'max_mark': self.max_mark,
                'regions': self.regions.count()}

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

@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))