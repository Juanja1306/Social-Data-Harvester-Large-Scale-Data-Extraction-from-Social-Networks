(function () {
  const API = "/api";
  const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
  const WS_BASE = WS_PROTOCOL + "//" + window.location.host;
  let pollInterval = null;
  let reportPollInterval = null;
  let logWs = null;

  const queryEl = document.getElementById("query");
  const maxPostsEl = document.getElementById("max_posts");
  const btnStart = document.getElementById("btnStart");
  const btnStop = document.getElementById("btnStop");
  const logArea = document.getElementById("logArea");
  const statusBar = document.getElementById("statusBar");
  const linkDownload = document.getElementById("linkDownload");
  const downloadRequest = document.getElementById("downloadRequest");
  const llmRequest = document.getElementById("llmRequest");
  const btnLLM = document.getElementById("btnLLM");
  const reportsSection = document.getElementById("reportsSection");
  const reportsHint = document.getElementById("reportsHint");
  const llmRunning = document.getElementById("llmRunning");
  const reportsTabs = document.getElementById("reportsTabs");
  const reportContent = document.getElementById("reportContent");
  const reportTitle = document.getElementById("reportTitle");
  const reportText = document.getElementById("reportText");

  function getSelectedNetworks() {
    const checkboxes = document.querySelectorAll('input[name="network"]:checked');
    return Array.from(checkboxes).map((cb) => cb.value);
  }

  function setStatus(text, running) {
    statusBar.textContent = text;
    statusBar.classList.toggle("running", !!running);
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function appendLogEntry(entry) {
    const div = document.createElement("div");
    div.className = "log-entry";
    div.innerHTML = `<span class="time">[${escapeHtml(entry.time || "")}]</span> ${escapeHtml(entry.message || "")}`;
    logArea.appendChild(div);
    // Solo hacer scroll automático si el usuario marcó la casilla "autoScroll"
    const autoScrollCb = document.getElementById("autoScroll");
    if (autoScrollCb && autoScrollCb.checked) {
      logArea.scrollTop = logArea.scrollHeight;
    }
  }

  function connectLogWebSocket() {
    if (logWs && logWs.readyState === WebSocket.OPEN) return;
    logWs = new WebSocket(WS_BASE + "/ws/log");
    logWs.onopen = function () {};
    logWs.onmessage = function (event) {
      try {
        const entry = JSON.parse(event.data);
        appendLogEntry(entry);
      } catch (e) {
        console.warn("Log WS parse error", e);
      }
    };
    logWs.onclose = function () {
      logWs = null;
      setTimeout(connectLogWebSocket, 2000);
    };
    logWs.onerror = function () {
      logWs.close();
    };
  }

  function updateUIFromStatus(data) {
    const running = data.running === true;
    const llmRunningState = data.llm_running === true;
    btnStart.disabled = running;
    btnStop.disabled = !running;
    setStatus(running ? "Estado: Scraping activo..." : "Estado: Inactivo", running);
    if (llmRunningState) {
      llmRunning.classList.remove("hidden");
      startReportPolling();
    } else {
      llmRunning.classList.add("hidden");
      stopReportPolling();
    }
    if (running) {
      startPolling();
    } else {
      stopPolling();
    }
  }

  function fetchStatus() {
    fetch(API + "/scrape/status")
      .then((r) => r.json())
      .then((data) => updateUIFromStatus(data))
      .catch((err) => {
        console.error(err);
        setStatus("Error al obtener estado", false);
      });
  }

  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(fetchStatus, 1200);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  function loadReport(network, format) {
    const fmt = format || "text";
    fetch(API + "/llm/reports/" + encodeURIComponent(network) + "?format=" + fmt)
      .then((r) => {
        if (!r.ok) throw new Error("Report not found");
        return r.json();
      })
      .then((data) => {
        // Título para saber de qué request es el reporte
        if (data.request) {
          reportTitle.textContent = "Request: " + data.request;
          reportTitle.classList.remove("hidden");
        } else {
          reportTitle.textContent = "Red: " + network;
          reportTitle.classList.remove("hidden");
        }
        if (fmt === "json") {
          reportText.textContent = JSON.stringify(data, null, 2);
        } else {
          reportText.textContent = data.content || "";
        }
        reportContent.classList.remove("hidden");
      })
      .catch(() => {
        reportTitle.textContent = "Red: " + network + " (sin reporte)";
        reportTitle.classList.remove("hidden");
        reportText.textContent = "No hay reporte para esta red. Ejecuta el análisis LLM seleccionando " + network + " para generarlo.";
        reportContent.classList.remove("hidden");
      });
  }

  function renderReportsList(list) {
    if (!list || !list.length) return;
    reportsHint.classList.add("hidden");
    llmRunning.classList.add("hidden");
    reportsTabs.classList.remove("hidden");
    reportsTabs.innerHTML = "";
    list.forEach((r, index) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "report-tab" + (index === 0 ? " active" : "");
      tab.textContent = r.network;
      tab.dataset.network = r.network;
      tab.dataset.hasData = (r.has_text || r.has_json) ? "1" : "0";
      tab.addEventListener("click", function () {
        reportsTabs.querySelectorAll(".report-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        loadReport(r.network, "text");
      });
      reportsTabs.appendChild(tab);
    });
    const first = list[0];
    if (first) loadReport(first.network, "text");
  }

  function fetchReportsList() {
    fetch(API + "/llm/reports")
      .then((r) => r.json())
      .then((data) => {
        const list = data.reports || [];
        if (list.length > 0) {
          renderReportsList(list);
          stopReportPolling();
        }
      })
      .catch(() => {});
  }

  function startReportPolling() {
    if (reportPollInterval) return;
    reportPollInterval = setInterval(() => {
      fetchStatus();
      fetchReportsList();
    }, 1500);
  }

  function stopReportPolling() {
    if (reportPollInterval) {
      clearInterval(reportPollInterval);
      reportPollInterval = null;
    }
  }

  function fetchRequests() {
    fetch(API + "/requests")
      .then((r) => r.json())
      .then((data) => {
        const list = data.requests || [];
        const requestListEl = document.getElementById("requestList");
        requestListEl.innerHTML = "";
        list.forEach((req) => {
          const opt = document.createElement("option");
          opt.value = req;
          requestListEl.appendChild(opt);
        });
        const optionsHtml = list.map((req) => `<option value="${escapeHtml(req)}">${escapeHtml(req)}</option>`).join("");
        downloadRequest.innerHTML = "<option value=\"\">-- Todos --</option>" + optionsHtml;
        llmRequest.innerHTML = "<option value=\"\">-- Selecciona un Request --</option>" + optionsHtml;
        updateDownloadLink();
      })
      .catch(() => {});
  }

  function updateDownloadLink() {
    const req = downloadRequest.value;
    linkDownload.href = API + "/results" + (req ? "?request=" + encodeURIComponent(req) : "");
  }

  downloadRequest.addEventListener("change", updateDownloadLink);

  btnStart.addEventListener("click", function () {
    const query = queryEl.value.trim();
    if (!query) {
      alert("Debes ingresar un tema de búsqueda.");
      return;
    }
    const max_posts = parseInt(maxPostsEl.value, 10);
    if (isNaN(max_posts) || max_posts <= 0) {
      alert("El máximo de posts debe ser un número entero positivo.");
      return;
    }
    const networks = getSelectedNetworks();
    if (networks.length === 0) {
      alert("Selecciona al menos una red.");
      return;
    }

    btnStart.disabled = true;
    fetch(API + "/scrape/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, max_posts, networks }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(new Error(d.detail || r.statusText)));
        return r.json();
      })
      .then(() => {
        setStatus("Estado: Scraping activo...", true);
        btnStop.disabled = false;
        startPolling();
        fetchStatus();
        fetchRequests();
      })
      .catch((err) => {
        alert("Error: " + (err.message || err));
        btnStart.disabled = false;
      });
  });

  btnStop.addEventListener("click", function () {
    fetch(API + "/scrape/stop", { method: "POST" })
      .then((r) => r.json())
      .then(() => {
        stopPolling();
        fetchStatus();
      })
      .catch((err) => console.error(err));
  });

  btnLLM.addEventListener("click", function () {
    const request = (llmRequest.value || "").trim();
    if (!request) {
      alert("Selecciona un Request para analizar (el tema del que quieres el análisis de sentimientos).");
      return;
    }
    btnLLM.disabled = true;
    fetch(API + "/llm/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request: request,
        networks: getSelectedNetworks().filter((n) =>
          ["LinkedIn", "Instagram", "Twitter", "Facebook"].includes(n)
        ),
      }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(new Error(d.detail || r.statusText)));
        return r.json();
      })
      .then((data) => {
        reportsSection.scrollIntoView({ behavior: "smooth", block: "start" });
        llmRunning.classList.remove("hidden");
        startReportPolling();
        fetchStatus();
      })
      .catch((err) => alert("Error: " + (err.message || err)))
      .finally(() => {
        btnLLM.disabled = false;
      });
  });

  connectLogWebSocket();
  fetchRequests();
  fetchStatus();
  fetchReportsList();
})();
