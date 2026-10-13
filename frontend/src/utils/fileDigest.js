// Incremental SHA-256 works on private HTTP deployments without WebCrypto.
const primes = [];
for (let value = 2; primes.length < 64; value++) {
  if (!primes.some(prime => prime * prime <= value && value % prime === 0)) primes.push(value);
}
const constants = primes.map(prime => (Math.cbrt(prime) % 1 * 0x100000000) >>> 0);
const initial = primes.slice(0, 8).map(prime => (Math.sqrt(prime) % 1 * 0x100000000) >>> 0);
const rotate = (value, bits) => (value >>> bits) | (value << (32 - bits));
const read = blob => typeof blob.arrayBuffer === 'function' ? blob.arrayBuffer() : new Promise((resolve, reject) => {
  const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('Cannot read source file')); reader.readAsArrayBuffer(blob);
});

export async function fileSha256(file) {
  const hash = [...initial];
  const words = new Uint32Array(64);
  const block = bytes => {
    const view = new DataView(bytes.buffer, bytes.byteOffset, 64);
    for (let i = 0; i < 16; i++) words[i] = view.getUint32(i * 4);
    for (let i = 16; i < 64; i++) {
      const a = words[i - 15], b = words[i - 2];
      words[i] = words[i - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ (a >>> 3)) + words[i - 7] + (rotate(b, 17) ^ rotate(b, 19) ^ (b >>> 10));
    }
    let [a,b,c,d,e,f,g,h] = hash;
    for (let i = 0; i < 64; i++) {
      const first = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + ((e & f) ^ (~e & g)) + constants[i] + words[i]) | 0;
      const second = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h=g; g=f; f=e; e=(d+first)|0; d=c; c=b; b=a; a=(first+second)|0;
    }
    [a,b,c,d,e,f,g,h].forEach((value, index) => { hash[index] = (hash[index] + value) >>> 0; });
  };
  let remainder = new Uint8Array();
  for (let offset = 0; offset < file.size; offset += 1048576) {
    const part = new Uint8Array(await read(file.slice(offset, offset + 1048576)));
    const bytes = new Uint8Array(remainder.length + part.length); bytes.set(remainder); bytes.set(part, remainder.length);
    const end = bytes.length - bytes.length % 64;
    for (let position = 0; position < end; position += 64) block(bytes.subarray(position, position + 64));
    remainder = bytes.slice(end);
  }
  const tail = new Uint8Array(remainder.length < 56 ? 64 : 128);
  tail.set(remainder); tail[remainder.length] = 128;
  const view = new DataView(tail.buffer);
  view.setUint32(tail.length - 8, Math.floor(file.size / 0x20000000));
  view.setUint32(tail.length - 4, (file.size * 8) >>> 0);
  for (let position = 0; position < tail.length; position += 64) block(tail.subarray(position, position + 64));
  return hash.map(value => value.toString(16).padStart(8, '0')).join('');
}
