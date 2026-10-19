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
    this.startStatusPolling();
  },

  showUploadView() {
    const uploadView = document.getElementById('uploadView');
    const mainView = document.getElementById('mainView');
    const cancelBtn = document.getElementById('cancelUploadBtn');
    if (uploadView) uploadView.style.display = 'flex';
    if (mainView) mainView.style.display = 'none';
    if (cancelBtn) {
      cancelBtn.style.display = this.totalMessages > 0 ? 'inline-block' : 'none';
    }
  },

  showMainView() {
    const uploadView = document.getElementById('uploadView');
    const mainView = document.getElementById('mainView');
    if (uploadView) uploadView.style.display = 'none';
    if (mainView) mainView.style.display = 'flex';
    this.loadSenders();
    this.loadStats();
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
      this.renderSendersTable(data.items);
      this.updatePagination();
    } catch (err) {
      console.error(err);
      this.showAlert('Error', 'Unable to load email senders');
    }
  },

  renderSendersTable(senders) {
    const tbody = document.getElementById('sendersTableBody');
    if (!tbody) return;

    if (!senders || senders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: #777;">No email senders found</td></tr>`;
      return;
    }

    let html = '';
    senders.forEach(s => {
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
          <td style="text-align: center;" onclick="event.stopPropagation()">
            <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="app.toggleSenderSelect('${s.email}', this.checked)">
          </td>
          <td><strong>${safeName}</strong></td>
          <td>${safeEmail}</td>
          <td>${classBadge}</td>
          <td style="text-align: right; font-weight: bold;">${s.message_count.toLocaleString()}</td>
          <td style="font-size: 11px;">${s.last_seen ? s.last_seen.split(' ')[0] : '-'}</td>
          <td style="text-align: center;" onclick="event.stopPropagation()">
            <button class="system-btn" onclick="app.openSenderModal(${s.id})">Review</button>
          </td>
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
  },

  async selectJunkCandidates() {
    try {
      const res = await fetch('/api/senders?filter_type=newsletters&limit=500');
      if (!res.ok) return;
      const data = await res.json();
      data.items.forEach(s => this.selectedSenderEmails.add(s.email));
      this.loadSenders();
      this.generateFilterRules();
      this.showAlert('Selection Updated', `Selected ${data.items.length} newsletters and promotional senders`);
    } catch (err) {
      console.error(err);
    }
  },

  clearSelection() {
    this.selectedSenderEmails.clear();
    this.loadSenders();
    this.generateFilterRules();
    this.showAlert('Selection Cleared', 'All selections removed');
  },

  openFilterModal() {
    const modal = document.getElementById('filterModal');
    if (!modal) return;
    this.generateFilterRules();
    modal.classList.add('open');
  },

  closeFilterModal() {
    const modal = document.getElementById('filterModal');
    if (modal) modal.classList.remove('open');
  },

  async generateFilterRules() {
    const emails = Array.from(this.selectedSenderEmails);
    const queryEl = document.getElementById('gmailQueryOutput');

    if (emails.length === 0) {
      if (queryEl) queryEl.value = 'No senders selected. Check boxes next to senders or click Select All Newsletters and Ads.';
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
      if (queryEl) queryEl.value = data.gmail_search_query;
      this._lastXmlContent = data.xml_content;
    } catch (err) {
      console.error(err);
    }
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
        tbody.innerHTML = data.messages.map(m => {
          let kind = 'General';
          if (m.is_transactional) kind = 'Receipt or Bill';
          if (m.is_promotional) kind = 'Ad or Promo';
          const safeSubj = (m.subject || 'No Subject').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          return `
            <tr>
              <td style="width: 110px; font-size: 11px;">${m.date ? m.date.split(' ')[0] : '-'}</td>
              <td>${safeSubj}</td>
              <td style="width: 120px; font-size: 11px;">${kind}</td>
            </tr>
          `;
        }).join('');
      } else {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center;">No recent emails found</td></tr>`;
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
        this.startStatusPolling();
      } else {
        if (pMsg) pMsg.textContent = 'Upload failed. Please check the file.';
        this.showAlert('Upload Failed', 'The server could not accept the file');
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
        this.selectedSenderEmails.clear();
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
            this.showAlert('Import Finished', `Successfully read ${status.messages_processed.toLocaleString()} emails`);
            this.showMainView();
          } else {
            if (pBar) pBar.classList.remove('visible');
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
  }
};

document.addEventListener('DOMContentLoaded', () => {
  app.init();
});
