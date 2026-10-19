// CleanMail Application Controller

const app = {
  currentFilter: 'all',
  currentSortBy: 'volume',
  currentSortOrder: 'desc',
  searchQuery: '',
  currentPage: 1,
  pageSize: 50,
  totalSenders: 0,
  totalMessages: 0,
  selectedSenderEmails: new Set(),
  activeSenderId: null,
  activeSenderEmail: null,
  isPollingIndexing: false,

  init() {
    this.setupDropzone();
    this.loadStats().then(() => {
      if (this.totalMessages > 0) {
        this.showMainView();
        this.loadSenders();
      } else {
        this.showUploadView();
      }
    });
    this.checkInitialIndexingStatus();
  },

  async checkInitialIndexingStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const status = await res.json();
        if (status.status === 'parsing' || status.status === 'indexing') {
          this._userInitiatedUpload = true;
          this.startStatusPolling();
        }
      }
    } catch (e) {
      console.error(e);
    }
  },

  showUploadView() {
    const uploadView = document.getElementById('uploadView');
    const mainView = document.getElementById('mainView');
    const cleanView = document.getElementById('cleanView');
    const cancelBtn = document.getElementById('cancelUploadBtn');
    if (uploadView) uploadView.style.display = 'flex';
    if (mainView) mainView.style.display = 'none';
    if (cleanView) cleanView.style.display = 'none';
    if (cancelBtn) {
      cancelBtn.style.display = this.totalMessages > 0 ? 'inline-block' : 'none';
    }
  },

  showMainView() {
    const uploadView = document.getElementById('uploadView');
    const mainView = document.getElementById('mainView');
    const cleanView = document.getElementById('cleanView');
    if (uploadView) uploadView.style.display = 'none';
    if (mainView) mainView.style.display = 'flex';
    if (cleanView) cleanView.style.display = 'none';
    const vizCont = document.getElementById('allSendersVizContainer');
    if (vizCont) {
      vizCont.style.display = this.currentFilter === 'all' ? 'grid' : 'none';
    }
    this.loadSenders();
    this.loadStats();
  },

  showCleanView(mode = 'ai') {
    const uploadView = document.getElementById('uploadView');
    const mainView = document.getElementById('mainView');
    const cleanView = document.getElementById('cleanView');
    if (uploadView) uploadView.style.display = 'none';
    if (mainView) mainView.style.display = 'none';
    if (cleanView) cleanView.style.display = 'flex';
    this.switchCleanMode(mode);
  },

  switchCleanMode(mode) {
    this.currentCleanMode = mode;
    const aiBtn = document.getElementById('cleanModeAiBtn');
    const filterBtn = document.getElementById('cleanModeFilterBtn');
    const aiContainer = document.getElementById('cleanAiModeContainer');
    const filterContainer = document.getElementById('cleanFilterModeContainer');
    const subtitle = document.getElementById('cleanModeSubtitle');

    if (mode === 'filter') {
      if (aiBtn) aiBtn.classList.remove('active');
      if (filterBtn) filterBtn.classList.add('active');
      if (aiContainer) aiContainer.style.display = 'none';
      if (filterContainer) filterContainer.style.display = 'flex';
      if (subtitle) subtitle.textContent = 'Rule-based multi-sender filtering, copy search query, and export filter files.';
      this.updatePoolButton();
      this.renderCleanFilterSelectedTable();
      this.generateFilterRules();
    } else {
      if (aiBtn) aiBtn.classList.add('active');
      if (filterBtn) filterBtn.classList.remove('active');
      if (aiContainer) aiContainer.style.display = 'flex';
      if (filterContainer) filterContainer.style.display = 'none';
      if (subtitle) subtitle.textContent = 'Local AI scans and categorizes emails per sender to build precision rules.';
      this.updatePoolButton();
      this.showAiCleanSenderList();
      this.loadAiCleanSenders();
    }
  },

  setFilter(filterType) {
    this.currentFilter = filterType;
    this.currentPage = 1;

    const btns = document.querySelectorAll('.segmented-btn');
    btns.forEach(btn => {
      if (btn.getAttribute('data-filter') === filterType) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    const vizCont = document.getElementById('allSendersVizContainer');
    if (vizCont) {
      vizCont.style.display = filterType === 'all' ? 'grid' : 'none';
    }

    this.loadSenders();
  },

  handleSearch(query) {
    this.searchQuery = query;
    this.currentPage = 1;
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.loadSenders();
    }, 250);
  },

  sortBy(column) {
    if (this.currentSortBy === column) {
      this.currentSortOrder = this.currentSortOrder === 'desc' ? 'asc' : 'desc';
    } else {
      this.currentSortBy = column;
      this.currentSortOrder = 'desc';
    }
    this.loadSenders();
  },

  async loadStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) return;
      const data = await res.json();
      this.totalMessages = data.total_messages || 0;
      const elMsg = document.getElementById('statTotalMessages');
      const elSenders = document.getElementById('statTotalSenders');
      const elJunk = document.getElementById('statJunkCandidates');
      const elDomains = document.getElementById('statTotalDomains');

      if (elMsg) elMsg.textContent = data.total_messages.toLocaleString();
      if (elSenders) elSenders.textContent = data.total_senders.toLocaleString();
      if (elJunk) elJunk.textContent = data.junk_candidates.toLocaleString();
      if (elDomains) elDomains.textContent = data.total_domains.toLocaleString();
      this.loadVizStats();
    } catch (err) {
      console.error(err);
    }
  },

  async loadSenders() {
    const offset = (this.currentPage - 1) * this.pageSize;
    const url = `/api/senders?filter_type=${encodeURIComponent(this.currentFilter)}&sort_by=${encodeURIComponent(this.currentSortBy)}&sort_order=${encodeURIComponent(this.currentSortOrder)}&search=${encodeURIComponent(this.searchQuery)}&limit=${this.pageSize}&offset=${offset}`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('Could not get senders');
      const data = await res.json();
      this.totalSenders = data.total;
      if (!this.sendersCache) this.sendersCache = new Map();
      (data.items || []).forEach(s => this.sendersCache.set(s.email, s));
      this.renderSendersTable(data.items);
      this.updatePagination();
      this.updatePoolButton();
    } catch (err) {
      console.error(err);
      this.showAlert('Error', 'Unable to load email senders');
    }
  },

  renderSendersTable(senders) {
    const tbody = document.getElementById('sendersTableBody');
    if (!tbody) return;

    if (!senders || senders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: #777;">No email senders found</td></tr>`;
      return;
    }

    let html = '';
    senders.forEach((s, idx) => {
      const rowNum = (this.currentPage - 1) * this.pageSize + idx + 1;
      const isSelected = this.selectedSenderEmails.has(s.email);
      const rowClass = isSelected ? 'selected' : '';
      const safeName = (s.name || s.email.split('@')[0]).replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const safeEmail = s.email.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      
      let typeLabel = 'Company';
      if (s.classification === 'people') typeLabel = 'Personal';
      if (s.classification === 'newsletters') typeLabel = 'Newsletter';
      if (s.classification === 'mixed') typeLabel = 'Receipts and Ads';

      const classBadge = `<span class="badge-pill badge-${s.classification}">${typeLabel}</span>`;

      html += `
        <tr class="${rowClass}" onclick="app.openSenderModal(${s.id})">
          <td style="text-align: center; white-space: nowrap;" onclick="event.stopPropagation()">
            <div style="display: flex; align-items: center; justify-content: center; gap: 4px;">
              <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="app.toggleSenderSelect('${s.email}', this.checked)">
              <span style="font-family: monospace; font-size: 11px; color: #555;">${rowNum}</span>
            </div>
          </td>
          <td><strong>${safeName}</strong></td>
          <td>${safeEmail}</td>
          <td>${classBadge}</td>
          <td style="text-align: right; font-weight: bold;">${s.message_count.toLocaleString()}</td>
          <td style="font-size: 11px;">${s.last_seen ? s.last_seen.split(' ')[0] : '-'}</td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
  },

  updatePagination() {
    const summary = document.getElementById('paginationSummary');
    const start = this.totalSenders === 0 ? 0 : (this.currentPage - 1) * this.pageSize + 1;
    const end = Math.min(this.currentPage * this.pageSize, this.totalSenders);
    if (summary) {
      summary.textContent = `Showing ${start} to ${end} of ${this.totalSenders} senders`;
    }

    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    const pageInd = document.getElementById('currentPageIndicator');

    if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
    if (nextBtn) nextBtn.disabled = end >= this.totalSenders;
    if (pageInd) pageInd.textContent = `Page ${this.currentPage}`;
  },

  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.loadSenders();
    }
  },

  nextPage() {
    const maxPage = Math.ceil(this.totalSenders / this.pageSize);
    if (this.currentPage < maxPage) {
      this.currentPage++;
      this.loadSenders();
    }
  },

  toggleSenderSelect(email, checked) {
    if (checked) {
      this.selectedSenderEmails.add(email);
    } else {
      this.selectedSenderEmails.delete(email);
    }
    this.loadSenders();
    this.generateFilterRules();
    this.renderCleanFilterSelectedTable();
    this.updatePoolButton();
  },

  toggleSelectAll(checked) {
    const checkboxes = document.querySelectorAll('#sendersTableBody input[type="checkbox"]');
    checkboxes.forEach(cb => {
      cb.checked = checked;
    });
    if (checked) {
      const rows = document.querySelectorAll('#sendersTableBody tr');
      rows.forEach(r => {
        const emailCell = r.children[2];
        if (emailCell) {
          const email = emailCell.textContent.trim();
          if (email) this.selectedSenderEmails.add(email);
        }
      });
    } else {
      this.selectedSenderEmails.clear();
    }
    this.loadSenders();
    this.generateFilterRules();
    this.renderCleanFilterSelectedTable();
    this.updatePoolButton();
  },

  async selectJunkCandidates() {
    try {
      if (!this.sendersCache) this.sendersCache = new Map();
      const res = await fetch('/api/senders?filter_type=newsletters&limit=500');
      if (!res.ok) return;
      const data = await res.json();
      data.items.forEach(s => {
        this.selectedSenderEmails.add(s.email);
        this.sendersCache.set(s.email, s);
      });
      this.loadSenders();
      this.generateFilterRules();
      this.renderCleanFilterSelectedTable();
      this.updatePoolButton();
      this.showAlert('Selection Updated', `Selected ${data.items.length} newsletters and promotional senders`);
    } catch (err) {
      console.error(err);
    }
  },

  clearSelection() {
    this.selectedSenderEmails.clear();
    this.loadSenders();
    this.generateFilterRules();
    this.renderCleanFilterSelectedTable();
    this.updatePoolButton();
    this.showAlert('Selection Cleared', 'All selections removed');
  },

  updatePoolButton() {
    const poolBtn = document.getElementById('poolCleanBtn');
    const scopeSwitcher = document.getElementById('aiCleanScopeSwitcher');
    const scopePoolBtn = document.getElementById('aiScopePoolBtn');
    const count = this.selectedSenderEmails.size;

    if (poolBtn) {
      if (count > 0) {
        poolBtn.style.display = 'inline-block';
        poolBtn.textContent = `Pool (${count})`;
      } else {
        poolBtn.style.display = 'none';
      }
    }

    if (scopeSwitcher && scopePoolBtn) {
      if (count > 0) {
        scopeSwitcher.style.display = 'inline-flex';
        scopePoolBtn.textContent = `Pooled Senders (${count})`;
      } else {
        scopeSwitcher.style.display = 'none';
        this.aiCleanScope = 'all';
      }
    }
  },

  goToCleanPool() {
    this.aiCleanScope = 'pool';
    this.showCleanView(this.currentCleanMode || 'ai');
    const poolBtn = document.getElementById('aiScopePoolBtn');
    const allBtn = document.getElementById('aiScopeAllBtn');
    if (poolBtn) poolBtn.classList.add('active');
    if (allBtn) allBtn.classList.remove('active');
  },

  setAiCleanScope(scope) {
    this.aiCleanScope = scope;
    const poolBtn = document.getElementById('aiScopePoolBtn');
    const allBtn = document.getElementById('aiScopeAllBtn');
    if (scope === 'pool') {
      if (poolBtn) poolBtn.classList.add('active');
      if (allBtn) allBtn.classList.remove('active');
    } else {
      if (poolBtn) poolBtn.classList.remove('active');
      if (allBtn) allBtn.classList.add('active');
    }
    this.filterAiCleanSenders();
  },

  openFilterModal() {
    this.showCleanView('filter');
  },

  closeFilterModal() {
    const modal = document.getElementById('filterModal');
    if (modal) modal.classList.remove('open');
  },

  async generateFilterRules() {
    const emails = Array.from(this.selectedSenderEmails);
    const modalQueryEl = document.getElementById('gmailQueryOutput');
    const cleanQueryEl = document.getElementById('cleanGmailQueryOutput');
    const countEl = document.getElementById('cleanFilterSelectionCount');

    if (countEl) {
      countEl.textContent = `${emails.length} senders selected`;
    }

    if (emails.length === 0) {
      const emptyMsg = 'No senders selected. Check boxes next to senders or click Select All Newsletters and Ads.';
      if (modalQueryEl) modalQueryEl.value = emptyMsg;
      if (cleanQueryEl) cleanQueryEl.value = emptyMsg;
      this._lastXmlContent = null;
      return;
    }

    try {
      const res = await fetch('/api/filter-export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_emails: emails })
      });
      if (!res.ok) throw new Error('Rule creation failed');
      const data = await res.json();
      if (modalQueryEl) modalQueryEl.value = data.gmail_search_query;
      if (cleanQueryEl) cleanQueryEl.value = data.gmail_search_query;
      this._lastXmlContent = data.xml_content;
    } catch (err) {
      console.error(err);
    }
  },

  renderCleanFilterSelectedTable() {
    const tbody = document.getElementById('cleanFilterSelectedTableBody');
    const countEl = document.getElementById('cleanFilterSelectionCount');
    if (countEl) {
      countEl.textContent = `${this.selectedSenderEmails.size} senders selected`;
    }
    if (!tbody) return;

    if (this.selectedSenderEmails.size === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 16px; color: #666;">No senders selected yet. Check boxes in the Senders tab or click Select All Newsletters and Ads above.</td></tr>';
      return;
    }

    const emails = Array.from(this.selectedSenderEmails);
    tbody.innerHTML = emails.map((email, idx) => {
      const s = (this.sendersCache && this.sendersCache.get(email)) || {
        name: email.split('@')[0],
        email: email,
        message_count: '-',
        classification: 'newsletters'
      };

      const safeName = (s.name || email.split('@')[0]).replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const safeEmail = email.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      let typeLabel = 'Newsletter';
      if (s.classification === 'people') typeLabel = 'Personal';
      if (s.classification === 'organizations') typeLabel = 'Company';
      if (s.classification === 'mixed') typeLabel = 'Receipts and Ads';

      const classBadge = `<span class="badge-pill badge-${s.classification || 'newsletters'}">${typeLabel}</span>`;
      const countDisplay = typeof s.message_count === 'number' ? s.message_count.toLocaleString() : s.message_count;

      return `
        <tr>
          <td style="text-align: center; font-family: monospace; font-size: 11px; color: #555;">${idx + 1}</td>
          <td><strong>${safeName}</strong></td>
          <td>${safeEmail}</td>
          <td style="text-align: right; font-weight: bold;">${countDisplay}</td>
          <td>${classBadge}</td>
          <td style="text-align: center;">
            <button class="system-btn danger" onclick="app.removeSelectedSender('${email}')">Remove</button>
          </td>
        </tr>
      `;
    }).join('');
  },

  removeSelectedSender(email) {
    this.selectedSenderEmails.delete(email);
    this.loadSenders();
    this.generateFilterRules();
    this.renderCleanFilterSelectedTable();
    this.updatePoolButton();
  },

  downloadXmlFile() {
    if (!this._lastXmlContent || this.selectedSenderEmails.size === 0) {
      this.showAlert('Notice', 'Please select at least one sender first');
      return;
    }
    const blob = new Blob([this._lastXmlContent], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mailFilters.xml';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    this.showAlert('Downloaded', 'Saved mailFilters.xml to your downloads folder');
  },

  copyToClipboard(elementId) {
    const el = document.getElementById(elementId);
    if (!el || !el.value) return;
    navigator.clipboard.writeText(el.value).then(() => {
      this.showAlert('Copied', 'Rule copied to clipboard');
    }).catch(() => {
      el.select();
      document.execCommand('copy');
      this.showAlert('Copied', 'Rule copied to clipboard');
    });
  },

  async openSenderModal(senderId) {
    this.activeSenderId = senderId;
    const modal = document.getElementById('senderDetailModal');
    if (!modal) return;

    modal.classList.add('open');
    document.getElementById('mcpBriefResult').style.display = 'none';
    document.getElementById('mcpLoadingIndicator').style.display = 'none';

    try {
      const res = await fetch(`/api/senders/${senderId}`);
      if (!res.ok) throw new Error('Could not get sender details');
      const data = await res.json();
      const s = data.sender;
      this.activeSenderEmail = s.email;

      document.getElementById('modalSenderTitle').textContent = `Sender: ${s.email}`;
      document.getElementById('modalSenderName').textContent = s.name || s.email.split('@')[0];
      document.getElementById('modalSenderEmail').textContent = s.email;
      document.getElementById('modalMessageCount').textContent = s.message_count.toLocaleString();
      document.getElementById('modalLastSeen').textContent = s.last_seen ? s.last_seen.split(' ')[0] : '-';

      const tbody = document.getElementById('modalSubjectsTableBody');
      if (data.messages && data.messages.length > 0) {
        tbody.innerHTML = data.messages.map((m, idx) => {
          let kind = 'General';
          if (m.is_transactional) kind = 'Receipt or Bill';
          if (m.is_promotional) kind = 'Ad or Promo';
          const safeSubj = (m.subject || 'No Subject').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          return `
            <tr>
              <td style="width: 35px; text-align: center; font-family: monospace; font-size: 11px; color: #555;">${idx + 1}</td>
              <td style="width: 100px; font-size: 11px;">${m.date ? m.date.split(' ')[0] : '-'}</td>
              <td>${safeSubj}</td>
              <td style="width: 120px; font-size: 11px;">${kind}</td>
            </tr>
          `;
        }).join('');
      } else {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center;">No recent emails found</td></tr>`;
      }
    } catch (err) {
      console.error(err);
      this.showAlert('Error', 'Failed to open sender details');
    }
  },

  closeSenderModal() {
    const modal = document.getElementById('senderDetailModal');
    if (modal) modal.classList.remove('open');
  },

  async runMcpVerification() {
    if (!this.activeSenderEmail) return;

    const loader = document.getElementById('mcpLoadingIndicator');
    const resultBox = document.getElementById('mcpBriefResult');
    const triggerBtn = document.getElementById('triggerMcpBtn');

    if (loader) loader.style.display = 'block';
    if (resultBox) resultBox.style.display = 'none';
    if (triggerBtn) triggerBtn.disabled = true;

    try {
      const res = await fetch('/api/mcp/verify-sender', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_email: this.activeSenderEmail })
      });

      if (!res.ok) throw new Error('AI check failed');
      const data = await res.json();

      document.getElementById('mcpEngineLabel').textContent = `Engine: ${data.engine}`;
      const riskEl = document.getElementById('mcpRiskScore');
      if (data.risk_score > 60) {
        riskEl.textContent = 'Caution: Contains receipts';
        riskEl.className = 'risk-pill risk-high';
      } else if (data.risk_score > 30) {
        riskEl.textContent = 'Review before removing';
        riskEl.className = 'risk-pill risk-med';
      } else {
        riskEl.textContent = 'Safe to block';
        riskEl.className = 'risk-pill risk-low';
      }

      document.getElementById('mcpSummaryText').textContent = data.summary;

      const listEl = document.getElementById('mcpFindingsList');
      listEl.innerHTML = (data.key_findings || []).map(f => `<li>${f}</li>`).join('');

      document.getElementById('mcpSafeQueryInput').value = data.safe_filter_query || '';

      if (loader) loader.style.display = 'none';
      if (resultBox) resultBox.style.display = 'block';

      this.loadSenders();
      this.loadStats();
    } catch (err) {
      console.error(err);
      if (loader) loader.style.display = 'none';
      this.showAlert('Notice', 'Could not complete AI review at this time');
    } finally {
      if (triggerBtn) triggerBtn.disabled = false;
    }
  },

  copySafeQuery() {
    const queryInput = document.getElementById('mcpSafeQueryInput');
    if (queryInput && queryInput.value) {
      navigator.clipboard.writeText(queryInput.value).then(() => {
        this.showAlert('Copied', 'Rule copied to clipboard');
      });
    }
  },

  async updateSenderTriage(status) {
    if (!this.activeSenderId) return;
    try {
      const res = await fetch('/api/triage-sender', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender_id: this.activeSenderId,
          status: status
        })
      });
      if (res.ok) {
        const msg = status === 'junk' ? 'Sender marked as junk' : 'Sender kept in inbox';
        this.showAlert('Updated', msg);
        this.closeSenderModal();
        this.loadSenders();
        this.loadStats();
      }
    } catch (err) {
      console.error(err);
    }
  },

  setupDropzone() {
    const dropzone = document.getElementById('fileDropzone');
    if (!dropzone) return;

    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, e => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropzone.addEventListener(eventName, e => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      }, false);
    });

    dropzone.addEventListener('drop', e => {
      const dt = e.dataTransfer;
      const files = dt.files;
      this.handleFileSelect(files);
    }, false);
  },

  handleFileSelect(files) {
    if (!files || files.length === 0) return;
    const file = files[0];

    const pBar = document.getElementById('indexingProgressBar');
    const pFill = document.getElementById('progressFillBar');
    const pMsg = document.getElementById('progressMessageLabel');
    const pPct = document.getElementById('progressPercentageLabel');

    if (pBar) pBar.classList.add('visible');
    if (pFill) pFill.style.width = '0%';
    if (pPct) pPct.textContent = '0%';
    if (pMsg) pMsg.textContent = `Uploading ${file.name}...`;

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        const loadedMB = (e.loaded / (1024 * 1024)).toFixed(1);
        const totalMB = (e.total / (1024 * 1024)).toFixed(1);
        if (pFill) pFill.style.width = `${pct}%`;
        if (pPct) pPct.textContent = `${pct}%`;
        if (pMsg) pMsg.textContent = `Uploading: ${pct}% (${loadedMB} MB of ${totalMB} MB)`;
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        if (pFill) pFill.style.width = '100%';
        if (pPct) pPct.textContent = '100%';
        if (pMsg) pMsg.textContent = 'Upload complete! Reading emails from file...';
        this._userInitiatedUpload = true;
        this.startStatusPolling();
      } else {
        if (pMsg) pMsg.textContent = 'Upload failed. Please check the file.';
        let errMsg = 'The server could not accept the file';
        try {
          const errData = JSON.parse(xhr.responseText);
          if (errData && errData.detail) errMsg = errData.detail;
        } catch (e) {}
        this.showAlert('Upload Failed', errMsg);
      }
    };

    xhr.onerror = () => {
      if (pMsg) pMsg.textContent = 'Upload error. Connection failed.';
      this.showAlert('Upload Failed', 'A connection error occurred during upload');
    };

    xhr.open('POST', '/api/upload-mbox', true);
    xhr.send(formData);
  },

  async resetDatabase() {
    try {
      const res = await fetch('/api/reset-db', { method: 'POST' });
      if (res.ok) {
        this._userInitiatedUpload = false;
        this.selectedSenderEmails.clear();
        this.updatePoolButton();
        this.totalMessages = 0;
        this.totalSenders = 0;
        this.loadStats();
        this.showUploadView();
        const pBar = document.getElementById('indexingProgressBar');
        if (pBar) pBar.classList.remove('visible');
        this.showAlert('Reset Complete', 'All email data cleared. You can upload a new file now.');
      }
    } catch (err) {
      console.error(err);
      this.showAlert('Error', 'Could not reset database');
    }
  },

  startStatusPolling() {
    if (this.isPollingIndexing) return;
    this.isPollingIndexing = true;

    const poll = async () => {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const status = await res.json();
          const pBar = document.getElementById('indexingProgressBar');
          const pFill = document.getElementById('progressFillBar');
          const pMsg = document.getElementById('progressMessageLabel');
          const pPct = document.getElementById('progressPercentageLabel');
          if (status.status === 'parsing' || status.status === 'indexing') {
            if (pBar) pBar.classList.add('visible');

            const pct = status.total_messages_estimated > 0
              ? Math.min(99, Math.round((status.messages_processed / status.total_messages_estimated) * 100))
              : 50;

            if (pFill) pFill.style.width = `${pct}%`;
            if (pPct) pPct.textContent = `${pct}%`;
            if (pMsg) pMsg.textContent = `Reading emails: ${status.messages_processed.toLocaleString()} processed so far...`;

            setTimeout(poll, 700);
            return;
          } else if (status.status === 'completed') {
            if (pBar) pBar.classList.remove('visible');
            if (this._userInitiatedUpload && status.messages_processed > 0) {
              this.showAlert('Import Finished', `Successfully read ${status.messages_processed.toLocaleString()} emails`);
              this.showMainView();
            }
            this._userInitiatedUpload = false;
          } else {
            if (pBar) pBar.classList.remove('visible');
            this._userInitiatedUpload = false;
          }
        }
      } catch (err) {
        console.error(err);
      }
      this.isPollingIndexing = false;
    };

    poll();
  },

  showAlert(title, message) {
    const alertModal = document.getElementById('systemAlertDialog');
    const alertTitle = document.getElementById('alertTitle');
    const alertMsg = document.getElementById('alertMessage');
    if (!alertModal) return;

    const cleanTitle = (title || 'Notice').replace(/;/g, ',').replace(/[—–]/g, '-');
    const cleanMsg = (message || '').replace(/;/g, ',').replace(/[—–]/g, '-');

    if (alertTitle) alertTitle.textContent = cleanTitle;
    if (alertMsg) alertMsg.textContent = cleanMsg;
    alertModal.classList.add('open');
  },

  closeAlert() {
    const alertModal = document.getElementById('systemAlertDialog');
    if (alertModal) alertModal.classList.remove('open');
  },

  resetView() {
    this.currentFilter = 'all';
    this.searchQuery = '';
    const searchInput = document.getElementById('searchInput');
    if (searchInput) searchInput.value = '';
    this.setFilter('all');
  },

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
    }
  },

  showAiCleanView() {
    this.showCleanView('ai');
  },

  showAiCleanSenderList() {
    const listSec = document.getElementById('aiCleanSenderListSection');
    const progSec = document.getElementById('aiCleanProgressSection');
    const resSec = document.getElementById('aiCleanResultsSection');
    if (listSec) listSec.style.display = 'flex';
    if (progSec) progSec.style.display = 'none';
    if (resSec) resSec.style.display = 'none';
    this.loadAiCleanSenders();
  },

  async loadAiCleanSenders(search = '') {
    const tbody = document.getElementById('aiCleanSendersTableBody');
    if (!tbody) return;
    try {
      const url = search ? `/api/ai-clean/senders?search=${encodeURIComponent(search)}` : '/api/ai-clean/senders';
      const res = await fetch(url);
      const data = await res.json();
      this.aiCleanSendersData = data.senders || [];

      const knownEmails = new Set(this.aiCleanSendersData.map(s => s.email));
      this.selectedSenderEmails.forEach(email => {
        if (!knownEmails.has(email)) {
          const cached = this.sendersCache && this.sendersCache.get(email);
          this.aiCleanSendersData.push({
            id: cached ? cached.id : null,
            email: email,
            name: cached ? cached.name : email.split('@')[0],
            message_count: cached && typeof cached.message_count === 'number' ? cached.message_count : 1,
            summarized_count: 0,
            categories_count: 0
          });
        }
      });

      this.updatePoolButton();
      this.filterAiCleanSenders();
    } catch (e) {
      console.error(e);
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: red;">Failed to load senders</td></tr>';
    }
  },

  filterAiCleanSenders() {
    const q = (document.getElementById('aiCleanSearchInput')?.value || '').toLowerCase();
    if (!this.aiCleanSendersData) return;

    let list = this.aiCleanSendersData;
    if (this.aiCleanScope === 'pool' && this.selectedSenderEmails.size > 0) {
      list = list.filter(s => this.selectedSenderEmails.has(s.email));
    }

    if (q) {
      list = list.filter(s => 
        s.email.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q)
      );
    }
    this.renderAiCleanSenders(list);
  },

  renderAiCleanSenders(senders) {
    const tbody = document.getElementById('aiCleanSendersTableBody');
    if (!tbody) return;
    if (!senders || senders.length === 0) {
      if (this.aiCleanScope === 'pool') {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: #777;">No pooled senders. Check boxes in the Senders tab to add senders to the pool.</td></tr>';
      } else {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: #777;">No senders found</td></tr>';
      }
      return;
    }

    tbody.innerHTML = senders.map((s, idx) => {
      const isComplete = s.categories_count > 0;
      let statusHtml = '';
      let actionBtn = '';

      if (isComplete) {
        statusHtml = `<span style="color: #1b6e34; font-weight: bold;">Completed (${s.categories_count} categories)</span>`;
        actionBtn = `<button class="system-btn primary" onclick="app.viewAiCleanCategories('${s.email}')">View Categories</button>`;
      } else if (s.summarized_count > 0) {
        const pct = Math.round((s.summarized_count / s.message_count) * 100);
        statusHtml = `<span style="color: #9c6500; font-weight: bold;">Summarized ${s.summarized_count}/${s.message_count} (${pct}%)</span>`;
        actionBtn = `<button class="system-btn primary" onclick="app.startSenderAiClean('${s.email}')">Continue Analysis</button>`;
      } else {
        statusHtml = '<span style="color: #666;">Ready to scan</span>';
        actionBtn = `<button class="system-btn" onclick="app.startSenderAiClean('${s.email}')">Analyze with Local AI</button>`;
      }

      const safeName = (s.name || s.email.split('@')[0]).replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const safeEmail = s.email.replace(/</g, '&lt;').replace(/>/g, '&gt;');

      return `
        <tr>
          <td style="text-align: center; font-family: monospace; font-size: 11px; color: #555;">${idx + 1}</td>
          <td><strong>${safeName}</strong></td>
          <td>${safeEmail}</td>
          <td style="text-align: right; font-weight: bold;">${s.message_count.toLocaleString()}</td>
          <td>${statusHtml}</td>
          <td style="text-align: center;">${actionBtn}</td>
        </tr>
      `;
    }).join('');
  },

  async startSenderAiClean(email) {
    try {
      const res = await fetch('/api/ai-clean/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
      });
      const data = await res.json();
      if (!res.ok && res.status !== 409) {
        this.showAlert('Analysis Error', data.detail || 'Could not start analysis');
        return;
      }

      this.activeAiCleanEmail = email;
      const listSec = document.getElementById('aiCleanSenderListSection');
      const progSec = document.getElementById('aiCleanProgressSection');
      const resSec = document.getElementById('aiCleanResultsSection');
      if (listSec) listSec.style.display = 'none';
      if (progSec) progSec.style.display = 'flex';
      if (resSec) resSec.style.display = 'none';

      document.getElementById('aiCleanProgressTitle').textContent = `Analyzing ${email}`;
      document.getElementById('aiCleanProgressSubtitle').textContent = 'Local AI is reading and generating summaries for every email from this sender.';
      this.pollAiCleanStatus(email);
    } catch (e) {
      console.error(e);
      this.showAlert('Error', 'Failed to connect to local AI analysis');
    }
  },

  pollAiCleanStatus(email) {
    if (this.aiCleanPollInterval) clearInterval(this.aiCleanPollInterval);

    this.aiCleanPollInterval = setInterval(async () => {
      try {
        const res = await fetch('/api/ai-clean/status');
        const status = await res.json();

        const pBar = document.getElementById('aiCleanProgressBar');
        const pCounter = document.getElementById('aiCleanProgressCounter');
        const pPercent = document.getElementById('aiCleanProgressPercent');
        const pSubject = document.getElementById('aiCleanProgressSubject');
        const pStage = document.getElementById('aiCleanProgressStage');

        if (pBar) pBar.style.width = `${status.percent || 0}%`;
        if (pPercent) pPercent.textContent = `${status.percent || 0}%`;
        if (pCounter) pCounter.textContent = `${status.processed || 0} / ${status.total || 0} emails`;
        if (pSubject && status.current_subject) pSubject.textContent = status.current_subject;

        if (status.stage === 'loading_model') {
          if (pStage) pStage.textContent = 'Loading local model into memory...';
        } else if (status.stage === 'summarizing') {
          if (pStage) pStage.textContent = 'Step 1 of 2: Generating local summaries for each email';
        } else if (status.stage === 'categorizing') {
          if (pStage) pStage.textContent = 'Step 2 of 2: Grouping emails into categories and building search rules';
        }

        if (status.status === 'completed' && status.sender === email) {
          clearInterval(this.aiCleanPollInterval);
          this.viewAiCleanCategories(email);
        } else if (status.status === 'error') {
          clearInterval(this.aiCleanPollInterval);
          this.showAlert('Analysis Notice', status.error || 'Local AI analysis encountered an error');
          this.showAiCleanSenderList();
          this.loadAiCleanSenders();
        }
      } catch (e) {
        console.error(e);
      }
    }, 800);
  },

  async viewAiCleanCategories(email) {
    this.activeAiCleanEmail = email;
    const listSec = document.getElementById('aiCleanSenderListSection');
    const progSec = document.getElementById('aiCleanProgressSection');
    const resSec = document.getElementById('aiCleanResultsSection');
    if (listSec) listSec.style.display = 'none';
    if (progSec) progSec.style.display = 'none';
    if (resSec) resSec.style.display = 'flex';

    const header = document.getElementById('aiCleanResultsHeader');
    if (header) header.textContent = `Categories for ${email}`;

    const container = document.getElementById('aiCleanCategoriesContainer');
    if (!container) return;
    container.innerHTML = '<div style="text-align: center; padding: 20px;">Loading categories...</div>';

    try {
      const res = await fetch(`/api/ai-clean/categories?email=${encodeURIComponent(email)}`);
      const data = await res.json();
      const cats = data.categories || [];

      if (cats.length === 0) {
        container.innerHTML = `
          <div style="background: #fff; border: 1px solid var(--border-dark); padding: 20px; text-align: center;">
            <div style="margin-bottom: 10px; font-weight: bold;">No categories found yet for this sender.</div>
            <button class="system-btn primary" onclick="app.startSenderAiClean('${email}')">Run Local AI Analysis</button>
          </div>
        `;
        return;
      }

      container.innerHTML = cats.map((cat, idx) => {
        const safeName = cat.category_name.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const safeDesc = (cat.description || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const safeQuery = (cat.gmail_query || `from:${email}`).replace(/"/g, '&quot;');
        const count = cat.message_count || 0;

        return `
          <div style="background: var(--base-light); border: 2px solid var(--border-dark); padding: 14px; box-shadow: 2px 2px 0 rgba(0,0,0,0.15);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div style="font-size: 14px; font-weight: bold; color: var(--crimson-accent);">${safeName}</div>
              <div style="font-size: 11px; font-weight: bold; background: #fff; border: 1px solid var(--border-dark); padding: 2px 8px;">
                ${count.toLocaleString()} emails
              </div>
            </div>
            <div style="font-size: 12px; color: var(--base-dark); margin-bottom: 12px; line-height: 1.4;">
              ${safeDesc}
            </div>
            <div style="font-size: 11px; font-weight: bold; margin-bottom: 4px; color: #444;">Gmail Delete Search Query:</div>
            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 10px;">
              <input type="text" id="catQuery_${idx}" class="system-input" style="flex: 1; font-family: monospace; font-size: 11px;" value="${safeQuery}" readonly>
              <button class="system-btn primary" onclick="app.copyQueryFromInput('catQuery_${idx}')">Copy Query</button>
              <button class="system-btn" onclick="app.downloadCategoryXmlFilter('${email}', '${safeName}', '${safeQuery}')">Download Filter</button>
            </div>
            <div style="font-size: 11px; color: #666;">
              Paste this query in Gmail search bar to view and delete only the ${count.toLocaleString()} emails in this category.
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error(e);
      container.innerHTML = '<div style="color: red; text-align: center;">Failed to load categories</div>';
    }
  },

  copyQueryFromInput(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.select();
    input.setSelectionRange(0, 99999);
    navigator.clipboard.writeText(input.value).then(() => {
      this.showAlert('Copied', 'Gmail search query copied to clipboard. Paste into Gmail search bar to select and delete these emails.');
    }).catch(() => {
      document.execCommand('copy');
      this.showAlert('Copied', 'Gmail search query copied to clipboard.');
    });
  },

  async downloadCategoryXmlFilter(email, categoryName, query) {
    try {
      const res = await fetch('/api/ai-clean/category-filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email,
          category_name: categoryName,
          gmail_query: query
        })
      });
      const data = await res.json();
      const blob = new Blob([data.xml_content], { type: 'text/xml;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `filter_${categoryName.toLowerCase().replace(/[^a-z0-9]/g, '_')}.xml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      this.showAlert('Error', 'Failed to generate category filter file');
    }
  },

  async loadVizStats() {
    try {
      const res = await fetch('/api/viz-stats');
      if (!res.ok) return;
      const data = await res.json();
      const cats = data.categories || {};
      const news = cats.newsletters || { message_count: 0, message_percent: 0 };
      const mixed = cats.mixed || { message_count: 0, message_percent: 0 };
      const orgs = cats.organizations || { message_count: 0, message_percent: 0 };
      const people = cats.people || { message_count: 0, message_percent: 0 };

      const barNews = document.getElementById('vizBarNewsletters');
      const barMixed = document.getElementById('vizBarMixed');
      const barOrgs = document.getElementById('vizBarOrgs');
      const barPeople = document.getElementById('vizBarPeople');

      if (barNews) barNews.style.width = `${news.message_percent}%`;
      if (barMixed) barMixed.style.width = `${mixed.message_percent}%`;
      if (barOrgs) barOrgs.style.width = `${orgs.message_percent}%`;
      if (barPeople) barPeople.style.width = `${people.message_percent}%`;

      const elNewsCnt = document.getElementById('vizNewslettersCount');
      const elNewsPct = document.getElementById('vizNewslettersPct');
      const elMixedCnt = document.getElementById('vizMixedCount');
      const elMixedPct = document.getElementById('vizMixedPct');
      const elOrgsCnt = document.getElementById('vizOrgsCount');
      const elOrgsPct = document.getElementById('vizOrgsPct');
      const elPeopleCnt = document.getElementById('vizPeopleCount');
      const elPeoplePct = document.getElementById('vizPeoplePct');

      if (elNewsCnt) elNewsCnt.textContent = news.message_count.toLocaleString();
      if (elNewsPct) elNewsPct.textContent = `${news.message_percent}%`;
      if (elMixedCnt) elMixedCnt.textContent = mixed.message_count.toLocaleString();
      if (elMixedPct) elMixedPct.textContent = `${mixed.message_percent}%`;
      if (elOrgsCnt) elOrgsCnt.textContent = orgs.message_count.toLocaleString();
      if (elOrgsPct) elOrgsPct.textContent = `${orgs.message_percent}%`;
      if (elPeopleCnt) elPeopleCnt.textContent = people.message_count.toLocaleString();
      if (elPeoplePct) elPeoplePct.textContent = `${people.message_percent}%`;
    } catch (e) {
      console.error(e);
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  app.init();
});
