'''Word reports for students. Built with python-docx so they can be edited by hand afterwards.

Nothing here is subject-specific: topic names, sections, revision points and videos come
from the paper's course. Without a course (or topic codes on the questions) the report
still gives the marks and comments, just without the topic pages.
'''
import os
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Pt, Cm, RGBColor
from app import app

GREEN, LIME, BLACK, GREY, RED, MUTED = '008741', '8CC841', '000000', 'B2B2B2', 'C00000', '595959'
HEAD, BODY = 'Century Gothic', 'Arial'
GOOD, WEAK = 70, 40     # scores at or above GOOD% are green, below WEAK% red
FOCUS = 3               # how many topics to work on

# --- low-level helpers ---------------------------------------------------------
# Word ignores properties that are out of schema order, so they are inserted in place
TBL_ORDER = ['tblStyle', 'tblpPr', 'tblOverlap', 'bidiVisual', 'tblStyleRowBandSize', 'tblStyleColBandSize',
             'tblW', 'jc', 'tblCellSpacing', 'tblInd', 'tblBorders', 'shd', 'tblLayout', 'tblCellMar', 'tblLook']
TC_ORDER = ['cnfStyle', 'tcW', 'gridSpan', 'hMerge', 'vMerge', 'tcBorders', 'shd', 'noWrap', 'tcMar',
            'textDirection', 'tcFitText', 'vAlign', 'hideMark']

def put(parent, el, order):
    tag = el.tag.split('}')[1]
    for old in parent.findall(qn('w:' + tag)):
        parent.remove(old)
    later = order[order.index(tag) + 1:]
    for i, child in enumerate(parent):
        if child.tag.split('}')[1] in later:
            parent.insert(i, el)
            return
    parent.append(el)

def border_el(name, spec):
    el = OxmlElement('w:' + name)
    if spec:
        el.set(qn('w:val'), 'single'); el.set(qn('w:sz'), str(spec[0])); el.set(qn('w:color'), spec[1])
    else:
        el.set(qn('w:val'), 'nil')
    return el

def table_borders(table, rows=(4, GREY)):
    '''No borders except a hairline between rows (and under the last), unless rows is None.'''
    b = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        b.append(border_el(side, rows if side in ('insideH', 'bottom') else None))
    put(table._tbl.tblPr, b, TBL_ORDER)

def cell_border(cell, **sides):
    b = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        if side in sides:
            b.append(border_el(side, sides[side]))
    put(cell._tc.get_or_add_tcPr(), b, TC_ORDER)

def cell_margins(table, top=60, bottom=60, left=80, right=80):
    m = OxmlElement('w:tblCellMar')
    for side, v in (('top', top), ('left', left), ('bottom', bottom), ('right', right)):
        el = OxmlElement('w:' + side); el.set(qn('w:w'), str(v)); el.set(qn('w:type'), 'dxa'); m.append(el)
    put(table._tbl.tblPr, m, TBL_ORDER)

def new_table(container, widths, rows=1):
    t = container.add_table(rows=rows, cols=len(widths))
    t.autofit = False
    layout = OxmlElement('w:tblLayout'); layout.set(qn('w:type'), 'fixed'); put(t._tbl.tblPr, layout, TBL_ORDER)
    for row in t.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = Cm(w)
    return t

def add_row(table, widths):
    row = table.add_row()
    trPr = row._tr.get_or_add_trPr(); trPr.append(OxmlElement('w:cantSplit'))
    for c, w in zip(row.cells, widths):
        c.width = Cm(w)
    return row.cells

def run(par, text, size=10, color=BLACK, bold=False, italic=False, caps=False, font=BODY, spacing=None):
    r = par.add_run(text)
    r.font.name = font; r.font.size = Pt(size); r.font.color.rgb = RGBColor.from_string(color)
    r.font.bold = bold; r.font.italic = italic; r.font.all_caps = caps
    if spacing:
        sp = OxmlElement('w:spacing'); sp.set(qn('w:val'), str(spacing)); r._r.get_or_add_rPr().append(sp)
    return r

def para(container, before=0, after=0, keep=False):
    p = container.add_paragraph()
    f = p.paragraph_format
    f.space_before = Pt(before); f.space_after = Pt(after); f.keep_with_next = keep
    return p

def cell_par(cell, first=True, align=None):
    p = cell.paragraphs[0] if first else cell.add_paragraph()
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(0)
    if align is not None:
        p.alignment = align
    return p

def label(par, text, color=MUTED):
    '''The uppercase, letter-spaced label style.'''
    return run(par, text, 8, color, bold=True, caps=True, spacing=20)

def heading(container, text, size=17, before=16, after=4):
    p = para(container, before, after, keep=True)
    run(p, text, size, GREEN, font=HEAD)
    return p

def page_break(doc):
    para(doc).add_run().add_break(WD_BREAK.PAGE)

def rule_below(par, color=LIME, size=12):
    bdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), str(size))
    bottom.set(qn('w:space'), '4'); bottom.set(qn('w:color'), color)
    bdr.append(bottom); par._p.get_or_add_pPr().append(bdr)

def run_props(size, color, underline=False):
    rPr = OxmlElement('w:rPr')
    f = OxmlElement('w:rFonts'); f.set(qn('w:ascii'), BODY); f.set(qn('w:hAnsi'), BODY); rPr.append(f)
    c = OxmlElement('w:color'); c.set(qn('w:val'), color); rPr.append(c)
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), str(int(size * 2))); rPr.append(sz)
    if underline:
        u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); rPr.append(u)
    return rPr

def hyperlink(par, text, url, size=9.5):
    h = OxmlElement('w:hyperlink')
    h.set(qn('r:id'), par.part.relate_to(url, RT.HYPERLINK, is_external=True))
    r = OxmlElement('w:r'); r.append(run_props(size, GREEN, underline=True))
    t = OxmlElement('w:t'); t.text = text; t.set(qn('xml:space'), 'preserve'); r.append(t)
    h.append(r); par._p.append(h)

def field(par, instr, size=8, color=MUTED):
    for kind in ('begin', None, 'end'):
        r = OxmlElement('w:r'); r.append(run_props(size, color))
        if kind:
            fc = OxmlElement('w:fldChar'); fc.set(qn('w:fldCharType'), kind); r.append(fc)
        else:
            it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = instr; r.append(it)
        par._p.append(r)

def score_colour(got, of):
    pct = 100 * got / of if of else 0
    return GREEN if pct >= GOOD else RED if pct < WEAK else BLACK

def plural(n, word):
    return '{} {}{}'.format(n, word, '' if n == 1 else 's')

def listing(items):
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]

# --- the report ----------------------------------------------------------------------
MARGIN = 1.8
TEXT_W = 21 - 2 * MARGIN

def student_report(script):
    paper = script.paper
    course = paper.course
    topic_info = {t.code: t for t in course.topics} if course else {}
    answers = {a.question_id: a for a in script.answers}
    rows = []       # (question, mark, out of, comment for the student)
    for q in paper.questions:
        a = answers.get(q.id)
        rows.append((q, (a.mark or 0) if a else 0, q.max_mark or 0, (a.comment or '') if a else ''))

    topics = {}     # code -> [got, out of, [labels]], only for codes the course knows
    for q, got, of, _ in rows:
        if q.topic in topic_info:
            t = topics.setdefault(q.topic, [0, 0, []]); t[0] += got; t[1] += of; t[2].append(q.label)
    total = sum(r[1] for r in rows); out_of = sum(r[2] for r in rows)
    student = script.student_name or 'Script {}'.format(script.number)

    doc = Document()
    normal = doc.styles['Normal']
    normal.font.name = BODY; normal.font.size = Pt(10)
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), BODY)
    doc.styles['List Bullet'].font.name = BODY
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(MARGIN)
    sec.top_margin = Cm(2.9); sec.bottom_margin = Cm(1.6)
    sec.header_distance = Cm(1.0); sec.footer_distance = Cm(0.8)

    header(sec, paper, course)
    fp = sec.footer.paragraphs[0]
    run(fp, student + '  ·  page ', 8, MUTED); field(fp, 'PAGE'); run(fp, ' of ', 8, MUTED); field(fp, 'NUMPAGES')

    # Page 1: scores, summary and topics
    p = para(doc, 6, 2)
    run(p, '{}, here’s how your exam went'.format(student.split()[0]), 24, GREEN, font=HEAD)
    p = para(doc, 0, 12)
    run(p, 'Your marks, what went well, and what will make the biggest difference next time.', 10.5, MUTED)
    score_tiles(doc, rows, course, total, out_of)

    focus = sorted((k for k in topics if topics[k][0] < topics[k][1]),
                   key=lambda k: (topics[k][0] - topics[k][1], topics[k][0] / topics[k][1]))[:FOCUS]
    heading(doc, 'In a nutshell')
    run(para(doc), nutshell(topics, topic_info, focus, total, out_of), 10.5)
    if script.comment:
        p = para(doc, 6, 0)
        run(p, 'From your teacher: ', 10.5, bold=True); run(p, script.comment, 10.5)

    if topics:
        topic_table(doc, topics, topic_info, course)
    if focus:
        page_break(doc)
        focus_page(doc, focus, topics, topic_info, course)
    page_break(doc)
    question_page(doc, rows)
    return doc

def header(sec, paper, course):
    hdr = sec.header
    ht = hdr.add_table(rows=1, cols=2, width=Cm(TEXT_W))
    for c, w in zip(ht.rows[0].cells, (6, TEXT_W - 6)):
        c.width = Cm(w)
    table_borders(ht, None); cell_margins(ht, 0, 0, 0, 0)
    logo_cell, text_cell = ht.rows[0].cells
    logo = app.config.get('REPORT_LOGO')
    if logo and os.path.exists(logo):
        cell_par(logo_cell).add_run().add_picture(logo, height=Cm(0.95))
    text_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
    title = '  ·  '.join(x for x in (course.subject if course else None, paper.paper_name) if x)
    label(cell_par(text_cell, align=WD_ALIGN_PARAGRAPH.RIGHT), title)
    # The header's own paragraph sits above the table: move it below to carry the lime rule
    hp = hdr.paragraphs[0]
    hdr._element.remove(hp._p); hdr._element.append(hp._p)
    hp.paragraph_format.line_spacing = Pt(2)
    rule_below(hp)

def score_tiles(doc, rows, course, total, out_of):
    tiles = [('Overall', total, out_of)]
    for key, name in ((course.sections or {}).items() if course else ()):
        part = [r for r in rows if r[0].topic and r[0].topic.split('.')[0] == key]
        if part:
            tiles.append((name, sum(r[1] for r in part), sum(r[2] for r in part)))
    gap = 0.5; tw = (TEXT_W - gap * (len(tiles) - 1)) / len(tiles)
    widths = []
    for i in range(len(tiles)):
        widths += [tw] + ([gap] if i < len(tiles) - 1 else [])
    kt = new_table(doc, widths); table_borders(kt, None); cell_margins(kt, 80, 40, 0, 0)
    for i, (name, got, of) in enumerate(tiles):
        c = kt.rows[0].cells[i * 2]
        cell_border(c, top=(18, LIME))
        label(cell_par(c), name)
        p = cell_par(c, False); p.paragraph_format.space_before = Pt(2)
        colour = score_colour(got, of)
        run(p, str(got), 30, colour, font=HEAD); run(p, ' / {}'.format(of), 13, BLACK, font=HEAD)
        run(cell_par(c, False), '{}%'.format(round(100 * got / of) if of else 0), 11, colour, bold=True)
    p = para(doc, 6, 0)
    run(p, 'Scores in ', 8, MUTED); run(p, 'green', 8, GREEN, bold=True)
    run(p, ' are {}% or more. Scores in '.format(GOOD), 8, MUTED); run(p, 'red', 8, RED, bold=True)
    run(p, ' are below {}%.'.format(WEAK), 8, MUTED)

def nutshell(topics, info, focus, total, out_of):
    '''A summary written from the marks. Teachers can add their own words in Word.'''
    if not topics:
        return 'You scored {} out of {} ({}%).'.format(total, out_of, round(100 * total / out_of) if out_of else 0)
    best = sorted((k for k in topics if topics[k][0]),
                  key=lambda k: (-topics[k][0] / topics[k][1], -topics[k][1]))[:3]
    text = []
    if best:
        text.append('You did best on {}.'.format(
            listing(['{} ({}/{})'.format(info[k].name, topics[k][0], topics[k][1]) for k in best])))
    if focus:
        lost = sum(topics[k][1] - topics[k][0] for k in focus)
        if len(focus) == 1:
            text.append('The topic that cost you most was {}: {}.'.format(info[focus[0]].name, plural(lost, 'mark')))
        else:
            text.append('The topics that cost you most were {}: {} between them. Sort those out and you '
                        'could win back up to {}.'.format(listing([info[k].name for k in focus]),
                                                          plural(lost, 'mark'), plural(lost, 'mark')))
    else:
        text.append('You got full marks on every topic. Brilliant.')
    return ' '.join(text)

def topic_table(doc, topics, info, course):
    heading(doc, 'Topic by topic')
    widths = [1.4, TEXT_W - 1.4 - 4.6 - 1.8, 4.6, 1.8]
    tt = new_table(doc, widths); table_borders(tt); cell_margins(tt, 40, 40, 0, 80)
    for c, h in zip(tt.rows[0].cells, ('', 'Topic', 'Questions', 'Score')):
        cell_border(c, bottom=(8, BLACK)); label(cell_par(c), h, BLACK)
    tt.rows[0].cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    order = {t: i for i, t in enumerate(info)}
    for code in sorted(topics, key=order.get):
        got, of, labels = topics[code]
        cells = add_row(tt, widths)
        run(cell_par(cells[0]), code, 9, MUTED)
        run(cell_par(cells[1]), info[code].name, 9.5)
        run(cell_par(cells[2]), ', '.join(labels), 8.5, MUTED)
        run(cell_par(cells[3], align=WD_ALIGN_PARAGRAPH.RIGHT), '{}/{}'.format(got, of), 10,
            score_colour(got, of), bold=True)
    if course.topic_note:
        run(para(doc, 6, 0), course.topic_note, 9, MUTED)

def focus_page(doc, focus, topics, info, course):
    words = {1: 'one thing', 2: 'two things', 3: 'three things'}
    heading(doc, 'Your {} to work on'.format(words.get(len(focus), '{} things'.format(len(focus)))),
            size=22, before=6, after=2)
    source = course.resource_name or 'videos'
    run(para(doc, 0, 4), 'Watch the videos, tick them off, then have another go at the questions in your paper.',
        10.5, MUTED)
    for n, code in enumerate(focus, 1):
        got, of, labels = topics[code]
        topic = info[code]
        p = para(doc, 14, 0, keep=True)
        run(p, '{}  '.format(n), 20, LIME, font=HEAD); run(p, topic.name, 15, GREEN, font=HEAD)
        p = para(doc, 0, 6, keep=True)
        run(p, '{}  ·  You dropped {}. Try again: question{} {}'.format(
            code, plural(of - got, 'mark'), 's' if len(labels) > 1 else '', listing(labels)), 9, MUTED)
        if not (topic.revise or topic.videos):
            continue
        ft = new_table(doc, [9.0, 0.6, TEXT_W - 9.6]); table_borders(ft, None); cell_margins(ft, 0, 0, 0, 0)
        left, _, right = ft.rows[0].cells
        if topic.revise:
            label(cell_par(left), 'What to revise')
            for line in topic.revise:
                p = left.add_paragraph(style='List Bullet'); p.paragraph_format.space_after = Pt(2)
                run(p, line, 9.5)
        if topic.videos:
            label(cell_par(right), 'Watch ({})'.format(source))
            for title, url in topic.videos[:4]:
                p = right.add_paragraph(); p.paragraph_format.space_before = Pt(4)
                run(p, '☐  ', 11, BLACK, font='Segoe UI Symbol')
                hyperlink(p, title, url)
    if course.resource_url:
        p = para(doc, 16, 0)
        run(p, 'Want more? Everything from {} for the course is at '.format(source), 9, MUTED)
        hyperlink(p, course.resource_url.split('//')[-1].split('/')[0], course.resource_url, 9)

def question_page(doc, rows):
    heading(doc, 'Question by question', size=22, before=6, after=2)
    run(para(doc, 0, 8), 'Comments for you come from your teacher. Comments for the class are things lots of '
        'people missed.', 10, MUTED)
    widths = [1.8, 1.5, 1.3, 6.1, TEXT_W - 10.7]
    qt = new_table(doc, widths); table_borders(qt); cell_margins(qt, 40, 40, 0, 100)
    for c, h in zip(qt.rows[0].cells, ('Q', 'Topic', 'Mark', 'For you', 'For the class')):
        cell_border(c, bottom=(8, BLACK)); label(cell_par(c), h, BLACK)
    qt.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    # Long papers get smaller type so the table stays on one page where it can
    size = 9 if len(rows) <= 30 else 8
    for q, got, of, comment in rows:
        cells = add_row(qt, widths)
        run(cell_par(cells[0]), q.label, size + 0.5, bold=True)
        run(cell_par(cells[1]), q.topic or '', size - 0.5, MUTED)
        run(cell_par(cells[2]), '{}/{}'.format(got, of), size + 1, score_colour(got, of), bold=True)
        run(cell_par(cells[3]), comment, size)
        run(cell_par(cells[4]), q.class_comment or '', size, MUTED, italic=True)

def report_filename(script):
    name = script.student_name or 'Script {}'.format(script.number)
    safe = ''.join(c for c in '{} - {}'.format(script.paper.paper_name, name) if c.isalnum() or c in ' -_()')
    return safe.strip() + '.docx'
