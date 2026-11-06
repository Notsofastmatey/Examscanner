import re
import cv2
import numpy as np
import pymupdf
from app.pdf import areas_from_ends, FOOTER

'''
Working with scanned pages, which are pictures with no text layer.
'''
def page_image(doc, index, dpi, clip=None, gray=False):
    '''A page as a numpy image. clip is (left, top, right, bottom) as fractions of the page.'''
    page = doc[index]
    rect = None
    if clip:
        r = page.rect
        rect = pymupdf.Rect(r.width * clip[0], r.height * clip[1], r.width * clip[2], r.height * clip[3])
    pix = page.get_pixmap(dpi=dpi, clip=rect, colorspace=pymupdf.csGRAY if gray else pymupdf.csRGB)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n).squeeze()


'''
Splitting a batch into scripts. Every script starts with the same cover sheet,
so each page is compared with the first one: covers share hundreds of matching
features, other pages only a handful.
'''
orb = cv2.ORB_create(3000)
matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

def features(img):
    return orb.detectAndCompute(img, None)

def homography(a, b):
    '''The transform taking points on image a to image b, and how many features agreed with it.'''
    (ka, da), (kb, db) = a, b
    if da is None or db is None or len(da) < 10 or len(db) < 10:
        return None, 0
    good = [m for m, n in (p for p in matcher.knnMatch(da, db, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 10:
        return None, 0
    src = np.float32([ka[m.queryIdx].pt for m in good])
    dst = np.float32([kb[m.trainIdx].pt for m in good])
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    return H, int(mask.sum()) if mask is not None else 0

def matching_points(a, b):
    return homography(a, b)[1]

def split_scripts(pdf_path, min_points=40):
    '''Returns a list of scripts, each a list of 0-based page indexes.'''
    with pymupdf.open(pdf_path) as doc:
        cover = features(page_image(doc, 0, 60, gray=True))
        starts = [0] + [i for i in range(1, doc.page_count)
                        if matching_points(features(page_image(doc, i, 60, gray=True)), cover) >= min_points]
        return [list(range(s, e)) for s, e in zip(starts, starts[1:] + [doc.page_count])]


'''
Reading printed text with OCR. Only the template needs this, so it can be slow.
'''
_ocr = None

def ocr(img):
    global _ocr
    if _ocr is None:
        from rapidocr import RapidOCR
        _ocr = RapidOCR()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    result = _ocr(img)
    boxes = result.boxes if result.boxes is not None else []
    return [(text.strip(), float(min(p[1] for p in box)) / img.shape[0], float(max(p[1] for p in box)) / img.shape[0])
            for box, text in zip(boxes, result.txts or []) if text.strip()]

FOOTER_TEXT = re.compile(r'exambuilder|©|^\d+\s+of\s+\d+$', re.I)

def ocr_lines(doc, indexes, dpi=150):
    '''Printed text of some pages, as {page number in script: [(text, top, bottom)]}.'''
    return {n: sorted(l for l in ocr(page_image(doc, i, dpi)) if not FOOTER_TEXT.search(l[0]) and l[1] < 0.96)
            for n, i in enumerate(indexes, start=1)}

def ink_lines(doc, indexes, dpi=50):
    '''
    Bands of print or pencil on each page, as {page number in script: [('', top, bottom)]},
    for telling blank space from content. An adaptive threshold ignores the gradual
    shadows of phone scans, and red pen is invisible in the red channel.
    '''
    pages = {}
    for n, i in enumerate(indexes, start=1):
        red = page_image(doc, i, dpi)[:, :, 0]
        ink = cv2.adaptiveThreshold(red, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
        h, w = ink.shape
        rows = ink[:, int(w * 0.06):int(w * 0.94)].sum(axis=1) > w * 0.005
        bands, start = [], None
        for y, has_ink in enumerate(list(rows[:int(h * (1 - FOOTER))]) + [False]):
            if has_ink and start is None:
                start = y
            elif not has_ink and start is not None:
                bands.append(('', start / h, y / h))
                start = None
        pages[n] = bands
    return pages

# Marks such as [3] often come back as 13], [31 or [ε] when pen is written nearby
MISREADS = {'ε': '3', 'O': '0', 'o': '0', 'l': '1', 'I': '1', '|': '1', 'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2'}

def parse_mark(text):
    text = text.replace(' ', '')
    m = re.fullmatch(r'\[(\d{1,2})\]', text)
    if m:
        return int(m.group(1))
    if len(text) == 3 and (text[0] == '[' or text[2] == ']'):
        digit = MISREADS.get(text[1], text[1])
        if digit.isdigit():
            return int(digit)
    return None

def ocr_marks(doc, indexes, dpi=250):
    '''
    The [n] marks down the right-hand margin, as (page number in script, top, bottom, marks).
    The red channel is used because red pen almost disappears in it.
    '''
    found = []
    for n, i in enumerate(indexes, start=1):
        red = page_image(doc, i, dpi, clip=(0.8, 0, 1, 1))[:, :, 0]
        for text, top, bottom in sorted(ocr(red), key=lambda l: l[1]):
            marks = parse_mark(text)
            if marks is not None and top < 1 - FOOTER:
                found.append((n, top, bottom, marks))
    return found

def align_marks(expected, found):
    '''
    Lines up the marks found with the marks expected from the mark scheme, allowing
    for marks that were missed, misread or invented. Returns, for each expected mark,
    the index of the found mark or None.
    '''
    n, m = len(expected), len(found)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    step = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            options = []
            if i and j:
                options.append((cost[i - 1][j - 1] + (0 if expected[i - 1] == found[j - 1][3] else 0.8), 'match'))
            if i:
                options.append((cost[i - 1][j] + 1, 'missed'))
            if j:
                options.append((cost[i][j - 1] + 1, 'extra'))
            cost[i][j], step[i][j] = min(options)
    result = [None] * n
    i, j = n, m
    while i or j:
        move = step[i][j]
        if move == 'match':
            result[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif move == 'missed':
            i -= 1
        else:
            j -= 1
    return result

def ink_profile(gray, height=400):
    ink = cv2.adaptiveThreshold(gray, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    profile = ink[:, int(gray.shape[1] * 0.06):int(gray.shape[1] * 0.94)].mean(axis=1).astype(np.float32)
    profile = cv2.resize(profile.reshape(-1, 1), (1, height)).ravel()
    return profile - profile.mean()

def vertical_shift(a, b, most=0.06, height=400):
    '''How far down (as a fraction of the page) page b's content sits compared with page a's.'''
    pa, pb = ink_profile(a, height), ink_profile(b, height)
    limit = int(most * height)
    scores = {s: float(np.dot(pa[max(0, -s):height - max(0, s)], pb[max(0, s):height - max(0, -s)]))
              for s in range(-limit, limit + 1)}
    return max(scores, key=scores.get) / height

def page_mapper(doc, index, template_index, dpi=80, min_points=15):
    '''
    A function mapping (x, y) on one scanned page to the same printed spot on a
    template page, both as fractions of the page. Scans are cropped and skewed
    differently, so the same mark can sit at a different height on each.
    '''
    a, b = page_image(doc, index, dpi, gray=True), page_image(doc, template_index, dpi, gray=True)
    H, points = homography(features(a), features(b))
    if H is None or points < min_points:
        # Too much handwriting to match features: line up the rows of ink instead
        shift = vertical_shift(a, b)
        return lambda x, y: (x, y + shift)
    def to_template(x, y):
        p = cv2.perspectiveTransform(np.float32([[[x * a.shape[1], y * a.shape[0]]]]), H)[0][0]
        return float(p[0]) / b.shape[1], float(p[1]) / b.shape[0]
    return to_template

def pooled_marks(doc, template, others):
    '''
    The [n] marks of the template script, plus any found only on other scripts (where a
    student may have written over them), mapped onto the template's pages.
    '''
    marks = ocr_marks(doc, template)
    for script in others:
        mappers = {}
        for page, top, bottom, value in ocr_marks(doc, script):
            if page not in mappers:
                mappers[page] = page_mapper(doc, script[page - 1], template[page - 1])
            to_template = mappers[page]
            if to_template is None:
                continue
            top, bottom = to_template(0.93, top)[1], to_template(0.93, bottom)[1]
            if not any(p == page and abs(t - top) < 0.02 for p, t, _, _ in marks):
                marks.append((page, top, bottom, value))
    return sorted(marks)

def scan_layout(pdf_path, expected, labels, max_scripts=3):
    '''
    Works out the template from a scan of one or more printed scripts. The first
    script gives the page images; marks hidden by a student's writing are taken from
    the next few scripts. Returns the script's pages, its text lines, answer areas and messages.
    '''
    scripts = split_scripts(pdf_path)
    template = scripts[0]
    messages = []
    others = [s for s in scripts[1:] if len(s) == len(template)]
    if len(others) < len(scripts) - 1:
        messages.append('{} scanned scripts had a different number of pages and were ignored.'
                        .format(len(scripts) - 1 - len(others)))
    with pymupdf.open(pdf_path) as doc:
        # Real text for the cover and first page, ink elsewhere to tell blank space from questions
        pages = ink_lines(doc, template)
        pages.update(ocr_lines(doc, template[:2]))
        found = pooled_marks(doc, template, others[:max_scripts - 1])
    ends = [None] * len(expected)
    for k, j in enumerate(align_marks(expected, found)):
        if j is not None:
            page, _, bottom, marks = found[j]
            ends[k] = (page, bottom + 0.005, marks)
    missing = [labels[k] for k, e in enumerate(ends) if e is None]
    if missing:
        messages.append('Could not find the end of {} on the scan, so please draw those boxes.'.format(', '.join(missing)))
    areas = areas_from_ends(ends, pages, len(template), gap=0.015)
    return {'pages': template, 'lines': pages, 'areas': areas, 'messages': messages,
            'scripts': len(scripts)}


'''
Importing a batch of scripts. Each scanned page is warped onto its template page,
so the answer boxes drawn on the template can be cut straight out of it.
'''
def load_gray(path):
    return cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_GRAYSCALE)

def sensible(H, width, height):
    '''Rejects transforms that would fold, flip or wildly stretch the page.'''
    corners = np.float32([[[0, 0]], [[width, 0]], [[width, height]], [[0, height]]])
    mapped = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
    area = cv2.contourArea(mapped)
    return 0.6 < area / (width * height) < 1.6 and cv2.isContourConvex(mapped.astype(np.float32))

def align_page(scan, template, scale, min_points=15):
    '''
    Warps a scanned page (RGB) onto a template page (grey), at scale times the
    template's size. Returns the warped page and whether features matched; if
    they didn't, the page is only stretched to fit and shifted vertically.
    '''
    th, tw = template.shape
    gray = cv2.cvtColor(scan, cv2.COLOR_RGB2GRAY)
    f = th / gray.shape[0]
    small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    H, points = homography(features(small), features(template))
    matched = H is not None and points >= min_points and sensible(H, small.shape[1], small.shape[0])
    if not matched:
        stretch = cv2.resize(small, (tw, th))
        shift = vertical_shift(stretch, template) * th
        H = np.float64([[tw / small.shape[1], 0, 0], [0, 1, shift], [0, 0, 1]])
    M = np.diag([scale, scale, 1.0]) @ H @ np.diag([f, f, 1.0])
    size = (int(tw * scale), int(th * scale))
    return cv2.warpPerspective(scan, M, size, borderValue=(255, 255, 255)), matched

def ink_fraction(red):
    if red.size == 0:
        return 0.0
    return float(cv2.adaptiveThreshold(red, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15).mean())

def crop(img, box, pad=0.004):
    h, w = img.shape[:2]
    x0, y0 = int(max(0, box['x'] - pad) * w), int(max(0, box['y'] - pad) * h)
    x1, y1 = int(min(1, box['x'] + box['w'] + pad) * w), int(min(1, box['y'] + box['h'] + pad) * h)
    return img[y0:y1, x0:x1]

def stack(images):
    '''Joins the pieces of an answer that spans pages, one above the other.'''
    width = max(i.shape[1] for i in images)
    rows = []
    for k, img in enumerate(images):
        if k:
            rows.append(np.full((6, width, 3), 200, np.uint8))
        rows.append(cv2.copyMakeBorder(img, 0, 0, 0, width - img.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)))
    return np.vstack(rows)

def split_batch(doc, cover, min_points=40):
    '''Splits a batch into scripts at every page that matches the template's cover.'''
    f = 60 / 110
    cover = features(cv2.resize(cover, None, fx=f, fy=f, interpolation=cv2.INTER_AREA))
    starts = [i for i in range(doc.page_count)
              if matching_points(features(page_image(doc, i, 60, gray=True)), cover) >= min_points]
    if not starts or starts[0] != 0:
        starts = [0] + starts
    return [list(range(s, e)) for s, e in zip(starts, starts[1:] + [doc.page_count])]

def import_scripts(pdf_path, template_dir, page_count, boxes, dpi=150):
    '''
    Cuts every answer out of a scanned batch. boxes maps a key (a question id, or
    'name') to its boxes on the template. Returns a list of scripts, each
    {'pages': [...], 'crops': {key: image}, 'ink': {key: extra ink}, 'rough': [pages]},
    plus a list of messages. Works a page at a time so big batches fit in memory.
    '''
    messages = []
    template = {n: load_gray('{}/page-{}.png'.format(template_dir, n)) for n in range(1, page_count + 1)}
    scale = (dpi / 110)
    with pymupdf.open(pdf_path) as doc:
        scripts = split_batch(doc, template[1])
        wrong = [k + 1 for k, s in enumerate(scripts) if len(s) != page_count]
        if wrong:
            messages.append('Script(s) {} do not have {} pages, so were left out: check for missing or extra pages.'
                            .format(', '.join(map(str, wrong)), page_count))
        scripts = [{'pages': s, 'pieces': {}, 'ink': {}, 'rough': []} for s in scripts if len(s) == page_count]
        for n in range(1, page_count + 1):
            on_page = [(key, b) for key, bs in boxes.items() for b in bs if b['page'] == n]
            if not on_page:
                continue
            warped = []
            for script in scripts:
                page, matched = align_page(page_image(doc, script['pages'][n - 1], dpi), template[n], scale)
                warped.append(page)
                if not matched:
                    script['rough'].append(n)
            # The lightest pixel across all scripts keeps the print but loses most handwriting
            clean = np.minimum.reduce([255 - w[:, :, 0] for w in warped])
            clean = 255 - clean
            for key, box in on_page:
                printed = ink_fraction(crop(clean, box))
                for script, page in zip(scripts, warped):
                    piece = crop(page, box)
                    script['pieces'].setdefault(key, []).append(piece)
                    area = piece.shape[0] * piece.shape[1]
                    extra = max(0.0, ink_fraction(piece[:, :, 0]) - printed) * area
                    script['ink'][key] = script['ink'].get(key, 0.0) + extra
        for script in scripts:
            areas = {key: sum(p.shape[0] * p.shape[1] for p in pieces) for key, pieces in script['pieces'].items()}
            script['ink'] = {key: script['ink'][key] / areas[key] for key in script['ink']}
            script['crops'] = {key: stack(pieces) for key, pieces in script.pop('pieces').items()}
    return scripts, messages
