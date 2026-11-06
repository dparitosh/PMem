import { createHash } from 'node:crypto';
import { fileSha256 } from './fileDigest';

test.each(['', 'abc', 'a'.repeat(55), 'a'.repeat(56), 'a'.repeat(64), 'a'.repeat(1048579)].map(text => [text.length, text]))('file digest agrees with SHA-256 for input length %i', async (_length, text) => {
  expect(await fileSha256(new File([text], 'source'))).toBe(createHash('sha256').update(text).digest('hex'));
});
