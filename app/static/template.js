// Paper template editor: draw, move and resize answer boxes for each question.
// Box coordinates are stored as fractions of the page so they fit any scan size.
let questions = [];
let regions = [];
let active = null;      // a question id, or 'name' for the name box
let drag = null;        // the box being drawn, moved or resized

function api(url, method, body) {
  return fetch(url, {
    method: method,
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': PAPER.csrf},
    body: body ? JSON.stringify(body) : undefined
  }).then(r => {
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  });
}

function colour(questionId) {
  if (questionId === 'name') return '#333';
  const i = questions.findIndex(q => q.id === questionId);
  return 'hsl(' + ((i * 137) % 360) + ', 70%, 40%)';
}

function owner(region) {
  return region.kind === 'name' ? 'name' : region.question_id;
}

function label(questionId) {
  if (questionId === 'name') return 'Name';
  const q = questions.find(q => q.id === questionId);
  return q ? q.label : '?';
}

function renderList() {
  const list = document.getElementById('questionList');
  list.innerHTML = '';
  const items = [{id: 'name', label: 'Name box', max_mark: null}].concat(questions);
  for (const q of items) {
    const count = regions.filter(r => owner(r) === q.id).length;
    const item = document.createElement('div');
    item.className = 'list-group-item' + (q.id === active ? ' active-question' : '');
    item.innerHTML = '<span class="swatch"></span><strong></strong>' +
      (q.id === 'name' ? '' : ' <span class="pull-right"><input class="form-control" type="number" min="0"> marks</span>') +
      ' <small class="' + (count ? 'text-muted' : 'no-boxes') + '">' +
      (count ? count + (count === 1 ? ' box' : ' boxes') : 'no box') + '</small>';
    item.querySelector('.swatch').style.background = colour(q.id);
    item.querySelector('strong').textContent = q.label;
    if (q.id !== 'name') {
      item.querySelector('strong').title = 'Double-click to rename';
      item.querySelector('strong').addEventListener('dblclick', () => {
        const name = prompt('Question name', q.label);
        if (name && name.trim()) {
          q.label = name.trim().slice(0, 20);
          api('/question/' + q.id, 'POST', {label: q.label});
          render();
        }
      });
    }
    const input = item.querySelector('input');
    if (input) {
      input.value = q.max_mark ?? '';
      input.addEventListener('click', e => e.stopPropagation());
      input.addEventListener('change', () => {
        q.max_mark = input.value === '' ? null : parseInt(input.value);
        api('/question/' + q.id, 'POST', {max_mark: q.max_mark});
      });
    }
    item.addEventListener('click', () => select(q.id, true));
    list.appendChild(item);
  }
}

function renderBoxes() {
  document.querySelectorAll('.page-wrap .box').forEach(b => b.remove());
  for (const r of regions) {
    const wrap = document.querySelector('.page-wrap[data-page="' + r.page + '"]');
    if (!wrap) continue;
    const c = colour(owner(r));
    const box = document.createElement('div');
    box.className = 'box' + (owner(r) === active ? ' selected' : '');
    box.dataset.id = r.id;
    box.style.cssText = 'left:' + r.x * 100 + '%;top:' + r.y * 100 + '%;width:' + r.w * 100 +
      '%;height:' + r.h * 100 + '%;border-color:' + c + ';background:' + c.replace('hsl', 'hsla').replace(')', ', 0.08)');
    if (owner(r) === 'name') box.style.background = 'rgba(0,0,0,0.08)';
    box.innerHTML = '<span class="tag"></span><span class="remove" title="Delete box">&times;</span><span class="handle"></span>';
    box.querySelector('.tag').textContent = label(owner(r));
    box.querySelector('.tag').style.background = c;
    box.querySelector('.handle').style.borderColor = c;
    box.querySelector('.remove').addEventListener('mousedown', e => {
      e.stopPropagation();
      api('/region/' + r.id, 'DELETE').then(() => {
        regions = regions.filter(x => x.id !== r.id);
        render();
      });
    });
    box.querySelector('.tag').addEventListener('mousedown', e => {
      e.stopPropagation();
      select(owner(r), false);
    });
    box.addEventListener('mousedown', e => {
      // Boxes of other questions don't get in the way of drawing a new one
      if (owner(r) !== active) return;
      e.stopPropagation();
      const mode = e.target.classList.contains('handle') ? 'resize' : 'move';
      drag = {mode: mode, region: r, wrap: wrap, start: point(e, wrap), orig: Object.assign({}, r)};
    });
    wrap.appendChild(box);
  }
}

function render() {
  renderList();
  renderBoxes();
}

function select(questionId, scroll) {
  active = questionId;
  render();
  const ms = document.getElementById('markScheme');
  ms.innerHTML = '';
  if (questionId !== 'name') {
    const img = document.createElement('img');
    img.src = '/question/' + questionId + '/markscheme';
    img.onerror = () => img.remove();
    ms.appendChild(img);
  }
  if (scroll) {
    const first = regions.find(r => owner(r) === questionId);
    const box = first && document.querySelector('.box[data-id="' + first.id + '"]');
    if (box) box.scrollIntoView({behavior: 'smooth', block: 'center'});
  }
}

function point(e, wrap) {
  const rect = wrap.getBoundingClientRect();
  return {
    x: Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
    y: Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height))
  };
}

document.querySelectorAll('.page-wrap').forEach(wrap => {
  wrap.addEventListener('mousedown', e => {
    if (active === null) {
      alert('Pick a question (or the name box) on the left first.');
      return;
    }
    const start = point(e, wrap);
    const region = {id: null, kind: active === 'name' ? 'name' : 'answer',
                    question_id: active === 'name' ? null : active,
                    page: parseInt(wrap.dataset.page), x: start.x, y: start.y, w: 0, h: 0};
    if (active === 'name') regions = regions.filter(r => r.kind !== 'name');
    regions.push(region);
    drag = {mode: 'draw', region: region, wrap: wrap, start: start};
  });
});

document.addEventListener('mousemove', e => {
  if (!drag) return;
  const p = point(e, drag.wrap);
  const r = drag.region;
  if (drag.mode === 'draw') {
    r.x = Math.min(p.x, drag.start.x); r.w = Math.abs(p.x - drag.start.x);
    r.y = Math.min(p.y, drag.start.y); r.h = Math.abs(p.y - drag.start.y);
  } else if (drag.mode === 'move') {
    r.x = Math.min(1 - r.w, Math.max(0, drag.orig.x + p.x - drag.start.x));
    r.y = Math.min(1 - r.h, Math.max(0, drag.orig.y + p.y - drag.start.y));
  } else {
    r.w = Math.max(0.02, p.x - r.x);
    r.h = Math.max(0.01, p.y - r.y);
  }
  drag.moved = true;
  renderBoxes();
});

document.addEventListener('mouseup', () => {
  if (!drag) return;
  const {mode, region} = drag;
  drag = null;
  if (mode === 'draw') {
    if (region.w < 0.02 || region.h < 0.01) {
      regions = regions.filter(r => r !== region);
      render();
      return;
    }
    api(PAPER.regions, 'POST', region).then(saved => {
      Object.assign(region, saved);
      render();
    });
  } else {
    api('/region/' + region.id, 'POST', region);
    render();
  }
});

document.getElementById('addQuestion').addEventListener('submit', e => {
  e.preventDefault();
  const form = e.target;
  api(PAPER.questions, 'POST', {label: form.label.value, max_mark: parseInt(form.max_mark.value) || null})
    .then(q => {
      questions.push(q);
      form.reset();
      select(q.id, false);
    });
});

api(PAPER.data, 'GET').then(data => {
  questions = data.questions;
  regions = data.regions;
  render();
});
