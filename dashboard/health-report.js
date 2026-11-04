/* 学生测温页与当日日报页的共用脚本。
 *
 * 数据来源分两种模式：
 *   1. live  —— 名单、测温与日报接口已经实现并通过文档约定；
 *   2. demo  —— 接口返回 404 或页面直接以本地文件打开时，使用明确标注的演示数据。
 * 两种模式共用同一套归一化结构，页面渲染代码不区分数据来源。
 */
(() => {
  "use strict";

  const TZ = "Asia/Shanghai";
  const HIGH_TEMP = 37.3;
  const MIN_TEMP = 35;
  const MAX_TEMP = 42;
  const REFRESH_MS = 30000;
  const REALTIME_MS = 2000;
  const REQUEST_TIMEOUT_MS = 4000;

  const API = {
    students: "/api/health/students",
    records: "/api/health/records",
    realtime: "/api/health/realtime",
    importStudents: "/api/health/import",
    daily: "/api/reports/daily"
  };

  const SOURCES = [
    { value: "forehead", label: "额温枪" },
    { value: "infrared", label: "红外测温" },
    { value: "ear", label: "耳温枪" },
    { value: "axillary", label: "腋下体温计" }
  ];

  const STATUS_LABELS = { measured: "已测", pending: "未测", recheck: "需复测" };
  const STATUS_TONES = { measured: "ok", pending: "warn", recheck: "bad" };
  const ATTENTION_LABELS = { urgent: "紧急关注", watch: "建议留意", none: "普通" };
  const ATTENTION_TONES = { urgent: "bad", watch: "warn", none: "idle" };
  const EVENT_LEVEL_LABELS = { high: "高", medium: "中", low: "低" };
  const EVENT_STATUS_LABELS = { pending: "待处理", handled: "已处置", false_alarm: "误报" };
  const EVENT_STATUS_TONES = { pending: "warn", handled: "ok", false_alarm: "idle" };

  /* ---------- 演示数据 ---------- */

  const DEMO_CLASSES = [
    { id: "C-02", name: "小二班" },
    { id: "C-11", name: "中一班" },
    { id: "C-21", name: "大一班" }
  ];

  const DEMO_STUDENTS = [
    { id: "S-0201", name: "陈小满", class_id: "C-02" },
    { id: "S-0202", name: "李知夏", class_id: "C-02" },
    { id: "S-0203", name: "王乐一", class_id: "C-02" },
    { id: "S-0204", name: "张念安", class_id: "C-02" },
    { id: "S-0205", name: "陈小满", class_id: "C-02" },
    { id: "S-0206", name: "刘星野", class_id: "C-02" },
    { id: "S-0207", name: "周清和", class_id: "C-02" },
    { id: "S-1101", name: "孙可可", class_id: "C-11" },
    { id: "S-1102", name: "赵宁远", class_id: "C-11" },
    { id: "S-1103", name: "吴一诺", class_id: "C-11" },
    { id: "S-1104", name: "郑思齐", class_id: "C-11" },
    { id: "S-2101", name: "冯小树", class_id: "C-21" },
    { id: "S-2102", name: "何予安", class_id: "C-21" },
    { id: "S-2103", name: "许知遥", class_id: "C-21" }
  ];

  /* time 为当天的 HH:MM:SS，加载时拼成带时区的 ISO 8601 字符串。 */
  const DEMO_RECORD_SEED = [
    { id: "R-1001", student_id: "S-0201", time: "08:42:10", temp: 36.6, source: "forehead", note: "" },
    { id: "R-1002", student_id: "S-0202", time: "08:44:35", temp: 36.4, source: "forehead", note: "" },
    { id: "R-1003", student_id: "S-0205", time: "08:47:02", temp: 36.8, source: "forehead", note: "" },
    { id: "R-1004", student_id: "S-0207", time: "08:49:41", temp: 36.5, source: "ear", note: "" },
    { id: "R-1005", student_id: "S-1101", time: "08:52:18", temp: 36.9, source: "forehead", note: "" },
    { id: "R-1006", student_id: "S-1104", time: "08:55:07", temp: 36.3, source: "forehead", note: "" },
    { id: "R-1007", student_id: "S-2101", time: "09:03:26", temp: 36.7, source: "forehead", note: "" },
    { id: "R-1008", student_id: "S-2103", time: "09:06:44", temp: 36.2, source: "ear", note: "" },
    { id: "R-1009", student_id: "S-0204", time: "09:12:31", temp: 37.6, source: "infrared", note: "户外活动后测量" },
    { id: "R-1010", student_id: "S-0204", time: "09:31:09", temp: 36.9, source: "infrared", note: "复测正常", recheck_of: "R-1009" },
    { id: "R-1011", student_id: "S-1102", time: "09:40:55", temp: 37.4, source: "infrared", note: "精神略疲倦" },
    { id: "R-1012", student_id: "S-1102", time: "10:05:23", temp: 37.5, source: "infrared", note: "复测仍偏高，已通知保健老师", recheck_of: "R-1011" }
  ];

  const DEMO_EVENTS = [
    {
      id: "E-2401", type: "fight", title: "户外活动区推搡", level: "high", class_id: "C-11",
      location: "户外活动区", time: "09:15:22", status: "handled", handler: "王老师",
      handled_time: "09:22:40", note: "两名幼儿争抢玩具推搡，已分开并安抚，家长已告知。"
    },
    {
      id: "E-2402", type: "fall", title: "教室奔跑跌倒", level: "medium", class_id: "C-02",
      location: "教室阅读区", time: "10:41:08", status: "pending", handler: "",
      handled_time: "", note: "教师现场查看无外伤，待家长接回时确认。"
    }
  ];

  const DEMO_DIALOGUES = [
    {
      id: "D-2401", class_id: "C-02", student_id: "S-0205", attention: "urgent",
      reason: "连续两次提到不想来幼儿园", excerpt: "我不想上幼儿园，早上肚子疼。", time: "10:12:04"
    },
    {
      id: "D-2402", class_id: "C-02", student_id: "S-0202", attention: "watch",
      reason: "午睡时提到想妈妈", excerpt: "我睡觉的时候想妈妈。", time: "09:48:37"
    }
  ];

  const DEMO_IMPORT = {
    at: "2026-10-20T08:31:00+08:00",
    imported: 13,
    skipped: 1,
    errors: [{ line: 12, reason: "缺少姓名", raw: "S-0208,,小二班" }]
  };

  const SAMPLE_CSV = [
    "学号,姓名,班级",
    "S-0301,顾时安,小二班",
    "S-0302,宋予棠,小二班",
    "S-0201,陈小满,小二班",
    "S-0303,,中一班",
    "S-0304,唐知行,大四班",
    "S-0305,程一诺,中一班"
  ].join("\n");

  /* ---------- 通用工具 ---------- */

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const timeFmt = new Intl.DateTimeFormat("zh-CN", {
    timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
  });
  const shortFmt = new Intl.DateTimeFormat("zh-CN", {
    timeZone: TZ, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  });
  const dateFmt = new Intl.DateTimeFormat("zh-CN", {
    timeZone: TZ, year: "numeric", month: "long", day: "numeric", weekday: "long"
  });

  function setText(node, value) {
    if (!node) return;
    const next = String(value ?? "");
    if (node.textContent !== next) node.textContent = next;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  /* 统计卡片由“数值 + 单位”组成；保留 <small> 单位节点，避免每次刷新重建结构。 */
  function setStatValue(id, value, unit) {
    const node = document.getElementById(id);
    if (!node) return;
    const first = node.childNodes[0];
    if (first && first.nodeType === Node.TEXT_NODE && node.querySelector("small")) {
      first.nodeValue = String(value);
      node.querySelector("small").textContent = unit;
    } else {
      node.textContent = `${value}${unit}`;
    }
  }

  function timeValue(value) {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function todayISO() {
    return dateFmtISO(new Date());
  }

  function dateFmtISO(date) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(date);
    const pick = (type) => parts.find((part) => part.type === type)?.value || "";
    return `${pick("year")}-${pick("month")}-${pick("day")}`;
  }

  function shiftDate(isoDate, days) {
    const [y, m, d] = isoDate.split("-").map(Number);
    const base = Date.UTC(y, m - 1, d) + days * 86400000;
    const next = new Date(base);
    const pad = (value) => String(value).padStart(2, "0");
    return `${next.getUTCFullYear()}-${pad(next.getUTCMonth() + 1)}-${pad(next.getUTCDate())}`;
  }

  function isoAt(date, time) {
    return `${date}T${time}+08:00`;
  }

  function fmtTime(value) {
    if (!value) return "--:--";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "--:--" : timeFmt.format(date);
  }

  function fmtShort(value) {
    if (!value) return "--";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "--" : shortFmt.format(date);
  }

  function fmtDateCN(value) {
    const iso = value || todayISO();
    const [y, m, d] = iso.split("-").map(Number);
    return dateFmt.format(new Date(Date.UTC(y, m - 1, d, 12)));
  }

  function tempText(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(1) : "--";
  }

  function clampPercent(value) {
    if (!Number.isFinite(value)) return 0;
    return Math.max(0, Math.min(100, Math.round(value)));
  }

  function sourceLabel(value) {
    return SOURCES.find((item) => item.value === value)?.label || value || "未记录";
  }

  function statusOf(student, records) {
    const mine = records
      .filter((record) => record.student_id === student.id)
      .sort((a, b) => timeValue(a.measured_at) - timeValue(b.measured_at));
    if (!mine.length) return { key: "pending", latest: null, rechecked: false };
    const latest = mine[mine.length - 1];
    if (Number(latest.temperature_c) >= HIGH_TEMP) return { key: "recheck", latest, rechecked: false };
    const highRecords = mine.filter((record) => Number(record.temperature_c) >= HIGH_TEMP);
    const rechecked = highRecords.some((high) =>
      mine.some((record) => record.recheck_of === high.id && timeValue(record.measured_at) > timeValue(high.measured_at))
    );
    return { key: "measured", latest, rechecked };
  }

  function hasRecheckChild(record, records) {
    return records.some((item) => item.recheck_of === record.id);
  }

  function toneForTemp(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "idle";
    if (number >= HIGH_TEMP) return "bad";
    if (number >= 37) return "warn";
    return "ok";
  }

  /* ---------- 请求与状态 ---------- */

  function failure(kind, status = 0, message = "") {
    const error = new Error(message || kind);
    error.kind = kind;
    error.status = status;
    return error;
  }

  async function requestJSON(url, timeout = REQUEST_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: controller.signal
      });
      const text = await response.text();
      let payload = null;
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (error) {
          if (response.ok) throw failure("parse", response.status);
        }
      }
      if (!response.ok) {
        throw failure("http", response.status, (payload && payload.error) || "");
      }
      return payload;
    } catch (error) {
      if (error && error.kind) throw error;
      if (error && error.name === "AbortError") throw failure("timeout");
      throw failure("network", 0, error && error.message ? error.message : "");
    } finally {
      clearTimeout(timer);
    }
  }

  const app = {
    mode: "loading",
    reason: "",
    date: todayISO(),
    day: todayISO(),
    toastTimer: null,
    clockTimer: null,
    refreshTimer: null,
    realtimeTimer: null
  };

  const demo = {
    date: todayISO(),
    students: [],
    classes: [],
    records: [],
    events: [],
    dialogues: [],
    importSummary: null
  };

  function buildDemo(date) {
    demo.date = date;
    demo.classes = DEMO_CLASSES.map((item) => ({ ...item }));
    demo.students = DEMO_STUDENTS.map((item) => ({ ...item, class_name: className(item.class_id) }));
    demo.records = DEMO_RECORD_SEED.map((item) => ({
      id: item.id,
      student_id: item.student_id,
      measured_at: isoAt(date, item.time),
      temperature_c: item.temp,
      source: item.source,
      note: item.note,
      recheck_of: item.recheck_of || null
    }));
    demo.events = DEMO_EVENTS.map((item) => ({
      ...item,
      occurred_at: isoAt(date, item.time),
      handled_at: item.handled_time ? isoAt(date, item.handled_time) : ""
    }));
    demo.dialogues = DEMO_DIALOGUES.map((item) => ({ ...item, last_at: isoAt(date, item.time) }));
    demo.importSummary = { ...DEMO_IMPORT, errors: DEMO_IMPORT.errors.map((item) => ({ ...item })) };
  }

  function className(classId) {
    return DEMO_CLASSES.find((item) => item.id === classId)?.name || classId || "未分班";
  }

  function setMode(mode, reason = "") {
    app.mode = mode;
    app.reason = reason;
    const banner = $("#demoBanner");
    const tag = $("#demoTag");
    const title = $("#demoTitle");
    const text = $("#demoText");
    const sideDot = $("#sideDot");
    const sideStatus = $("#sideStatus");

    if (banner) {
      banner.hidden = mode === "live";
      banner.dataset.mode = mode;
    }
    if (mode === "demo") {
      setText(tag, "演示数据");
      setText(title, "当前显示演示数据，接口尚未接通");
      setText(text, reason || "名单、测温或日报接口不可用。页面结构与交互可用，数据来自固定样例，不会写入服务器。");
      if (sideDot) sideDot.className = "dot warn";
      setText(sideStatus, "演示数据");
    } else if (mode === "error") {
      setText(tag, "接口异常");
      setText(title, "无法读取数据接口");
      setText(text, reason || "请求失败。页面保留最后一次成功的数据，可点击“重新检测”。");
      if (sideDot) sideDot.className = "dot bad";
      setText(sideStatus, "接口异常");
    } else if (mode === "live") {
      setText(tag, "已接通");
      if (sideDot) sideDot.className = "dot ok";
      setText(sideStatus, "接口已连接");
    }
  }

  async function probeMode() {
    if (location.protocol === "file:") {
      buildDemo(app.date);
      setMode("demo", "页面以本地文件方式打开，没有 Dashboard 服务，因此使用演示数据。请通过 http://127.0.0.1:8088/health.html 访问。");
      return;
    }
    try {
      if (document.body.dataset.page === 'reports') {
        const payload = await requestJSON(`${API.daily}?date=${encodeURIComponent(app.date)}`);
        demo.classes = (payload.report?.health?.classes || []).map(item => ({id: item.id, name: item.name}));
        setMode('live');
        return;
      }
      const payload = await requestJSON(API.students);
      applyStudentsPayload(payload);
      setMode("live");
    } catch (error) {
      if (error.kind === "http" && error.status === 404) {
        buildDemo(app.date);
        setMode("demo", "GET /api/health/students 返回 404：名单接口当前不可用，使用演示数据。字段约定见 docs/HEALTH_REPORT_UI.md。");
      } else {
        buildDemo(app.date);
        setMode("error", describeError(error));
      }
    }
  }

  function describeError(error) {
    if (error.kind === "timeout") return "请求超时：Dashboard 服务没有在 4 秒内响应。";
    if (error.kind === "http") return `接口返回 HTTP ${error.status}${error.message ? "：" + error.message : ""}。`;
    if (error.kind === "parse") return "接口返回的内容不是合法 JSON。";
    return "网络错误：无法连接到 Dashboard 服务。";
  }

  function applyStudentsPayload(payload) {
    const students = Array.isArray(payload?.students) ? payload.students : [];
    const classes = Array.isArray(payload?.classes) ? payload.classes : [];
    const classMap = new Map(classes.map((item) => [item.id, item.name]));
    demo.classes = classes.length ? classes.map((item) => ({ id: item.id, name: item.name })) : DEMO_CLASSES.map((item) => ({ ...item }));
    demo.students = students.map((item) => ({
      id: String(item.id || ""),
      name: String(item.name || "未命名"),
      class_id: String(item.class_id || ""),
      class_name: classMap.get(item.class_id) || className(item.class_id)
    }));
  }

  function demoRecordsFor(date) {
    return date === demo.date ? demo.records.map((item) => ({ ...item })) : [];
  }

  function toast(message, tone = "") {
    const node = $("#toast");
    if (!node) return;
    setText(node, message);
    node.dataset.tone = tone;
    node.dataset.visible = "true";
    clearTimeout(app.toastTimer);
    app.toastTimer = setTimeout(() => {
      node.dataset.visible = "false";
    }, 3600);
  }

  function announce(message) {
    const node = $("#srAnnounce");
    if (node) node.textContent = message;
  }

  function startClock() {
    const clock = $("#liveClock");
    const pageDate = $("#pageDate");
    const notifyDayChange = () => {
      const current = todayISO();
      if (current === app.day) return;
      const previous = app.day;
      app.day = current;
      window.dispatchEvent(new CustomEvent("dashboard-day-change", {
        detail: { previous, today: current }
      }));
    };
    const tick = () => {
      const now = new Date();
      if (clock) setText(clock, timeFmt.format(now));
      if (pageDate) {
        setText(pageDate, `${dateFmt.format(now)} · 数据按 Asia/Shanghai 统计`);
      }
      notifyDayChange();
    };
    tick();
    app.clockTimer = setInterval(tick, 1000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) notifyDayChange();
    });
  }

  function downloadCSV(filename, rows) {
    const content = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob([`\ufeff${content}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = el("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function parseCSV(text) {
    const rows = [];
    let row = [];
    let cell = "";
    let quoted = false;
    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      if (quoted) {
        if (char === '"' && text[index + 1] === '"') {
          cell += '"';
          index += 1;
        } else if (char === '"') {
          quoted = false;
        } else {
          cell += char;
        }
      } else if (char === '"') {
        quoted = true;
      } else if (char === ",") {
        row.push(cell);
        cell = "";
      } else if (char === "\n") {
        row.push(cell);
        rows.push(row);
        row = [];
        cell = "";
      } else if (char !== "\r") {
        cell += char;
      }
    }
    if (cell !== "" || row.length) {
      row.push(cell);
      rows.push(row);
    }
    return rows.filter((item) => item.some((value) => String(value).trim() !== ""));
  }

  /* ---------- 学生测温页 ---------- */

  function initHealthPage() {
    const state = {
      students: [],
      classes: [],
      records: [],
      statusRecords: [],
      query: "",
      classId: "",
      status: "",
      date: todayISO(),
      recordClass: "",
      recordStudent: "",
      importSummary: null,
      importSample: "",
      busy: false,
      realtime: null,
      realtimeBusy: false
    };

    const els = {
      rosterBody: $("#rosterBody"),
      rosterEmpty: $("#rosterEmpty"),
      rosterTableWrap: $("#rosterTableWrap"),
      rosterChip: $("#rosterChip"),
      rosterProgress: $("#rosterProgress"),
      rosterBar: $("#rosterBar"),
      rosterProgressText: $("#rosterProgressText"),
      rosterProgressHint: $("#rosterProgressHint"),
      searchInput: $("#searchInput"),
      classFilter: $("#classFilter"),
      statusSeg: $("#statusSeg"),
      entryForm: $("#entryForm"),
      entryStudent: $("#entryStudent"),
      entryTemp: $("#entryTemp"),
      entrySource: $("#entrySource"),
      entryNote: $("#entryNote"),
      entryRecheckWrap: $("#entryRecheckWrap"),
      entryRecheck: $("#entryRecheck"),
      entryMessage: $("#entryMessage"),
      entrySubmit: $("#entrySubmit"),
      quickTemps: $("#quickTemps"),
      recordBody: $("#recordBody"),
      recordEmpty: $("#recordEmpty"),
      recordTableWrap: $("#recordTableWrap"),
      recordChip: $("#recordChip"),
      recordDate: $("#recordDate"),
      recordClass: $("#recordClass"),
      recordStudent: $("#recordStudent"),
      exportCsv: $("#exportCsv"),
      importNote: $("#importNote"),
      importNoteTitle: $("#importNoteTitle"),
      importNoteText: $("#importNoteText"),
      importNoteDetail: $("#importNoteDetail"),
      openImport: $("#openImport"),
      importDialog: $("#importDialog"),
      importFile: $("#importFile"),
      importRun: $("#importRun"),
      importSample: $("#importSample"),
      importSummary: $("#importSummary"),
      importErrors: $("#importErrors"),
      importErrorBody: $("#importErrorBody"),
      importClose: $("#importClose"),
      importCancel: $("#importCancel"),
      importDone: $("#importDone"),
      infraredRealtime: $("#infraredRealtime"),
      irChip: $("#irChip"),
      irTemperature: $("#irTemperature"),
      irAge: $("#irAge"),
      irStudent: $("#irStudent"),
      irAmbient: $("#irAmbient"),
      irMeasuredAt: $("#irMeasuredAt"),
      irDevice: $("#irDevice"),
      irUseReading: $("#irUseReading"),
      irMessage: $("#irMessage"),
      refreshBtn: $("#refreshBtn"),
      demoRetry: $("#demoRetry")
    };

    function fillClassFilter(select, value, placeholder = "全部班级") {
      if (!select) return;
      select.replaceChildren(new Option(placeholder, ""));
      state.classes.forEach((item) => {
        select.append(new Option(item.name, item.id));
      });
      select.value = value;
    }

    function fillStudentFilter(select, classId, value) {
      if (!select) return;
      select.replaceChildren(new Option("全部学生", ""));
      state.students
        .filter((student) => !classId || student.class_id === classId)
        .forEach((student) => {
          select.append(new Option(`${student.name}（${student.id}）`, student.id));
        });
      select.value = value;
    }

    function fillEntryStudents() {
      if (!els.entryStudent) return;
      const previous = els.entryStudent.value;
      els.entryStudent.replaceChildren(new Option("请选择学生", ""));
      state.classes.forEach((klass) => {
        const group = document.createElement("optgroup");
        group.label = klass.name;
        state.students
          .filter((student) => student.class_id === klass.id)
          .forEach((student) => {
            group.append(new Option(`${student.name} · ${student.id}`, student.id));
          });
        if (group.children.length) els.entryStudent.append(group);
      });
      if (previous) els.entryStudent.value = previous;
    }

    function fillSources() {
      if (!els.entrySource) return;
      els.entrySource.replaceChildren();
      SOURCES.forEach((item) => els.entrySource.append(new Option(item.label, item.value)));
      els.entrySource.value = "forehead";
    }

    function filteredStudents() {
      const query = state.query.trim().toLowerCase();
      return state.students.filter((student) => {
        if (state.classId && student.class_id !== state.classId) return false;
        if (query && !`${student.name} ${student.id}`.toLowerCase().includes(query)) return false;
        if (state.status && statusOf(student, state.statusRecords).key !== state.status) return false;
        return true;
      });
    }

    function duplicateNames() {
      const counts = new Map();
      state.students.forEach((student) => counts.set(student.name, (counts.get(student.name) || 0) + 1));
      return new Set(Array.from(counts.entries()).filter(([, count]) => count > 1).map(([name]) => name));
    }

    function renderStats() {
      const total = state.students.length;
      let measured = 0;
      let pending = 0;
      let recheck = 0;
      state.students.forEach((student) => {
        const status = statusOf(student, state.statusRecords).key;
        if (status === "measured") measured += 1;
        else if (status === "pending") pending += 1;
        else recheck += 1;
      });
      const rate = total ? (measured / total) * 100 : 0;

      setStatValue("statTotal", total, "人");
      setText($("#statTotalNote"), state.classes.length ? `${state.classes.length} 个班级在册` : "等待名单数据");
      setStatValue("statMeasured", measured, "人");
      setText($("#statMeasuredNote"), `完成率 ${clampPercent(rate)}%`);
      setStatValue("statPending", pending, "人");
      setText($("#statPendingNote"), pending ? "名单中尚未登记体温" : "名单内均已登记");
      setStatValue("statRecheck", recheck, "人");
      setText($("#statRecheckNote"), "体温 ≥ 37.3 ℃ 或复测仍偏高");

      if (els.rosterBar) els.rosterBar.style.width = `${clampPercent(rate)}%`;
      if (els.rosterProgress) {
        els.rosterProgress.dataset.tone = pending > 0 ? "warn" : "ok";
      }
      setText(els.rosterProgressText, `今日完成 ${measured} / ${total}`);
      setText(els.rosterProgressHint, `完成率 ${clampPercent(rate)}% · 未测 ${pending} · 需复测 ${recheck}`);
      if (els.rosterChip) {
        els.rosterChip.dataset.tone = total ? "ok" : "idle";
        setText(els.rosterChip, total ? `${total} 名在册` : "名单为空");
      }
    }

    function renderRoster() {
      if (!els.rosterBody) return;
      const students = filteredStudents();
      const duplicates = duplicateNames();
      els.rosterBody.replaceChildren();

      students.forEach((student) => {
        const status = statusOf(student, state.statusRecords);
        const row = document.createElement("tr");
        row.dataset.studentId = student.id;

        row.append(el("td", "cell-mono", student.id));
        const nameCell = el("td", "cell-name");
        nameCell.append(document.createTextNode(student.name));
        if (duplicates.has(student.name)) {
          const badge = el("span", "badge", "同名");
          badge.dataset.tone = "warn";
          badge.title = "名单中有重名学生，请用学号区分";
          badge.style.marginLeft = "6px";
          nameCell.append(badge);
        }
        row.append(nameCell);
        row.append(el("td", "", student.class_name || className(student.class_id)));

        const statusCell = el("td");
        const badge = el("span", "badge", STATUS_LABELS[status.key]);
        badge.dataset.tone = STATUS_TONES[status.key];
        statusCell.append(badge);
        if (status.rechecked) {
          const recheckBadge = el("span", "badge", "复测完成");
          recheckBadge.dataset.tone = "ok";
          recheckBadge.style.marginLeft = "5px";
          statusCell.append(recheckBadge);
        }
        row.append(statusCell);

        const tempCell = el("td");
        if (status.latest) {
          const temp = el("span", "temp", `${tempText(status.latest.temperature_c)} ℃`);
          temp.dataset.tone = toneForTemp(status.latest.temperature_c);
          tempCell.append(temp);
        } else {
          tempCell.append(el("span", "cell-mono", "—"));
        }
        row.append(tempCell);

        row.append(el("td", "col-secondary cell-mono", status.latest ? fmtShort(status.latest.measured_at) : "—"));

        const actionCell = el("td");
        const actions = el("div", "row-actions");
        const action = el("button", "btn btn-sm", status.key === "recheck" ? "复测" : "登记");
        action.type = "button";
        action.addEventListener("click", () => prefillEntry(student, status));
        actions.append(action);
        actionCell.append(actions);
        row.append(actionCell);

        els.rosterBody.append(row);
      });

      const hasRows = students.length > 0;
      if (els.rosterEmpty) els.rosterEmpty.hidden = hasRows;
      if (els.rosterTableWrap) els.rosterTableWrap.hidden = !hasRows;
      if (!hasRows) {
        const emptyTitle = $("#rosterEmptyTitle");
        const emptyText = $("#rosterEmptyText");
        if (app.mode === "error") {
          setText(emptyTitle, "接口异常，名单无法读取");
          setText(emptyText, `${app.reason || "请求失败。"} 页面保留筛选条件，恢复服务后点击“重新检测”。`);
        } else if (state.students.length === 0) {
          setText(emptyTitle, "名单还是空的");
          setText(emptyText, "先通过“导入名单”添加学生，或等待名单接口返回数据。");
        } else {
          setText(emptyTitle, "没有符合条件的学生");
          setText(emptyText, "请调整搜索关键字或筛选条件。");
        }
        announce("名单筛选结果为空");
      } else {
        announce(`名单已更新，共 ${students.length} 名学生`);
      }
    }

    function renderRecords() {
      if (!els.recordBody) return;
      const rows = state.records
        .filter((record) => !state.recordClass || studentById(record.student_id)?.class_id === state.recordClass)
        .filter((record) => !state.recordStudent || record.student_id === state.recordStudent)
        .sort((a, b) => timeValue(b.measured_at) - timeValue(a.measured_at));

      els.recordBody.replaceChildren();
      rows.forEach((record) => {
        const student = studentById(record.student_id);
        const row = document.createElement("tr");

        row.append(el("td", "cell-mono", fmtShort(record.measured_at)));
        row.append(el("td", "cell-mono", record.student_id));
        row.append(el("td", "cell-name", student ? student.name : "已移出名单"));
        row.append(el("td", "col-secondary", student ? student.class_name || className(student.class_id) : "—"));

        const tempCell = el("td");
        const temp = el("span", "temp", `${tempText(record.temperature_c)} ℃`);
        temp.dataset.tone = toneForTemp(record.temperature_c);
        tempCell.append(temp);
        row.append(tempCell);

        row.append(el("td", "col-secondary", sourceLabel(record.source)));
        row.append(el("td", "col-secondary cell-note", record.note || "—"));

        const relation = el("td");
        if (record.recheck_of) {
          const parent =
            state.records.find((item) => item.id === record.recheck_of) ||
            state.statusRecords.find((item) => item.id === record.recheck_of);
          const badge = el("span", "badge", parent ? `复测自 ${fmtShort(parent.measured_at)}` : "复测记录");
          badge.dataset.tone = "brand";
          relation.append(badge);
        } else if (hasRecheckChild(record, state.records)) {
          const child = state.records
            .filter((item) => item.recheck_of === record.id)
            .sort((a, b) => timeValue(a.measured_at) - timeValue(b.measured_at))[0];
          const badge = el("span", "badge", child ? `已复测 ${fmtShort(child.measured_at)}` : "已复测");
          badge.dataset.tone = "ok";
          relation.append(badge);
        } else {
          relation.append(el("span", "cell-mono", "—"));
        }
        row.append(relation);

        els.recordBody.append(row);
      });

      const hasRows = rows.length > 0;
      if (els.recordEmpty) els.recordEmpty.hidden = hasRows;
      if (els.recordTableWrap) els.recordTableWrap.hidden = !hasRows;
      if (els.recordChip) {
        els.recordChip.dataset.tone = hasRows ? "ok" : "idle";
        setText(els.recordChip, `${rows.length} 条`);
      }
      if (!hasRows) {
        setText($("#recordEmptyTitle"), `${state.date} 没有测温记录`);
        setText($("#recordEmptyText"), "换一个日期，或在右侧登记一条新的测温记录。");
      }
    }

    function studentById(id) {
      return state.students.find((student) => student.id === id);
    }

    function prefillEntry(student, status) {
      if (!els.entryStudent) return;
      els.entryStudent.value = student.id;
      els.entryTemp.value = "";
      els.entryTemp.focus();
      renderRecheckOptions();
      if (status && status.key === "recheck") {
        const options = Array.from(els.entryRecheck?.options || []);
        if (options.length > 1) {
          els.entryRecheck.selectedIndex = 1;
        }
      }
      els.entryStudent.scrollIntoView({ block: "center", behavior: "smooth" });
      toast(`已选择 ${student.name}（${student.id}），请输入体温`);
    }

    function renderRecheckOptions() {
      if (!els.entryRecheckWrap || !els.entryRecheck) return;
      const studentId = els.entryStudent.value;
      const candidates = state.statusRecords
        .filter((record) => record.student_id === studentId && Number(record.temperature_c) >= HIGH_TEMP)
        .filter((record) => !hasRecheckChild(record, state.statusRecords))
        .sort((a, b) => timeValue(b.measured_at) - timeValue(a.measured_at));

      els.entryRecheck.replaceChildren(new Option("本次为独立测量", ""));
      candidates.forEach((record) => {
        els.entryRecheck.append(
          new Option(`${fmtShort(record.measured_at)} · ${tempText(record.temperature_c)} ℃ · ${sourceLabel(record.source)}`, record.id)
        );
      });
      els.entryRecheckWrap.hidden = candidates.length === 0;
      if (candidates.length === 0) els.entryRecheck.value = "";
    }

    function showEntryMessage(text, tone = "bad") {
      if (!els.entryMessage) return;
      els.entryMessage.hidden = !text;
      els.entryMessage.dataset.tone = tone;
      setText(els.entryMessage, text);
    }

    function validateEntry() {
      const studentId = els.entryStudent.value;
      const raw = els.entryTemp.value.trim();
      const number = Number(raw);

      els.entryStudent.removeAttribute("aria-invalid");
      els.entryTemp.removeAttribute("aria-invalid");

      if (!studentId) {
        els.entryStudent.setAttribute("aria-invalid", "true");
        els.entryStudent.focus();
        return { error: "请先选择学生。" };
      }
      if (raw === "" || Number.isNaN(number)) {
        els.entryTemp.setAttribute("aria-invalid", "true");
        els.entryTemp.focus();
        return { error: "请输入体温数值，例如 36.5。" };
      }
      if (number < MIN_TEMP || number > MAX_TEMP) {
        els.entryTemp.setAttribute("aria-invalid", "true");
        els.entryTemp.focus();
        return { error: `体温需要在 ${MIN_TEMP}–${MAX_TEMP} ℃ 之间；超范围数值不会被保存。` };
      }
      const note = els.entryNote.value.trim();
      if (note.length > 50) {
        els.entryNote.setAttribute("aria-invalid", "true");
        return { error: "备注最多 50 个字。" };
      }
      return {
        payload: {
          student_id: studentId,
          temperature_c: Number(number.toFixed(1)),
          source: els.entrySource.value,
          note,
          recheck_of: els.entryRecheckWrap.hidden ? "" : els.entryRecheck.value
        }
      };
    }

    async function submitEntry(event) {
      event.preventDefault();
      if (state.busy) return;
      const result = validateEntry();
      if (result.error) {
        showEntryMessage(result.error, "bad");
        return;
      }
      state.busy = true;
      if (els.entrySubmit) els.entrySubmit.disabled = true;
      showEntryMessage("正在保存…", "warn");

      try {
        const record = await saveRecord(result.payload);
        /* 新记录属于“现在”，如果正在查看历史日期，保存后切回今天再刷新。 */
        const today = todayISO();
        if (state.date !== today) {
          state.date = today;
          if (els.recordDate) els.recordDate.value = today;
        }
        await reload();
        els.entryForm.reset();
        fillSources();
        renderRecheckOptions();
        toast("测温记录已保存", "ok");
        showEntryMessage(
          `已保存：${studentById(record.student_id)?.name || record.student_id} ${tempText(record.temperature_c)} ℃`,
          "ok"
        );
        if (record.temperature_c >= HIGH_TEMP) {
          toast("体温达到 37.3 ℃，已标记为需复测", "bad");
        }
      } catch (error) {
        showEntryMessage(`保存失败：${describeError(error)}`, "bad");
      } finally {
        state.busy = false;
        if (els.entrySubmit) els.entrySubmit.disabled = false;
      }
    }

    async function saveRecord(payload) {
      if (app.mode === "demo") {
        const record = {
          id: `R-${Date.now()}`,
          student_id: payload.student_id,
          measured_at: new Date().toISOString(),
          temperature_c: payload.temperature_c,
          source: payload.source,
          note: payload.note,
          recheck_of: payload.recheck_of || null
        };
        demo.records.push(record);
        return record;
      }
      const response = await fetch(API.records, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload)
      });
      const text = await response.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (error) {
        data = null;
      }
      if (!response.ok) throw failure("http", response.status, (data && data.error) || "");
      const saved = data?.record || data || {};
      return {
        id: saved.id || `R-${Date.now()}`,
        student_id: saved.student_id || payload.student_id,
        measured_at: saved.measured_at || new Date().toISOString(),
        temperature_c: Number(saved.temperature_c ?? payload.temperature_c),
        source: saved.source || payload.source,
        note: saved.note ?? payload.note,
        recheck_of: saved.recheck_of || null
      };
    }

    function renderImportSummary(summary) {
      if (!summary) {
        if (els.importNote) els.importNote.hidden = true;
        return;
      }
      if (els.importNote) els.importNote.hidden = false;
      setText(els.importNoteTitle, `${fmtShort(summary.at)} 导入结果`);
      setText(
        els.importNoteText,
        `成功 ${summary.imported} 行 · 跳过 ${summary.skipped} 行 · 错误 ${summary.errors.length} 行`
      );
    }

    function renderImportResult(summary) {
      if (!els.importSummary) return;
      els.importSummary.hidden = false;
      els.importSummary.replaceChildren();
      const chips = [
        ["成功", summary.imported, "ok"],
        ["跳过", summary.skipped, "warn"],
        ["错误", summary.errors.length, "bad"]
      ];
      chips.forEach(([label, value, tone]) => {
        const chip = el("span", "chip", `${label} ${value} 行`);
        chip.dataset.tone = tone;
        els.importSummary.append(chip);
      });
      if (summary.note) {
        const note = el("span", "chip", summary.note);
        note.dataset.tone = "idle";
        els.importSummary.append(note);
      }

      const hasErrors = summary.errors.length > 0;
      if (els.importErrors) els.importErrors.hidden = !hasErrors;
      if (els.importErrorBody) {
        els.importErrorBody.replaceChildren();
        summary.errors.forEach((item) => {
          const row = document.createElement("tr");
          row.append(el("td", "cell-mono", `第 ${item.line} 行`));
          row.append(el("td", "", item.reason));
          row.append(el("td", "cell-mono", item.raw));
          els.importErrorBody.append(row);
        });
      }
    }

    function validateImportRows(rows) {
      const header = rows[0] || [];
      const indexOf = (name) => header.findIndex((cell) => String(cell).trim() === name);
      const idIndex = indexOf("学号");
      const nameIndex = indexOf("姓名");
      const classIndex = indexOf("班级");
      if (idIndex < 0 || nameIndex < 0 || classIndex < 0) {
        return { fatal: "CSV 表头需要包含“学号, 姓名, 班级”三列。" };
      }

      const classByName = new Map(state.classes.map((item) => [item.name.trim(), item]));
      const seen = new Set();
      const known = new Set(state.students.map((student) => student.id));
      const valid = [];
      const errors = [];
      let skipped = 0;

      rows.slice(1).forEach((cells, offset) => {
        const line = offset + 2;
        const raw = cells.join(",");
        const id = String(cells[idIndex] ?? "").trim();
        const name = String(cells[nameIndex] ?? "").trim();
        const classNameValue = String(cells[classIndex] ?? "").trim();

        if (!id) {
          errors.push({ line, reason: "缺少学号", raw });
          return;
        }
        if (!/^[A-Za-z0-9-]{3,20}$/.test(id)) {
          errors.push({ line, reason: "学号格式不正确", raw });
          return;
        }
        if (!name) {
          errors.push({ line, reason: "缺少姓名", raw });
          return;
        }
        if (name.length > 20) {
          errors.push({ line, reason: "姓名超过 20 个字符", raw });
          return;
        }
        const klass = classByName.get(classNameValue);
        if (!klass) {
          errors.push({ line, reason: `班级“${classNameValue}”不在现有名单中`, raw });
          return;
        }
        if (seen.has(id)) {
          errors.push({ line, reason: "同一文件内学号重复", raw });
          return;
        }
        seen.add(id);
        if (known.has(id)) {
          skipped += 1;
          return;
        }
        valid.push({ id, name, class_id: klass.id });
      });

      return { valid, errors, skipped };
    }

    async function runImport(rows) {
      const checked = validateImportRows(rows);
      if (checked.fatal) {
        toast(checked.fatal, "bad");
        return;
      }
      const summary = {
        at: new Date().toISOString(),
        imported: checked.valid.length,
        skipped: checked.skipped,
        errors: checked.errors
      };

      if (app.mode === "demo") {
        summary.note = "演示模式：未写入后端";
        renderImportResult(summary);
        state.importSummary = summary;
        demo.importSummary = { ...summary, errors: summary.errors.map((item) => ({ ...item })) };
        renderImportSummary(summary);
        toast(`演示模式：校验通过 ${summary.imported} 行，未写入后端`, "warn");
        return;
      }

      try {
        const response = await fetch(API.importStudents, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ students: checked.valid })
        });
        const text = await response.text();
        const data = text ? JSON.parse(text) : null;
        if (!response.ok) throw failure("http", response.status, (data && data.error) || "");
        summary.imported = Number(data?.imported ?? checked.valid.length);
        summary.skipped = Number(data?.skipped ?? checked.skipped);
        summary.errors = Array.isArray(data?.errors) ? data.errors : checked.errors;
        renderImportResult(summary);
        state.importSummary = summary;
        renderImportSummary(summary);
        toast(`导入完成：成功 ${summary.imported} 行`, "ok");
        await reload();
      } catch (error) {
        renderImportResult(summary);
        toast(`导入失败：${describeError(error)}`, "bad");
      }
    }

    function openImportDialog() {
      if (!els.importDialog) return;
      els.importSummary.hidden = true;
      els.importErrors.hidden = true;
      if (els.importFile) els.importFile.value = "";
      if (state.importSummary) renderImportResult(state.importSummary);
      if (typeof els.importDialog.showModal === "function") {
        els.importDialog.showModal();
      } else {
        els.importDialog.setAttribute("open", "open");
      }
    }

    async function readFile(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("无法读取文件"));
        reader.readAsText(file, "utf-8");
      });
    }

    async function handleImportFile() {
      const file = els.importFile.files && els.importFile.files[0];
      if (!file) {
        toast("请先选择一个 CSV 文件", "warn");
        return;
      }
      try {
        const text = await readFile(file);
        await runImport(parseCSV(text));
      } catch (error) {
        toast(`读取文件失败：${error.message}`, "bad");
      }
    }

    function persistFilters() {
      if (els.recordDate) state.date = els.recordDate.value || todayISO();
      if (els.recordClass) state.recordClass = els.recordClass.value;
      if (els.recordStudent) state.recordStudent = els.recordStudent.value;
    }

    const canRecord = window.TongyuBootstrap?.user?.role === "admin";

    function realtimePresentation(payload) {
      const reading = payload?.reading;
      const reason = payload?.ingest?.reason || "";
      if (!reading) {
        return {
          tone: "bad",
          chip: payload && payload.source_available === false ? "连接中断" : "等待数据",
          age: payload?.source_available === false ? "无法读取 RDK 红外接口" : "等待第一帧红外数据",
          message: payload?.sensor_error
            ? `实时红外接口不可用：${String(payload.sensor_error).slice(0, 120)}`
            : "正在连接实时红外接口。",
        };
      }
      const stateMeta = {
        ready: { tone: "ok", chip: reason === "stored" ? "已自动入库" : "实时正常" },
        unassigned: { tone: "warn", chip: "待关联学生" },
        unknown_student: { tone: "warn", chip: "学生未匹配" },
        stale: { tone: "bad", chip: "数据已过期" },
        timestamp_unknown: { tone: "warn", chip: "缺少采集时间" },
        offline: { tone: "bad", chip: "设备离线" },
        invalid_temperature: { tone: "warn", chip: "温度不可用" },
        unavailable: { tone: "idle", chip: "无测温值" },
        unstable: { tone: "warn", chip: "读数波动" }
      };
      let meta = stateMeta[reading.status] || { tone: "warn", chip: "状态未知" };
      if (reason === "unknown_student") meta = stateMeta.unknown_student;
      const age = Number.isFinite(reading.age_seconds)
        ? `${reading.age_seconds} 秒前采集`
        : "采集时间未知";
      const messages = {
        stored: "新红外读数已自动写入该学生的今日测温记录。",
        duplicate: "该帧已经写入，重复上报不会产生重复记录。",
        unassigned: "实时读数已到达，但设备未携带 student_id；请选择学生后采用当前读数。",
        unknown_student: `学生 ${reading.student_id || "--"} 不在当前名单中，请检查设备映射。`,
        stale: `读数超过 ${reading.stale_after_seconds || 10} 秒未更新，不会自动入库。`,
        timestamp_unknown: "设备未提供采集时间，读数仅供查看，不能自动入库。",
        offline: "红外设备报告未连接。",
        invalid_temperature: "mlx_obj 不在 35.0–42.0 ℃ 范围内，不能作为人体测温记录。",
        unavailable: "接口暂时没有提供 mlx_obj 目标温度。",
        unstable: "设备报告读数仍在波动，等待稳定后再自动记录。"
      };
      let message = messages[reason] || messages[reading.status] || "等待下一次红外采样。";
      if (payload?.source_available === false) {
        message += " RDK 拉取暂时失败，当前显示最近一次设备推送。";
        if (reading.status !== "ready") meta = { tone: "bad", chip: "连接中断" };
      }
      return { tone: meta.tone, chip: meta.chip, age, message };
    }

    function renderInfraredRealtime(payload = state.realtime) {
      if (!els.infraredRealtime) return;
      const reading = payload?.reading || null;
      const view = realtimePresentation(payload);
      els.infraredRealtime.dataset.tone = view.tone;
      els.irChip.dataset.tone = view.tone;
      setText(els.irChip, view.chip);
      setText(els.irTemperature, reading && Number.isFinite(Number(reading.temperature_c))
        ? tempText(reading.temperature_c)
        : "--");
      setText(els.irAge, view.age);
      setText(els.irAmbient, reading && Number.isFinite(Number(reading.ambient_c))
        ? `${tempText(reading.ambient_c)} ℃`
        : "--");
      setText(els.irMeasuredAt, reading?.measured_at ? fmtShort(reading.measured_at) : "--");
      setText(els.irDevice, reading?.device_id || "--");
      let studentText = "未关联";
      if (reading?.student_id) {
        const student = studentById(reading.student_id);
        studentText = student
          ? `${student.name} · ${student.id}`
          : `未知学生 · ${reading.student_id}`;
      }
      setText(els.irStudent, studentText);
      setText(els.irMessage, view.message);
      els.irUseReading.hidden = !canRecord;
      const knownStudent = !reading?.student_id || Boolean(studentById(reading.student_id));
      els.irUseReading.disabled = !canRecord
        || app.mode !== "live"
        || !reading?.valid_temperature
        || reading?.status === "stale"
        || reading?.status === "timestamp_unknown"
        || !knownStudent;
    }

    function mergeRealtimeRecord(record) {
      if (!record || record.origin !== "device" || !record.measured_at) return;
      const measuredDate = dateFmtISO(new Date(record.measured_at));
      if (measuredDate !== todayISO()) return;
      const normalized = normalizeRecords({ records: [record] }, measuredDate)[0];
      if (!normalized) return;
      let changed = false;
      if (!state.statusRecords.some((item) => item.id === normalized.id)) {
        state.statusRecords.push(normalized);
        changed = true;
      }
      if (state.date === measuredDate && !state.records.some((item) => item.id === normalized.id)) {
        state.records.push(normalized);
        changed = true;
      }
      if (changed) renderAll();
    }

    async function pollInfraredRealtime() {
      if (state.realtimeBusy || app.mode !== "live" || document.hidden) {
        renderInfraredRealtime();
        return;
      }
      state.realtimeBusy = true;
      try {
        const payload = await requestJSON(API.realtime, REQUEST_TIMEOUT_MS);
        state.realtime = payload;
        if (payload?.ingest?.record) mergeRealtimeRecord(payload.ingest.record);
      } catch (error) {
        state.realtime = {
          source_available: false,
          sensor_error: describeError(error),
          reading: state.realtime?.reading || null,
          ingest: state.realtime?.ingest || null,
        };
      } finally {
        state.realtimeBusy = false;
        renderInfraredRealtime();
      }
    }

    function useInfraredReading() {
      const reading = state.realtime?.reading;
      if (!reading || !reading.valid_temperature) return;
      els.entryTemp.value = tempText(reading.temperature_c);
      els.entrySource.value = "infrared";
      if (reading.student_id && studentById(reading.student_id)) {
        els.entryStudent.value = reading.student_id;
        renderRecheckOptions();
      }
      if (!reading.student_id) els.entryStudent.focus();
      else els.entryTemp.focus();
      showEntryMessage(
        reading.student_id
          ? `已采用 ${fmtShort(reading.measured_at)} 的红外读数，请核对后保存。`
          : "已填入红外温度，请选择对应学生后保存。",
        "warn"
      );
    }

    function renderAll() {
      renderStats();
      renderRoster();
      renderRecords();
      renderImportSummary(state.importSummary);
    }

    async function reload() {
      const today = todayISO();
      const date = state.date || today;
      try {
        if (app.mode === "live") {
          const [studentsPayload, todayPayload, selectedPayload] = await Promise.all([
            requestJSON(API.students),
            requestJSON(`${API.records}?date=${encodeURIComponent(today)}`),
            date === today ? null : requestJSON(`${API.records}?date=${encodeURIComponent(date)}`)
          ]);
          applyStudentsPayload(studentsPayload);
          state.students = demo.students;
          state.classes = demo.classes;
          state.statusRecords = normalizeRecords(todayPayload, today);
          state.records = date === today ? state.statusRecords : normalizeRecords(selectedPayload, date);
        } else if (app.mode === "demo") {
          state.students = demo.students;
          state.classes = demo.classes;
          state.statusRecords = demoRecordsFor(today);
          state.records = demoRecordsFor(date);
          state.importSummary = demo.importSummary;
        } else {
          state.students = [];
          state.classes = [];
          state.statusRecords = [];
          state.records = [];
        }
      } catch (error) {
        setMode("error", describeError(error));
        state.students = [];
        state.classes = [];
        state.statusRecords = [];
        state.records = [];
      }
      fillClassFilter(els.classFilter, state.classId);
      fillClassFilter(els.recordClass, state.recordClass);
      fillStudentFilter(els.recordStudent, state.recordClass, state.recordStudent);
      fillEntryStudents();
      if (els.entrySubmit) els.entrySubmit.disabled = app.mode !== "live" && app.mode !== "demo";
      renderAll();
    }

    function normalizeRecords(payload, date) {
      const list = Array.isArray(payload?.records) ? payload.records : [];
      return list
        .map((item) => ({
          id: String(item.id || `R-${Math.random().toString(36).slice(2, 9)}`),
          student_id: String(item.student_id || ""),
          measured_at: String(item.measured_at || isoAt(date, "00:00:00")),
          temperature_c: Number(item.temperature_c),
          source: String(item.source || ""),
          note: String(item.note || ""),
          recheck_of: item.recheck_of ? String(item.recheck_of) : null
        }))
        .filter((item) => Number.isFinite(item.temperature_c));
    }

    function bindEvents() {
      if (els.searchInput) {
        let timer = null;
        els.searchInput.addEventListener("input", () => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            state.query = els.searchInput.value;
            renderRoster();
          }, 120);
        });
      }
      if (els.classFilter) {
        els.classFilter.addEventListener("change", () => {
          state.classId = els.classFilter.value;
          renderRoster();
        });
      }
      if (els.statusSeg) {
        els.statusSeg.addEventListener("click", (event) => {
          const button = event.target.closest("button[data-status]");
          if (!button) return;
          state.status = button.dataset.status;
          $$("button[data-status]", els.statusSeg).forEach((item) => {
            item.setAttribute("aria-pressed", String(item === button));
          });
          renderRoster();
        });
      }
      if (els.entryStudent) {
        els.entryStudent.addEventListener("change", renderRecheckOptions);
      }
      if (els.entryForm) els.entryForm.addEventListener("submit", submitEntry);
      if (els.entryForm) {
        els.entryForm.addEventListener("reset", () => {
          setTimeout(() => {
            fillSources();
            renderRecheckOptions();
          }, 0);
        });
      }
      if (els.quickTemps) {
        [36.3, 36.5, 36.8, 37.2, 37.6].forEach((value) => {
          const button = el("button", "", `${value} ℃`);
          button.type = "button";
          button.addEventListener("click", () => {
            els.entryTemp.value = value.toFixed(1);
            els.entryTemp.focus();
          });
          els.quickTemps.append(button);
        });
      }
      if (els.recordDate) {
        els.recordDate.addEventListener("change", async () => {
          persistFilters();
          await reload();
        });
      }
      if (els.recordClass) {
        els.recordClass.addEventListener("change", () => {
          persistFilters();
          fillStudentFilter(els.recordStudent, state.recordClass, "");
          state.recordStudent = "";
          renderRecords();
        });
      }
      if (els.recordStudent) {
        els.recordStudent.addEventListener("change", () => {
          persistFilters();
          renderRecords();
        });
      }
      if (els.exportCsv) {
        els.exportCsv.addEventListener("click", exportRecords);
      }
      if (els.openImport) els.openImport.addEventListener("click", openImportDialog);
      if (els.importNoteDetail) els.importNoteDetail.addEventListener("click", openImportDialog);
      if (els.importRun) els.importRun.addEventListener("click", handleImportFile);
      if (els.importSample) {
        els.importSample.addEventListener("click", async () => {
          await runImport(parseCSV(SAMPLE_CSV));
        });
      }
      if (els.irUseReading) els.irUseReading.addEventListener("click", useInfraredReading);
      [els.importClose, els.importCancel, els.importDone].forEach((button) => {
        if (!button) return;
        button.addEventListener("click", () => {
          if (els.importDialog && typeof els.importDialog.close === "function") {
            els.importDialog.close();
          } else if (els.importDialog) {
            els.importDialog.removeAttribute("open");
          }
        });
      });
      if (els.refreshBtn) els.refreshBtn.addEventListener("click", () => reload());
      if (els.demoRetry) els.demoRetry.addEventListener("click", () => boot());
    }

    function exportRecords() {
      const rows = [
        ["日期", "时间", "学号", "姓名", "班级", "体温(℃)", "来源", "备注", "复测关系"]
      ];
      const visible = state.records
        .filter((record) => !state.recordClass || studentById(record.student_id)?.class_id === state.recordClass)
        .filter((record) => !state.recordStudent || record.student_id === state.recordStudent)
        .sort((a, b) => timeValue(a.measured_at) - timeValue(b.measured_at));

      visible.forEach((record) => {
        const student = studentById(record.student_id);
        const parent =
          state.records.find((item) => item.id === record.recheck_of) ||
          state.statusRecords.find((item) => item.id === record.recheck_of);
        rows.push([
          record.measured_at.slice(0, 10),
          fmtTime(record.measured_at),
          record.student_id,
          student ? student.name : "",
          student ? student.class_name || className(student.class_id) : "",
          tempText(record.temperature_c),
          sourceLabel(record.source),
          record.note,
          parent ? `复测自 ${fmtShort(parent.measured_at)}` : ""
        ]);
      });

      if (visible.length === 0) {
        toast("当前筛选没有可导出的记录", "warn");
        return;
      }
      downloadCSV(`测温记录_${state.date}.csv`, rows);
      toast(`已导出 ${visible.length} 条记录`, "ok");
    }

    async function boot() {
      setMode("loading");
      await probeMode();
      state.date = els.recordDate ? els.recordDate.value || todayISO() : todayISO();
      if (els.recordDate && !els.recordDate.value) els.recordDate.value = state.date;
      await reload();
      if (app.mode === "demo") {
        state.importSummary = demo.importSummary;
        renderImportSummary(state.importSummary);
      }
      if (app.refreshTimer) clearInterval(app.refreshTimer);
      if (app.realtimeTimer) clearInterval(app.realtimeTimer);
      if (app.mode === "live") {
        app.refreshTimer = setInterval(() => reload(), REFRESH_MS);
        await pollInfraredRealtime();
        app.realtimeTimer = setInterval(() => pollInfraredRealtime(), REALTIME_MS);
      } else {
        renderInfraredRealtime();
      }
    }

    window.addEventListener("dashboard-day-change", (event) => {
      if (state.date !== event.detail.previous) return;
      state.date = event.detail.today;
      if (els.recordDate) els.recordDate.value = state.date;
      if (app.mode === "demo") buildDemo(state.date);
      reload();
      toast(`日期已切换到 ${state.date}`, "ok");
    });

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && app.mode === "live") pollInfraredRealtime();
    });

    startClock();
    fillSources();
    bindEvents();
    const dateInput = els.recordDate;
    if (dateInput) dateInput.value = todayISO();
    boot();
  }

  /* ---------- 当日日报页 ---------- */

  function initReportsPage() {
    const state = {
      date: todayISO(),
      classId: "",
      busy: false
    };

    const els = {
      date: $("#reportDate"),
      klass: $("#reportClass"),
      prev: $("#prevDay"),
      next: $("#nextDay"),
      today: $("#todayBtn"),
      refresh: $("#refreshBtn"),
      print: $("#printReport"),
      chip: $("#reportChip"),
      body: $("#reportBody"),
      empty: $("#reportEmpty"),
      eventList: $("#eventList"),
      eventEmpty: $("#eventEmpty"),
      eventChip: $("#eventChip"),
      attentionList: $("#attentionList"),
      attentionEmpty: $("#attentionEmpty"),
      dialogueChip: $("#dialogueChip"),
      classList: $("#classList"),
      classChip: $("#classChip"),
      summaryList: $("#summaryList"),
      detailList: $("#detailList"),
      unmeasuredList: $("#unmeasuredList"),
      footerMeta: $("#footerMeta"),
      demoRetry: $("#demoRetry")
    };

    function fillClasses() {
      if (!els.klass) return;
      els.klass.replaceChildren(new Option("全部班级", ""));
      demo.classes.forEach((item) => els.klass.append(new Option(item.name, item.id)));
      els.klass.value = state.classId;
    }

    function setStat(id, noteId, value, unit, note) {
      setStatValue(id, value, unit);
      setText($(`#${noteId}`), note);
    }

    function renderStats(report) {
      const health = report.health;
      const events = report.events;
      const handled = events.filter((item) => item.status === "handled").length;
      const urgent = report.dialogues.filter((item) => item.attention === "urgent").length;

      setStat("statEvents", "statEventsNote", events.length, "起",
        events.length ? `待处理 ${events.filter((item) => item.status === "pending").length} 起` : "当日无事件");
      setStat("statHandled", "statHandledNote", handled, "起",
        events.length ? `处置率 ${clampPercent((handled / events.length) * 100)}%` : "无需处置");
      setStat("statDialogues", "statDialoguesNote", report.dialogues.length, "段",
        report.dialogues.length ? `紧急关注 ${urgent} 段` : "当日无留意记录");
      setStat("statMeasured", "statMeasuredNote", health.measured, "人",
        `完成率 ${clampPercent(health.total ? (health.measured / health.total) * 100 : 0)}%`);
      setStat("statPending", "statPendingNote", health.pending, "人",
        health.pending ? "名单内尚未登记" : "名单内均已登记");
      setStat("statRecheck", "statRecheckNote", health.recheck, "人",
        health.recheck ? "体温仍偏高，需要跟进" : "无需复测");
    }

    function classLabel(report, classId) {
      const found = report.health.classes.find((klass) => klass.id === classId);
      return found ? found.name : className(classId);
    }

    function renderEvents(report) {
      if (!els.eventList) return;
      els.eventList.replaceChildren();
      els.eventEmpty.hidden = report.events.length > 0;

      report.events
        .slice()
        .sort((a, b) => timeValue(a.occurred_at) - timeValue(b.occurred_at))
        .forEach((event) => {
          const item = el("li", "event-item");
          item.dataset.level = event.level;

          const top = el("div", "event-top");
          top.append(el("strong", "event-title", event.title || "未命名事件"));
          const level = el("span", "badge", `等级 ${EVENT_LEVEL_LABELS[event.level] || event.level}`);
          level.dataset.tone = event.level === "high" ? "bad" : event.level === "medium" ? "warn" : "idle";
          top.append(level);
          item.append(top);

          const meta = el("p", "event-meta",
            `${fmtTime(event.occurred_at)} · ${classLabel(report, event.class_id)}${event.location ? " · " + event.location : ""} · 来源：行为识别`);
          item.append(meta);

          const statusRow = el("div", "attention-top");
          statusRow.style.marginTop = "6px";
          const status = el("span", "badge", EVENT_STATUS_LABELS[event.status] || event.status);
          status.dataset.tone = EVENT_STATUS_TONES[event.status] || "idle";
          statusRow.append(status);
          if (event.status === "handled") {
            statusRow.append(el("span", "event-meta", `${event.handler || "值班教师"} · ${fmtTime(event.handled_at)} 完成`));
          } else {
            statusRow.append(el("span", "event-meta", "等待值班教师跟进"));
          }
          item.append(statusRow);

          if (event.note) item.append(el("p", "event-note", event.note));
          els.eventList.append(item);
        });

      if (els.eventChip) {
        els.eventChip.dataset.tone = report.events.some((item) => item.status === "pending") ? "warn" : report.events.length ? "ok" : "idle";
        setText(els.eventChip, `${report.events.length} 起`);
      }
    }

    function renderDialogues(report) {
      if (!els.attentionList) return;
      els.attentionList.replaceChildren();
      els.attentionEmpty.hidden = report.dialogues.length > 0;

      report.dialogues
        .slice()
        .sort((a, b) => timeValue(b.last_at) - timeValue(a.last_at))
        .forEach((item) => {
          const card = el("li", "attention-item");
          const top = el("div", "attention-top");
          const student = demo.students.find((entry) => entry.id === item.student_id);
          const studentLabel = item.student_name
            || (student ? `${student.name}（${student.id}）` : item.student_id)
            || "未关联学生";
          top.append(el("strong", "attention-title", studentLabel));
          const badge = el("span", "badge", ATTENTION_LABELS[item.attention] || item.attention);
          badge.dataset.tone = ATTENTION_TONES[item.attention] || "idle";
          top.append(badge);
          card.append(top);

          card.append(el("p", "attention-meta", `${classLabel(report, item.class_id)} · 最近消息 ${fmtShort(item.last_at)}`));
          if (window.TongyuBootstrap.permissions.dialogue_raw) {
            if (item.excerpt) card.append(el("p", "attention-excerpt", `“${item.excerpt}”`));
            if (item.reason) card.append(el("p", "event-meta", `留意原因：${item.reason}`));
          } else card.append(el("p", "event-meta", "对话原文与留意原因未开放"));
          els.attentionList.append(card);
        });

      if (els.dialogueChip) {
        const urgent = report.dialogues.filter((item) => item.attention === "urgent").length;
        els.dialogueChip.dataset.tone = urgent ? "bad" : report.dialogues.length ? "warn" : "idle";
        setText(els.dialogueChip, urgent ? `${urgent} 段紧急` : `${report.dialogues.length} 段`);
      }
    }

    function renderClasses(report) {
      if (!els.classList) return;
      els.classList.replaceChildren();

      report.health.classes.forEach((klass) => {
        const row = el("div", "class-row");
        const head = el("div", "class-row-head");
        head.append(el("strong", "", klass.name));
        head.append(el("span", "", `已测 ${klass.measured}/${klass.total}`));
        row.append(head);

        const progress = el("div", "progress");
        progress.dataset.tone = klass.recheck > 0 ? "bad" : klass.pending > 0 ? "warn" : "ok";
        const bar = el("span");
        bar.style.width = `${clampPercent(klass.total ? (klass.measured / klass.total) * 100 : 0)}%`;
        progress.append(bar);
        row.append(progress);

        const foot = el("div", "class-row-foot");
        [["未测", klass.pending, "warn"], ["复测", klass.recheck, "bad"]].forEach(([label, value, tone]) => {
          const badge = el("span", "badge", `${label} ${value}`);
          badge.dataset.tone = value ? tone : "idle";
          foot.append(badge);
        });
        row.append(foot);
        els.classList.append(row);
      });

      if (els.classChip) {
        els.classChip.dataset.tone = report.health.pending || report.health.recheck ? "warn" : "ok";
        setText(els.classChip, `${report.health.classes.length} 个班级`);
      }
    }

    function renderSummary(report) {
      if (!els.summaryList) return;
      els.summaryList.replaceChildren();
      const health = report.health;
      const pendingNames = health.classes
        .flatMap((klass) => klass.students.filter((student) => student.status !== "measured").map((student) => `${klass.name} · ${student.name}`));

      const lines = [];
      lines.push(`今日 ${health.total} 名在册幼儿中 ${health.measured} 人完成测温，${health.pending} 人未测，${health.recheck} 人需要复测。`);
      if (report.events.length) {
        const handled = report.events.filter((item) => item.status === "handled").length;
        lines.push(`安全事件 ${report.events.length} 起，已处置 ${handled} 起，待跟进 ${report.events.length - handled} 起。`);
      } else {
        lines.push("行为识别与人工登记均未上报安全事件。");
      }
      if (report.dialogues.length) {
        const urgent = report.dialogues.filter((item) => item.attention === "urgent").length;
        lines.push(`需要关注的对话 ${report.dialogues.length} 段，其中紧急关注 ${urgent} 段，建议交接班时复核。`);
      } else {
        lines.push("当日对话记录中没有需要留意的文本线索。");
      }
      if (pendingNames.length) {
        lines.push(`待完成：${pendingNames.slice(0, 6).join("、")}${pendingNames.length > 6 ? " 等" : ""}。`);
      }

      lines.forEach((line) => els.summaryList.append(el("li", "", line)));
    }

    function renderDetails(report) {
      if (els.detailList) {
        els.detailList.replaceChildren();
        const pairs = [
          ["统计日期", report.date],
          ["统计口径", "Asia/Shanghai · 00:00–24:00"],
          ["班级范围", state.classId ? className(state.classId) : "全部班级"],
          ["数据来源", app.mode === "demo" ? "演示数据（未接通后端）" : "名单 / 测温 / 事件 / 对话接口"],
          ["生成时间", fmtShort(report.generated_at || new Date().toISOString())]
        ];
        pairs.forEach(([key, value]) => {
          const row = el("div", "kv-row");
          row.append(el("dt", "", key), el("dd", "", value));
          els.detailList.append(row);
        });
      }

      if (els.unmeasuredList) {
        els.unmeasuredList.replaceChildren();
        const items = report.health.classes.flatMap((klass) =>
          klass.students
            .filter((student) => student.status !== "measured")
            .map((student) => ({ ...student, className: klass.name }))
        );
        if (!items.length) {
          els.unmeasuredList.append(el("span", "badge", "全部学生已完成测温"));
          return;
        }
        items.forEach((student) => {
          const badge = el("span", "badge",
            `${student.className} · ${student.name}${student.status === "recheck" ? "（需复测）" : "（未测）"}`);
          badge.dataset.tone = student.status === "recheck" ? "bad" : "warn";
          els.unmeasuredList.append(badge);
        });
      }

      if (els.footerMeta) {
        setText(els.footerMeta,
          `数据范围：${report.date} 00:00–24:00（Asia/Shanghai）· 生成于 ${fmtShort(report.generated_at || new Date().toISOString())}。`);
      }
    }

    function renderReport(report) {
      const isEmpty = report.events.length === 0 && report.dialogues.length === 0 && report.health.total === 0;
      if (els.body) els.body.hidden = isEmpty;
      if (els.empty) els.empty.hidden = !isEmpty;
      if (isEmpty) {
        if (app.mode === "error") {
          setText($("#reportEmptyTitle"), "无法读取当日日报");
          setText($("#reportEmptyText"), `${app.reason || "接口请求失败。"} 恢复 Dashboard 服务后点击“重新检测”，页面不会用演示数据冒充真实日报。`);
        } else {
          setText($("#reportEmptyTitle"), `${report.date} 暂无日报数据`);
          setText($("#reportEmptyText"),
            "该日期没有事件、对话或测温记录。可以切换到有数据的日期，或先到学生测温页登记体温。");
        }
        setText(els.chip, app.mode === "error" ? "接口异常" : "无数据");
        els.chip.dataset.tone = app.mode === "error" ? "bad" : "idle";
        if (els.footerMeta) setText(els.footerMeta, `数据范围：${report.date}（Asia/Shanghai）。当日没有可汇总的记录。`);
        return;
      }

      renderStats(report);
      renderEvents(report);
      renderDialogues(report);
      renderClasses(report);
      renderSummary(report);
      renderDetails(report);

      if (els.chip) {
        els.chip.dataset.tone = app.mode === "demo" ? "warn" : "ok";
        setText(els.chip, app.mode === "demo" ? "演示数据" : "已同步");
      }
      announce(`${report.date} 日报已更新：事件 ${report.events.length} 起，关注对话 ${report.dialogues.length} 段，已测 ${report.health.measured} 人。`);
    }

    function normalizeReport(payload, date) {
      const report = payload?.report || payload || {};
      const health = report.health || {};
      const classes = Array.isArray(health.classes) ? health.classes : [];
      return {
        date: report.date || date,
        timezone: report.timezone || TZ,
        generated_at: report.generated_at || new Date().toISOString(),
        events: Array.isArray(report.events) ? report.events : [],
        dialogues: Array.isArray(report.dialogues) ? report.dialogues : [],
        health: {
          total: Number(health.total || 0),
          measured: Number(health.measured || 0),
          pending: Number(health.pending || 0),
          recheck: Number(health.recheck || 0),
          classes: classes.map((klass) => ({
            id: klass.id || "",
            name: klass.name || className(klass.id),
            total: Number(klass.total || 0),
            measured: Number(klass.measured || 0),
            pending: Number(klass.pending || 0),
            recheck: Number(klass.recheck || 0),
            students: Array.isArray(klass.students) ? klass.students : []
          }))
        }
      };
    }

    function buildDemoReport(date, classId) {
      /* 演示样例只覆盖“演示当天”，其他日期返回空报表，用于演示“当日暂无数据”。 */
      if (date !== demo.date) {
        return {
          date,
          timezone: TZ,
          generated_at: new Date().toISOString(),
          events: [],
          dialogues: [],
          health: { total: 0, measured: 0, pending: 0, recheck: 0, classes: [] }
        };
      }

      const records = demo.records;
      const students = demo.students.filter((student) => !classId || student.class_id === classId);
      const classes = demo.classes
        .filter((klass) => !classId || klass.id === classId)
        .map((klass) => {
          const classStudents = students.filter((student) => student.class_id === klass.id);
          let measured = 0;
          let pending = 0;
          let recheck = 0;
          const detailed = classStudents.map((student) => {
            const status = statusOf(student, records).key;
            if (status === "measured") measured += 1;
            else if (status === "pending") pending += 1;
            else recheck += 1;
            return { id: student.id, name: student.name, status };
          });
          return { id: klass.id, name: klass.name, total: classStudents.length, measured, pending, recheck, students: detailed };
        });

      const events = demo.events
        .filter((event) => !classId || event.class_id === classId)
        .map((event) => ({ ...event }));
      const dialogues = demo.dialogues
        .filter((item) => !classId || item.class_id === classId)
        .map((item) => ({ ...item }));

      const health = classes.reduce(
        (acc, klass) => ({
          total: acc.total + klass.total,
          measured: acc.measured + klass.measured,
          pending: acc.pending + klass.pending,
          recheck: acc.recheck + klass.recheck
        }),
        { total: 0, measured: 0, pending: 0, recheck: 0 }
      );

      return {
        date,
        timezone: TZ,
        generated_at: new Date().toISOString(),
        events,
        dialogues,
        health: { ...health, classes }
      };
    }

    async function loadReport() {
      if (state.busy) return;
      state.busy = true;
      if (els.refresh) els.refresh.disabled = true;
      try {
        let report;
        if (app.mode === "live") {
          const query = new URLSearchParams({ date: state.date });
          if (state.classId) query.set("class_id", state.classId);
          const payload = await requestJSON(`${API.daily}?${query.toString()}`);
          report = normalizeReport(payload, state.date);
        } else {
          report = buildDemoReport(state.date, state.classId);
        }
        renderReport(report);
      } catch (error) {
        setMode("error", describeError(error));
        toast(`日报加载失败：${describeError(error)}`, "bad");
        renderReport({
          date: state.date,
          timezone: TZ,
          generated_at: new Date().toISOString(),
          events: [],
          dialogues: [],
          health: { total: 0, measured: 0, pending: 0, recheck: 0, classes: [] }
        });
      } finally {
        state.busy = false;
        if (els.refresh) els.refresh.disabled = false;
      }
    }

    function setDate(value) {
      state.date = value || todayISO();
      if (els.date) els.date.value = state.date;
      loadReport();
    }

    function bindEvents() {
      if (els.date) els.date.addEventListener("change", () => setDate(els.date.value));
      if (els.prev) els.prev.addEventListener("click", () => setDate(shiftDate(state.date, -1)));
      if (els.next) els.next.addEventListener("click", () => setDate(shiftDate(state.date, 1)));
      if (els.today) els.today.addEventListener("click", () => setDate(todayISO()));
      if (els.klass) {
        els.klass.addEventListener("change", () => {
          state.classId = els.klass.value;
          loadReport();
        });
      }
      if (els.refresh) els.refresh.addEventListener("click", () => loadReport());
      if (els.print) els.print.addEventListener("click", () => window.print());
      if (els.demoRetry) {
        els.demoRetry.addEventListener("click", async () => {
          setMode("loading");
          await probeMode();
          await loadReport();
        });
      }
    }

    async function boot() {
      setMode("loading");
      if (els.date) els.date.value = state.date;
      fillClasses();
      await probeMode();
      fillClasses();
      await loadReport();
    }

    window.addEventListener("dashboard-day-change", (event) => {
      if (state.date !== event.detail.previous) return;
      state.date = event.detail.today;
      if (els.date) els.date.value = state.date;
      if (app.mode === "demo") buildDemo(state.date);
      loadReport();
    });

    startClock();
    bindEvents();
    boot();
  }

  /* ---------- 启动 ---------- */

  function boot() {
    const page = document.body.dataset.page;
    buildDemo(todayISO());
    if (page === "health") initHealthPage();
    else if (page === "reports") initReportsPage();

    /* 窄屏下侧边导航变成可横向滚动的标签条，把当前页滚到可见位置。 */
    const activeNav = document.querySelector('.nav-link[aria-current="page"]');
    if (activeNav && typeof activeNav.scrollIntoView === "function") {
      setTimeout(() => activeNav.scrollIntoView({ block: "nearest", inline: "center" }), 0);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
