import os
import cv2
from app import app, db
from app.models import Script, Answer
from app.papers import paper_dir
from app.scans import import_scripts

# Answers with less extra ink than this (a fraction of the box) are probably blank
BLANK_INK = 0.004

def batch_path(batch):
    return os.path.join(app.config['UPLOAD_PATH'], str(batch.paper.user_id), batch.filename)

def script_dir(script):
    return os.path.join(paper_dir(script.paper), 'scripts')

def answer_image(answer):
    return os.path.join(script_dir(answer.script), 'answer-{}.png'.format(answer.id))

def name_image(script):
    return os.path.join(script_dir(script), 'name-{}.png'.format(script.id))

def save_png(path, rgb):
    ok, data = cv2.imencode('.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    data.tofile(path)

def process_batch(batch):
    '''Splits an uploaded batch into scripts and saves every student's answers. Returns messages.'''
    paper = batch.paper
    questions = paper.questions.all()
    boxes = {q.id: [r.to_dict() for r in q.regions] for q in questions if q.regions.count()}
    name_boxes = [r.to_dict() for r in paper.regions if r.kind == 'name']
    if name_boxes:
        boxes['name'] = name_boxes
    scanned, messages = import_scripts(batch_path(batch), paper_dir(paper), paper.page_count, boxes)
    number = paper.scripts.count()
    for s in scanned:
        number += 1
        script = Script(batch=batch, paper=paper, number=number)
        db.session.add(script)
        db.session.flush()
        os.makedirs(script_dir(script), exist_ok=True)
        if 'name' in s['crops']:
            save_png(name_image(script), s['crops']['name'])
        for question in questions:
            if question.id not in s['crops']:
                continue
            ink = s['ink'][question.id]
            answer = Answer(script=script, question=question, ink=ink, blank=ink < BLANK_INK)
            db.session.add(answer)
            db.session.flush()
            save_png(answer_image(answer), s['crops'][question.id])
        if s['rough']:
            messages.append('Script {}: pages {} were hard to line up, so check their answers look right.'
                            .format(number, ', '.join(map(str, s['rough']))))
    db.session.commit()
    messages.insert(0, 'Added {} scripts.'.format(len(scanned)))
    missing = [q.label for q in questions if q.id not in boxes]
    if missing:
        messages.append('Questions {} have no answer box, so were not cut out.'.format(', '.join(missing)))
    return messages
