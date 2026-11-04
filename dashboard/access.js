/* Shared session, navigation and demo settings. Never stores credentials in Web Storage. */
(() => {
  'use strict';
  const state = window.TongyuBootstrap || {user: null};
  const nativeFetch = window.fetch.bind(window);
  const routes = {monitor: ['/index.html', '实时监控', '设备状态与传感器数据'], events: ['/events.html', '异常事件', '事件筛选与处置演示'], chat: ['/chat.html', '对话与情绪', '会话回顾与情绪线索'], health: ['/health.html', '学生测温', '名单与测温记录演示'], reports: ['/reports.html', '当日日报', '当日记录汇总演示']};
  const roleLabels = {admin: '管理员', pending: '待分配', parent: '家长', merchant: '商家', viewer: '演示账号'};
  const roleHomes = {admin: '/admin', pending: '/welcome', parent: '/family-events.html', merchant: '/sensors.html'};
  window.TongyuStudentLabel = student => `${student.nickname || student.name} · ${student.class_name || student.class_id} · ${student.id}`;
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
    const allowed = ['/welcome', '/family-events.html', '/', '/admin', '/admin.html', '/events', '/chat', ...Object.values(routes).map(r => r[0])];
    const home = roleHomes[user?.role] || '/welcome';
    if (['pending', 'parent', 'merchant'].includes(user?.role)) return home;
    if (user?.role !== 'admin' && ['/admin', '/admin.html'].includes(next)) return home;
    return allowed.includes(next) ? next : home;
  }
  async function checkSession() {
    if (checking) return;
    checking = true;
    try {
      const latest = await json('/api/auth/session');
      if (!latest.user || latest.user.username !== state.user?.username) return exitToLogin();
      if (latest.user.role !== state.user.role) {
        document.body.style.visibility = 'hidden';
        return location.replace(roleHomes[latest.user.role] || '/welcome');
      }
      if (JSON.stringify(latest.user) !== JSON.stringify(state.user)) {
        document.body.style.visibility = 'hidden';
        return location.reload();
      }
      if (JSON.stringify(latest.policy) !== JSON.stringify(state.policy)) return location.reload();
    } catch (_) { /* A temporary network outage does not log the user out. */ }
    finally { checking = false; }
  }
  function accountBar() {
    const bar = document.createElement('div'); bar.className = 'account-bar';
    const roleLabel = roleLabels[state.user.role];
    const who = document.createElement('span'); who.textContent = `${state.user.username} · ${roleLabel}`; bar.append(who);
    const home = document.createElement('a'); home.href = '/welcome'; home.textContent = '模块入口'; bar.append(home);
    if (state.user.role === 'admin') { const link = document.createElement('a'); link.href = '/admin'; link.textContent = '账号管理'; bar.append(link); }
    if (state.user.role === 'parent') { const link = document.createElement('a'); link.href = '/family-events.html'; link.textContent = '家长工作台'; bar.append(link); }
    if (state.user.role === 'merchant') { const link = document.createElement('a'); link.href = '/sensors.html'; link.textContent = '环境传感器'; bar.append(link); }
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
      $('accessTitle').textContent = mode === 'register' ? '注册账号' : '欢迎登录';
      $('accessSubtitle').textContent = mode === 'register' ? '注册后可登录，管理员分配角色后即可查看对应内容。' : '首次使用？请先注册账号。';
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
        setMode('login'); feedback.dataset.success = 'true'; feedback.textContent = '注册成功。登录后可查看分配状态。'; $('accountPassword').focus();
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

    const byId = id => document.getElementById(id);
    const rows = byId('accountList');
    const listStatus = byId('accountListStatus');
    const dialog = byId('accountDialog');
    const role = byId('accountRole');
    const fields = byId('roleFields');
    const parentFields = byId('parentFields');
    const parentStudents = byId('parentStudents');
    const editStatus = byId('accountEditStatus');
    const nicknameStudent = byId('nicknameStudent');
    const nicknameInput = byId('studentNickname');
    const nicknameStatus = byId('nicknameStatus');
    const parentDefaults = {events: true, snapshots: false, reports: true, dialogues: false};
    let accounts = [];
    let students = [];
    let editing = null;

    function selectOptions(selected = []) {
      return students.filter(student => student.active !== false).map(student =>
        new Option(window.TongyuStudentLabel(student), student.id, false, selected.includes(student.id)));
    }

    function updateRoleFields() {
      parentFields.hidden = role.value !== 'parent';
      parentStudents.required = role.value === 'parent';
    }

    function editAccount(account) {
      editing = account;
      byId('accountEditTitle').textContent = '管理账号 · ' + account.username;
      role.value = account.role;
      parentStudents.replaceChildren(...selectOptions(account.student_ids || []));
      for (const [key, enabled] of Object.entries(account.access || parentDefaults)) {
        byId('parent-' + key).checked = enabled;
      }
      editStatus.textContent = '';
      updateRoleFields();
      dialog.showModal();
    }

    function renderAccounts() {
      const studentById = new Map(students.map(student => [student.id, student]));
      const ordered = [...accounts].sort((a, b) => Number(b.role === 'pending') - Number(a.role === 'pending'));
      rows.replaceChildren(...ordered.map(account => {
        const row = document.createElement('tr');
        const children = (account.student_ids || []).map(id => {
          const student = studentById.get(id);
          return student ? window.TongyuStudentLabel(student) : id;
        });
        for (const value of [account.username, roleLabels[account.role], children.join('、') || '—']) {
          row.insertCell().textContent = value;
        }
        const actions = row.insertCell();
        if (account.role !== 'admin') {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'access-secondary';
          button.textContent = account.role === 'pending' ? '分配角色' : '修改';
          button.addEventListener('click', () => editAccount(account));
          actions.append(button);
        }
        return row;
      }));
    }

    function fillNicknameEditor() {
      const selection = nicknameStudent.value;
      nicknameStudent.replaceChildren(...selectOptions());
      if (selection) nicknameStudent.value = selection;
      nicknameInput.value = students.find(student => student.id === nicknameStudent.value)?.nickname || '';
      byId('nicknameForm').querySelector('button').disabled = !nicknameStudent.value;
    }

    async function loadAccounts() {
      const refresh = byId('refreshAccounts');
      refresh.disabled = true;
      listStatus.textContent = '正在读取账号…';
      try {
        const [studentData, accountData] = await Promise.all([
          json('/api/health/students'), json('/api/admin/accounts'),
        ]);
        students = studentData.students;
        accounts = accountData.accounts;
        renderAccounts();
        fillNicknameEditor();
        listStatus.textContent = '共 ' + accounts.length + ' 个账号';
      } catch (error) {
        listStatus.textContent = '账号列表加载失败：' + error.message;
      } finally {
        refresh.disabled = false;
      }
    }

    role.addEventListener('change', updateRoleFields);
    byId('accountCancel').addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', event => { if (fields.disabled) event.preventDefault(); });
    byId('roleForm').addEventListener('submit', async event => {
      event.preventDefault();
      const payload = {username: editing.username, role: role.value};
      if (payload.role === 'parent') {
        payload.student_ids = [...parentStudents.selectedOptions].map(option => option.value);
        payload.access = Object.fromEntries(Object.keys(parentDefaults).map(key => [key, byId('parent-' + key).checked]));
      }
      fields.disabled = true;
      editStatus.textContent = '正在保存…';
      try {
        const {account} = await json('/api/admin/accounts', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)});
        accounts = accounts.map(item => item.username === account.username ? account : item);
        dialog.close();
        renderAccounts();
        listStatus.textContent = account.username + ' 已设为' + roleLabels[account.role] + '。';
      } catch (error) {
        editStatus.textContent = error.message;
      } finally {
        fields.disabled = false;
      }
    });

    nicknameStudent.addEventListener('change', () => {
      nicknameInput.value = students.find(student => student.id === nicknameStudent.value)?.nickname || '';
      nicknameStatus.textContent = '';
    });
    byId('nicknameForm').addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.currentTarget.querySelector('button');
      button.disabled = true;
      nicknameStudent.disabled = true;
      nicknameInput.disabled = true;
      nicknameStatus.dataset.success = 'false';
      try {
        const {student} = await json('/api/admin/student-nickname', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({student_id: nicknameStudent.value, nickname: nicknameInput.value})});
        students = students.map(item => item.id === student.id ? student : item);
        fillNicknameEditor();
        renderAccounts();
        nicknameStatus.dataset.success = 'true';
        nicknameStatus.textContent = '昵称已保存。';
      } catch (error) {
        nicknameStatus.textContent = error.message;
      } finally {
        button.disabled = false;
        nicknameStudent.disabled = false;
        nicknameInput.disabled = false;
      }
    });
    byId('refreshAccounts').addEventListener('click', loadAccounts);
    loadAccounts();
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
    if (state.user.role !== 'admin') for (const id of ['settingsButton', 'analysisButton', 'openImport', 'importNoteDetail', 'assignParticipants', 'resolveBtn', 'falseAlarmBtn', 'reopenBtn', 'saveNoteBtn', 'noteInput']) { const node = document.getElementById(id); if (node) node.hidden = true; }
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
      const restricted = {parent: ['/family-events.html', '家长工作台'], merchant: ['/sensors.html', '环境传感器']}[state.user.role];
      if (restricted) {
        const card = document.createElement('a');
        [card.href, card.textContent] = restricted;
        card.className = 'access-module';
        document.getElementById('moduleCards').append(card);
      }
      document.getElementById('noModules').hidden = count > 0 || Boolean(restricted);
      if (state.user.role === 'pending') {
        document.querySelector('h1').textContent = '等待分配角色';
        document.getElementById('welcomeNote').textContent = '账号已注册。管理员分配角色后，此页面会自动更新。';
        document.getElementById('noModules').hidden = true;
      }
    }
    if (page === 'admin') adminPage();
    setInterval(checkSession, 5000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) checkSession(); });
    window.addEventListener('pageshow', event => { if (event.persisted) { document.body.style.visibility = 'hidden'; location.reload(); } });
  });
})();
