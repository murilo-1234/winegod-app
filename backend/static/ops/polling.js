/* winegod data ops - polling simples 10s. Sem WebSocket. */
(function(){
  const OpsPoll = {
    _timer: null,
    _abort: null,
    start: function(opts){
      const endpoints = opts.endpoints || [];
      const intervalMs = opts.intervalMs || 10000;
      const run = async () => {
        for (const ep of endpoints) {
          try {
            const resp = await fetch(ep.url, { credentials: 'same-origin', cache: 'no-store' });
            if (resp.status === 401 || resp.status === 403) {
              window.location.href = '/ops/login';
              return;
            }
            if (!resp.ok) {
              console.warn('poll err', ep.url, resp.status);
              continue;
            }
            const data = await resp.json();
            if (ep.handler) ep.handler(data);
          } catch (e) {
            console.warn('poll fetch err', e);
          }
        }
      };
      run();
      this._timer = setInterval(run, intervalMs);
    },
    stop: function(){ if (this._timer) { clearInterval(this._timer); this._timer = null; } },

    // ----- Renderers -----
    renderSummary: function(data){
      if (!data) return;
      const setText = (id, v) => {
        const el = document.getElementById(id); if (el) el.textContent = v;
      };
      setText('card-ativos', data.scrapers_ativos_agora ?? '0');
      setText('card-observado', (data.observado_hoje ?? 0).toLocaleString('pt-BR'));
      setText('card-enviado', (data.enviado_hoje ?? 0).toLocaleString('pt-BR'));
      setText('card-sla', (data.sla_health_pct ?? 0) + '%');
    },

    renderScrapersTable: function(data){
      const tbody = document.getElementById('home-tbody');
      if (!tbody) return;
      const items = (data && data.items) || [];
      if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="ops-empty">nenhum scraper cadastrado ainda</td></tr>';
        return;
      }
      tbody.innerHTML = items.map(it => {
        const dotCls = (it.last_run_status === 'failed' || it.last_run_status === 'timeout') ? 'red'
                     : (it.last_run_status === 'running' || it.last_run_status === 'started') ? 'green'
                     : (it.last_run_status === 'success') ? 'gray' : 'gray';
        const familyCls = 'ops-badge family ' + (it.family || '');
        const freshCls = 'ops-freshness ' + (it.freshness || 'never');
        const lastEnd = it.last_ended ? new Date(it.last_ended).toLocaleString('pt-BR') : '—';
        const url = '/ops/scraper/' + encodeURIComponent(it.scraper_id);
        return `<tr>
          <td><span class="ops-dot ${dotCls}"></span></td>
          <td><a href="${url}"><strong>${escapeHtml(it.scraper_id)}</strong></a></td>
          <td><span class="${familyCls}">${escapeHtml(it.family || '')}</span></td>
          <td><span class="ops-pc-tag">${escapeHtml(it.host || '')}</span></td>
          <td>${escapeHtml(it.status || '')}</td>
          <td>${lastEnd}</td>
          <td>${(it.observado_hoje ?? 0).toLocaleString('pt-BR')}</td>
          <td>${(it.enviado_hoje ?? 0).toLocaleString('pt-BR')}</td>
          <td><span class="${freshCls}">${it.freshness || 'never'}</span></td>
        </tr>`;
      }).join('');
    },

    renderScraperDetail: function(data){
      if (!data || data.error) {
        document.getElementById('detail-sub').textContent = 'erro: ' + ((data && data.error) || 'desconhecido');
        return;
      }
      const id = data.identity || {};
      const sub = document.getElementById('detail-sub');
      if (sub) sub.textContent = (id.display_name || id.scraper_id || '') + ' · ' + (id.family || '') + ' · ' + (id.host || '');

      // Identidade
      const secId = document.getElementById('sec-identity');
      if (secId) {
        secId.innerHTML = `<dl class="ops-kv">
          <dt>scraper_id</dt><dd><code class="ops-code">${escapeHtml(id.scraper_id || '')}</code></dd>
          <dt>display</dt><dd>${escapeHtml(id.display_name || '')}</dd>
          <dt>family</dt><dd>${escapeHtml(id.family || '')}</dd>
          <dt>source</dt><dd>${escapeHtml(id.source || '')}</dd>
          <dt>variant</dt><dd>${escapeHtml(id.variant || '—')}</dd>
          <dt>host</dt><dd><span class="ops-pc-tag">${escapeHtml(id.host || '')}</span></dd>
          <dt>contract</dt><dd><code class="ops-code">${escapeHtml(id.contract_name || '')} / ${escapeHtml(id.contract_version || '')}</code></dd>
          <dt>status</dt><dd>${escapeHtml(id.status || '')}</dd>
          <dt>SLA freshness</dt><dd>${id.freshness_sla_hours || 0} h</dd>
          <dt>can_create_wine_sources</dt><dd>${id.can_create_wine_sources ? 'true' : 'false'}</dd>
          <dt>requires_dq_v3</dt><dd>${id.requires_dq_v3 ? 'true' : 'false'}</dd>
          <dt>requires_matching</dt><dd>${id.requires_matching ? 'true' : 'false'}</dd>
          <dt>declared_fields</dt><dd>${(id.declared_fields || []).map(f=>`<code class="ops-code">${escapeHtml(f)}</code>`).join(' ') || '—'}</dd>
        </dl>`;
      }

      // Saude
      const lr = data.last_run;
      if (lr) {
        const hbEl = document.getElementById('hb-age');
        if (hbEl) {
          if (lr.last_heartbeat_at) {
            const age = Math.round((Date.now() - new Date(lr.last_heartbeat_at).getTime()) / 1000);
            hbEl.textContent = (age < 60) ? (age + 's') : (Math.round(age/60) + 'm');
          } else hbEl.textContent = '—';
        }
        const lastRate = (data.speed && data.speed.length) ? (data.speed[data.speed.length-1].items_per_minute ?? '—') : '—';
        setText('hb-rate', lastRate == null ? '—' : Math.round(lastRate) + '/min');
        setText('hb-dur', lr.duration_ms ? (Math.round(lr.duration_ms/1000) + 's') : '—');
        setText('hb-err', ((lr.error_count_transient || 0) + (lr.error_count_fatal || 0)).toString());
      } else {
        setText('hb-age', '—'); setText('hb-rate', '—'); setText('hb-dur', '—'); setText('hb-err', '0');
      }

      // Funil
      const f = data.funnel;
      const funnelEl = document.getElementById('sec-funnel');
      if (funnelEl) {
        if (!f || f.extracted === 0) {
          funnelEl.innerHTML = '<div class="ops-empty">nenhum batch ainda</div>';
        } else {
          const base = Math.max(f.extracted, 1);
          const rows = [
            ['Extraido', f.extracted, ''],
            ['Valido local', f.valid_local, ''],
            ['Enviado', f.sent, ''],
            ['Aceito (ready)', f.accepted_ready, ''],
            ['Rejeitado NOT_WINE', f.rejected_notwine, 'notwine'],
            ['Needs enrichment', f.needs_enrichment, ''],
            ['Uncertain', f.uncertain, ''],
            ['Duplicado', f.duplicate, 'dup'],
            ['Final inserted (MVP=0)', f.final_inserted, 'inserted'],
          ];
          funnelEl.innerHTML = rows.map(r => {
            const pct = Math.round(100 * (r[1] || 0) / base);
            return `<div class="ops-funnel-row">
              <div class="ops-funnel-label">${r[0]}</div>
              <div class="ops-funnel-bar ${r[2]}"><div class="fill" style="width:${pct}%"></div></div>
              <div class="ops-funnel-num">${(r[1]||0).toLocaleString('pt-BR')} (${pct}%)</div>
            </div>`;
          }).join('');
        }
      }

      // Velocidade
      const speedEl = document.getElementById('sec-speed');
      if (speedEl) {
        const s = data.speed || [];
        if (!s.length) speedEl.innerHTML = '<div class="ops-empty">sem heartbeats no ultimo run</div>';
        else speedEl.innerHTML = `<div>${s.length} heartbeats capturados. Ultimo: ${new Date(s[s.length-1].ts).toLocaleTimeString('pt-BR')}.</div>`;
      }

      // Campos declarados
      const fcEl = document.getElementById('sec-fields');
      if (fcEl) {
        const fc = data.field_coverage || {};
        const keys = Object.keys(fc);
        if (!keys.length) fcEl.innerHTML = '<div class="ops-empty">sem dados de coverage</div>';
        else {
          fcEl.innerHTML = `<table class="ops-table"><thead><tr><th>Campo</th><th>Coverage atual</th></tr></thead><tbody>${
            keys.map(k => `<tr><td>${escapeHtml(k)}</td><td>${Math.round((fc[k]||0)*100)}%</td></tr>`).join('')
          }</tbody></table>`;
        }
      }

      // Dedup
      const ddEl = document.getElementById('sec-dedup');
      if (ddEl) {
        const d = data.dedup || {intra:0, cross_run:0, cross_scraper:0};
        ddEl.innerHTML = `<dl class="ops-kv">
          <dt>Intra-run</dt><dd>${(d.intra||0).toLocaleString('pt-BR')}</dd>
          <dt>Cross-run</dt><dd>${(d.cross_run||0).toLocaleString('pt-BR')}</dd>
          <dt>Cross-scraper (informativo)</dt><dd>${(d.cross_scraper||0).toLocaleString('pt-BR')}</dd>
        </dl>`;
      }

      // Historico
      const hEl = document.getElementById('sec-history');
      if (hEl) {
        const h = data.history || [];
        if (!h.length) hEl.innerHTML = '<div class="ops-empty">sem runs</div>';
        else {
          hEl.innerHTML = `<table class="ops-table"><thead><tr>
            <th>run_id</th><th>inicio</th><th>duracao</th><th>observado</th><th>enviado</th><th>status</th>
          </tr></thead><tbody>${
            h.map(r => `<tr>
              <td><code class="ops-code">${escapeHtml(r.run_id.substring(0,8))}…</code></td>
              <td>${r.started_at ? new Date(r.started_at).toLocaleString('pt-BR') : '—'}</td>
              <td>${r.duration_ms ? Math.round(r.duration_ms/1000)+'s' : '—'}</td>
              <td>${(r.items_extracted||0).toLocaleString('pt-BR')}</td>
              <td>${(r.items_sent||0).toLocaleString('pt-BR')}</td>
              <td>${escapeHtml(r.status||'')}</td>
            </tr>`).join('')
          }</tbody></table>`;
        }
      }

      // Eventos + alertas
      const evEl = document.getElementById('sec-events');
      if (evEl) {
        const ev = data.events_24h || [];
        const al = data.open_alerts || [];
        if (!ev.length && !al.length) {
          evEl.innerHTML = '<div class="ops-empty">sem erros ou alertas nas ultimas 24h</div>';
        } else {
          let html = '';
          if (al.length) {
            html += '<h3 style="color:#fca5a5;font-size:13px;margin-bottom:8px">Alertas abertos</h3>';
            html += al.map(a => `<div class="ops-err" style="margin-bottom:8px">[${a.priority}] ${escapeHtml(a.code)} · ${escapeHtml(a.title || '')} (${a.occurrences}x)</div>`).join('');
          }
          if (ev.length) {
            html += '<h3 style="color:#fbbf24;font-size:13px;margin-top:14px;margin-bottom:8px">Eventos 24h</h3>';
            html += ev.map(e => `<div style="margin-bottom:4px;font-size:12px">[${escapeHtml(e.level)}] ${e.ts ? new Date(e.ts).toLocaleTimeString('pt-BR') : '—'} · ${escapeHtml(e.code)}: ${escapeHtml(e.message || '')}</div>`).join('');
          }
          evEl.innerHTML = html;
        }
      }

      // 30d
      const o = data.observed_30d || {};
      setText('o-obs', (o.observado_30d || 0).toLocaleString('pt-BR'));
      setText('o-sent', (o.enviado_30d || 0).toLocaleString('pt-BR'));
      setText('o-runs', (o.runs_30d || 0).toLocaleString('pt-BR'));

      // Lineage
      const lnEl = document.getElementById('sec-lineage');
      if (lnEl) {
        const ln = data.lineage || [];
        if (!ln.length) lnEl.innerHTML = '<div class="ops-empty">sem lineage registrado</div>';
        else {
          lnEl.innerHTML = `<table class="ops-table"><thead><tr>
            <th>seq</th><th>source_system</th><th>source_kind</th><th>source_pointer</th><th>records</th>
          </tr></thead><tbody>${
            ln.map(l => `<tr>
              <td>${l.seq ?? '—'}</td>
              <td>${escapeHtml(l.source_system || '—')}</td>
              <td>${escapeHtml(l.source_kind || '—')}</td>
              <td><code class="ops-code">${escapeHtml(l.source_pointer || '—')}</code></td>
              <td>${l.source_record_count == null ? '—' : l.source_record_count.toLocaleString('pt-BR')}</td>
            </tr>`).join('')
          }</tbody></table>`;
        }
      }
    },

    renderAlertsTable: function(data){
      const tbody = document.getElementById('alerts-tbody');
      if (!tbody) return;
      const items = (data && data.items) || [];
      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="ops-empty">nenhum alerta registrado</td></tr>';
        return;
      }
      tbody.innerHTML = items.map(a => `<tr>
        <td><strong>${escapeHtml(a.priority)}</strong></td>
        <td>${escapeHtml(a.scraper_id || '(global)')}</td>
        <td><code class="ops-code">${escapeHtml(a.code)}</code></td>
        <td>${escapeHtml(a.title || '')}</td>
        <td>${a.occurrences || 1}</td>
        <td>${a.last_seen ? new Date(a.last_seen).toLocaleString('pt-BR') : '—'}</td>
        <td>${escapeHtml(a.status || '')}</td>
      </tr>`).join('');
    },
  };

  function escapeHtml(s){
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }
  function setText(id, v){
    const el = document.getElementById(id); if (el) el.textContent = v;
  }

  window.OpsPoll = OpsPoll;
})();
