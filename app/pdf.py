import os
import re
import pdfplumber
import pymupdf

'''
Rendering PDF pages to images. PyMuPDF replaces pdf2image, so Poppler is no longer needed.
'''
def render_pages(pdf_path, out_dir, first=1, last=None, dpi=110, prefix='page'):
    os.makedirs(out_dir, exist_ok=True)
    with pymupdf.open(pdf_path) as doc:
        last = last or doc.page_count
        for n in range(first, last + 1):
            doc[n - 1].get_pixmap(dpi=dpi).save(
                os.path.join(out_dir, '{}-{}.png'.format(prefix, n - first + 1)))
        return last - first + 1


'''
Reading an ExamBuilder mark scheme. Each page has a table with the columns
Question | (part) | (sub-part) | Answer | Marks | Guidance. The question number
is split over the first columns and a blank cell means "same as the row above".
Table detection is unreliable when answers contain their own tables, so words
are sorted into columns by their x position instead, using the column edges
of the first full row. Each question keeps its text plus the strips of page it
covers, so the marker can be shown a picture of the real mark scheme.
'''
def is_header(cells):
    cells = [' '.join((c or '').split()).lower() for c in cells]
    return cells and cells[0].startswith('question') and any(c.startswith('mark') for c in cells)

def find_mark_scheme_start(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if any(is_header(row) for row in table):
                    return n
    return None

def find_columns(page):
    '''Returns the column edges, e.g. [30, 58, 84, 110, 311, 364, 565], and the bottom of the header row.'''
    for table in page.find_tables():
        rows = list(zip(table.rows, table.extract()))
        for i, (row, cells) in enumerate(rows):
            if is_header(cells):
                for full_row, _ in rows[i + 1:]:
                    if all(full_row.cells):
                        return [c[0] for c in full_row.cells] + [full_row.cells[-1][2]], row.bbox[3]
    return None, None

def lines_of(words):
    lines = []
    for w in sorted(words, key=lambda w: (round(w['top']), w['x0'])):
        if lines and abs(lines[-1][0]['top'] - w['top']) < 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines

def parse_mark_scheme(pdf_path, first_page=1):
    questions = []
    number = ['', '', '']
    with pdfplumber.open(pdf_path) as pdf:
        edges, _ = find_columns(pdf.pages[first_page - 1])
        if edges is None:
            return []
        n_number = len(edges) - 4   # the last three columns are answer, marks, guidance
        def column(word):
            centre = (word['x0'] + word['x1']) / 2
            return max(i for i, e in enumerate(edges[:-1]) if centre >= e - 1) if centre >= edges[0] - 1 else 0
        for n, page in enumerate(pdf.pages[first_page - 1:], start=first_page):
            _, top = find_columns(page)
            words = page.extract_words()
            footer = min((w['top'] for w in words if w['text'] == '©'), default=page.height - 40)
            top = top or 0
            words = [w for w in words if top < w['top'] < footer - 2]
            for line in lines_of(words):
                cells = [' '.join(w['text'] for w in line if column(w) == i) for i in range(len(edges) - 1)]
                y = line[0]['top'] - 3
                if questions and questions[-1]['open'] and questions[-1]['rows'][-1]['page'] != n:
                    questions[-1]['rows'].append({'page': n, 'top': top})
                if cells[n_number].lower() == 'total':
                    if questions and questions[-1]['open']:
                        questions[-1]['rows'][-1]['bottom'] = y
                        questions[-1]['open'] = False
                    continue
                parts = cells[:n_number]
                if any(parts):
                    # The first filled column and everything to its right replace the number so far
                    first = next(i for i, part in enumerate(parts) if part)
                    number[first:] = parts[first:] + [''] * (len(number) - len(parts))
                    if questions and questions[-1]['open']:
                        questions[-1]['rows'][-1]['bottom'] = y
                    marks = re.findall(r'\d+', cells[n_number + 1])
                    questions.append({'label': number[0] + ''.join('({})'.format(p) for p in number[1:] if p),
                                      'max_mark': int(marks[0]) if marks else None,
                                      'answer': [], 'guidance': [], 'open': True,
                                      'rows': [{'page': n, 'top': y}]})
                if not questions or not questions[-1]['open']:
                    continue
                q = questions[-1]
                q['rows'][-1]['last'] = max(w['bottom'] for w in line)
                if cells[n_number]:
                    q['answer'].append(cells[n_number])
                if cells[n_number + 2]:
                    q['guidance'].append(cells[n_number + 2])
            if questions and questions[-1]['open']:
                row = questions[-1]['rows'][-1]
                row['bottom'] = row['last'] + 6 if 'last' in row else row['top']
    for q in questions:
        q['answer'] = '\n'.join(q['answer'])
        q['guidance'] = '\n'.join(q['guidance'])
        for r in q['rows']:
            r['x0'], r['x1'] = edges[0], edges[-1]
        q['rows'] = [r for r in q['rows'] if r['bottom'] - r['top'] > 4]
        del q['open']
    return questions

def render_mark_scheme(pdf_path, rows, out_path, dpi=110):
    '''Stitches a question's mark scheme rows (possibly over several pages) into one image.'''
    with pymupdf.open(pdf_path) as doc:
        pixmaps = []
        for r in rows:
            clip = pymupdf.Rect(r['x0'], r['top'], r['x1'], r['bottom'])
            pixmaps.append(doc[r['page'] - 1].get_pixmap(dpi=dpi, clip=clip))
        width = max(p.width for p in pixmaps)
        out = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, sum(p.height for p in pixmaps)), False)
        out.clear_with(255)
        y = 0
        for p in pixmaps:
            p.set_origin(0, y)
            out.copy(p, p.irect)
            y += p.height
        out.save(out_path)


'''
Guessing the answer areas on the question paper. Every markable part ends with
its mark in square brackets, e.g. [4] or ........ [4], so the answer area for
part N runs from the end of part N-1 down to its own [4], spanning page breaks
if necessary. Exam board papers start with a cover sheet, which is skipped.
'''
MARK = re.compile(r'(?:^|[.\s])\[(\d+)\]$')
COVER_WORDS = ('candidate number', 'centre number', 'first name', 'last name', 'candidate name')

def is_cover(lines):
    text = ' '.join(t for t, _, _ in lines).lower()
    return any(w in text for w in COVER_WORDS) and not any(MARK.search(t) for t, _, _ in lines)
FOOTER_MARGIN = 45

def text_lines(page):
    height = page.rect.height
    lines = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text = ''.join(s['text'] for s in line['spans']).strip()
            if text and line['bbox'][1] < height - FOOTER_MARGIN:
                lines.append((text, line['bbox'][1], line['bbox'][3]))
    return lines

def find_answer_areas(pdf_path, page_count):
    areas = []
    start = (1, 0.0)
    with pymupdf.open(pdf_path) as doc:
        height = doc[0].rect.height
        pages = {n: text_lines(doc[n - 1]) for n in range(1, page_count + 1)}
        first = 2 if page_count > 1 and is_cover(pages[1]) else 1
        # Start at the first line of text, leaving the top margin free for a name
        if pages[first]:
            start = (first, max(0.0, min(t for _, t, _ in pages[first]) - 8))
        for n in range(first, page_count + 1):
            for text, top, bottom in pages[n]:
                m = MARK.search(text)
                if not m:
                    continue
                end = (n, bottom + 4)
                boxes = []
                for p in range(start[0], end[0] + 1):
                    y0 = start[1] if p == start[0] else 0.0
                    y1 = end[1] if p == end[0] else height - FOOTER_MARGIN
                    # Space left below the previous answer only counts if this question starts there
                    if p != end[0] and not any(t > y0 for _, t, _ in pages[p]):
                        continue
                    if y1 - y0 > 10:
                        boxes.append({'page': p, 'x': 0.04, 'w': 0.92, 'y': y0 / height, 'h': (y1 - y0) / height})
                areas.append({'marks': int(m.group(1)), 'boxes': boxes})
                start = end
    return areas

NAME_WORDS = ('forename', 'surname', 'first name', 'last name', 'candidate name', 'candidate number')

def find_name_area(pdf_path):
    '''On a cover sheet, a box around the name and candidate number fields.'''
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        if not is_cover(text_lines(page)):
            return None
        hits = [r for w in NAME_WORDS for r in page.search_for(w)]
        if not hits:
            return None
        # The same words appear again in the instructions, so keep to the first cluster of fields
        first = min(r.y0 for r in hits)
        hits = [r for r in hits if r.y0 < first + 90]
        height = page.rect.height
        top = max(0.0, first - 16)
        bottom = min(height, max(r.y1 for r in hits) + 16)
        return {'page': 1, 'x': 0.02, 'w': 0.96, 'y': top / height, 'h': (bottom - top) / height}
