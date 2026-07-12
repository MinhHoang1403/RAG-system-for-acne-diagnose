import assert from 'node:assert/strict';
import test from 'node:test';

import { parseApiError, sendChatMessage } from './chatApi.js';

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('parseApiError maps structured HTTP errors safely', async () => {
  const badRequest = await parseApiError(jsonResponse(400, { detail: { message: 'Nội dung không hợp lệ.' } }));
  const validation = await parseApiError(jsonResponse(422, { detail: { message: 'Sai schema.' } }));
  const rateLimited = await parseApiError(jsonResponse(429, { detail: { message: 'raw backend rate' } }));
  const server = await parseApiError(jsonResponse(500, { detail: { message: 'raw backend server' } }));
  const unavailable = await parseApiError(jsonResponse(503, { detail: { message: 'raw backend unavailable' } }));
  const timeout = await parseApiError(jsonResponse(504, { detail: { message: 'raw backend timeout' } }));

  assert.equal(badRequest.message, 'Nội dung không hợp lệ.');
  assert.equal(validation.message, 'Sai schema.');
  assert.equal(rateLimited.message, 'Hệ thống đang nhận quá nhiều yêu cầu. Vui lòng thử lại sau.');
  assert.equal(server.message, 'Backend không thể xử lý yêu cầu. Vui lòng thử lại.');
  assert.equal(unavailable.message, 'Dịch vụ AI tạm thời chưa sẵn sàng. Vui lòng thử lại sau.');
  assert.equal(timeout.message, 'Yêu cầu xử lý quá thời gian. Vui lòng thử lại hoặc chọn mô hình khác.');
});

test('sendChatMessage distinguishes network failure from HTTP errors', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  globalThis.fetch = async () => {
    throw new TypeError('network down');
  };

  await assert.rejects(
    () => sendChatMessage({ message: 'mụn', sessionId: null }),
    (error) => {
      assert.equal(error.status, null);
      assert.match(error.message, /Không thể kết nối tới backend/);
      return true;
    },
  );
});

test('sendChatMessage sends selected provider and model id', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  let capturedBody = null;
  globalThis.fetch = async (_url, init) => {
    capturedBody = JSON.parse(init.body);
    return jsonResponse(200, { answer: 'ok' });
  };

  await sendChatMessage({
    message: 'Bốn cơ chế chính gây mụn là gì?',
    sessionId: 'session-1',
    llmProvider: 'gemini',
    llmModel: 'gemini-3.5-flash',
    allowModelFallback: true,
  });

  assert.equal(capturedBody.llm_provider, 'gemini');
  assert.equal(capturedBody.llm_model, 'gemini-3.5-flash');
  assert.equal(capturedBody.allow_model_fallback, true);
});
