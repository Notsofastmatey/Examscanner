'''
Creates a demo account and loads sample ExamBuilder papers through the same code
as an upload, for trying the app out locally.

    .venv/Scripts/python seed_demo.py "../J27701 Computer systems June 2025.pdf" ...
'''
import os
import shutil
import sys
from app import app, db
from app.models import User, Paper
from app.papers import prepare_paper

DEMO_USERNAME = 'demo'
DEMO_PASSWORD = 'demo-password'

with app.app_context():
    user = User.query.filter_by(username=DEMO_USERNAME).first()
    if user is None:
        user = User(username=DEMO_USERNAME, email='demo@example.com')
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.commit()
    for path in sys.argv[1:]:
        filename = os.path.basename(path).replace(' ', '_')
        folder = os.path.join(app.config['UPLOAD_PATH'], str(user.id))
        os.makedirs(folder, exist_ok=True)
        shutil.copy(path, os.path.join(folder, filename))
        paper = Paper(paper_name=os.path.splitext(os.path.basename(path))[0], author=user, filename=filename)
        db.session.add(paper)
        db.session.commit()
        print(paper.paper_name, prepare_paper(paper))
