/* Shared session, navigation and demo settings. Never stores credentials in Web Storage. */
(() => {
  'use strict';
  const state = window.TongyuBootstrap || {user: null};
  const nativeFetch = window.fetch.bind(window);
  const routes = {monitor: ['/index.html', '实时监控', '设备状态与传感器数据'], events: ['/events.html', '异常事件', '事件筛选与处置演示'], chat: ['/chat.html', '对话与情绪', '会话回顾与情绪线索'], health: ['/health.html', '学生测温', '名单与测温记录演示'], reports: ['/reports.html', '当日日报', '当日记录汇总演示']};
  let checking = false;
  function exitToLogin() {
    document.body?.replaceChildren();
    location.replace('/login');
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    const method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (url.origin === location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      if (state.csrf) headers.set('X-CSRF-Token', state.csrf);
      options = {...options, headers};
    }
    const response = await nativeFetch(input, options);
    if (url.origin === location.origin && response.status === 401 && state.user && !url.pathname.startsWith('/api/auth/')) exitToLogin();
    return response;
  };
  async function json(url, options = {}) {
    const response = await fetch(url, {cache: 'no-store', ...options});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败，请重试');
    return data;
  }
  function safeNext(user) {
    const next = new URLSearchParams(location.search).get('next');
    const allowed = ['/welcome', '/', '/admin', '/admin.html', '/events', '/chat', ...Object.values(routes).map(r => r[0])];
    const home = user?.role === 'admin' ? '/admin' : '/welcome';
    if (user?.role !== 'admin' && ['/admin', '/admin.html'].includes(next)) return home;
    return allowed.includes(next) ? next : home;
  }
  async function checkSession() {
    if (checking) return;
    checking = true;
    try {
      const latest = await json('/api/auth/session');
      if (!latest.user || latest.user.username !== state.user?.username || latest.user.role !== state.user?.role) return exitToLogin();
      if (JSON.stringify(latest.policy) !== JSON.stringify(state.policy)) return location.reload();
    } catch (_) { /* A temporary network outage does not log the user out. */ }
    finally { checking = false; }
  }
  function accountBar() {
    const bar = document.createElement('div'); bar.className = 'account-bar';
    const who = document.createElement('span'); who.textContent = `${state.user.username} · ${state.user.role === 'admin' ? '管理员' : '演示账号'}`; bar.append(who);
    const home = document.createElement('a'); home.href = '/welcome'; home.textContent = '模块入口'; bar.append(home);
    if (state.user.role === 'admin') { const link = document.createElement('a'); link.href = '/admin'; link.textContent = '展示设置'; bar.append(link); }
    const logout = document.createElement('button'); logout.type = 'button'; logout.textContent = '退出登录';
    logout.addEventListener('click', async () => {
      logout.disabled = true;
      try { await json('/api/auth/logout', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}); exitToLogin(); }
      catch (error) { logout.disabled = false; logout.textContent = '退出失败，点击重试'; }
    }); bar.append(logout);
    (document.querySelector('.main-inner') || document.querySelector('main') || document.body).prepend(bar);
  }
  async function loginPage() {
    let mode = 'login';
    const $ = id => document.getElementById(id);
    function setMode(next) {
      mode = next;
      $('loginTab').setAttribute('aria-selected', String(mode === 'login'));
      $('registerTab').setAttribute('aria-selected', String(mode === 'register'));
      $('confirmField').hidden = mode !== 'register'; $('accountConfirm').required = mode === 'register';
      $('accountPassword').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
      $('accessTitle').textContent = mode === 'register' ? '注册演示账号' : '欢迎登录';
      $('accessSubtitle').textContent = mode === 'register' ? '创建账号后即可登录，查看已开放的内容。' : '首次使用？先注册一个演示账号。';
      $('accountSubmit').textContent = mode === 'register' ? '注册账号' : '登录'; $('accountFeedback').textContent = '';
      $('accountPassword').value = ''; $('accountConfirm').value = '';
    }
    $('loginTab').addEventListener('click', () => setMode('login'));
    $('registerTab').addEventListener('click', () => setMode('register'));
    let initialized = false;
    async function connect() {
      const data = await json('/api/auth/session'); state.csrf = data.csrf; initialized = data.initialized;
      if (data.user) { location.replace(safeNext(data.user)); return; }
      $('accountSubmit').disabled = !initialized; setMode(mode);
      if (!initialized) $('accountFeedback').textContent = '管理员尚未完成初始化，请联系演示人员。';
    }
    $('accountForm').addEventListener('submit', async event => {
      event.preventDefault(); if (!initialized) return;
      const feedback = $('accountFeedback'); feedback.dataset.success = 'false'; feedback.textContent = '';
      if (mode === 'register' && $('accountPassword').value !== $('accountConfirm').value) { feedback.textContent = '两次密码不一致'; return; }
      const submittedMode = mode;
      $('accountSubmit').disabled = true; $('accountSubmit').textContent = '提交中…';
      try {
        const data = await json('/api/auth/' + submittedMode, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: $('accountUsername').value.trim(), password: $('accountPassword').value})});
        if (submittedMode === 'login') { location.replace(safeNext(data.user)); return; }
        setMode('login'); feedback.dataset.success = 'true'; feedback.textContent = '注册成功，请输入密码登录。'; $('accountPassword').focus();
      } catch (error) { feedback.textContent = error.message; }
      finally { $('accountSubmit').disabled = false; $('accountSubmit').textContent = mode === 'register' ? '注册账号' : '登录'; }
    });
    try { await connect(); }
    catch (_) { $('accountFeedback').textContent = '连接失败，请刷新页面重试。'; $('accountSubmit').textContent = '连接失败'; }
  }
  function adminPage() {
    const policy = state.policy;
    for (const key of Object.keys(routes)) document.getElementById('allow-' + key).checked = policy.modules[key];
    for (const key of ['video', 'dialogue_raw']) document.getElementById('allow-' + key).checked = policy[key];
    document.getElementById('policyForm').addEventListener('submit', async event => {
      event.preventDefault(); const button = document.getElementById('policySave'), feedback = document.getElementById('policyFeedback');
      const next = {modules: {}, video: document.getElementById('allow-video').checked, dialogue_raw: document.getElementById('allow-dialogue_raw').checked};
      for (const key of Object.keys(routes)) next.modules[key] = document.getElementById('allow-' + key).checked;
      button.disabled = true; feedback.textContent = '保存中…';
      try { const data = await json('/api/admin/policy', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(next)}); state.policy = data.policy; feedback.dataset.success = 'true'; feedback.textContent = '已保存，演示账号按此设置展示。'; }
      catch (error) { feedback.dataset.success = 'false'; feedback.textContent = error.message; }
      finally { button.disabled = false; }
    });
  }
  document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.accessPage;
    if (page === 'login') { loginPage(); return; }
    if (!state.user) return;
    accountBar();
    for (const [key, [path]] of Object.entries(routes)) {
      for (const link of document.querySelectorAll('nav[aria-label="主导航"] a')) {
        if (new URL(link.href).pathname === path) link.hidden = !state.permissions.modules[key];
      }
    }
    if (state.user.role !== 'admin') for (const id of ['settingsButton', 'analysisButton', 'openImport', 'importNoteDetail', 'resolveBtn', 'falseAlarmBtn', 'reopenBtn', 'saveNoteBtn', 'noteInput']) { const node = document.getElementById(id); if (node) node.hidden = true; }
    if (state.user.role !== 'admin') {
      const entry = document.querySelector('.entry-card');
      if (entry) entry.hidden = true;
    }
    if (!state.permissions.dialogue_raw) {
      const search = document.getElementById('search');
      if (search) { search.disabled = true; search.placeholder = '对话原文未开放'; }
    }
    if (page === 'welcome') {
      let count = 0;
      for (const [key, [path, name, note]] of Object.entries(routes)) if (state.permissions.modules[key]) {
        const card = document.createElement('a'); card.href = path; card.className = 'access-module'; card.textContent = name;
        const small = document.createElement('span'); small.textContent = note; card.append(small); document.getElementById('moduleCards').append(card); count++;
      }
      document.getElementById('noModules').hidden = count > 0;
    }
    if (page === 'admin') adminPage();
    setInterval(checkSession, 5000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) checkSession(); });
    window.addEventListener('pageshow', event => { if (event.persisted) { document.body.style.visibility = 'hidden'; location.reload(); } });
  });
})();
