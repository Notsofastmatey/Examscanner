from app import db
from app.models import Course, Topic

FIELDS = ('subject', 'sections', 'topic_note', 'resource_name', 'resource_url')

def import_course(user, data):
    '''Create a course from its JSON description, or replace the user's course of the same name.
    See courses/*.json for the format.'''
    name = (data.get('name') or '').strip()[:140]
    if not name:
        raise ValueError('The course needs a name.')
    course = user.courses.filter_by(name=name).first()
    if course is None:
        course = Course(author=user, name=name)
        db.session.add(course)
    for field in FIELDS:
        setattr(course, field, data.get(field))
    for topic in course.topics:
        db.session.delete(topic)
    db.session.flush()
    for i, t in enumerate(data.get('topics') or []):
        db.session.add(Topic(course=course, position=i, code=str(t['code'])[:20], name=t.get('name', '')[:140],
                             revise=t.get('revise') or [], videos=t.get('videos') or []))
    db.session.commit()
    return course

def export_course(course):
    data = {'name': course.name}
    data.update({field: getattr(course, field) for field in FIELDS})
    data['topics'] = [{'code': t.code, 'name': t.name, 'revise': t.revise or [], 'videos': t.videos or []}
                      for t in course.topics]
    return data
