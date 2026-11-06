'''
Creates a demo account and loads sample ExamBuilder papers through the same code
as an upload, for trying the app out locally.

    .venv/Scripts/python seed_demo.py "../J27701 Computer systems June 2025.pdf" ...

A paper followed by --printed scan.pdf uses that scan of the printed paper for the layout.
Every course in courses/ is loaded too (run with no papers to just load courses).
'''
import glob
import json
import os
import shutil
import sys
from app import app, db
from app.models import User, Paper
from app.courses import import_course
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
    for path in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'courses', '*.json')):
        with open(path, encoding='utf-8') as f:
            print('Course:', import_course(user, json.load(f)).name)
    args = sys.argv[1:]
    for k, path in enumerate(args):
        if path == '--printed' or (k and args[k - 1] == '--printed'):
            continue
        printed = args[k + 2] if k + 2 < len(args) and args[k + 1] == '--printed' else None
        filename = os.path.basename(path).replace(' ', '_')
        folder = os.path.join(app.config['UPLOAD_PATH'], str(user.id))
        os.makedirs(folder, exist_ok=True)
        shutil.copy(path, os.path.join(folder, filename))
        paper = Paper(paper_name=os.path.splitext(os.path.basename(path))[0], author=user, filename=filename)
        if printed:
            paper.layout_filename = 'printed-' + os.path.basename(printed).replace(' ', '_')
            shutil.copy(printed, os.path.join(folder, paper.layout_filename))
        db.session.add(paper)
        db.session.commit()
        print(paper.paper_name, prepare_paper(paper))
