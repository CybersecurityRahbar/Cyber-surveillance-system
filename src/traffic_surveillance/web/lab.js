(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    mode: "file",
    jobId: null,
    timer: null,
    previewVersion: 0,
    previewUrl: null,
    videoUrl: null,
  };
  const terminal = new Set(["completed", "stopped", "failed"]);

  function headers(extra = {}) {
    const result = { ...extra };
    const key = $("apiKey").value.trim();
    if (key) result["X-API-Key"] = key;
    return result;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: headers(options.headers || {}),
    });
    if (!response.ok) {
      let message = "HTTP " + response.status;
      try {
        const body = await response.json();
        message = body.detail || message;
      } catch (_) {}
      throw new Error(message);
    }
    return response.status === 204 ? null : response;
  }

  function setNotice(message, visible = true) {
    $("capabilityNotice").textContent = message;
    $("capabilityNotice").hidden = !visible;
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll(".mode").forEach((button) => {
      button.classList.toggle("active", button.dataset.mode === mode);
    });
    $("fileMode").hidden = mode !== "file";
    $("liveMode").hidden = mode !== "live";
    $("startFile").hidden = mode !== "file";
    $("startLive").hidden = mode !== "live";
  }

  function resetResult() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
    state.jobId = null;
    state.previewVersion = 0;
    $("processedPreview").hidden = true;
    $("monitorPlaceholder").hidden = false;
    $("resultVideoWrap").hidden = true;
    $("resultVideo").removeAttribute("src");
    $("progressBar").style.width = "0%";
    $("progressText").textContent = "0%";
    $("jobState").textContent = "جاهز لاستقبال فيديو";
    $("monitorBadge").classList.remove("running");
    $("monitorBadge").innerHTML = "<i></i> بانتظار المصدر";
    $("stopJob").disabled = true;
    $("startFile").disabled = false;
    $("startLive").disabled = false;
    setMetrics(null);
  }

  function setMetrics(job) {
    $("metricVehicles").textContent = job ? (job.unique_vehicle_tracks ?? "0") : "—";
    $("metricPeople").textContent = job ? (job.unique_person_tracks ?? "0") : "—";
    $("metricDown").textContent = job ? (job.line_crossings?.down ?? "0") : "—";
    $("metricUp").textContent = job ? (job.line_crossings?.up ?? "0") : "—";
    $("metricFps").textContent = job ? (job.processing_fps ?? "0") : "—";
    $("metricDuration").textContent = job?.result
      ? job.result.media_duration_seconds.toFixed(1) + "s"
      : "—";

    const counts = job?.class_counts || job?.result?.class_counts || {};
    const list = $("classCountList");
    list.innerHTML = "";
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
      const empty = document.createElement("span");
      empty.className = "empty-count";
      empty.textContent = "لم يتم رصد هويات تتبع بعد";
      list.appendChild(empty);
    } else {
      for (const [label, count] of entries) {
        const pill = document.createElement("div");
        pill.className = "class-pill";
        const name = document.createElement("span");
        name.textContent = label;
        const value = document.createElement("b");
        value.textContent = count;
        pill.append(name, value);
        list.appendChild(pill);
      }
    }
  }

  async function startFileJob() {
    const file = $("videoFile").files[0];
    if (!file) {
      setNotice("اختر ملف فيديو أولاً.");
      return;
    }
    resetResult();
    const form = new FormData();
    form.append("file", file);
    form.append("tracker", $("tracker").value);
    form.append("confidence", (Number($("confidence").value) / 100).toString());
    form.append("line_position", (Number($("linePosition").value) / 100).toString());
    form.append("max_width", $("maxWidth").value);
    $("startFile").disabled = true;
    setNotice("يتم رفع الفيديو وتهيئة جلسة المختبر...");
    try {
      const response = await api("/api/v1/lab/jobs", { method: "POST", body: form });
      const job = await response.json();
      beginWatching(job.job_id, job.filename);
      setNotice("", false);
    } catch (error) {
      setNotice(error.message);
      $("startFile").disabled = false;
    }
  }

  async function startLiveJob() {
    const source = $("liveSource").value.trim();
    if (!source) {
      setNotice("أدخل عنوان RTSP أو server-camera:0.");
      return;
    }
    resetResult();
    $("startLive").disabled = true;
    try {
      const payload = {
        source: source,
        duration_seconds: Number($("liveDuration").value),
        tracker: $("tracker").value,
        confidence: Number($("confidence").value) / 100,
        line_position: Number($("linePosition").value) / 100,
        max_width: Number($("liveWidth").value),
      };
      const response = await api("/api/v1/lab/live-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const job = await response.json();
      beginWatching(job.job_id, job.source_label);
      setNotice("", false);
    } catch (error) {
      setNotice(error.message);
      $("startLive").disabled = false;
    }
  }

  function beginWatching(jobId, sourceLabel) {
    state.jobId = jobId;
    $("monitorSource").textContent = sourceLabel;
    $("monitorPlaceholder").hidden = true;
    $("processedPreview").hidden = false;
    $("monitorBadge").classList.add("running");
    $("monitorBadge").innerHTML = "<i></i> المحرك يعمل";
    $("stopJob").disabled = false;
    $("jobState").textContent = "تم إنشاء جلسة المعالجة";
    $("startFile").disabled = true;
    $("startLive").disabled = true;
    state.timer = setInterval(() => pollJob(jobId), 750);
    pollJob(jobId);
  }

  async function pollJob(jobId) {
    if (state.jobId !== jobId) return;
    try {
      const response = await api("/api/v1/lab/jobs/" + jobId);
      const job = await response.json();
      updateJob(job);
      if (job.status === "running" || job.status === "queued") {
        await refreshPreview(jobId);
      }
      if (terminal.has(job.status)) {
        clearInterval(state.timer);
        state.timer = null;
        $("stopJob").disabled = true;
        $("startFile").disabled = false;
        $("startLive").disabled = false;
        $("monitorBadge").classList.remove("running");
        $("monitorBadge").innerHTML = job.status === "failed"
          ? "<i></i> فشلت المعالجة"
          : "<i></i> انتهت الجلسة";
        if (job.status === "completed" || job.status === "stopped") {
          await loadOutput(jobId);
          $("jobState").textContent = job.status === "stopped"
            ? "أوقفت الجلسة يدوياً"
            : "اكتملت المعالجة بنجاح";
        } else {
          setNotice(job.error || "حدث خطأ أثناء تحليل الفيديو.");
          $("jobState").textContent = "فشلت المعالجة";
        }
      }
    } catch (error) {
      $("jobState").textContent = error.message;
    }
  }

  function updateJob(job) {
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    $("progressBar").style.width = progress + "%";
    $("progressText").textContent = progress.toFixed(1) + "%";
    $("frameProgress").textContent = (job.frames_processed || 0) + " إطار";
    $("processingFps").textContent = (job.processing_fps || 0) + " FPS معالجة";
    $("jobState").textContent = job.status === "running"
      ? "يتم الكشف والتتبع وتحليل خط العد..."
      : job.status === "queued"
        ? "في قائمة الانتظار..."
        : job.status;
    setMetrics(job);
  }

  async function refreshPreview(jobId) {
    const response = await api("/api/v1/lab/jobs/" + jobId + "/preview.jpg");
    if (!response) return;
    const version = Number(response.headers.get("X-Preview-Version") || 0);
    if (version <= state.previewVersion) return;
    state.previewVersion = version;
    const blob = await response.blob();
    const nextUrl = URL.createObjectURL(blob);
    $("processedPreview").src = nextUrl;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = nextUrl;
  }

  async function loadOutput(jobId) {
    const response = await api("/api/v1/lab/jobs/" + jobId + "/video");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
    state.videoUrl = url;
    $("resultVideo").src = url;
    $("resultVideoWrap").hidden = false;
    $("downloadVideo").href = url;
  }

  async function stopJob() {
    if (!state.jobId) return;
    try {
      await api("/api/v1/lab/jobs/" + state.jobId + "/stop", { method: "POST" });
      $("jobState").textContent = "تم إرسال طلب الإيقاف...";
      $("stopJob").disabled = true;
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function loadCapabilities() {
    try {
      const response = await api("/api/v1/lab/capabilities");
      const info = await response.json();
      $("modelName").textContent = info.model || "YOLO26n";
      $("backendStatus").textContent = info.processing_ready
        ? "جاهز للتشغيل"
        : "حزم ناقصة: " + info.missing_packages.join(", ");
      if (!info.processing_ready) {
        setNotice(
          "بيئة التحليل غير مكتملة. الحزم المطلوبة: " +
          info.missing_packages.join(", ") +
          ". نفّذ أمر التثبيت الموضح في README ثم أعد تشغيل الخادم."
        );
      } else if (info.model_will_download_on_first_use) {
        setNotice(
          "أول تشغيل سيطلب تنزيل أوزان YOLO26n تلقائياً إلى مخزن النماذج المحلي. " +
          "يلزم اتصال إنترنت في المرة الأولى فقط."
        );
      } else {
        setNotice("", false);
      }
    } catch (error) {
      $("backendStatus").textContent = "تعذر الاتصال";
      setNotice(error.message);
    }
  }

  $("apiKey").value = sessionStorage.getItem("trafficLabApiKey") || "";
  $("apiKey").addEventListener("change", () => {
    const key = $("apiKey").value.trim();
    if (key) {
      sessionStorage.setItem("trafficLabApiKey", key);
      loadCapabilities();
    } else {
      sessionStorage.removeItem("trafficLabApiKey");
      $("backendStatus").textContent = "بانتظار مفتاح API";
      setNotice("أدخل مفتاح API المخصص لهذه الجلسة للوصول إلى واجهات التحليل.");
    }
  });
  document.querySelectorAll(".mode").forEach((button) =>
    button.addEventListener("click", () => setMode(button.dataset.mode))
  );
  $("startFile").addEventListener("click", startFileJob);
  $("startLive").addEventListener("click", startLiveJob);
  $("stopJob").addEventListener("click", stopJob);
  $("confidence").addEventListener("input", () =>
    $("confidenceValue").textContent = $("confidence").value + "%"
  );
  $("linePosition").addEventListener("input", () =>
    $("lineValue").textContent = $("linePosition").value + "%"
  );
  $("videoFile").addEventListener("change", () => {
    const file = $("videoFile").files[0];
    if (!file) return;
    $("selectedFile").textContent = file.name;
    $("fileMeta").textContent = file.name;
    $("filePreviewWrap").hidden = false;
    const old = $("localPreview").src;
    if (old.startsWith("blob:")) URL.revokeObjectURL(old);
    $("localPreview").src = URL.createObjectURL(file);
    $("localPreview").onloadedmetadata = () => {
      $("fileDimensions").textContent =
        $("localPreview").videoWidth +
        " × " +
        $("localPreview").videoHeight +
        " · " +
        $("localPreview").duration.toFixed(1) +
        " ثانية";
    };
  });
  const drop = $("dropZone");
  drop.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("dragging");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("dragging");
    if (event.dataTransfer.files.length) {
      $("videoFile").files = event.dataTransfer.files;
      $("videoFile").dispatchEvent(new Event("change"));
    }
  });
  setMode("file");
  loadCapabilities();
})();
