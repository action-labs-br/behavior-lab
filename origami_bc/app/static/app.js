const $ = (id) => document.getElementById(id);
let experiment, run, samples = [], participants = [], previewURL, nextPreviewURL, sessionParticipant, lastPrediction, lastTraining, lastNotice = "";
const show = (id, visible = true) => { $(id).hidden = !visible; };
const notice = (text = '') => { lastNotice = text; $('notice').textContent = translateError(text); };
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
  sessionParticipant = session.participant; localizeStatic();
  const adminPage = location.pathname.startsWith('/admin');
  for (const id of ['join','participant','admin-login','admin-panel']) show(id, false);
  if (adminPage) {
    show(session.admin ? 'admin-panel' : 'admin-login');
    if (session.admin) await refresh();
  } else {
    show(session.participant ? 'participant' : 'join');
    if (session.participant) $('welcome').textContent = t('welcome', {name:session.participant.display_name});
  }
}
async function renderRun() {
  run = await api(`/api/runs/${run.id}`);
  const finished = run.status === 'COMPLETE';
  show('start', false); show('finished', finished); show('fold', !finished);
  if (finished) return;
  const step = experiment.steps[run.step_index];
  const stage = run.stage || (run.sample?.status === 'READY' ? 'ACTION' : 'CURRENT_PHOTO');
  $('step-label').textContent = t('step', {current:run.step_index + 1, total:experiment.steps.length});
  $('step-progress').max = experiment.steps.length; $('step-progress').value = run.step_index;
  $('step-title').textContent = stepText(step, 'title');
  $('instruction-text').textContent = stepText(step, 'instruction');
  const diagrams = {crease_center:'01', fold_left_corner:'02', fold_right_corner:'02', narrow_left_side:'03', narrow_right_side:'03', close_body:'04', fold_first_wing:'05', fold_second_wing:'06'};
  $('instruction-image').src = `/static/instructions/How-to-Make-a-Paper-Airplane-${diagrams[step.action_id]}.jpg`;
  $('instruction-image').alt = t('Diagram for {action}', {action:stepText(step, 'title')});
  show('current-photo', stage === 'CURRENT_PHOTO');
  show('instruction', stage !== 'CURRENT_PHOTO');
  show('confirm-action', stage === 'ACTION');
  show('next-state', stage === 'NEXT_PHOTO');
  $('photo').value = ''; $('upload').disabled = true; show('preview', false);
  if (nextPreviewURL) URL.revokeObjectURL(nextPreviewURL);
  nextPreviewURL = null;
  $('next-photo').value = ''; $('upload-next').disabled = true;
  const nextReady = run.next_sample?.status === 'READY';
  if (nextReady) $('next-preview').src = `/api/samples/${run.next_sample.id}/image`;
  show('next-preview', nextReady); show('advance', stage === 'NEXT_PHOTO' && nextReady);
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
async function uploadSample(file, stepIndex) {
  if (!file) throw new Error(t('Choose a photo first'));
  if (file.size > 10 * 1024 * 1024) throw new Error(t('Choose an image smaller than 10 MiB'));
  const {sample, upload} = await api('/api/samples', {method:'POST', body:{run_id:run.id, step_index:stepIndex, content_type:file.type}});
  if (upload) {
    let response;
    if (upload.fields) {
      const body = new FormData();
      for (const [key,value] of Object.entries(upload.fields)) body.append(key,value);
      body.append('file', file);
      response = await fetch(upload.url, {method:'POST', body});
    } else response = await fetch(upload.url, {method:'PUT', headers:{'X-Origami-Request':'1'}, body:file});
    if (!response.ok) throw new Error(t('Upload failed. Your step is saved; try again.'));
    await api(`/api/samples/${sample.id}/complete`, {method:'POST'});
  }
  await renderRun();
}
action('upload', async () => { await uploadSample($('photo').files[0], run.step_index); });
$('next-photo').addEventListener('change', () => {
  const file = $('next-photo').files[0]; $('upload-next').disabled = !file;
  if (nextPreviewURL) URL.revokeObjectURL(nextPreviewURL);
  if (file) { nextPreviewURL = URL.createObjectURL(file); $('next-preview').src = nextPreviewURL; }
  show('next-preview', !!file);
});
action('upload-next', async () => { await uploadSample($('next-photo').files[0], run.step_index + 1); });
action('confirm-action', async () => { await api(`/api/runs/${run.id}/confirm/${run.step_index}`, {method:'POST'}); await renderRun(); });
action('advance', async () => { await api(`/api/runs/${run.id}/advance/${run.step_index}`, {method:'POST'}); await renderRun(); });
function gallery() {
  $('gallery').replaceChildren();
  for (const sample of samples.filter(s => s.status === 'READY' && (!$('filter').value || s.action_id === $('filter').value))) {
    const card = document.createElement('div');
    const image = document.createElement('img'); image.src = `/api/samples/${sample.id}/image`; image.loading = 'lazy'; image.alt = t('photoBefore', {action:actionTitle(sample.action_id)});
    const name = participants.find(p => p.id === sample.participant_id)?.display_name || t('Participant');
    card.append(image, text('p', t('gallery', {name, run:sample.run_id.slice(0,6), step:sample.step_index + 1, action:actionTitle(sample.action_id)})));
    const button = text('button', sample.excluded ? t('Include sample') : t('Exclude sample'), 'secondary');
    button.onclick = async () => { button.disabled = true; try { await api(`/api/samples/${sample.id}/exclude`, {method:'POST'}); await refresh(); } catch(error) { notice(error.message); button.disabled = false; } };
    card.append(button); $('gallery').append(card);
  }
}
async function refresh() {
  const [stats, collection, models] = await Promise.all([api('/api/dataset/stats'), api('/api/samples'), api('/api/models')]);
  participants = stats.participants; samples = collection;
  $('stats').replaceChildren();
  for (const [label, value] of [[t('Participants'),participants.length],[t('Completed runs'),stats.completed_runs],[t('Eligible photos'),stats.samples],[t('Excluded'),stats.excluded]]) {
    const item = text('div','', 'stat'); item.append(text('strong',value), text('span',label)); $('stats').append(item);
  }
  $('stats').append(text('p', experiment.steps.map(s => `${actionTitle(s.action_id)}: ${stats.counts[s.action_id] || 0}`).join(' · ')));
  $('active').textContent = `${stats.control.closed ? t('Collection closed.')+' ' : ''}${stats.active ? t('activeModel', {source:t(stats.active.source), id:stats.active.id}) : t('No active model.')} ${stats.fallback ? t('fallbackSaved', {id:stats.fallback.id}) : t('No fallback prepared yet.')}`;
  const held = $('holdout').value;
  $('holdout').replaceChildren(new Option(t('Automatic participant holdout'),'auto'), new Option(t('Training only — no held-out evaluation'),'none'));
  for (const participant of participants) $('holdout').add(new Option(participant.display_name,participant.id));
  if ([...$('holdout').options].some(o => o.value === held)) $('holdout').value = held;
  const filtered = $('filter').value;
  $('filter').replaceChildren(new Option(t('All actions'), ''));
  for (const step of experiment.steps) $('filter').add(new Option(stepText(step, 'title'), step.action_id));
  $('filter').value = filtered;
  gallery(); $('models').replaceChildren();
  for (const model of models.sort((a,b) => b.created_at.localeCompare(a.created_at))) {
    const row = text('div','', 'model');
    row.append(text('p', t('modelHistory', {date:new Date(model.created_at).toLocaleString(language), id:model.id, train:model.training_samples, test:model.test_samples, accuracy:model.test_accuracy == null ? t('not evaluated') : (model.test_accuracy*100).toFixed(1)+'%'})));
    for (const [label, command] of [[t('Mark as fallback'),'fallback'],[t('Activate'),'activate']]) {
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
  lastTraining = status;
  $('training-status').textContent = `${t(status.status)}${status.total ? t('embeddingProgress', {done:status.done, total:status.total}) : ''}${status.error ? ': '+translateError(status.error) : ''}`;
  const running = ['QUEUED','RUNNING'].includes(status.status); $('train').disabled = running;
  $('metrics').replaceChildren();
  if (status.model) {
    const m = status.model;
    $('metrics').append(text('p', t('metrics', {train:(m.training_accuracy*100).toFixed(1)+'%', test:m.test_accuracy == null ? t('not evaluated') : (m.test_accuracy*100).toFixed(1)+'%', mode:t(m.evaluation_mode)})));
    if (m.confusion_matrix) {
      $('metrics').append(text('p', t('confusion', {classes:m.classes.map(actionTitle).join(', ')})));
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
  const file = $('inference-photo').files[0]; if (!file) throw new Error(t('Choose a photo first'));
  const result = await api('/api/predict', {method:'POST', body:file});
  lastPrediction = result; renderPrediction();
});
function renderPrediction() {
  const result = lastPrediction; if (!result) return;
  $('prediction').replaceChildren(text('h3',actionTitle(result.prediction.action_id)), text('p',t('predictionModel', {source:t(result.source), id:result.model_version})));
  for (const item of result.probabilities) {
    const row = text('div','', 'probability'); const bar = document.createElement('meter'); bar.min=0; bar.max=1; bar.value=item.probability; bar.setAttribute('aria-label',actionTitle(item.action_id));
    row.append(text('label', `${actionTitle(item.action_id)} — ${(item.probability*100).toFixed(1)}%`), bar); $('prediction').append(row);
  }
}
action('cleanup', async () => {
  const result = await api('/api/admin/cleanup', {method:'POST',body:{experiment_id:$('cleanup-confirm').value}});
  await refresh(); notice(result.message);
});
action('reopen', async () => { await api('/api/admin/reopen',{method:'POST'}); await refresh(); });
$('language').addEventListener('change', async () => {
  language = $('language').value;
  try { localStorage.setItem('origami-language', language); } catch (_) {}
  localizeStatic(); notice(lastNotice);
  if (sessionParticipant) $('welcome').textContent = t('welcome', {name:sessionParticipant.display_name});
  // Update copy in place: changing language must not clear a selected photo.
  if (run && run.status !== 'COMPLETE') {
    const step = experiment.steps[run.step_index];
    $('step-label').textContent = t('step', {current:run.step_index + 1, total:experiment.steps.length});
    $('step-title').textContent = stepText(step, 'title');
    $('instruction-text').textContent = stepText(step, 'instruction');
    $('instruction-image').alt = t('Diagram for {action}', {action:stepText(step, 'title')});
  }
  renderPrediction();
  if (!$('admin-panel').hidden) {
    try { await refresh(); } catch(error) { notice(error.message); }
  }
});
boot().catch(error => notice(error.message));
