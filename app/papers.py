import os
from app import app, db
from app.models import Question, Region
from app.pdf import render_pages, find_mark_scheme_start, parse_mark_scheme, \
    render_mark_scheme, find_answer_areas, find_name_area

def master_path(paper):
    return os.path.join(app.config['UPLOAD_PATH'], str(paper.user_id), paper.filename)

def paper_dir(paper):
    return os.path.join(app.config['UPLOAD_PATH'], str(paper.user_id), 'paper{}'.format(paper.id))

def mark_scheme_image(question):
    return os.path.join(paper_dir(question.paper), 'ms-{}.png'.format(question.id))

def prepare_paper(paper):
    '''
    Splits an uploaded ExamBuilder PDF into the question paper and its mark scheme,
    renders the paper pages, creates a Question per mark scheme row and pre-draws
    an answer box for each one. Returns a list of messages for the user.
    '''
    pdf = master_path(paper)
    messages = []
    ms_start = find_mark_scheme_start(pdf)
    paper.page_count = render_pages(pdf, paper_dir(paper), last=ms_start - 1 if ms_start else None)
    areas = find_answer_areas(pdf, paper.page_count)
    name_area = find_name_area(pdf)
    if name_area:
        db.session.add(Region(paper=paper, kind='name', **name_area))
    if not ms_start:
        # No mark scheme: one question per answer space found, for the teacher to rename
        for i, area in enumerate(areas):
            question = Question(paper=paper, label=str(i + 1), position=i, max_mark=area['marks'])
            db.session.add(question)
            for box in area['boxes']:
                db.session.add(Region(paper=paper, question=question, **box))
        db.session.commit()
        return ['No mark scheme table was found. {} answer spaces were found worth {} marks: '
                'please check the question names.'.format(len(areas), sum(a['marks'] for a in areas))]

    parsed = parse_mark_scheme(pdf, ms_start)
    questions = []
    for i, q in enumerate(parsed):
        question = Question(paper=paper, label=q['label'], position=i, max_mark=q['max_mark'],
                            mark_scheme=q['answer'], guidance=q['guidance'])
        db.session.add(question)
        questions.append(question)
    db.session.flush()
    for question, q in zip(questions, parsed):
        if q['rows']:
            render_mark_scheme(pdf, q['rows'], mark_scheme_image(question))

    if len(areas) == len(questions):
        for question, area in zip(questions, areas):
            for box in area['boxes']:
                db.session.add(Region(paper=paper, question=question, **box))
        for q, a in zip(questions, areas):
            if q.max_mark != a['marks']:
                messages.append('Check {}: the paper says [{}] but the mark scheme says {}. '
                                'The mark scheme value has been used.'.format(q.label, a['marks'], q.max_mark))
    else:
        messages.append('Found {} questions in the mark scheme but {} answer spaces on the paper, '
                        'so please draw the boxes yourself.'.format(len(questions), len(areas)))
    db.session.commit()
    messages.insert(0, 'Found {} questions worth {} marks.'.format(
        len(questions), sum(q.max_mark or 0 for q in questions)))
    return messages
