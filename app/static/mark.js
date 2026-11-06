// Marking one question across every script, one answer at a time.
const answers = MARKING.answers;
let current = Math.max(0, answers.findIndex(a => a.mark === null));

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': MARKING.csrf},
    body: JSON.stringify(body)
  }).then(r => {
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  });
}

function save(answer, changes) {
  Object.assign(answer, changes);
  render();
  return post('/answer/' + answer.id, changes).catch(() => alert('Could not save: check the app is still running.'));
}

function show(i) {
  if (!answers.length) return;
  saveComment();
  current = Math.max(0, Math.min(answers.length - 1, i));
  render();
  // Load the next image in the background so moving on is instant
  if (answers[current + 1]) new Image().src = '/answer/' + answers[current + 1].id + '.png';
}

function render() {
  if (!answers.length) return;
  const a = answers[current];
  document.getElementById('answerImage').src = '/answer/' + a.id + '.png';
  renderTicks(a);
  document.getElementById('scriptLabel').textContent = 'Script ' + a.script;
  document.getElementById('blankBadge').style.display = a.blank ? '' : 'none';
  const comment = document.getElementById('comment');
  if (document.activeElement !== comment) comment.value = a.comment;
  comment.dataset.answer = a.id;

  const buttons = document.getElementById('markButtons');
  buttons.innerHTML = '';
  for (let m = 0; m <= MARKING.maxMark; m++) {
    const b = document.createElement('button');
    b.className = 'btn btn-lg ' + (a.mark === m ? 'btn-primary' : 'btn-default');
    b.textContent = m;
    b.addEventListener('click', () => give(m));
    buttons.appendChild(b);
  }

  const chips = document.getElementById('chips');
  chips.innerHTML = '';
  answers.forEach((x, i) => {
    const c = document.createElement('span');
    c.className = 'chip' + (x.mark !== null ? ' marked' : '') + (x.blank ? ' blank' : '') + (i === current ? ' current' : '');
    c.textContent = x.mark !== null ? x.script + ': ' + x.mark : x.script;
    c.title = 'Script ' + x.script + (x.blank ? ' (little writing found)' : '');
    c.addEventListener('click', () => show(i));
    chips.appendChild(c);
  });

  const marked = answers.filter(x => x.mark !== null).length;
  document.getElementById('progress').textContent =
    'Answer ' + (current + 1) + ' of ' + answers.length + ' · ' + marked + ' marked';

  const blanks = answers.filter(x => x.blank && x.mark === null);
  document.getElementById('blankTools').style.display = blanks.length ? '' : 'none';
  document.getElementById('blankCount').textContent =
    blanks.length + ' unmarked answer' + (blanks.length === 1 ? ' has' : 's have') + ' little or no writing.';
}

// Ticks are placed at fractions of the answer image, so they stay put at any size
function renderTicks(a) {
  const area = document.getElementById('answerArea');
  area.querySelectorAll('.tick').forEach(t => t.remove());
  a.ticks.forEach((t, i) => {
    const tick = document.createElement('span');
    tick.className = 'tick';
    tick.textContent = '✓';
    tick.title = 'Remove tick';
    tick.style.left = t[0] * 100 + '%';
    tick.style.top = t[1] * 100 + '%';
    tick.addEventListener('click', e => {
      e.stopPropagation();
      save(a, {ticks: a.ticks.filter((_, j) => j !== i)});
    });
    area.appendChild(tick);
  });
}

function addTick(e) {
  const a = answers[current];
  const rect = document.getElementById('answerImage').getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  save(a, {ticks: a.ticks.concat([[x, y]])});
}

function give(mark) {
  const a = answers[current];
  saveComment();
  save(a, {mark: mark});
  setTimeout(nextUnmarked, 200);
}

function nextUnmarked() {
  const after = answers.findIndex((x, i) => i > current && x.mark === null);
  const any = answers.findIndex(x => x.mark === null);
  if (after >= 0) show(after);
  else if (any >= 0) show(any);
  else {
    render();
    document.getElementById('progress').textContent = 'All ' + answers.length + ' answers marked.';
    const next = document.getElementById('nextQuestion');
    if (next) next.classList.replace('btn-default', 'btn-success');
  }
}

function saveComment() {
  const input = document.getElementById('comment');
  const a = answers.find(x => String(x.id) === input.dataset.answer);
  if (a && input.value.trim() !== a.comment) save(a, {comment: input.value.trim()});
}

if (answers.length) {
  document.getElementById('answerArea').addEventListener('click', addTick);
  document.getElementById('prev').addEventListener('click', () => show(current - 1));
  document.getElementById('next').addEventListener('click', () => show(current + 1));
  document.getElementById('zeroBlanks').addEventListener('click', () => {
    const blanks = answers.filter(x => x.blank && x.mark === null);
    if (confirm('Give 0 to all ' + blanks.length + ' of these? Check a few first: some short answers look blank.')) {
      blanks.forEach(x => save(x, {mark: 0}));
      nextUnmarked();
    }
  });
  const comment = document.getElementById('comment');
  comment.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      saveComment();
      comment.blur();
      show(current + 1);
    } else if (e.key === 'Escape') {
      comment.blur();
    }
  });
  comment.addEventListener('blur', saveComment);

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (/^[0-9]$/.test(e.key) && Number(e.key) <= MARKING.maxMark) give(Number(e.key));
    else if (e.key === 'ArrowRight') show(current + 1);
    else if (e.key === 'ArrowLeft') show(current - 1);
    else if (e.key === 'c' || e.key === 'C') { e.preventDefault(); comment.focus(); }
  });
  show(current);
}

const classComment = document.getElementById('classComment');
if (classComment) {
  classComment.addEventListener('change', () => {
    post(MARKING.classCommentUrl, {comment: classComment.value})
      .then(() => document.getElementById('classSaved').textContent = 'Saved.');
  });
}
