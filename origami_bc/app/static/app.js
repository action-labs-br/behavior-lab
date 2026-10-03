const $ = (id) => document.getElementById(id);
let experiment, run, samples = [], participants = [], previewURL;
const show = (id, visible = true) => { $(id).hidden = !visible; };
const notice = (text = '') => { $('notice').textContent = text; };
async function api(path, options = {}) {
  const headers = {'X-Origami-Request': '1', ...options.headers};
  if (options.body && typeof options.body !== 'string' && !(options.body instanceof Blob)) {
    headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, {...options, headers});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
function action(id, callback) {
  $(id).addEventListener('click', async () => {
    $(id).disabled = true; notice();
    try { await callback(); } catch (error) { notice(error.message); }
    finally { $(id).disabled = false; }
  });
}
function form(id, path, after) {
  $(id).addEventListener('submit', async (event) => {
    event.preventDefault(); notice();
    const button = event.target.querySelector('button'); button.disabled = true;
    try { await api(path, {method:'POST', body:Object.fromEntries(new FormData(event.target))}); await after(); }
    catch(error) { notice(error.message); } finally { button.disabled = false; }
  });
}
function text(tag, value, className) {
  const node = document.createElement(tag); node.textContent = value;
  if (className) node.className = className; return node;
}
async function boot() {
  experiment = await api('/api/experiment');
  const session = await api('/api/session');
  const adminPage = location.pathname.startsWith('/admin');
  for (const id of ['join','participant','admin-login','admin-panel']) show(id, false);
  if (adminPage) {
    show(session.admin ? 'admin-panel' : 'admin-login');
    if (session.admin) await refresh();
  } else {
    show(session.participant ? 'participant' : 'join');
    if (session.participant) $('welcome').textContent = `Welcome, ${session.participant.display_name}. Ready to make a demonstration?`;
  }
}
async function renderRun() {
  run = await api(`/api/runs/${run.id}`);
  const finished = run.status === 'COMPLETE';
  show('start', false); show('finished', finished); show('fold', !finished);
  if (finished) return;
  const step = experiment.steps[run.step_index];
  $('step-label').textContent = `Step ${run.step_index + 1} of ${experiment.steps.length}`;
  $('step-progress').max = experiment.steps.length; $('step-progress').value = run.step_index;
  $('step-title').textContent = step.title;
  $('instruction-text').textContent = step.instruction;
  const ready = run.sample?.status === 'READY';
  show('instruction', ready); show('capture-label', !ready); show('upload', !ready); show('capture-prompt', !ready);
  $('photo').value = ''; $('upload').disabled = true; show('preview', false);
}
async function start() { run = await api('/api/runs', {method:'POST'}); await renderRun(); }
form('join-form', '/api/session/join', async () => { await boot(); await start(); });
form('admin-form', '/api/admin/login', boot);
action('leave', async () => { await api('/api/session/leave', {method:'POST'}); location.href = '/'; });
action('start', start); action('again', start);
$('photo').addEventListener('change', () => {
  const file = $('photo').files[0]; $('upload').disabled = !file;
  if (previewURL) URL.revokeObjectURL(previewURL);
  if (file) { previewURL = URL.createObjectURL(file); $('preview').src = previewURL; }
  show('preview', !!file);
});
action('upload', async () => {
  const file = $('photo').files[0];
  if (!file) throw new Error('Choose a photo first');
  if (file.size > 10 * 1024 * 1024) throw new Error('Choose an image smaller than 10 MiB');
  const {sample, upload} = await api('/api/samples', {method:'POST', body:{run_id:run.id, step_index:run.step_index, content_type:file.type}});
  if (upload) {
    let response;
    if (upload.fields) {
      const body = new FormData();
      for (const [key,value] of Object.entries(upload.fields)) body.append(key,value);
      body.append('file', file);
      response = await fetch(upload.url, {method:'POST', body});
    } else response = await fetch(upload.url, {method:'PUT', headers:{'X-Origami-Request':'1'}, body:file});
    if (!response.ok) throw new Error('Upload failed. Your step is saved; try again.');
    await api(`/api/samples/${sample.id}/complete`, {method:'POST'});
  }
  await renderRun();
});
action('advance', async () => { await api(`/api/runs/${run.id}/advance/${run.step_index}`, {method:'POST'}); await renderRun(); });
function gallery() {
  $('gallery').replaceChildren();
  for (const sample of samples.filter(s => s.status === 'READY' && (!$('filter').value || s.action_id === $('filter').value))) {
    const card = document.createElement('div');
    const image = document.createElement('img'); image.src = `/api/samples/${sample.id}/image`; image.loading = 'lazy'; image.alt = `Paper before ${sample.action_id}`;
    const name = participants.find(p => p.id === sample.participant_id)?.display_name || 'Participant';
    card.append(image, text('p', `${name} · Run ${sample.run_id.slice(0,6)} · Step ${sample.step_index + 1} · ${sample.action_id}`));
    const button = text('button', sample.excluded ? 'Include sample' : 'Exclude sample', 'secondary');
    button.onclick = async () => { button.disabled = true; try { await api(`/api/samples/${sample.id}/exclude`, {method:'POST'}); await refresh(); } catch(error) { notice(error.message); button.disabled = false; } };
    card.append(button); $('gallery').append(card);
  }
}
async function refresh() {
  const [stats, collection, models] = await Promise.all([api('/api/dataset/stats'), api('/api/samples'), api('/api/models')]);
  participants = stats.participants; samples = collection;
  $('stats').replaceChildren();
  for (const [label, value] of [['Participants',participants.length],['Completed runs',stats.completed_runs],['Eligible photos',stats.samples],['Excluded',stats.excluded]]) {
    const item = text('div','', 'stat'); item.append(text('strong',value), text('span',label)); $('stats').append(item);
  }
  $('stats').append(text('p', experiment.steps.map(s => `${s.title}: ${stats.counts[s.action_id] || 0}`).join(' · ')));
  $('active').textContent = `${stats.control.closed ? 'Collection closed. ' : ''}${stats.active ? `Active ${stats.active.source} model: ${stats.active.id}` : 'No active model.'} ${stats.fallback ? `Fallback saved: ${stats.fallback.id}` : 'No fallback prepared yet.'}`;
  const held = $('holdout').value;
  $('holdout').replaceChildren(new Option('Automatic participant holdout','auto'), new Option('Training only — no held-out evaluation','none'));
  for (const participant of participants) $('holdout').add(new Option(participant.display_name,participant.id));
  if ([...$('holdout').options].some(o => o.value === held)) $('holdout').value = held;
  if ($('filter').options.length === 1) for (const step of experiment.steps) $('filter').add(new Option(step.title, step.action_id));
  gallery(); $('models').replaceChildren();
  for (const model of models.sort((a,b) => b.created_at.localeCompare(a.created_at))) {
    const row = text('div','', 'model');
    row.append(text('p', `${model.created_at} · ${model.id} · ${model.training_samples} training / ${model.test_samples} test photos · test accuracy ${model.test_accuracy == null ? 'not evaluated' : (model.test_accuracy*100).toFixed(1)+'%'}`));
    for (const [label, command] of [['Mark as fallback','fallback'],['Activate','activate']]) {
      const button = text('button',label,'secondary'); button.onclick = async () => {
        button.disabled = true;
        try { await api(`/api/models/${model.id}/${command}`, {method:'POST'}); await refresh(); }
        catch(error) { notice(error.message); button.disabled = false; }
      }; row.append(button);
    }
    $('models').append(row);
  }
  await pollTraining();
}
$('filter').addEventListener('change', gallery);
action('refresh', refresh);
let polling;
async function pollTraining() {
  clearTimeout(polling);
  const status = await api('/api/train/status');
  $('training-status').textContent = `${status.status}${status.total ? ` — embeddings ${status.done}/${status.total}` : ''}${status.error ? ': '+status.error : ''}`;
  const running = ['QUEUED','RUNNING'].includes(status.status); $('train').disabled = running;
  $('metrics').replaceChildren();
  if (status.model) {
    const m = status.model;
    $('metrics').append(text('p', `Training accuracy ${(m.training_accuracy*100).toFixed(1)}% · Held-out accuracy ${m.test_accuracy == null ? 'not evaluated' : (m.test_accuracy*100).toFixed(1)+'%'} · ${m.evaluation_mode}`));
    if (m.confusion_matrix) {
      $('metrics').append(text('p', 'Confusion matrix: rows = actual, columns = predicted. Class order: '+m.classes.join(', ')));
      $('metrics').append(text('pre',m.confusion_matrix.map(row => row.join(' ')).join('\n')));
    }
  }
  if (running) polling = setTimeout(async () => { try { await refresh(); } catch(error) { notice(error.message); } }, 1500);
}
action('train', async () => {
  const selection = $('holdout').value;
  await api('/api/train', {method:'POST', body:{holdout:selection === 'auto' ? null : selection === 'none' ? [] : [selection]}});
  await pollTraining();
});
action('predict', async () => {
  const file = $('inference-photo').files[0]; if (!file) throw new Error('Choose a photo first');
  const result = await api('/api/predict', {method:'POST', body:file});
  $('prediction').replaceChildren(text('h3',experiment.steps.find(s => s.action_id === result.prediction.action_id).title), text('p',`${result.source} model ${result.model_version}`));
  for (const item of result.probabilities) {
    const row = text('div','', 'probability'); const bar = document.createElement('meter'); bar.min=0; bar.max=1; bar.value=item.probability; bar.setAttribute('aria-label',item.action_id);
    row.append(text('label', `${experiment.steps.find(s => s.action_id === item.action_id).title} — ${(item.probability*100).toFixed(1)}%`), bar); $('prediction').append(row);
  }
});
action('cleanup', async () => {
  const result = await api('/api/admin/cleanup', {method:'POST',body:{experiment_id:$('cleanup-confirm').value}});
  await refresh(); notice(result.message);
});
action('reopen', async () => { await api('/api/admin/reopen',{method:'POST'}); await refresh(); });
boot().catch(error => notice(error.message));
