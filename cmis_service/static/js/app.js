/* CMIScope front-end controller.
 * Chinese is the default UI language; English is selectable via #langToggle.
 * All user-visible strings go through CMIS_I18N.t(); technical identifiers
 * (page numbers, CMDIDs, field keys) stay in English in both languages.
 */
(function () {
  'use strict';

  var I18N = window.CMIS_I18N;
  var t = I18N.t;
  var state = {
    view: 'overview', meta: null, overview: null, sections: null,
    devices: [], selectedDevice: '', selectedKg: '', editorItem: null,
    cdbCommands: [], lang: 'zh'
  };

  // --------------------------------------------------------------- helpers
  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function pick(zh, en) {
    return (I18N.getLang() === 'en' && en) ? en : (zh || en || '');
  }
  // Data records (knowledge graph, source catalogue, generated seed data) are
  // stored in Chinese. In English mode their display strings are looked up in
  // the curated dictionary shipped as js/data_en.js. Technical identifiers and
  // user-entered values are never rewritten.
  function L(value) {
    if (I18N.getLang() !== 'en' || value === null || value === undefined) return value;
    var text = String(value);
    if (!/[\u3400-\u9fff]/.test(text)) return text;
    var map = window.CMIS_DATA_EN || {};
    var hit = map[text];
    if (typeof hit === 'string' && hit && !/[\u3400-\u9fff]/.test(hit)) return hit;
    // Safety net for records added later: never render Chinese in English mode.
    return text.replace(/[\u3400-\u9fff]/g, '').replace(/\s{2,}/g, ' ').trim() || '-';
  }
  function LJson(value) {
    if (I18N.getLang() !== 'en') return value;
    if (Array.isArray(value)) return value.map(LJson);
    if (value && typeof value === 'object') {
      var out = {};
      Object.keys(value).forEach(function (k) { out[k] = LJson(value[k]); });
      return out;
    }
    return typeof value === 'string' ? L(value) : value;
  }
  function groupLabel(key) {
    var k = 'search.group.' + key;
    var label = t(k);
    return label === k ? key : label;
  }
  function badge(text, color) {
    return '<span class="badge bg-' + (color || 'secondary') + '-lt">' + esc(text) + '</span>';
  }
  function mono(text) { return '<span class="mono">' + esc(text) + '</span>'; }
  function el(id) { return document.getElementById(id); }
  function qs(id) { return document.querySelector(id); }

  function api(method, path, body) {
    var opts = { method: method, headers: {} };
    if (body !== undefined && body !== null) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (json) { return { status: r.status, json: json }; });
    }).then(function (res) {
      if (!res.json.ok) {
        var e = res.json.error || {};
        var err = new Error((e.message || 'Request failed') + (e.code ? ' [' + e.code + ']' : ''));
        err.code = e.code;
        err.details = e.details;
        err.status = res.status;
        throw err;
      }
      return res.json.data;
    });
  }
  function toast(message, kind) {
    var box = document.createElement('div');
    box.className = 'cm-toast ' + (kind === 'err' ? 'err' : 'ok');
    box.textContent = message;
    el('toastContainer').appendChild(box);
    setTimeout(function () { box.remove(); }, 5200);
  }
  function fail(err) {
    toast((err && err.message) || String(err), 'err');
  }
  function kv(label, value) {
    return '<div class="kv"><div class="k">' + esc(label) + '</div><div class="v">' + value + '</div></div>';
  }
  function barRow(name, value, max) {
    var pct = max > 0 ? Math.max(4, Math.round(value / max * 100)) : 0;
    return '<div class="bar-row"><div class="bar-name">' + esc(name) + '</div>' +
      '<div class="bar-track"><span class="bar-fill" style="width:' + pct + '%"></span></div>' +
      '<div class="bar-num">' + esc(value) + '</div></div>';
  }
  function emptyRow(count, text) {
    return '<tr><td colspan="' + count + '" class="empty-hint">' + esc(text) + '</td></tr>';
  }
  function confBadge(c) {
    if (c === 'confirmed') return badge(t('common.confirmed'), 'green');
    if (c === 'pending') return badge(t('common.pending'), 'orange');
    return badge(t('common.partial'), 'yellow');
  }
  function statusBadge(s) {
    var map = { online: ['green', 'common.online'], maintenance: ['yellow', 'common.maintenance'], offline: ['red', 'common.offline'] };
    var m = map[s] || ['secondary', null];
    return badge(m[1] ? t(m[1]) : esc(s), m[0]);
  }
  function timeShort(s) { return esc(String(s || '').replace('T', ' ').slice(0, 19)); }
  function hexDump(text) {
    var chunks = [];
    for (var i = 0; i < text.length; i += 32) chunks.push(text.slice(i, i + 32).replace(/(..)/g, '$1 ').trim());
    return chunks.join('\n');
  }

  // --------------------------------------------------------------- navigation
  var VIEW_TITLE = {
    overview: 'nav.overview', devices: 'nav.devices', module: 'nav.module',
    config: 'nav.config', graph: 'nav.graph', sources: 'nav.sources',
    targets: 'nav.targets', about: 'nav.about', search: 'common.searchResults'
  };
  function setView(name, skipHash) {
    state.view = name;
    document.querySelectorAll('section.view').forEach(function (s) { s.hidden = true; });
    var section = el('view-' + name);
    if (section) section.hidden = false;
    document.querySelectorAll('#sideNav a').forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('data-view') === name);
    });
    el('viewTitle').textContent = t(VIEW_TITLE[name] || 'nav.overview');
    if (!skipHash && location.hash !== '#' + name) { location.hash = '#' + name; }
    window.scrollTo({ top: 0, behavior: 'auto' });
    renderCurrent();
  }
  function renderCurrent() {
    var name = state.view;
    if (name === 'overview') loadOverview();
    else if (name === 'devices') loadDevices();
    else if (name === 'module') loadModule();
    else if (name === 'config') loadConfig();
    else if (name === 'graph') loadGraph();
    else if (name === 'sources') loadSources();
    else if (name === 'targets') loadTargets();
    else if (name === 'about') loadAbout();
  }

  // --------------------------------------------------------------- overview
  function loadOverview() {
    api('GET', '/api/overview').then(function (d) {
      state.overview = d;
      var cards = [
        ['ov.devices', d.devices, 'ti ti-server-2', t('common.online') + ': ' + (d.status_counts.online || 0)],
        ['ov.modules', d.modules, 'ti ti-cpu', 'QSFP-DD / OSFP'],
        ['ov.fields', d.fields, 'ti ti-list-details', t('ov.sectionCount', { n: Object.keys(d.section_counts || {}).length })],
        ['ov.configItems', d.config_items, 'ti ti-settings', t('cfg.writable') + ': ' + d.writable_items],
        ['ov.changes', d.changes, 'ti ti-history', t('common.staged') + ' / ' + t('common.applied')],
        ['ov.cdbOps', d.cdb_operations, 'ti ti-terminal-2', 'Page 9Fh / A0h-AFh']
      ];
      el('statGrid').innerHTML = cards.map(function (c) {
        return '<div class="stat-card"><div class="d-flex justify-content-between">' +
          '<div class="stat-label">' + esc(t(c[0])) + '</div><i class="' + c[2] + '"></i></div>' +
          '<div class="stat-value">' + esc(c[1]) + '</div><div class="stat-sub">' + esc(c[3]) + '</div></div>';
      }).join('');

      var sc = d.status_counts || {};
      var maxSc = Math.max.apply(null, Object.values(sc).concat([1]));
      el('statusChart').innerHTML = Object.keys(sc).length
        ? Object.keys(sc).map(function (k) { return barRow(t('common.' + k) === 'common.' + k ? k : t('common.' + k), sc[k], maxSc); }).join('')
        : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';

      var changes = d.recent_changes || [];
      el('recentTable').innerHTML = '<thead><tr><th>' + esc(t('dev.col.id')) + '</th><th>' +
        esc(t('cfg.col.field')) + '</th><th>' + esc(t('cfg.col.value')) + '</th><th>' +
        esc(t('mod.result')) + '</th><th>' + esc(t('common.time')) + '</th></tr></thead><tbody>' +
        (changes.length ? changes.map(function (c) {
          return '<tr><td>' + mono(c.device_id) + '</td><td>' + mono(c.field_key) + '</td><td>' +
            esc(c.old_value) + ' → ' + esc(c.new_value) + '</td><td>' + badge(esc(c.result), c.result === 'applied' ? 'green' : 'blue') +
            '</td><td class="muted">' + timeShort(c.created_at) + '</td></tr>';
        }).join('') : emptyRow(5, t('ov.noChanges'))) + '</tbody>';

      var kg = d.kg || {};
      var byType = kg.entities_by_type || kg.by_type || {};
      var maxKg = Math.max.apply(null, Object.values(byType).concat([1]));
      el('kgTypeChart').innerHTML = Object.keys(byType).length
        ? Object.keys(byType).map(function (k) { return barRow(k, byType[k], maxKg); }).join('')
        : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';

      var svc = d.service || {};
      el('serviceInfo').innerHTML = '<div class="kv-grid">' +
        kv('CMIScope', badge(d.project ? d.project.name : 'CMIScope', 'blue')) +
        kv(t('side.mode'), badge(svc.read_only ? 'read-only' : 'read/write', svc.read_only ? 'orange' : 'green')) +
        kv(t('side.access'), esc(svc.access_mode || 'mirror')) +
        kv('CMIS', '5.3 / 5.4') +
        kv(t('side.framework'), esc((d.framework || {}).name + ' ' + (d.framework || {}).version)) +
        kv('DB', mono(svc.db_file || '')) + '</div>';

      var sec = d.section_counts || {};
      var maxSec = Math.max.apply(null, Object.values(sec).concat([1]));
      el('sectionChart').innerHTML = Object.keys(sec).length
        ? Object.keys(sec).map(function (k) { return barRow(sectionLabel(k), sec[k], maxSec); }).join('')
        : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';

      el('sideMode').textContent = (svc.read_only ? 'read-only' : 'read/write') + ' · ' + (svc.access_mode || 'mirror');
      el('sideAccess').innerHTML = badge(d.access ? d.access.mode : 'mirror', 'blue');
    }).catch(fail);
  }
  function sectionLabel(key) {
    var found = (state.sections || []).filter(function (s) { return s.key === key; })[0];
    if (found) return pick(found.zh, found.en);
    var map = { LOW_PAGE: 'mod.low', VDM: 'mod.vdm', CDB: 'mod.cdb', CONTROL: 'mod.control' };
    return t(map[key] || key) === (map[key] || key) ? key : t(map[key]);
  }

  // --------------------------------------------------------------- devices
  function loadDevices() {
    var q = el('deviceFilter').value.trim();
    var status = el('deviceStatus').value;
    api('GET', '/api/devices?q=' + encodeURIComponent(q) + '&status=' + encodeURIComponent(status))
      .then(function (d) {
        state.devices = d.items;
        el('deviceTable').querySelector('tbody').innerHTML = d.items.length ? d.items.map(function (r) {
          return '<tr class="clickable" data-device="' + esc(r.device_id) + '">' +
            '<td>' + mono(r.device_id) + '</td><td>' + esc(pick(r.name, r.name_en)) + '</td>' +
            '<td>' + esc(r.device_type) + '</td><td>' + esc((r.vendor || '') + ' / ' + (r.model || '')) + '</td>' +
            '<td>' + esc(r.location || '') + '</td><td>' + badge('CMIS ' + esc(r.cmis_revision), 'blue') + '</td>' +
            '<td>' + badge(esc(r.access_mode || 'mirror'), 'purple') + '</td>' +
            '<td>' + statusBadge(r.status) + '</td><td>' + esc(r.config_count) + '</td></tr>';
        }).join('') : emptyRow(9, t('common.noData'));
        el('deviceFooter').textContent = t('dev.footer', { n: d.total });
        el('deviceTable').querySelectorAll('tr[data-device]').forEach(function (tr) {
          tr.addEventListener('click', function () { showDeviceDetail(tr.getAttribute('data-device')); });
        });
        if (!el('deviceDetailCard').hidden) {
          var id = el('deviceDetailCard').getAttribute('data-device');
          if (id) showDeviceDetail(id);
        }
      }).catch(fail);
  }
  function showDeviceDetail(id) {
    api('GET', '/api/devices/' + encodeURIComponent(id)).then(function (d) {
      var card = el('deviceDetailCard');
      card.hidden = false;
      card.setAttribute('data-device', id);
      el('deviceDetailTitle').textContent = t('dev.detail') + ' · ' + id;
      var groups = {};
      (d.config_items || []).forEach(function (i) {
        (groups[i.section || 'LOW_PAGE'] = groups[i.section || 'LOW_PAGE'] || []).push(i);
      });
      var html = '<div class="kv-grid mb-3">' +
        kv(t('dev.col.name'), esc(pick(d.device.name, d.device.name_en))) +
        kv(t('dev.col.vendor'), esc(d.device.vendor + ' / ' + d.device.model)) +
        kv(t('dev.col.location'), esc(d.device.location)) +
        kv(t('side.access'), badge(esc(d.device.access_mode || 'mirror'), 'blue')) +
        kv('CMIS', esc(d.device.cmis_revision)) +
        kv(t('dev.col.status'), statusBadge(d.device.status)) + '</div>';
      html += '<div class="pill-row mb-3">' + Object.keys(groups).map(function (k) {
        return badge(sectionLabel(k) + ' · ' + groups[k].length, 'blue');
      }).join(' ') + '</div>';
      html += '<div class="table-responsive"><table class="table table-sm table-vcenter"><thead><tr>' +
        '<th>' + esc(t('mod.section')) + '</th><th>' + esc(t('cfg.col.field')) + '</th><th>' +
        esc(t('cfg.col.page')) + '</th><th>' + esc(t('cfg.col.value')) + '</th><th>' +
        esc(t('cfg.col.access')) + '</th></tr></thead><tbody>' +
        (d.config_items || []).slice(0, 60).map(function (i) {
          return '<tr><td>' + badge(sectionLabel(i.section), 'purple') + '</td><td>' +
            esc(pick(i.label, i.label_en)) + '</td><td>' + mono((i.page || '') + ':' + (i.byte_offset || '')) +
            '</td><td>' + mono(i.value) + '</td><td>' + (i.writable ? badge('RW', 'green') : badge('RO', 'secondary')) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
      el('deviceDetailBody').innerHTML = html;
    }).catch(fail);
  }

  // --------------------------------------------------------------- module CMIS partitions
  function loadModule() {
    var deviceId = el('moduleDevice').value || state.selectedDevice;
    var section = el('moduleSection').value;
    Promise.all([
      api('GET', '/api/sections'),
      api('GET', '/api/cmis/module?device_id=' + encodeURIComponent(deviceId) + '&section=' + encodeURIComponent(section)),
      api('GET', '/api/cdb/commands')
    ]).then(function (res) {
      state.sections = res[0].items;
      state.cdbCommands = res[2].items;
      var d = res[1];
      var m = d.module || {};
      var dev = d.device || {};
      el('moduleSummary').innerHTML = '<div class="kv-grid">' +
        kv(t('dev.col.id'), mono(dev.device_id)) +
        kv(t('dev.col.name'), esc(pick(dev.name, dev.name_en))) +
        kv(t('mod.portFormFactor'), esc((m.port || '-') + ' / ' + (m.form_factor || '-'))) +
        kv(t('mod.vendorPn'), mono(m.part_number || '-')) +
        kv(t('mod.serial'), mono(m.serial || '-')) +
        kv('CMIS', badge('rev ' + esc(dev.cmis_revision || '-'), 'blue')) +
        kv(t('dev.col.status'), esc(m.module_state || '-')) +
        kv(t('side.access'), badge(esc(dev.access_mode || 'mirror'), 'purple')) + '</div>' +
        '<div class="pill-row mt-2">' + (d.spec_releases || []).map(function (r) {
          return badge(esc(r.doc + ' · ' + r.date), 'secondary');
        }).join(' ') + '</div>';

      var host = el('moduleSections');
      host.innerHTML = '';
      (d.sections || []).forEach(function (sec) {
        var card = document.createElement('div');
        card.className = 'card mb-3';
        card.innerHTML = sectionCardHtml(sec, d, res[0]);
        host.appendChild(card);
        if (sec.key === 'CDB') {
          var wrap = document.createElement('div');
          wrap.className = 'card-body border-top';
          wrap.innerHTML = cdbPanelHtml(dev.device_id);
          card.appendChild(wrap);
          wireCdbPanel(card, dev.device_id);
        }
        card.querySelectorAll('button[data-edit]').forEach(function (b) {
          b.addEventListener('click', function () { openEditor(Number(b.getAttribute('data-edit'))); });
        });
      });
      if (!(d.sections || []).length) {
        host.innerHTML = '<div class="card"><div class="card-body empty-hint">' + esc(t('common.noData')) + '</div></div>';
      }
    }).catch(fail);
  }
  function sectionCardHtml(sec, view, sectionsData) {
    var pages = (sec.pages || []).map(function (p) { return badge(p, 'blue'); }).join(' ');
    var header = '<div class="card-header"><h3 class="card-title">' + esc(pick(sec.zh, sec.en)) +
      ' <span class="text-secondary small">' + esc(sec.key) + '</span></h3>' +
      '<div class="ms-auto d-flex gap-2 align-items-center flex-wrap">' + pages +
      badge(sec.write_policy, sec.write_policy === 'gated' ? 'orange' : 'secondary') + '</div></div>';
    var body = '<div class="card-body">' +
      '<div class="text-secondary mb-2">' + esc(pick(sec.summary_zh, sec.summary_en)) + '</div>' +
      '<div class="small muted mb-3">' + esc(t('mod.spec')) + ': ' + mono(sec.spec_ref || '') +
      ' · ' + esc(t('mod.writePolicy')) + ': ' + esc(pick(sec.write_note_zh, sec.write_note_en)) + '</div>';

    if (sec.key === 'LOW_PAGE') {
      var regs = (sectionsData.lower_memory_map || []);
      body += '<details class="mb-3"><summary class="small">' + esc(t('mod.registerMap')) +
        ' (Lower / Upper 00h-01h)</summary><div class="table-responsive mt-2"><table class="table table-sm table-vcenter">' +
        '<thead><tr><th>' + esc(t('mod.pageOffset')) + '</th><th>' + esc(t('mod.size')) + '</th><th>' +
        esc(t('mod.field')) + '</th><th>' + esc(t('mod.access')) + '</th><th>' + esc(t('mod.desc')) +
        '</th></tr></thead><tbody>' + regs.map(function (r) {
          return '<tr><td>' + mono(r.addr) + '</td><td>' + esc(r.size) + '</td><td>' +
            esc(pick(r.zh, r.en)) + '<div class="muted small">' + mono(r.en) + '</div></td><td>' +
            badge(esc(r.access), 'secondary') + '</td><td class="muted">' +
            esc(r.note) + '</td></tr>';
        }).join('') + '</tbody></table></div></details>';
      body += '<details class="mb-3"><summary class="small">' + esc(t('mod.identity')) +
        '</summary><div class="table-responsive mt-2"><table class="table table-sm table-vcenter"><thead><tr><th>' +
        esc(t('mod.field')) + '</th><th>' + esc(t('mod.pageOffset')) + '</th><th>' + esc(t('mod.size')) +
        '</th><th>' + esc(t('mod.access')) +
        '</th></tr></thead><tbody>' + (sectionsData.upper_page_00h || []).map(function (r) {
          return '<tr><td>' + esc(pick(r.zh, r.en)) + '<div class="muted small">' + mono(r.en) +
            '</div></td><td>' + mono(r.addr) + '</td><td>' + esc(r.size) + '</td><td>' +
            badge(esc(r.access), 'secondary') + '</td></tr>';
        }).join('') + '</tbody></table></div></details>';
    }
    if (sec.key === 'CDB') {
      body += '<details class="mb-3" open><summary class="small">' + esc(t('mod.registerMap')) +
        ' (Page 9Fh / A0h-AFh)</summary><div class="table-responsive mt-2"><table class="table table-sm table-vcenter">' +
        '<thead><tr><th>' + esc(t('mod.pageOffset')) + '</th><th>' + esc(t('mod.size')) + '</th><th>' +
        esc(t('mod.field')) + '</th><th>' + esc(t('mod.desc')) + '</th></tr></thead><tbody>' +
        (sectionsData.cdb_frame || []).map(function (r) {
          return '<tr><td>' + mono(r.offset) + '</td><td>' + esc(r.size) + '</td><td>' +
            esc(pick(r.zh, r.en)) + '</td><td class="muted">' + esc(r.note) + '</td></tr>';
        }).join('') + '</tbody></table></div></details>';
    }
    var items = sec.items || [];
    body += '<div class="table-responsive"><table class="table table-sm table-vcenter table-hover"><thead><tr>' +
      '<th>' + esc(t('mod.field')) + '</th><th>' + esc(t('mod.pageOffset')) + '</th><th>' +
      esc(t('mod.value')) + '</th><th>' + esc(t('mod.access')) + '</th><th>' + esc(t('mod.confidence')) +
      '</th><th>' + esc(t('mod.spec')) + '</th><th>' + esc(t('mod.action')) + '</th></tr></thead><tbody>' +
      (items.length ? items.map(function (i) {
        return '<tr><td>' + esc(pick(i.label, i.label_en)) + '<div class="muted small">' + mono(i.field_key) +
          '</div></td><td>' + mono((i.page || '') + ':' + (i.byte_offset || '')) + '</td><td>' +
          mono(i.value === '' ? '-' : i.value) + '</td><td>' +
          (i.writable ? badge('RW', 'green') : badge(esc(i.field_access || 'RO'), 'secondary')) + '</td><td>' +
          confBadge(i.field_confidence) + '</td><td class="muted small">' + esc(i.spec_ref || '') + '</td><td>' +
          (i.writable ? '<button class="btn btn-sm btn-outline-primary" data-edit="' + i.id + '">' +
            esc(t('mod.edit')) + '</button>' : '<span class="muted small">' + esc(t('mod.readOnly')) + '</span>') +
          '</td></tr>';
      }).join('') : emptyRow(7, t('mod.noItems'))) + '</tbody></table></div></div>';
    return header + body;
  }

  // --------------------------------------------------------------- CDB operations panel
  function cdbPanelHtml(deviceId) {
    var opts = state.cdbCommands.map(function (c) {
      return '<option value="' + esc(c.cmd_id) + '">' + esc(c.cmd_id + 'h · ' + pick(c.zh, c.en)) + '</option>';
    }).join('');
    return '<h3 class="card-title mb-2">' + esc(t('mod.cmdCatalog')) + '</h3>' +
      '<div class="table-responsive mb-3" style="max-height:230px"><table class="table table-sm table-vcenter">' +
      '<thead><tr><th>' + esc(t('mod.cmdId')) + '</th><th>' + esc(t('mod.cmdName')) + '</th><th>' +
      esc(t('mod.group')) + '</th><th>' + esc(t('mod.risk')) + '</th><th>' + esc(t('mod.specRef')) +
      '</th><th>' + esc(t('mod.lplRule')) + '</th></tr></thead><tbody>' +
      state.cdbCommands.map(function (c) {
        var riskColor = c.risk === 'firmware' ? 'red' : c.risk === 'security' ? 'orange' :
          c.risk === 'control' ? 'yellow' : 'green';
        return '<tr><td>' + mono(c.cmd_id + 'h') + '</td><td>' + esc(pick(c.zh, c.en)) + '</td><td>' +
          esc(c.group) + '</td><td>' + badge(esc(c.risk), riskColor) + '</td><td class="muted small">' +
          esc(c.spec_ref) + '</td><td class="muted small">' + esc(c.lpl_rule) + '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<h3 class="card-title mb-2">' + esc(t('mod.composer')) + '</h3>' +
      '<div class="row g-2">' +
      '<div class="col-md-3"><label class="form-label small">CMDID</label><select class="form-select form-select-sm cdb-cmd">' + opts + '</select></div>' +
      '<div class="col-md-3"><label class="form-label small">' + esc(t('mod.operator')) +
      '</label><input class="form-control form-control-sm cdb-operator" value="local-admin"></div>' +
      '<div class="col-md-3"><label class="form-label small">' + esc(t('mod.confirm')) +
      '</label><input class="form-control form-control-sm cdb-confirm" value="EXECUTE"></div>' +
      '<div class="col-md-3 d-flex align-items-end gap-2">' +
      '<button class="btn btn-sm btn-outline-primary cdb-compose">' + esc(t('mod.compose')) + '</button>' +
      '<button class="btn btn-sm btn-primary cdb-execute">' + esc(t('mod.execute')) + '</button></div>' +
      '<div class="col-md-6"><label class="form-label small">' + esc(t('mod.lpl')) +
      '</label><textarea class="form-control form-control-sm cdb-lpl" rows="2" placeholder="00 01 02"></textarea></div>' +
      '<div class="col-md-6"><label class="form-label small">' + esc(t('mod.epl')) +
      '</label><textarea class="form-control form-control-sm cdb-epl" rows="2" placeholder="' + esc(t('common.optional')) + '"></textarea></div>' +
      '</div><div class="small muted mt-2">' + esc(t('mod.note')) + '</div>' +
      '<div class="cdb-report mt-3"></div><div class="cdb-status mt-2"></div>' +
      '<h4 class="mt-3">' + esc(t('mod.history')) + '</h4><div class="cdb-history"></div>';
  }
  function wireCdbPanel(card, deviceId) {
    function payload() {
      return {
        device_id: deviceId,
        cmd_id: card.querySelector('.cdb-cmd').value,
        lpl_hex: card.querySelector('.cdb-lpl').value,
        epl_hex: card.querySelector('.cdb-epl').value,
        operator: card.querySelector('.cdb-operator').value,
        confirm: card.querySelector('.cdb-confirm').value
      };
    }
    function showFrame(frame, extra) {
      card.querySelector('.cdb-report').innerHTML =
        '<div class="report-box pass"><div class="mb-2">' + badge('CMD ' + esc(frame.cmd_id + 'h'), 'blue') + ' ' +
        esc(frame.command) + ' ' + badge(esc(frame.risk), frame.risk === 'firmware' ? 'red' : 'green') + '</div>' +
        '<div class="kv-grid mb-2">' + kv(t('mod.page'), mono(frame.page)) + kv(t('mod.epl'), mono(frame.epl_pages)) +
        kv(t('mod.lplLen'), esc(frame.lpl_len)) + kv(t('mod.eplLen'), esc(frame.epl_len)) +
        kv(t('mod.checkCode'), mono(frame.check_code)) + kv(t('mod.spec'), esc(frame.spec_ref)) + '</div>' +
        '<div class="small mb-1">' + esc(t('mod.framePreview')) + ' (128 bytes)</div>' +
        '<pre class="mono cdb-frame mb-0">' + esc(hexDump(frame.frame_hex)) + '</pre>' +
        (extra ? '<div class="mt-2">' + esc(extra) + '</div>' : '') + '</div>';
    }
    card.querySelector('.cdb-compose').addEventListener('click', function () {
      api('POST', '/api/cdb/compose', payload()).then(function (d) {
        showFrame(d.frame, t('mod.staged'));
        toast(t('mod.frameValidated', { id: d.frame.cmd_id }), 'ok');
      }).catch(fail);
    });
    card.querySelector('.cdb-execute').addEventListener('click', function () {
      api('POST', '/api/cdb/execute', payload()).then(function (d) {
        showFrame(d.frame, d.message);
        toast(d.message, 'ok');
        refreshCdbHistory(card, deviceId);
      }).catch(fail);
    });
    refreshCdbHistory(card, deviceId);
    api('GET', '/api/cdb/status?device_id=' + encodeURIComponent(deviceId)).then(function (d) {
      var sr = d.status_register || {};
      card.querySelector('.cdb-status').innerHTML = '<div class="kv-grid">' +
        kv(t('mod.status'), mono(sr.value || '-')) + kv(t('mod.pageOffset'), mono(sr.byte_offset || '-')) +
        kv(t('mod.spec'), esc(sr.spec_ref || '-')) + '</div>';
    }).catch(function () { /* status is optional */ });
  }
  function refreshCdbHistory(card, deviceId) {
    api('GET', '/api/cdb/history?device_id=' + encodeURIComponent(deviceId) + '&limit=8').then(function (d) {
      card.querySelector('.cdb-history').innerHTML = d.items.length
        ? '<div class="table-responsive"><table class="table table-sm table-vcenter"><thead><tr>' +
          '<th>CMDID</th><th>' + esc(t('mod.cmdName')) + '</th><th>' + esc(t('mod.result')) +
          '</th><th>' + esc(t('mod.applied')) + '</th><th>' + esc(t('common.time')) + '</th></tr></thead><tbody>' +
          d.items.map(function (r) {
            return '<tr><td>' + mono(r.cmd_id + 'h') + '</td><td>' + esc(r.command_name) + '</td><td>' +
              badge(esc(r.result), r.result === 'staged' ? 'blue' : 'green') + '</td><td>' +
              (r.applied_to_hardware ? badge(t('common.yes'), 'green') : badge(t('common.no'), 'secondary')) + '</td><td class="muted">' +
              timeShort(r.created_at) + '</td></tr>';
          }).join('') + '</tbody></table></div>'
        : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';
    }).catch(fail);
  }

  // --------------------------------------------------------------- configuration items
  function loadConfig() {
    var q = el('configFilter').value.trim();
    var device = el('configDevice').value;
    var section = el('configSection').value;
    var writable = el('configWritable').value;
    api('GET', '/api/config-items?limit=1000&q=' + encodeURIComponent(q) +
      '&device_id=' + encodeURIComponent(device) + '&section=' + encodeURIComponent(section) +
      '&writable=' + encodeURIComponent(writable)).then(function (d) {
        el('configTable').querySelector('tbody').innerHTML = d.items.length ? d.items.map(function (r) {
          return '<tr><td>' + mono(r.device_id) + '</td><td>' + esc(pick(r.label, r.label_en)) +
            '<div class="muted small">' + mono(r.field_key) + ' ' + badge(esc(r.section || ''), 'purple') + '</div></td>' +
            '<td>' + mono((r.page || '') + ':' + (r.byte_offset || '')) + '</td><td>' + mono(r.value) + '</td>' +
            '<td>' + mono(r.raw_hex || '-') + '</td><td>' + esc(r.data_type) + '</td><td>' +
            (r.writable ? badge('RW', 'green') : badge('RO', 'secondary')) + '</td>' +
            '<td class="muted small">' + esc(r.spec_ref || '') + '</td><td>' +
            '<button class="btn btn-sm btn-outline-primary" data-edit="' + r.id + '">' +
            esc(r.writable ? t('mod.edit') : t('mod.view')) + '</button></td></tr>';
        }).join('') : emptyRow(9, t('common.noData'));
        el('configFooter').textContent = t('cfg.footer', { n: d.total });
        el('configTable').querySelectorAll('button[data-edit]').forEach(function (b) {
          b.addEventListener('click', function () { openEditor(Number(b.getAttribute('data-edit'))); });
        });
      }).catch(fail);
  }

  function openEditor(itemId) {
    api('GET', '/api/config-items/' + itemId).then(function (d) {
      state.editorItem = d;
      var item = d.item, rules = d.rules;
      el('editTitle').textContent = t('edit.title') + ' · ' + item.field_key;
      el('editMeta').innerHTML = '<div class="kv-grid">' +
        kv(t('dev.col.id'), mono(item.device_id)) + kv(t('mod.field'), esc(pick(item.label, item.label_en))) +
        kv(t('cfg.col.page'), mono((item.page || '') + ':' + (item.byte_offset || ''))) +
        kv(t('mod.section'), esc(sectionLabel(item.section))) +
        kv(t('mod.spec'), esc(item.spec_ref || '')) + kv(t('common.version'), esc(item.version)) + '</div>';
      el('editTypeHint').textContent = '[' + esc(item.data_type) + (item.unit ? ' · ' + esc(item.unit) : '') + ']';
      el('editValue').value = item.value === null ? '' : item.value;
      el('editNote').value = '';
      el('editReport').innerHTML = '';
      el('editStatus').textContent = item.writable ? t('edit.status') : t('mod.readOnly');
      var ruleText = [
        'access=' + (item.writable ? 'RW' : 'RO'),
        'allowed_values=' + JSON.stringify(rules.allowed_values || []),
        'range=[' + rules.min_value + ', ' + rules.max_value + ']'
      ];
      if (rules.cross_rule) ruleText.push('cross_rule=' + rules.cross_rule);
      if (d.field && d.field.confidence !== 'confirmed') ruleText.push('confidence=' + d.field.confidence);
      el('editRules').textContent = ruleText.join(' · ');
      openModal();
    }).catch(fail);
  }
  function openModal() {
    el('editModal').classList.add('show');
    el('editModal').style.display = 'block';
    el('modalBackdrop').hidden = false;
  }
  function closeModal() {
    el('editModal').classList.remove('show');
    el('editModal').style.display = 'none';
    el('modalBackdrop').hidden = true;
  }
  function reportHtml(report) {
    var rows = (report.checks || []).map(function (c) {
      return '<div class="check-row"><span class="' + (c.status === 'pass' ? 'ok' : 'no') + '">' +
        (c.status === 'pass' ? '✓' : '✗') + '</span><span>' + esc(c.rule) + ': ' + esc(c.detail) + '</span></div>';
    }).join('');
    var warns = (report.warnings || []).map(function (w) {
      return '<div class="check-row"><span class="no">!</span><span>' + esc(w.code) + ': ' + esc(w.message) + '</span></div>';
    }).join('');
    return '<div class="report-box ' + (report.valid ? 'pass' : 'fail') + '">' +
      '<strong>' + esc(report.valid ? t('common.pass') : t('common.fail')) + '</strong>' + rows + warns + '</div>';
  }
  function editPayload() {
    var item = state.editorItem.item;
    return {
      value: el('editValue').value,
      expected_version: item.version,
      operator: 'local-admin',
      note: el('editNote').value
    };
  }

  // --------------------------------------------------------------- knowledge graph
  function loadGraph() {
    Promise.all([api('GET', '/api/kg/stats'), api('GET', '/api/kg/entities?limit=300'), api('GET', '/api/kg/graph?limit=220')])
      .then(function (res) {
        var stats = res[0], list = res[1], graph = res[2];
        var types = Object.keys(stats.entities_by_type || {});
        el('kgType').innerHTML = '<option value="">' + esc(t('graph.allTypes')) + '</option>' +
          types.map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + '</option>'; }).join('');
        renderKgList(list.items, el('kgFilter').value, el('kgType').value);
        renderKgGraph(graph);
        if (state.selectedKg) showKgEntity(state.selectedKg);
      }).catch(fail);
  }
  function renderKgList(items, filter, type) {
    var f = (filter || '').toLowerCase();
    var shown = items.filter(function (x) {
      return (!type || x.type === type) && (!f || (L(x.name) + ' ' + L(xsummarySafe(x))).toLowerCase().indexOf(f) >= 0);
    });
    el('kgEntityList').innerHTML = shown.length ? shown.map(function (x) {
      return '<div class="kg-item' + (x.entity_id === state.selectedKg ? ' active' : '') +
        '" data-kg="' + esc(x.entity_id) + '"><div class="kg-name">' + esc(L(x.name)) +
        '</div><div class="kg-meta">' + esc(x.type) + ' · ' + confBadge(x.confidence) + '</div></div>';
    }).join('') : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';
    el('kgEntityList').querySelectorAll('[data-kg]').forEach(function (n) {
      n.addEventListener('click', function () { showKgEntity(n.getAttribute('data-kg')); });
    });
  }
  function xsummarySafe(x) { return x.summary || ''; }
  function showKgEntity(id) {
    state.selectedKg = id;
    api('GET', '/api/kg/entity/' + encodeURIComponent(id)).then(function (d) {
      var e = d.entity || d;
      el('kgDetailTitle').textContent = L(e.name || id);
      el('kgDetailType').textContent = e.type || '';
      var src = (e.source_ids || []).map(function (s) { return badge(s, 'blue'); }).join(' ');
      var rels = (d.outgoing || []).map(function (r) {
        return '<div class="rel-item">' + badge(r.type, 'purple') + ' → <a data-kg="' +
          esc(r.dst || '') + '">' + esc(L(r.neighbor_name || r.dst || '')) + '</a> ' +
          esc(L(r.label || '')) + '</div>';
      }).join('');
      var ins = (d.incoming || []).map(function (r) {
        return '<div class="rel-item">' + badge(r.type, 'secondary') + ' ← ' +
          esc(L(r.neighbor_name || r.src || '')) + '</div>';
      }).join('');
      el('kgDetailBody').innerHTML = '<div class="mb-2 muted">' + esc(L(xsummarySafe(e))) + '</div>' +
        '<div class="mb-2">' + confBadge(e.confidence) + ' ' + src + '</div>' +
        '<h4>' + esc(t('kg.outgoing')) + '</h4><div class="rel-list">' + (rels || t('common.noData')) + '</div>' +
        '<h4 class="mt-3">' + esc(t('kg.incoming')) + '</h4><div class="rel-list">' + (ins || t('common.noData')) + '</div>' +
        '<h4 class="mt-3">' + esc(t('kg.attributes')) + '</h4><pre class="mono">' +
        esc(JSON.stringify(LJson(e.attrs || {}), null, 2)) + '</pre>';
      el('kgDetailBody').querySelectorAll('[data-kg]').forEach(function (a) {
        a.addEventListener('click', function () { if (a.getAttribute('data-kg')) showKgEntity(a.getAttribute('data-kg')); });
      });
      el('kgEntityList').querySelectorAll('[data-kg]').forEach(function (n) {
        n.classList.toggle('active', n.getAttribute('data-kg') === id);
      });
    }).catch(fail);
  }
  function renderKgGraph(graph) {
    var nodes = graph.nodes || [], edges = graph.edges || [];
    if (!nodes.length) { el('kgGraph').innerHTML = '<div class="empty-hint">' + esc(t('common.noData')) + '</div>'; return; }
    var colors = ['#3b82f6', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899'];
    var types = Array.from(new Set(nodes.map(function (n) { return n.type; })));
    var colorOf = function (ty) { return colors[types.indexOf(ty) % colors.length]; };
    var w = 760, h = 360, cx = w / 2, cy = h / 2;
    var pos = {};
    nodes.forEach(function (n, i) {
      var ring = Math.floor(i / 26) + 1;
      var angle = (i % 26) / 26 * Math.PI * 2;
      var radius = 60 + ring * 62;
      pos[n.entity_id] = { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius * 0.62 };
    });
    var lines = edges.map(function (e) {
      var a = pos[e.src], b = pos[e.dst];
      if (!a || !b) return '';
      return '<line class="edge" x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '"/>';
    }).join('');
    var circles = nodes.map(function (n) {
      var p = pos[n.entity_id];
      return '<circle class="node-circle" data-kg="' + esc(n.entity_id) + '" cx="' + p.x + '" cy="' + p.y +
        '" r="7" fill="' + colorOf(n.type) + '"/><text class="node-label" x="' + (p.x + 9) + '" y="' +
        (p.y + 3) + '">' + esc(L(String(n.name || n.entity_id)).slice(0, 16)) + '</text>';
    }).join('');
    el('kgGraph').innerHTML = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="360">' +
      lines + circles + '</svg>';
    el('kgGraph').querySelectorAll('[data-kg]').forEach(function (c) {
      c.addEventListener('click', function () { showKgEntity(c.getAttribute('data-kg')); });
    });
  }

  // --------------------------------------------------------------- sources / about / search
  function loadSources() {
    Promise.all([api('GET', '/api/kg/sources/coverage'), api('GET', '/api/kg/pending'), api('GET', '/api/kg/sources')])
      .then(function (res) {
        var coverage = res[0].sources || res[0].items || [], pending = res[1].items || [], sources = res[2].items || [];
        var cov = {};
        coverage.forEach(function (c) { cov[c.source_id] = c; });
        el('sourceTable').querySelector('tbody').innerHTML = sources.map(function (s) {
          var c = cov[s.source_id] || {};
          return '<tr><td>' + mono(s.source_id) + '</td><td>' + esc(L(s.title)) + '</td><td>' +
            esc(L(s.publisher || '')) + '</td><td>' + esc(s.kind || '') + '</td><td>' + esc(L(s.license || '')) +
            '</td><td>' + esc((c.entities || c.entity_count || 0) + ' / ' + (c.relations || c.relation_count || 0)) +
            '</td><td>' + (s.url ? '<a class="source-link" href="' + esc(s.url) + '" target="_blank" rel="noopener">' +
            esc(t('common.link')) + '</a>' : '-') + '</td></tr>';
        }).join('');
        el('sourceCount').textContent = t('common.total', { n: sources.length });
        el('pendingCount').textContent = pending.length;
        el('pendingList').innerHTML = pending.length ? pending.map(function (p) {
          return '<div class="rel-item mb-2">' + badge(esc(p.pending_id), 'orange') + ' ' +
            '<strong>' + esc(L(p.topic)) + '</strong><div class="muted small">' + esc(L(p.question)) +
            '</div><div class="muted small">' + esc(L(p.impact || '')) + '</div></div>';
        }).join('') : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';
      }).catch(fail);
  }
  function loadAbout() {
    Promise.all([api('GET', '/api/meta'), api('GET', '/api/access'), api('GET', '/api/sections')])
      .then(function (res) {
        state.meta = res[0];
        state.sections = res[2].items;
        var svc = res[0].service || {};
        el('aboutBody').innerHTML = '<div class="kv-grid mb-3">' +
          kv(t('common.project'), badge('CMIScope', 'blue')) + kv(t('common.tagline'), esc(res[0].project.tagline)) +
          kv(t('side.access'), esc(svc.access_mode || 'mirror')) +
          kv(t('side.mode'), badge(svc.read_only ? 'read-only' : 'read/write', 'green')) +
          kv(t('common.language'), esc(I18N.getLang() === 'zh' ? t('about.languageZh') : t('about.languageEn'))) +
          kv(t('common.dependencies'), esc('Python stdlib + SQLite')) + '</div>' +
          '<div class="small muted mb-2">' + esc(t('common.cmisRefs')) + (res[0].cmis_specs || []).map(function (r) {
            return r.doc + ' (' + r.date + ')';
          }).join(', ') + '</div>' +
          '<div class="small muted">' + esc(t('about.frameworkNote')) + '</div>';
        el('accessBody').innerHTML = (res[1].modes || []).map(function (m) {
          var active = m.key === (res[1].active || {}).mode;
          return '<div class="rel-item mb-2">' + (active ? badge(t('common.active'), 'green') : badge(m.key, 'secondary')) +
            ' <strong>' + esc(pick(m.zh, m.en)) + '</strong><div class="muted small">' + esc(m.topology) +
            '</div><div class="muted small">' + esc(t('mod.writePolicy')) + ': ' + esc(m.writes) +
            ' · risk: ' + esc(m.risk) + '</div></div>';
        }).join('');
        el('apiList').innerHTML = (res[0].endpoints || []).map(function (e) {
          return '<div>' + esc(e) + '</div>';
        }).join('');
      }).catch(fail);
  }
  function doSearch(term, scope) {
    api('GET', '/api/search?q=' + encodeURIComponent(term) + '&scope=' + encodeURIComponent(scope))
      .then(function (d) {
        el('searchSummary').textContent = t('common.total', { n: d.total });
        var parts = [];
        Object.keys(d.groups || {}).forEach(function (key) {
          var rows = d.groups[key] || [];
          if (!rows.length) return;
          parts.push('<h4>' + esc(groupLabel(key)) + ' (' + rows.length + ')</h4><div class="table-responsive"><table class="table table-sm table-vcenter"><tbody>' +
            rows.slice(0, 12).map(function (r) {
              var label = r.device_id || r.field_key || r.entity_id || r.label || '';
              var sub = L(r.name || r.title || r.label || r.description || '');
              return '<tr><td>' + mono(label) + '</td><td>' + esc(String(sub).slice(0, 110)) + '</td></tr>';
            }).join('') + '</tbody></table></div>');
        });
        el('searchResult').innerHTML = parts.length ? parts.join('') : '<div class="empty-hint">' + esc(t('common.noData')) + '</div>';
        setView('search', true);
      }).catch(fail);
  }

  // --------------------------------------------------------------- bootstrap
  function fillDeviceSelects() {
    api('GET', '/api/devices?limit=500').then(function (d) {
      var options = d.items.map(function (r) {
        return '<option value="' + esc(r.device_id) + '">' + esc(pick(r.name, r.name_en)) + ' · ' + esc(r.device_id) + '</option>';
      }).join('');
      var cfg = el('configDevice');
      var cfgValue = cfg.value;
      cfg.innerHTML = '<option value="">' + esc(t('cfg.allDevices')) + '</option>' + options;
      cfg.value = cfgValue;
      var mod = el('moduleDevice');
      var modValue = mod.value || state.selectedDevice || (d.items[0] || {}).device_id || '';
      mod.innerHTML = options;
      mod.value = modValue;
      state.selectedDevice = mod.value;
    }).catch(fail);
  }
  function fillSectionSelect() {
    if (!state.sections) {
      api('GET', '/api/sections').then(function (d) {
        state.sections = d.items;
        fillSectionSelect();
      }).catch(fail);
      return;
    }
    var sel = el('configSection');
    var value = sel.value;
    sel.innerHTML = '<option value="">' + esc(t('mod.allSections')) + '</option>' +
      state.sections.map(function (s) {
        return '<option value="' + esc(s.key) + '">' + esc(pick(s.zh, s.en)) + '</option>';
      }).join('');
    sel.value = value;
  }

  // --------------------------------------------------------------- access targets
  // The registry is edited in the browser but persisted as a plain JSON file
  // by PUT /api/targets, so the same configuration can be edited in a terminal.
  var tg = { version: 1, active_target: '', targets: [], editIndex: -1 };

  // ssh + i2c and restful API are strictly mutually exclusive. A target only
  // ever renders, reads and submits the fields of its selected mode.
  var TG_MODE_KEYS = {
    'mirror': [],
    'ssh-i2c': ['ssh_user', 'i2c_bus', 'i2c_addr'],
    'rest-api': ['rest_scheme', 'rest_base_path', 'token_env']
  };
  var TG_ALL_MODE_KEYS = ['ssh_user', 'i2c_bus', 'i2c_addr',
                          'rest_scheme', 'rest_base_path', 'token_env'];

  function syncTargetModeFields() {
    var mode = el('tgAccessMode').value;
    document.querySelectorAll('#tgFormFields [data-tg-modes]').forEach(function (box) {
      box.hidden = box.getAttribute('data-tg-modes').split(' ').indexOf(mode) < 0;
    });
    el('tgModeHint').textContent = t('tg.modeHint') + ' ' + targetModeLabel(mode) +
      ' — ' + t('tg.modeOnly');
  }

  function loadTargets() {
    api('GET', '/api/targets').then(function (d) {
      tg.version = d.version;
      tg.active_target = d.active_target || '';
      tg.targets = (d.targets || []).map(function (x) { return Object.assign({}, x); });
      el('tgNote').textContent = t('tg.note');
      el('tgFile').textContent = d.file || '';
      renderTargets();
    }).catch(fail);
  }

  function targetModeLabel(mode) {
    if (mode === 'ssh-i2c') return 'ssh + i2c';
    if (mode === 'rest-api') return 'restful API';
    return 'mirror';
  }

  // The list view also shows only the selected mode's parameters.
  function targetParams(x) {
    if (x.access_mode === 'ssh-i2c') {
      return 'ssh ' + (x.ssh_user || '-') + ' · bus ' + (x.i2c_bus || '-') +
        ' · addr ' + (x.i2c_addr || '-');
    }
    if (x.access_mode === 'rest-api') {
      return (x.rest_scheme || 'https') + ' ' + (x.rest_base_path || '-') +
        ' · ' + (x.token_env || '-');
    }
    return t('tg.offlineOnly');
  }

  function renderTargets() {
    el('tgActive').innerHTML = tg.targets.map(function (x) {
      return '<option value="' + esc(x.device_id) + '">' + esc(x.device_id) +
        ' - ' + esc(targetModeLabel(x.access_mode)) + '</option>';
    }).join('');
    el('tgActive').value = tg.active_target || '';
    el('tgRows').innerHTML = tg.targets.length ? tg.targets.map(function (x, i) {
      var isActive = x.device_id === tg.active_target;
      return '<tr>' +
        '<td class="mono">' + esc(x.device_id) + (isActive ? ' ' + badge(t('tg.setActive'), 'green') : '') + '</td>' +
        '<td>' + esc(x.name) + '</td>' +
        '<td>' + badge(targetModeLabel(x.access_mode), x.access_mode === 'mirror' ? 'secondary' : 'blue') +
        '<div class="small text-secondary mono mt-1">' + esc(targetParams(x)) + '</div></td>' +
        '<td class="mono">' + esc(x.host || '-') + '</td>' +
        '<td class="mono">' + esc(x.port || '-') + '</td>' +
        '<td>' + (x.enabled ? '&#10003;' : '-') + '</td>' +
        '<td class="text-end"><div class="btn-list flex-nowrap justify-content-end">' +
        '<button class="btn btn-sm btn-outline-primary tg-edit" data-i="' + i + '">' + esc(t('tg.edit')) + '</button>' +
        '<button class="btn btn-sm btn-outline-secondary tg-probe" data-i="' + i + '">' + esc(t('tg.probeRow')) + '</button>' +
        '<button class="btn btn-sm btn-outline-danger tg-del" data-i="' + i + '">' + esc(t('tg.del')) + '</button>' +
        '</div></td></tr>';
    }).join('') : '<tr><td colspan="7" class="text-secondary">-</td></tr>';

    el('tgRows').querySelectorAll('.tg-edit').forEach(function (b) {
      b.addEventListener('click', function () { openTargetEditor(parseInt(b.getAttribute('data-i'), 10)); });
    });
    el('tgRows').querySelectorAll('.tg-probe').forEach(function (b) {
      b.addEventListener('click', function () {
        var i = parseInt(b.getAttribute('data-i'), 10);
        probeTargetById(tg.targets[i].device_id);
      });
    });
    el('tgRows').querySelectorAll('.tg-del').forEach(function (b) {
      b.addEventListener('click', function () {
        var i = parseInt(b.getAttribute('data-i'), 10);
        var removed = tg.targets.splice(i, 1)[0];
        if (removed && removed.device_id === tg.active_target) {
          tg.active_target = tg.targets.length ? tg.targets[0].device_id : '';
        }
        renderTargets();
      });
    });
  }

  function openTargetEditor(index) {
    tg.editIndex = index;
    var x = index >= 0 ? tg.targets[index] : {
      device_id: '', name: '', enabled: true, access_mode: 'mirror', host: '', port: 0,
      ssh_user: 'admin', i2c_bus: '0', i2c_addr: '0x50', rest_scheme: 'https',
      rest_base_path: '/api', token_env: 'CMIS_REST_TOKEN', module_ids: [], notes: ''
    };
    document.querySelectorAll('[data-tg]').forEach(function (input) {
      var k = input.getAttribute('data-tg');
      var v = x[k];
      if (k === 'module_ids') v = (v || []).join(', ');
      else if (k === 'enabled') v = v ? 'true' : 'false';
      input.value = (v === undefined || v === null || v === false) ? '' : v;
    });
    el('tgEditor').hidden = false;
    el('tgEditorTitle').textContent = t('tg.editor') + ' - ' + (x.device_id || t('tg.add'));
    syncTargetModeFields();
  }

  function applyTargetForm() {
    var mode = el('tgAccessMode').value;
    var obj = {};
    // Only the visible (selected-mode) inputs are read. Hidden fields of the
    // other transport are never part of the payload.
    document.querySelectorAll('#tgFormFields [data-tg]').forEach(function (input) {
      var box = input.closest('[data-tg-modes]');
      if (box && box.hidden) return;
      obj[input.getAttribute('data-tg')] = String(input.value).trim();
    });
    // Defence in depth: drop every key owned by an unselected mode.
    TG_ALL_MODE_KEYS.forEach(function (k) {
      if (TG_MODE_KEYS[mode].indexOf(k) < 0) delete obj[k];
    });
    obj.access_mode = mode;
    if (!obj.device_id) { toast(t('tg.deviceIdRequired'), 'err'); return; }
    obj.port = parseInt(obj.port || '0', 10) || 0;
    obj.enabled = obj.enabled === 'true';
    obj.module_ids = String(obj.module_ids || '').split(',')
      .map(function (v) { return v.trim(); }).filter(Boolean);
    if (tg.editIndex >= 0) tg.targets[tg.editIndex] = obj;
    else tg.targets.push(obj);
    if (!tg.active_target) tg.active_target = obj.device_id;
    tg.editIndex = -1;
    el('tgEditor').hidden = true;
    renderTargets();
    toast(t('tg.added'), 'ok');
  }

  function saveTargets() {
    api('PUT', '/api/targets', {
      version: tg.version,
      active_target: el('tgActive').value || tg.active_target,
      targets: tg.targets
    }).then(function (d) {
      tg.version = d.version;
      tg.active_target = d.active_target || '';
      tg.targets = (d.targets || []).slice();
      renderTargets();
      toast(t('tg.saved'), 'ok');
    }).catch(function (err) {
      var extra = (err.details && err.details.errors)
        ? ' - ' + err.details.errors.slice(0, 3).join('; ') : '';
      toast((err.message || '') + extra, 'err');
    });
  }

  function probeTargetById(deviceId) {
    api('POST', '/api/targets/probe', { device_id: deviceId || '' }).then(function (d) {
      el('tgProbeResult').hidden = false;
      el('tgProbeResult').innerHTML = '<div class="report-box"><strong>' +
        esc(d.access_mode) + '</strong> - ' + esc(d.device_id || 'global') +
        '<pre class="mono mt-2">' + esc(JSON.stringify(d.probe, null, 2)) + '</pre></div>';
    }).catch(function (err) {
      el('tgProbeResult').hidden = false;
      el('tgProbeResult').innerHTML = '<div class="report-box fail">' +
        esc(t('tg.probeFail')) + ': ' + esc(err.message) + '</div>';
    });
  }

  function bind() {
    document.querySelectorAll('[data-view]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        setView(a.getAttribute('data-view'));
      });
    });
    el('globalSearch').addEventListener('submit', function (e) {
      e.preventDefault();
      var term = el('searchInput').value.trim();
      if (term) doSearch(term, el('searchScope').value);
    });
    el('langToggle').addEventListener('click', function () {
      I18N.setLang(I18N.getLang() === 'zh' ? 'en' : 'zh');
    });
    el('deviceFilter').addEventListener('input', loadDevices);
    el('deviceStatus').addEventListener('change', loadDevices);
    el('closeDeviceDetail').addEventListener('click', function () { el('deviceDetailCard').hidden = true; });
    ['configFilter', 'configDevice', 'configSection', 'configWritable'].forEach(function (id) {
      el(id).addEventListener(id === 'configFilter' ? 'input' : 'change', loadConfig);
    });
    el('configReset').addEventListener('click', function () {
      el('configFilter').value = ''; el('configDevice').value = '';
      el('configSection').value = ''; el('configWritable').value = '';
      loadConfig();
    });
    el('moduleDevice').addEventListener('change', function () {
      state.selectedDevice = el('moduleDevice').value;
      loadModule();
    });
    el('moduleSection').addEventListener('change', loadModule);
    el('kgFilter').addEventListener('input', function () {
      api('GET', '/api/kg/entities?limit=300').then(function (d) {
        renderKgList(d.items, el('kgFilter').value, el('kgType').value);
      }).catch(fail);
    });
    el('kgType').addEventListener('change', function () {
      api('GET', '/api/kg/entities?limit=300').then(function (d) {
        renderKgList(d.items, el('kgFilter').value, el('kgType').value);
      }).catch(fail);
    });
    el('editClose').addEventListener('click', closeModal);
    el('modalBackdrop').addEventListener('click', closeModal);
    el('editValidate').addEventListener('click', function () {
      if (!state.editorItem) return;
      api('POST', '/api/config-items/' + state.editorItem.item.id + '/validate',
        { value: el('editValue').value }).then(function (d) {
          el('editReport').innerHTML = reportHtml(d.report);
          el('editStatus').textContent = d.report.valid ? t('common.pass') : t('common.fail');
        }).catch(fail);
    });
    el('editSave').addEventListener('click', function () {
      if (!state.editorItem) return;
      api('PUT', '/api/config-items/' + state.editorItem.item.id, editPayload()).then(function (d) {
        el('editReport').innerHTML = reportHtml(d.validation) +
          '<div class="diff-box mt-2">' + mono(d.diff.before.value) + ' → ' + mono(d.diff.after.value) +
          ' ' + badge(esc(d.result), d.applied_to_hardware ? 'green' : 'blue') + '</div>';
        el('editStatus').textContent = d.message;
        toast(d.message, 'ok');
        state.editorItem.item.version = d.diff.after.version;
        state.editorItem.item.value = d.diff.after.value;
        renderCurrent();
      }).catch(function (err) {
        el('editReport').innerHTML = '<div class="report-box fail">' + esc(err.message) +
          (err.details ? '<pre class="mono">' + esc(JSON.stringify(err.details, null, 2)) + '</pre>' : '') + '</div>';
        fail(err);
      });
    });
    el('tgAccessMode').addEventListener('change', syncTargetModeFields);
    el('tgAdd').addEventListener('click', function () { openTargetEditor(-1); });
    el('tgSave').addEventListener('click', saveTargets);
    el('tgApply').addEventListener('click', applyTargetForm);
    el('tgCancel').addEventListener('click', function () {
      el('tgEditor').hidden = true; tg.editIndex = -1;
    });
    el('tgProbe').addEventListener('click', function () {
      probeTargetById(el('tgActive').value);
    });
    el('tgActive').addEventListener('change', function () {
      tg.active_target = el('tgActive').value;
    });
    window.addEventListener('hashchange', function () {
      var name = (location.hash || '#overview').slice(1);
      if (VIEW_TITLE[name] && name !== state.view) setView(name, true);
    });
  }

  window.onLanguageChange = function () {
    state.lang = I18N.getLang();
    el('langToggle').textContent = I18N.getLang() === 'zh' ? 'EN' : 'ZH';
    fillDeviceSelects();
    fillSectionSelect();
    renderCurrent();
  };

  function init() {
    I18N.init('zh');
    state.lang = I18N.getLang();
    bind();
    el('langToggle').textContent = I18N.getLang() === 'zh' ? 'EN' : 'ZH';
    api('GET', '/api/health').then(function () {
      el('healthDot').classList.add('up');
      el('healthText').textContent = t('status.up');
    }).catch(function () {
      el('healthDot').classList.add('down');
      el('healthText').textContent = t('status.down');
    });
    api('GET', '/api/sections').then(function (d) { state.sections = d.items; fillSectionSelect(); }).catch(fail);
    api('GET', '/api/meta').then(function (d) {
      var svc = d.service || {};
      el('sideMode').textContent = (svc.read_only ? 'read-only' : 'read/write') +
        ' - ' + (svc.access_mode || 'mirror');
    }).catch(function () { el('sideMode').textContent = t('common.unknown'); });
    fillDeviceSelects();
    var hash = (location.hash || '').slice(1);
    setView(VIEW_TITLE[hash] ? hash : 'overview', true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
