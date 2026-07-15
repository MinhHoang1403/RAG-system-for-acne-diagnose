import assert from 'node:assert/strict';
import test from 'node:test';
import {
  deriveChatTitleFromFirstUserMessage,
  deriveChatTitleFromMessages,
  shouldGenerateSessionTitle,
} from './chatTitle.js';

test('deriveChatTitleFromFirstUserMessage removes leading numbering and command filler', () => {
  const title = deriveChatTitleFromFirstUserMessage(
    '1. Hãy lập bảng so sánh các lựa chọn điều trị đầu tay trong 12 tuần cho mụn nhẹ đến trung bình.'
  );

  assert.equal(title.startsWith('1.'), false);
  assert.equal(title.startsWith('Hãy'), false);
  assert.match(title, /^Lập bảng so sánh/);
  assert.ok(title.length <= 49);
});

test('deriveChatTitleFromFirstUserMessage truncates long messages at a clean word boundary', () => {
  const title = deriveChatTitleFromFirstUserMessage(
    'Tôi đang uống isotretinoin, cần theo dõi gì và khi nào phải liên hệ bác sĩ?'
  );

  assert.match(title, /^Tôi đang uống isotretinoin/);
  assert.match(title, /\.\.\.$/);
  assert.ok(title.length <= 49);
});

test('deriveChatTitleFromFirstUserMessage preserves concise Vietnamese titles', () => {
  assert.equal(
    deriveChatTitleFromFirstUserMessage('Benzoyl peroxide có phải kháng sinh không?'),
    'Benzoyl peroxide có phải kháng sinh không'
  );
});

test('deriveChatTitleFromMessages uses first user message and ignores assistant content', () => {
  const title = deriveChatTitleFromMessages([
    { role: 'assistant', content: 'Đây là câu trả lời rất dài không được dùng làm tiêu đề.' },
    { role: 'user', content: '2) Sau khi bôi thuốc trị mụn, mắt tôi sưng và tôi bắt đầu khó thở.' },
    { role: 'user', content: 'Câu sau không được đổi tiêu đề.' },
  ]);

  assert.equal(title.startsWith('2)'), false);
  assert.match(title, /^Sau khi bôi thuốc trị mụn/);
  assert.doesNotMatch(title, /câu trả lời/i);
});

test('shouldGenerateSessionTitle only allows empty/default titles before the first user message', () => {
  assert.equal(shouldGenerateSessionTitle('Đoạn chat mới', []), true);
  assert.equal(shouldGenerateSessionTitle('', []), true);
  assert.equal(shouldGenerateSessionTitle('Uống isotretinoin cần theo dõi gì...', []), false);
  assert.equal(
    shouldGenerateSessionTitle('Đoạn chat mới', [{ role: 'user', content: 'Câu hỏi đầu tiên' }]),
    false
  );
});
