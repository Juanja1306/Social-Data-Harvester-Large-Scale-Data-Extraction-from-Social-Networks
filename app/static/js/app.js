(function () {
  const API = "/api";
  let pollInterval = null;

  const queryEl = document.getElementById("query");
  const maxPostsEl = document.getElementById("max_posts");
  const btnStart = document.getElementById("btnStart");
  const btnStop = document.getElementById("btnStop");
  const logArea = document.getElementById("logArea");
  const statusBar = document.getElementById("statusBar");
  const linkDownload = document.getElementById("linkDownload");
  const btnLLM = document.getElementById("btnLLM");

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

  function renderLog(entries) {
    logArea.innerHTML = "";
    if (!entries || !entries.length) return;
    entries.forEach((entry) => {
      const div = document.createElement("div");
      div.className = "log-entry";
      div.innerHTML = `<span class="time">[${entry.time}]</span> ${escapeHtml(entry.message)}`;
      logArea.appendChild(div);
    });
    logArea.scrollTop = logArea.scrollHeight;
  }

  function updateUIFromStatus(data) {
    const running = data.running === true;
    btnStart.disabled = running;
    btnStop.disabled = !running;
    setStatus(running ? "Estado: Scraping activo..." : "Estado: Inactivo", running);
    if (data.log && data.log.length > 0) {
      renderLog(data.log);
    }
  }

  function fetchStatus() {
    fetch(API + "/scrape/status")
      .then((r) => r.json())
      .then((data) => {
        updateUIFromStatus(data);
        if (data.running) {
          startPolling();
        } else {
          stopPolling();
        }
      })
      .catch((err) => {
        console.error(err);
        setStatus("Error al obtener estado", false);
      });
  }

  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(fetchStatus, 1500);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

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
        logArea.innerHTML = "";
        startPolling();
        fetchStatus();
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
    btnLLM.disabled = true;
    fetch(API + "/llm/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ networks: getSelectedNetworks().filter((n) => ["LinkedIn", "Instagram", "Twitter", "Facebook"].includes(n)) }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => Promise.reject(new Error(d.detail || r.statusText)));
        return r.json();
      })
      .then((data) => {
        alert(data.message || "Análisis LLM iniciado.");
      })
      .catch((err) => alert("Error: " + (err.message || err)))
      .finally(() => { btnLLM.disabled = false; });
  });

  // Initial load: clear log, fetch status once (no polling until we know running)
  logArea.innerHTML = "";
  fetchStatus();
})();
