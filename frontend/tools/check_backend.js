const http = require('http');
const url = 'http://127.0.0.1:8000/';

http.get(url, (res) => {
  console.log('STATUS', res.statusCode);
  res.setEncoding('utf8');
  let body = '';
  res.on('data', (chunk) => body += chunk);
  res.on('end', () => {
    console.log('BODY', body.substring(0, 500));
  });
}).on('error', (e) => {
  console.error('ERR', e.message);
  process.exit(1);
});
