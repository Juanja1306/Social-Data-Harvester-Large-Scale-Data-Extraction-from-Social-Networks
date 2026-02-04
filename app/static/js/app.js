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
        const chartsRequestEl = document.getElementById("chartsRequest");
        if (chartsRequestEl) chartsRequestEl.innerHTML = "<option value=\"\">-- Todos los requests --</option>" + optionsHtml;
        const commentsRequestEl = document.getElementById("commentsRequest");
        if (commentsRequestEl) commentsRequestEl.innerHTML = "<option value=\"\">-- Selecciona un Request --</option>" + optionsHtml;
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

  let galleryImages = [];
  let carouselIndex = 0;
  const chartsGallerySection = document.getElementById("chartsGallerySection");
  const galleryHint = document.getElementById("galleryHint");
  const chartsCarousel = document.getElementById("chartsCarousel");
  const carouselTrack = document.getElementById("carouselTrack");
  const carouselCaption = document.getElementById("carouselCaption");
  const carouselDots = document.getElementById("carouselDots");
  const carouselPrev = document.getElementById("carouselPrev");
  const carouselNext = document.getElementById("carouselNext");

  function imageUrl(item) {
    return API + "/charts/image/" + encodeURIComponent(item.folder) + "/" + encodeURIComponent(item.file);
  }

  function showCarouselSlide(index) {
    if (!galleryImages.length) return;
    carouselIndex = (index + galleryImages.length) % galleryImages.length;
    const item = galleryImages[carouselIndex];
    const img = document.getElementById("carouselImage");
    if (img) {
      img.src = imageUrl(item);
      img.alt = item.title;
    }
    if (carouselCaption) carouselCaption.textContent = item.title;
    if (carouselDots) {
      carouselDots.querySelectorAll(".carousel-dot").forEach((el, i) => {
        el.classList.toggle("active", i === carouselIndex);
      });
    }
  }

  function renderGallery(images) {
    galleryImages = images || [];
    if (!chartsGallerySection || !chartsCarousel) return;
    if (!galleryImages.length) {
      chartsCarousel.classList.add("hidden");
      if (galleryHint) galleryHint.classList.remove("hidden");
      return;
    }
    if (galleryHint) galleryHint.classList.add("hidden");
    chartsCarousel.classList.remove("hidden");
    carouselTrack.innerHTML = "";
    const img = document.createElement("img");
    img.id = "carouselImage";
    img.className = "carousel-image";
    img.alt = "";
    carouselTrack.appendChild(img);
    carouselDots.innerHTML = "";
    galleryImages.forEach((_, i) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "carousel-dot" + (i === 0 ? " active" : "");
      dot.setAttribute("aria-label", "Ir a gráfica " + (i + 1));
      dot.addEventListener("click", function () {
        showCarouselSlide(i);
      });
      carouselDots.appendChild(dot);
    });
    carouselIndex = 0;
    showCarouselSlide(0);
  }

  if (carouselPrev) {
    carouselPrev.addEventListener("click", function () {
      showCarouselSlide(carouselIndex - 1);
    });
  }
  if (carouselNext) {
    carouselNext.addEventListener("click", function () {
      showCarouselSlide(carouselIndex + 1);
    });
  }

  document.addEventListener("keydown", function (e) {
    if (!galleryImages.length || chartsCarousel.classList.contains("hidden")) return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      showCarouselSlide(carouselIndex - 1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      showCarouselSlide(carouselIndex + 1);
    }
  });

  const btnCharts = document.getElementById("btnCharts");
  if (btnCharts) {
    btnCharts.addEventListener("click", function () {
      const chartsRequestEl = document.getElementById("chartsRequest");
      const request = chartsRequestEl ? (chartsRequestEl.value || "").trim() : "";
      btnCharts.disabled = true;
      fetch(API + "/charts/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: request || null }),
      })
        .then((r) => {
          if (!r.ok) return r.json().then((d) => Promise.reject(new Error(d.detail || r.statusText)));
          return r.json();
        })
        .then((data) => {
          if (data.images && data.images.length > 0) {
            renderGallery(data.images);
            if (chartsGallerySection) {
              chartsGallerySection.classList.remove("hidden");
              chartsGallerySection.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }
          alert(data.message || "Gráficas generadas. Revisa la carpeta images/.");
        })
        .catch((err) => alert("Error: " + (err.message || err)))
        .finally(() => {
          btnCharts.disabled = false;
        });
    });
  }

  const commentsSection = document.getElementById("commentsSection");
  const commentsHint = document.getElementById("commentsHint");
  const commentsResults = document.getElementById("commentsResults");
  const commentsResultsTitle = document.getElementById("commentsResultsTitle");
  const commentsList = document.getElementById("commentsList");
  const commentsRequestEl = document.getElementById("commentsRequest");
  const commentsNetworkEl = document.getElementById("commentsNetwork");
  const btnComments = document.getElementById("btnComments");

  function renderCommentsExplained(data) {
    if (!data || !data.publications || !data.publications.length) {
      commentsList.innerHTML = "<p class=\"comments-empty\">No hay publicaciones para mostrar.</p>";
      return;
    }
    commentsResultsTitle.textContent = "Request: " + (data.request || "");
    commentsList.innerHTML = "";
    data.publications.forEach((pub, idx) => {
      const card = document.createElement("div");
      card.className = "publication-card";
      const redBadge = document.createElement("span");
      redBadge.className = "pub-red";
      redBadge.textContent = pub.red || "";
      const fecha = document.createElement("span");
      fecha.className = "pub-fecha";
      fecha.textContent = pub.fechaPublicacion ? " · " + pub.fechaPublicacion : "";
      const header = document.createElement("div");
      header.className = "pub-header";
      header.appendChild(redBadge);
      header.appendChild(fecha);

      const postBlock = document.createElement("div");
      postBlock.className = "post-block";
      const postLabel = document.createElement("div");
      postLabel.className = "block-label";
      postLabel.textContent = "Post";
      postBlock.appendChild(postLabel);
      const postText = document.createElement("div");
      postText.className = "block-text";
      postText.textContent = pub.post_text || "(sin texto)";
      postBlock.appendChild(postText);
      if (pub.post_sentimiento || pub.post_explicacion) {
        const postMeta = document.createElement("div");
        postMeta.className = "block-meta";
        if (pub.post_sentimiento) {
          const sent = document.createElement("span");
          sent.className = "sentimiento " + (pub.post_sentimiento === "Positivo" ? "positivo" : pub.post_sentimiento === "Negativo" ? "negativo" : "neutral");
          sent.textContent = pub.post_sentimiento;
          postMeta.appendChild(sent);
        }
        if (pub.post_explicacion) {
          const exp = document.createElement("div");
          exp.className = "explicacion";
          exp.textContent = pub.post_explicacion;
          postMeta.appendChild(exp);
        }
        postBlock.appendChild(postMeta);
      }
      card.appendChild(header);
      card.appendChild(postBlock);

      if (pub.comments && pub.comments.length) {
        const commentsLabel = document.createElement("div");
        commentsLabel.className = "comments-block-label";
        commentsLabel.textContent = "Comentarios (" + pub.comments.length + ")";
        card.appendChild(commentsLabel);
        pub.comments.forEach((c, i) => {
          const commentBlock = document.createElement("div");
          commentBlock.className = "comment-block";
          const cText = document.createElement("div");
          cText.className = "comment-text";
          cText.textContent = c.text || "(sin texto)";
          commentBlock.appendChild(cText);
          if (c.sentimiento || c.explicacion) {
            const cMeta = document.createElement("div");
            cMeta.className = "comment-meta";
            if (c.sentimiento) {
              const sent = document.createElement("span");
              sent.className = "sentimiento " + (c.sentimiento === "Positivo" ? "positivo" : c.sentimiento === "Negativo" ? "negativo" : "neutral");
              sent.textContent = c.sentimiento;
              cMeta.appendChild(sent);
            }
            if (c.explicacion) {
              const exp = document.createElement("div");
              exp.className = "explicacion";
              exp.textContent = c.explicacion;
              cMeta.appendChild(exp);
            }
            commentBlock.appendChild(cMeta);
          }
          card.appendChild(commentBlock);
        });
      }
      commentsList.appendChild(card);
    });
  }

  if (btnComments) {
    btnComments.addEventListener("click", function () {
      const request = (commentsRequestEl && commentsRequestEl.value || "").trim();
      if (!request) {
        alert("Selecciona un Request para ver comentarios y explicaciones.");
        return;
      }
      const network = (commentsNetworkEl && commentsNetworkEl.value) || "";
      btnComments.disabled = true;
      const qs = "?request=" + encodeURIComponent(request) + (network ? "&network=" + encodeURIComponent(network) : "");
      fetch(API + "/comments-explained" + qs)
        .then((r) => {
          if (!r.ok) return r.json().then((d) => Promise.reject(new Error(d.detail || r.statusText)));
          return r.json();
        })
        .then((data) => {
          if (commentsHint) commentsHint.classList.add("hidden");
          commentsResults.classList.remove("hidden");
          renderCommentsExplained(data);
          commentsSection.scrollIntoView({ behavior: "smooth", block: "start" });
        })
        .catch((err) => alert("Error: " + (err.message || err)))
        .finally(() => { btnComments.disabled = false; });
    });
  }

  connectLogWebSocket();
  fetchRequests();
  fetchStatus();
  fetchReportsList();
})();
