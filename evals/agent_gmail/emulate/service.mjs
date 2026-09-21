import { readFileSync } from 'node:fs';
import { Server } from 'node:http';
import { createEmulator } from 'emulate';

const seed = JSON.parse(readFileSync(process.argv[2], 'utf8'));
// Emulate 0.11.2 accepts port 0 but its public .url still contains ':0'.
// Observe the owned HTTP listener to report its OS-assigned address. No
// Gmail routing/state is replaced, and the prototype is restored immediately.
const descriptor = Object.getOwnPropertyDescriptor(Server.prototype, 'listen');
const originalListen = Server.prototype.listen;
let listeners = 0;
let resolveAddress;
let rejectAddress;
const addressReady = new Promise((resolve, reject) => {
  resolveAddress = resolve;
  rejectAddress = reject;
});
Server.prototype.listen = function () {
  listeners += 1;
  this.once('listening', () => {
    this.removeListener('error', rejectAddress);
    resolveAddress(this.address());
  });
  this.once('error', rejectAddress);
  return originalListen.call(this, 0, '127.0.0.1');
};
let emulator;
try {
  emulator = await createEmulator({ service: 'google', port: 0, seed });
} finally {
  if (descriptor) Object.defineProperty(Server.prototype, 'listen', descriptor);
  else delete Server.prototype.listen;
}
const address = await addressReady;
if (listeners !== 1 || !address || typeof address === 'string') {
  await emulator.close();
  throw new Error('Expected exactly one owned Emulate HTTP listener');
}
console.log(JSON.stringify({ ready: true, url: `http://127.0.0.1:${address.port}`, version: '0.11.2' }));
let closing = false;
async function close() {
  if (closing) return;
  closing = true;
  await emulator.close();
  process.exit(0);
}
process.on('SIGTERM', close);
process.on('SIGINT', close);
process.stdin.resume();
process.stdin.on('end', close);
