import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readSidebarCollapsed, saveSidebarCollapsed, SIDEBAR_PREFERENCE_KEY,
  readFolderSidebarCollapsed, saveFolderSidebarCollapsed, FOLDER_SIDEBAR_PREFERENCE_KEY } from '../src/sidebarPreferences.ts';

test('sidebar preference defaults to expanded without browser storage', () => {
  assert.equal(readSidebarCollapsed(), false);
  assert.doesNotThrow(() => saveSidebarCollapsed(true));
  assert.equal(readFolderSidebarCollapsed(), false);
  assert.doesNotThrow(() => saveFolderSidebarCollapsed(true));
});

test('sidebar preference persists both collapsed and expanded states using one versioned key', t => {
  const values = new Map();
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) },
  } });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'window', previous); else delete globalThis.window; });
  assert.equal(readSidebarCollapsed(), false);
  saveSidebarCollapsed(true);
  assert.equal(readSidebarCollapsed(), true);
  saveSidebarCollapsed(false);
  assert.equal(readSidebarCollapsed(), false);
  assert.deepEqual([...values], [[SIDEBAR_PREFERENCE_KEY, 'false']]);
  values.set(SIDEBAR_PREFERENCE_KEY, 'unexpected value');
  assert.equal(readSidebarCollapsed(), false);
});

test('blocked localStorage access never prevents menu use', t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    get localStorage() { throw new Error('Storage is blocked'); },
  } });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'window', previous); else delete globalThis.window; });
  assert.equal(readSidebarCollapsed(), false);
  assert.doesNotThrow(() => saveSidebarCollapsed(true));
  assert.equal(readFolderSidebarCollapsed(), false);
  assert.doesNotThrow(() => saveFolderSidebarCollapsed(true));
});

test('storage read and write errors are optional preference failures', t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    localStorage: {
      getItem() { throw new Error('Read denied'); },
      setItem() { throw new Error('Quota exceeded'); },
    },
  } });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'window', previous); else delete globalThis.window; });
  assert.equal(readSidebarCollapsed(), false);
  assert.doesNotThrow(() => saveSidebarCollapsed(false));
  assert.equal(readFolderSidebarCollapsed(), false);
  assert.doesNotThrow(() => saveFolderSidebarCollapsed(false));
});

test('main menu and folder panel preferences are independent in all four combinations', t => {
  const values = new Map();
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) },
  } });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'window', previous); else delete globalThis.window; });
  for (const mainCollapsed of [false, true]) {
    for (const foldersCollapsed of [false, true]) {
      saveSidebarCollapsed(mainCollapsed);
      saveFolderSidebarCollapsed(foldersCollapsed);
      assert.equal(readSidebarCollapsed(), mainCollapsed);
      assert.equal(readFolderSidebarCollapsed(), foldersCollapsed);
    }
  }
  assert.deepEqual([...values.keys()], [SIDEBAR_PREFERENCE_KEY, FOLDER_SIDEBAR_PREFERENCE_KEY]);
  values.set(FOLDER_SIDEBAR_PREFERENCE_KEY, 'invalid');
  assert.equal(readFolderSidebarCollapsed(), false);
  assert.equal(readSidebarCollapsed(), true);
});
