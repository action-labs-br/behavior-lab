const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const vm = require('node:vm');

const source = readFileSync('app/static/app.js', 'utf8');
const uploadSource = source.slice(source.indexOf('async function uploadSample('), source.indexOf("action('upload',"));

function setup(fetchResult, completionError, upload = {url:'https://storage.example', fields:{key:'photo'}}) {
  const calls = [];
  const context = vm.createContext({
    TypeError, Error, FormData, run:{id:'run-1'}, t:value => value,
    fetch:async (url, options) => {
      calls.push({url, options});
      if (fetchResult instanceof Error) throw fetchResult;
      return fetchResult;
    },
    api:async (path, options) => {
      calls.push({path, options});
      if (path === '/api/samples') return {sample:{id:'sample-1'}, upload};
      if (completionError) throw completionError;
      return {status:'READY'};
    },
    renderRun:async () => { calls.push({render:true}); },
  });
  vm.runInContext(uploadSource, context);
  return {calls, upload:() => context.uploadSample(new Blob(['photo'], {type:'image/png'}), 0)};
}

test('empty S3 204 response completes the photo and reveals the fold', async () => {
  const state = setup(new Response(null, {status:204}));
  await state.upload();
  assert.equal(state.calls[1].options.method, 'POST');
  assert.deepEqual([...state.calls[1].options.body.keys()], ['key', 'file']);
  assert.equal(state.calls[2].path, '/api/samples/sample-1/complete');
  assert.equal(state.calls[3].render, true);
});

test('unreadable S3 response recovers through server image validation', async () => {
  const state = setup(new TypeError('Failed to fetch'));
  await state.upload();
  assert.equal(state.calls[2].path, '/api/samples/sample-1/complete');
  assert.equal(state.calls[3].render, true);
});

test('missing or invalid upload never advances the participant', async () => {
  const state = setup(new TypeError('Failed to fetch'), new Error('Upload missing or invalid'));
  await assert.rejects(state.upload(), /Upload missing or invalid/);
  assert.equal(state.calls.some(call => call.render), false);
});

test('explicit S3 failure remains an upload error', async () => {
  const state = setup(new Response(null, {status:403}));
  await assert.rejects(state.upload(), /Upload failed/);
  assert.equal(state.calls.length, 2);
});

test('local upload network failures remain errors', async () => {
  const state = setup(new TypeError('Failed to fetch'), null, {url:'/api/samples/sample-1/upload'});
  await assert.rejects(state.upload(), /Failed to fetch/);
  assert.equal(state.calls.length, 2);
});

test('successful upload still requires server image validation', async () => {
  const state = setup(new Response(null, {status:204}), new Error('Upload missing or invalid'));
  await assert.rejects(state.upload(), /Upload missing or invalid/);
  assert.equal(state.calls.some(call => call.render), false);
});

test('already confirmed sample resumes without uploading again', async () => {
  const state = setup(null, null, null);
  await state.upload();
  assert.equal(state.calls.length, 2);
  assert.equal(state.calls[1].render, true);
});
