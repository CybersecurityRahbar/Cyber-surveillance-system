(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    mode: "file",
    jobId: null,
    timer: null,
    eventTimer: null,
    previewController: null,
    previewUrl: null,
    videoUrl: null,
    reportUrl: null,
    sourceUrl: null,
    sourcePlaybackMode: false,
    analysisView: false,
    selectedReportId: null,
    selectedTrackId: null,
    selectedTrack: null,
    currentReport: null,
    trackById: new Map(),
  };
  const terminal = new Set(["completed", "stopped", "failed"]);
  const colourNames = {
    beige: "بيج", white: "أبيض", black: "أسود", grey: "رمادي", silver: "فضي",
    brown: "بني", gold: "ذهبي", red: "أحمر", orange: "برتقالي",
    yellow: "أصفر", green: "أخضر", blue: "أزرق", pink: "وردي", purple: "بنفسجي",
  };

  function formatTimestamp(value) {
    if (!value) return "وقت غير متاح";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("ar-YE", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      fractionalSecondDigits: 3, hourCycle: "h23",
    }).format(date);
  }

  function clearHighlight(canvasId) {
    const canvas = $(canvasId);
    if (!canvas) return;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  }

  function drawHighlight(canvasId, media, track) {
    const canvas = $(canvasId);
    if (!canvas || !media || !track?.last_bbox) {
      clearHighlight(canvasId);
      return;
    }
    const naturalWidth = media.videoWidth || media.naturalWidth || 0;
    const naturalHeight = media.videoHeight || media.naturalHeight || 0;
    const rect = canvas.getBoundingClientRect();
    if (!naturalWidth || !naturalHeight || !rect.width || !rect.height) {
      clearHighlight(canvasId);
      return;
    }
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);
    const scale = Math.min(rect.width / naturalWidth, rect.height / naturalHeight);
    const renderWidth = naturalWidth * scale;
    const renderHeight = naturalHeight * scale;
    const offsetX = (rect.width - renderWidth) / 2;
    const offsetY = (rect.height - renderHeight) / 2;
    const sourceWidth = Number(track.frame_width || naturalWidth);
    const sourceHeight = Number(track.frame_height || naturalHeight);
    const box = track.last_bbox;
    const x = offsetX + Number(box.x1) / sourceWidth * renderWidth;
    const y = offsetY + Number(box.y1) / sourceHeight * renderHeight;
    const width = (Number(box.x2) - Number(box.x1)) / sourceWidth * renderWidth;
    const height = (Number(box.y2) - Number(box.y1)) / sourceHeight * renderHeight;
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return;
    context.lineWidth = 3;
    context.strokeStyle = "#ffd84d";
    context.shadowColor = "rgba(255,216,77,.82)";
    context.shadowBlur = 12;
    context.strokeRect(x, y, width, height);
    context.shadowBlur = 0;
    const label = "SELECTED  #" + track.track_id;
    context.font = "bold 12px Inter, sans-serif";
    const labelWidth = context.measureText(label).width + 14;
    const labelY = Math.max(18, y - 5);
    context.fillStyle = "#ffd84d";
    context.fillRect(x, Math.max(0, labelY - 18), labelWidth, 20);
    context.fillStyle = "#17202a";
    context.fillText(label, x + 7, Math.max(14, labelY - 4));
  }

  function observationAt(track, mediaTime) {
    const samples = Array.isArray(track.trajectory)
      ? track.trajectory.filter((item) => item && item.bbox)
      : [];
    if (!samples.length || !Number.isFinite(mediaTime)) return track;
    const nearest = samples.reduce((best, item) =>
      Math.abs(Number(item.time || 0) - mediaTime) <
      Math.abs(Number(best.time || 0) - mediaTime) ? item : best
    );
    return {
      ...track,
      last_bbox: nearest.bbox,
      frame_width: nearest.frame_width || track.frame_width,
      frame_height: nearest.frame_height || track.frame_height,
    };
  }

  function redrawSelectedTrack() {
    const track = state.selectedTrack;
    if (!track) {
      clearHighlight("monitorHighlightCanvas");
      clearHighlight("resultHighlightCanvas");
      return;
    }
    const source = $("sourcePlayback");
    const preview = $("processedPreview");
    const result = $("resultVideo");
    if (!source.hidden) {
      drawHighlight("monitorHighlightCanvas", source,
        observationAt(track, Number(source.currentTime || 0)));
    } else if (!preview.hidden) {
      drawHighlight("monitorHighlightCanvas", preview, track);
    } else {
      clearHighlight("monitorHighlightCanvas");
    }
    if (!$("resultVideoWrap").hidden) {
      drawHighlight("resultHighlightCanvas", result,
        observationAt(track, Number(result.currentTime || 0)));
    } else {
      clearHighlight("resultHighlightCanvas");
    }
  }

  async function loadReportVideo(sessionId) {
    const response = await api("/api/v1/lab/reports/" + sessionId + "/video");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
    state.videoUrl = url;
    $("resultVideo").src = url;
    $("resultVideoWrap").hidden = false;
    $("downloadVideo").href = url;
    if (state.selectedTrack) {
      const selected = state.selectedTrack;
      const seek = () => {
        $("resultVideo").currentTime = Number(
          selected.last_media_time_seconds ?? selected.last_seen_seconds ?? 0
        );
        $("resultVideo").pause();
        redrawSelectedTrack();
      };
      if ($("resultVideo").readyState >= 1) seek();
      else $("resultVideo").addEventListener("loadedmetadata", seek, { once: true });
    }
    return url;
  }

  async function focusTrack(track) {
    state.selectedTrackId = Number(track.track_id);
    state.selectedTrack = track;
    document.querySelectorAll(".live-track-card, .track-report-row").forEach((element) => {
      const selected = Number(element.dataset.trackId) === state.selectedTrackId;
      element.classList.toggle("selected-track-row", selected);
      if (element.classList.contains("live-track-card")) {
        element.setAttribute("aria-pressed", String(selected));
      }
    });
    const mediaTime = Number(track.last_media_time_seconds ?? track.last_seen_seconds ?? 0);

    if (state.videoUrl) {
      const video = $("resultVideo");
      $("resultVideoWrap").hidden = false;
      const seek = () => {
        video.currentTime = Math.max(0, mediaTime);
        video.pause();
        redrawSelectedTrack();
      };
      if (video.readyState >= 1) seek();
      else video.addEventListener("loadedmetadata", seek, { once: true });
      $("resultVideoWrap").scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    const localSourceMatchesSession =
      state.mode === "file" &&
      Boolean(state.sourceUrl) &&
      (!state.currentReport || state.currentReport.session_id === state.jobId);
    if (localSourceMatchesSession) {
      const video = $("sourcePlayback");
      if (video.src !== state.sourceUrl) video.src = state.sourceUrl;
      video.hidden = false;
      $("processedPreview").hidden = true;
      $("analysisModeNote").hidden = false;
      $("toggleAnalysisView").hidden = false;
      state.analysisView = false;
      $("toggleAnalysisView").textContent = "عرض إطار التحليل";
      video.pause();
      const seek = () => {
        video.currentTime = Math.max(0, mediaTime);
        video.pause();
        redrawSelectedTrack();
      };
      if (video.readyState >= 1) seek();
      else video.addEventListener("loadedmetadata", seek, { once: true });
      return;
    }

    if (state.currentReport?.session_id) {
      try {
        await loadReportVideo(state.currentReport.session_id);
        const video = $("resultVideo");
        const seek = () => {
          video.currentTime = Math.max(0, mediaTime);
          video.pause();
          redrawSelectedTrack();
        };
        if (video.readyState >= 1) seek();
        else video.addEventListener("loadedmetadata", seek, { once: true });
        $("resultVideoWrap").scrollIntoView({ behavior: "smooth", block: "nearest" });
        return;
      } catch (error) {
        setNotice("تعذر فتح فيديو الجلسة لهذه الهوية: " + error.message);
      }
    }

    $("sourcePlayback").hidden = true;
    $("processedPreview").hidden = false;
    redrawSelectedTrack();
    $("jobState").textContent =
      "تم تحديد #" + track.track_id + " عند " + formatTimestamp(track.last_seen_at) +
      " · الرجوع إلى الفيديو المحفوظ يصبح متاحاً بعد انتهاء الجلسة.";
  }

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
    if (mode === "live" && $("tracker").value === "models/trackers/cyber_tracktrack_reid.yaml") {
      $("tracker").value = "bytetrack.yaml";
    }
  }

  function stopPreviewStream() {
    if (state.previewController) {
      state.previewController.abort();
      state.previewController = null;
    }
  }

  function resetResult() {
    if (state.timer) clearInterval(state.timer);
    if (state.eventTimer) clearInterval(state.eventTimer);
    state.timer = null;
    state.eventTimer = null;
    stopPreviewStream();
    state.jobId = null;
    state.currentReport = null;
    state.selectedTrackId = null;
    state.selectedTrack = null;
    state.trackById.clear();
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
    $("processedPreview").removeAttribute("src");
    $("processedPreview").hidden = true;
    $("sourcePlayback").pause();
    $("sourcePlayback").hidden = true;
    $("analysisModeNote").hidden = true;
    $("toggleAnalysisView").hidden = true;
    state.sourcePlaybackMode = false;
    state.analysisView = false;
    if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
    state.videoUrl = null;
    $("resultVideo").pause();
    $("resultVideo").removeAttribute("src");
    $("resultVideo").load();
    $("resultVideoWrap").hidden = true;
    $("downloadVideo").removeAttribute("href");
    clearHighlight("monitorHighlightCanvas");
    clearHighlight("resultHighlightCanvas");
    $("monitorPlaceholder").hidden = false;
    $("progressBar").style.width = "0%";
    $("progressText").textContent = "0%";
    $("jobState").textContent = "بانتظار اختيار مصدر";
    $("monitorBadge").classList.remove("running");
    $("monitorBadge").innerHTML = "<i></i> في وضع الاستعداد";
    $("stopJob").disabled = true;
    $("startFile").disabled = false;
    $("startLive").disabled = false;
    $("liveTrackList").innerHTML = '<div class="empty-state">ستظهر بيانات الأجسام عند بدء المعالجة</div>';
    $("trackReportBody").innerHTML = '<tr><td colspan="10" class="table-empty">لم يتم حفظ تقارير بعد.</td></tr>';
    $("reportCount").textContent = "0 TRACKS";
    $("reportSession").textContent = "SESSION —";
    $("downloadReport").hidden = true;
    setMetrics(null);
  }

  function setMetrics(job) {
    $("metricVehicles").textContent = job ? (job.unique_vehicle_tracks ?? "0") : "—";
    $("metricPeople").textContent = job ? (job.unique_person_tracks ?? "0") : "—";
    $("metricDown").textContent = job ? (job.line_crossings?.down ?? "0") : "—";
    $("metricUp").textContent = job ? (job.line_crossings?.up ?? "0") : "—";
    const down = Number(job?.line_crossings?.down || 0);
    const up = Number(job?.line_crossings?.up || 0);
    $("metricCrossings").textContent = job ? String(down + up) : "—";
    $("metricFps").textContent = job ? (job.processing_fps ?? "0") : "—";
    const sourceFps = Number(job?.source_fps || job?.result?.source_fps || 0);
    const processingFps = Number(job?.processing_fps || job?.result?.processing_fps || 0);
    const realtimeFactor = sourceFps > 0 ? processingFps / sourceFps : 0;
    $("metricRealtime").textContent = job
      ? realtimeFactor.toFixed(2) + "× زمن المصدر"
      : "— × زمن المصدر";
    $("metricLatency").textContent = job
      ? Number(job.inference_latency_ms || job.result?.inference_latency_ms || 0).toFixed(0) + " ms"
      : "— ms";
    $("metricFrameAge").textContent = job
      ? Number(job.frame_age_ms || 0).toFixed(0) + " ms"
      : "— ms";
    $("metricReceived").textContent = String(
      job?.input_frames_received ?? job?.result?.input_frames_received ?? 0
    ) + " مستلم";
    $("metricInputFps").textContent = job
      ? Number(job.input_fps || job.result?.input_fps || 0).toFixed(2) + " FPS"
      : "— FPS";
    $("metricDropped").textContent = String(
      job?.input_frames_dropped ?? job?.result?.input_frames_dropped ?? 0
    ) + " ساقط";
    $("metricDuration").textContent = job?.result
      ? job.result.media_duration_seconds.toFixed(1) + " sec"
      : "—";

    const counts = job?.class_counts || job?.result?.class_counts || {};
    const list = $("classCountList");
    list.innerHTML = "";
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
      list.innerHTML = '<span class="empty-count">لا توجد بيانات بعد</span>';
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

  function renderLiveTracks(items) {
    const list = $("liveTrackList");
    list.innerHTML = "";
    const filtered = [...(items || [])]
      .filter((item) => item.object_type !== "other")
      .sort((a, b) => Number(b.last_seen_seconds || 0) - Number(a.last_seen_seconds || 0))
      .slice(0, 100);
    if (!filtered.length) {
      list.innerHTML = '<div class="empty-state">لا توجد هويات نشطة في الإطار الحالي</div>';
      return;
    }
    for (const item of filtered) {
      state.trackById.set(Number(item.track_id), item);
      const card = document.createElement("button");
      card.type = "button";
      card.dataset.trackId = String(item.track_id);
      const selected = Number(item.track_id) === state.selectedTrackId;
      card.setAttribute("aria-pressed", String(selected));
      card.className = "live-track-card" +
        (item.object_type === "person" ? " person" : "") +
        (selected ? " selected-track-row" : "");
      const token = document.createElement("div");
      token.className = "track-token";
      token.textContent = "#" + item.track_id;
      const info = document.createElement("div");
      info.className = "live-track-info";
      const name = document.createElement("b");
      name.textContent = item.object_type === "person"
        ? "شخص"
        : (item.vehicle_type || item.class_label || "مركبة");
      const meta = document.createElement("small");
      meta.textContent = formatTimestamp(item.last_seen_at) + " · " +
        Number(item.frames_seen || 0) + " إطار · " +
        Number(item.duration_seconds || 0).toFixed(1) + " ث";
      info.append(name, meta);
      const confidence = document.createElement("div");
      confidence.className = "track-confidence";
      confidence.textContent = Math.round((item.confidence || 0) * 100) + "%";
      card.append(token, info, confidence);
      card.addEventListener("click", () =>
        focusTrack(item).catch((error) => setNotice(error.message))
      );
      list.appendChild(card);
    }
  }

  function makeCell(text, className) {
    const cell = document.createElement("td");
    cell.textContent = text;
    if (className) cell.className = className;
    return cell;
  }

  function makeTimestampCell(value, basis) {
    const cell = makeCell(formatTimestamp(value), "track-time");
    cell.title = basis === "server_frame_arrival_utc"
      ? "وقت وصول إطار الكاميرا إلى الخادم بتوقيت UTC"
      : basis === "analysis_observed_utc"
        ? "وقت تحليل الإطار على الخادم، وليس بالضرورة وقت تصوير الفيديو الأصلي"
        : "مصدر التوقيت غير محدد";
    return cell;
  }

  function renderTrackReport(tracks) {
    const body = $("trackReportBody");
    body.innerHTML = "";
    $("reportCount").textContent = (tracks.length || 0) + " TRACKS";
    if (!tracks.length) {
      body.innerHTML = '<tr><td colspan="10" class="table-empty">لم يتم رصد هويات قابلة للحفظ في هذه الجلسة.</td></tr>';
      return;
    }
    const ordered = [...tracks].sort((a, b) =>
      Number(b.last_seen_seconds || 0) - Number(a.last_seen_seconds || 0)
    );
    for (const track of ordered) {
      state.trackById.set(Number(track.track_id), track);
      const row = document.createElement("tr");
      row.className = "track-report-row" +
        (Number(track.track_id) === state.selectedTrackId ? " selected-track-row" : "");
      row.dataset.trackId = String(track.track_id);
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.setAttribute("aria-label", "عرض المركبة أو الجسم رقم " + track.track_id + " في الفيديو");
      const object = document.createElement("td");
      const chip = document.createElement("span");
      chip.className = "object-chip" + (track.object_type === "person" ? " person" : "");
      chip.textContent = track.object_type === "person"
        ? "شخص"
        : (track.vehicle_type || track.class_label || "مركبة");
      object.appendChild(chip);
      row.append(makeCell("#" + track.track_id, "track-id"), object);

      let colourText = "غير مؤكد";
      if (track.vehicle_color) {
        colourText = (colourNames[track.vehicle_color] || track.vehicle_color)
          + " · " + Math.round((track.vehicle_color_confidence || 0) * 100) + "%";
      } else if (track.object_type === "person") {
        colourText = "—";
      }
      if (track.object_type === "vehicle" && track.manual_review_required) {
        colourText += " · مراجعة يدوية";
      }
      row.appendChild(makeCell(colourText));

      let modelText = "—";
      if (track.object_type === "vehicle") {
        const predictedModel = track.make_model
          || [track.make, track.model].filter(Boolean).join(" ");
        modelText = predictedModel
          ? predictedModel + " · " + Math.round((track.make_model_confidence || 0) * 100) + "%"
          : "لا توجد نتيجة موثوقة";
        modelText += " · مرشح يحتاج مراجعة";
      }
      row.append(
        makeCell(modelText),
        makeTimestampCell(track.first_seen_at, track.timestamp_basis),
        makeTimestampCell(track.last_seen_at, track.timestamp_basis),
        makeCell(Number(track.duration_seconds || 0).toFixed(1) + " ث"),
        makeCell(String(track.frames_seen || 0)),
        makeCell(Math.round((track.average_confidence || 0) * 100) + "%"),
        makeCell(String((track.line_crossings || []).length)),
      );
      row.addEventListener("click", () =>
        focusTrack(track).catch((error) => setNotice(error.message))
      );
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          focusTrack(track).catch((error) => setNotice(error.message));
        }
      });
      body.appendChild(row);
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
    form.append("show_hud", $("showHud").checked ? "true" : "false");
    $("startFile").disabled = true;
    setNotice("يتم رفع الفيديو وتهيئة جلسة الرؤية...");
    try {
      const response = await api("/api/v1/lab/jobs", { method: "POST", body: form });
      const job = await response.json();
      beginWatching(job.job_id, job.filename, true);
      setNotice("", false);
    } catch (error) {
      setNotice(error.message);
      $("startFile").disabled = false;
    }
  }

  async function startLiveJob() {
    const source = $("liveSource").value.trim();
    if (!source) {
      setNotice("أدخل RTSP أو server-camera:0 أو phone-camera:road-01.");
      return;
    }
    resetResult();
    $("startLive").disabled = true;
    try {
      const payload = {
        source,
        duration_seconds: Number($("liveDuration").value) || 0,
        tracker: $("tracker").value,
        confidence: Number($("confidence").value) / 100,
        line_position: Number($("linePosition").value) / 100,
        max_width: Number($("liveWidth").value),
        show_hud: $("showHud").checked,
      };
      const response = await api("/api/v1/lab/live-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const job = await response.json();
      beginWatching(job.job_id, job.source_label, false);
      setNotice("", false);
    } catch (error) {
      setNotice(error.message);
      $("startLive").disabled = false;
    }
  }

  function beginWatching(jobId, sourceLabel, sourcePlaybackMode = false) {
    state.jobId = jobId;
    state.sourcePlaybackMode = sourcePlaybackMode;
    state.analysisView = false;
    $("monitorSource").textContent = sourceLabel;
    $("monitorPlaceholder").hidden = true;
    $("sourcePlayback").hidden = !sourcePlaybackMode;
    $("processedPreview").hidden = sourcePlaybackMode;
    $("analysisModeNote").hidden = !sourcePlaybackMode;
    $("toggleAnalysisView").hidden = !sourcePlaybackMode;
    if (sourcePlaybackMode && state.sourceUrl) {
      $("sourcePlayback").src = state.sourceUrl;
      $("sourcePlayback").currentTime = 0;
      $("sourcePlayback").play().catch(() => {});
      $("monitorBadge").innerHTML = "<i></i> تشغيل المصدر · التحليل بالخلفية";
    } else {
      $("monitorBadge").innerHTML = "<i></i> بث الإطارات المحللة";
    }
    $("monitorBadge").classList.add("running");
    $("stopJob").disabled = false;
    $("jobState").textContent = "تم إنشاء جلسة المعالجة";
    $("startFile").disabled = true;
    $("startLive").disabled = true;
    startPreviewStream(jobId);
    state.timer = setInterval(() => pollJob(jobId), 350);
    state.eventTimer = setInterval(loadEvents, 2500);
    pollJob(jobId);
    loadEvents();
  }

  function concatBytes(a, b) {
    const next = new Uint8Array(a.length + b.length);
    next.set(a, 0);
    next.set(b, a.length);
    return next;
  }

  function findHeaderEnd(bytes) {
    for (let i = 0; i <= bytes.length - 4; i++) {
      if (bytes[i] === 13 && bytes[i + 1] === 10 &&
          bytes[i + 2] === 13 && bytes[i + 3] === 10) return i;
    }
    return -1;
  }

  async function startPreviewStream(jobId) {
    stopPreviewStream();
    const controller = new AbortController();
    state.previewController = controller;
    try {
      const response = await fetch(
        "/api/v1/lab/jobs/" + jobId + "/preview.mjpg",
        { headers: headers(), signal: controller.signal, cache: "no-store" }
      );
      if (!response.ok || !response.body) {
        throw new Error("Preview stream HTTP " + response.status);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder("latin1");
      let buffer = new Uint8Array(0);
      while (state.jobId === jobId) {
        const part = await reader.read();
        if (part.done) break;
        buffer = concatBytes(buffer, part.value);
        while (true) {
          const headerEnd = findHeaderEnd(buffer);
          if (headerEnd < 0) break;
          const headerText = decoder.decode(buffer.slice(0, headerEnd));
          const lengthMatch = /content-length:\s*(\d+)/i.exec(headerText);
          if (!lengthMatch) {
            buffer = buffer.slice(headerEnd + 4);
            continue;
          }
          const length = Number(lengthMatch[1]);
          const bodyStart = headerEnd + 4;
          if (buffer.length < bodyStart + length + 2) break;
          const jpeg = buffer.slice(bodyStart, bodyStart + length);
          buffer = buffer.slice(bodyStart + length + 2);
          const nextUrl = URL.createObjectURL(new Blob([jpeg], { type: "image/jpeg" }));
          $("processedPreview").src = nextUrl;
          if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
          state.previewUrl = nextUrl;
        }
        if (buffer.length > 8 * 1024 * 1024) {
          buffer = buffer.slice(-1024 * 1024);
        }
      }
    } catch (error) {
      if (error.name !== "AbortError" && state.jobId === jobId) {
        $("jobState").textContent = "توقف بث المعاينة: " + error.message;
      }
    }
  }

  async function pollJob(jobId) {
    if (state.jobId !== jobId) return;
    try {
      const response = await api("/api/v1/lab/jobs/" + jobId);
      const job = await response.json();
      updateJob(job);
      if (terminal.has(job.status)) {
        clearInterval(state.timer);
        state.timer = null;
        stopPreviewStream();
        $("stopJob").disabled = true;
        $("startFile").disabled = false;
        $("startLive").disabled = false;
        $("monitorBadge").classList.remove("running");
        $("monitorBadge").innerHTML = job.status === "failed"
          ? "<i></i> فشلت المعالجة"
          : "<i></i> اكتملت الجلسة";
        if (state.eventTimer) clearInterval(state.eventTimer);
        state.eventTimer = null;
        if (job.status === "completed" || job.status === "stopped") {
          $("sourcePlayback").pause();
          if (state.sourcePlaybackMode && state.sourceUrl) {
            $("sourcePlayback").hidden = false;
            $("analysisModeNote").hidden = false;
            $("toggleAnalysisView").hidden = false;
          } else {
            $("sourcePlayback").hidden = true;
            $("analysisModeNote").hidden = true;
            $("toggleAnalysisView").hidden = true;
          }
          if (job.result?.output_video_available) {
            if (!state.sourcePlaybackMode) $("processedPreview").hidden = true;
            await loadOutput(jobId);
          } else if (!state.sourcePlaybackMode) {
            $("resultVideoWrap").hidden = true;
            $("processedPreview").hidden = false;
            $("jobState").textContent = "انتهت الجلسة؛ لا يتوفر فيديو محفوظ لهذه العملية.";
          }
          await loadTrackReports(jobId);
          await loadSavedReports();
          await loadEvents();
          if (job.result?.output_video_available) {
            $("jobState").textContent = job.status === "stopped"
              ? "تم إيقاف الجلسة يدوياً"
              : "اكتملت المعالجة بنجاح";
          }
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
    $("processingFps").textContent = (job.processing_fps || 0) + " FPS";
    const ratio = Number(job.source_fps) > 0
      ? Number(job.processing_fps || 0) / Number(job.source_fps)
      : 0;
    $("metricRealtime").textContent = ratio.toFixed(2) + "× زمن المصدر";
    $("metricDropped").textContent = String(job.input_frames_dropped || 0) + " إطار ساقط";
    $("jobState").textContent = job.status === "running"
      ? (job.stage_label || "يتم الكشف والتتبع وتحليل الحركة...")
      : job.status === "queued"
        ? "في قائمة الانتظار..."
        : job.status;
    const currentTracks = job.current_tracks || [];
    renderLiveTracks(currentTracks);
    renderTrackReport(currentTracks);
    if (state.selectedTrackId != null) {
      const refreshed = currentTracks.find(
        (item) => Number(item.track_id) === state.selectedTrackId
      );
      if (refreshed) state.selectedTrack = refreshed;
      redrawSelectedTrack();
    }
    if (state.jobId) {
      $("reportSession").textContent = "LIVE · SESSION " + state.jobId.slice(0, 8).toUpperCase();
    }
    $("metricLatency").textContent = Number(job.inference_latency_ms || 0).toFixed(0) + " ms";
    $("metricFrameAge").textContent = Number(job.frame_age_ms || 0).toFixed(0) + " ms";
    $("metricReceived").textContent = String(job.input_frames_received || 0) + " مستلم";
    $("metricInputFps").textContent = Number(job.input_fps || 0).toFixed(2) + " FPS";
    $("analysisActiveTracks").textContent = String(currentTracks.length);
    $("analysisInferenceLatency").textContent =
      Number(job.inference_latency_ms || 0).toFixed(0) + " ms";
    $("analysisFrameAge").textContent = Number(job.frame_age_ms || 0).toFixed(0) + " ms";
    $("analysisFps").textContent = Number(job.processing_fps || 0).toFixed(2) + " FPS";
    $("analysisInputFps").textContent = Number(job.input_fps || 0).toFixed(2) + " FPS";
    $("analysisReceived").textContent = String(job.input_frames_received || 0);
    $("analysisDropped").textContent = String(job.input_frames_dropped || 0);
    setMetrics(job);
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

  async function loadTrackReports(jobId) {
    const [tracksResponse, reportResponse] = await Promise.all([
      api("/api/v1/lab/reports/" + jobId + "/tracks"),
      api("/api/v1/lab/reports/" + jobId),
    ]);
    const tracks = await tracksResponse.json();
    const report = await reportResponse.json();
    state.currentReport = report;
    state.trackById.clear();
    renderTrackReport(tracks);
    $("reportSession").textContent = "SESSION " + jobId.slice(0, 8).toUpperCase();
    const exportBlob = new Blob(
      [JSON.stringify({ report, tracks }, null, 2)],
      { type: "application/json" }
    );
    const url = URL.createObjectURL(exportBlob);
    if (state.reportUrl) URL.revokeObjectURL(state.reportUrl);
    state.reportUrl = url;
    $("downloadReport").href = url;
    $("downloadReport").download = "traffic-report-" + jobId.slice(0, 8) + ".json";
    $("downloadReport").hidden = false;
  }

  async function loadSavedReports() {
    const select = $("savedReportSelect");
    const previous = state.selectedReportId || select.value;
    try {
      const response = await api("/api/v1/lab/reports?limit=100");
      const reports = await response.json();
      select.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = reports.length
        ? "اختر جلسة محفوظة لعرض تفاصيلها"
        : "لا توجد جلسات محفوظة";
      select.appendChild(placeholder);
      for (const report of reports) {
        const option = document.createElement("option");
        option.value = report.session_id;
        const date = report.finished_at || report.started_at || "";
        const vehicles = report.summary?.unique_vehicle_tracks ?? 0;
        const people = report.summary?.unique_person_tracks ?? 0;
        option.textContent = formatTimestamp(date)
          + " · " + report.filename + " · " + vehicles + " مركبة / " + people + " شخص";
        select.appendChild(option);
      }
      if (reports.some((item) => item.session_id === previous)) {
        select.value = previous;
      } else if (reports.length) {
        select.value = reports[0].session_id;
      }
      if (select.value) {
        state.selectedReportId = select.value;
        await loadSavedReport(select.value);
      }
    } catch (error) {
      select.innerHTML = '<option value="">تعذر تحميل السجلات — تحقق من المفتاح</option>';
      setNotice("تعذر تحميل سجل الجلسات: " + error.message);
    }
  }

  async function loadSavedReport(sessionId) {
    const [reportResponse, tracksResponse] = await Promise.all([
      api("/api/v1/lab/reports/" + sessionId),
      api("/api/v1/lab/reports/" + sessionId + "/tracks"),
    ]);
    const report = await reportResponse.json();
    const tracks = await tracksResponse.json();
    state.selectedReportId = sessionId;
    state.currentReport = report;
    state.selectedTrackId = null;
    state.selectedTrack = null;
    if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
    state.videoUrl = null;
    $("resultVideo").pause();
    $("resultVideo").removeAttribute("src");
    $("resultVideo").load();
    $("resultVideoWrap").hidden = true;
    clearHighlight("resultHighlightCanvas");
    state.trackById.clear();
    renderTrackReport(tracks);
    $("reportSession").textContent =
      "SESSION " + sessionId.slice(0, 8).toUpperCase() + " · " + report.status;
    const url = URL.createObjectURL(new Blob(
      [JSON.stringify({ report, tracks }, null, 2)],
      { type: "application/json" }
    ));
    if (state.reportUrl) URL.revokeObjectURL(state.reportUrl);
    state.reportUrl = url;
    $("downloadReport").href = url;
    $("downloadReport").download = "traffic-report-" + sessionId.slice(0, 8) + ".json";
    $("downloadReport").hidden = false;
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

  async function loadEvents() {
    try {
      const response = await api("/api/v1/events?limit=30");
      const events = await response.json();
      const list = $("eventList");
      list.innerHTML = "";
      $("eventCount").textContent = events.length + " EVENTS";
      if (!events.length) {
        list.innerHTML = '<div class="empty-state">لا توجد أحداث مسجلة بعد.</div>';
        return;
      }
      for (const item of events) {
        const row = document.createElement("article");
        row.className = "event-row";
        const marker = document.createElement("span");
        marker.className = "event-marker " + (item.severity || "info");
        const details = document.createElement("div");
        details.className = "event-details";
        const title = document.createElement("b");
        title.textContent = item.title || item.event_type || "حدث مروري";
        const meta = document.createElement("small");
        const occurred = item.occurred_at
          ? formatTimestamp(item.occurred_at)
          : "وقت غير محدد";
        meta.textContent = (item.camera_id || "كاميرا") + " · " + occurred;
        details.append(title, meta);
        const identity = document.createElement("span");
        identity.className = "event-identity";
        identity.textContent = item.track_id == null ? "—" : "#" + item.track_id;
        row.append(marker, details, identity);
        list.appendChild(row);
      }
    } catch (error) {
      $("eventList").innerHTML =
        '<div class="empty-state">تعذر تحميل الأحداث: ' + error.message + '</div>';
    }
  }

  async function loadCapabilities() {
    try {
      const response = await api("/api/v1/lab/capabilities");
      const info = await response.json();
      const compute = info.compute || {};
      if (compute.cuda_available) {
        $("runtimeComputeStatus").textContent = "تسريع GPU متصل";
        $("runtimeComputeDetail").textContent = compute.gpu_name || compute.device;
        $("analysisRuntimeNote").textContent =
          "ملف الرصد الحي: YOLO26n بحجم استدلال 384، ByteTrack، ودقة إدخال 640px. تم إيقاف ترميز MP4 أثناء البث لتقليل التأخير.";
      } else {
        $("runtimeComputeStatus").textContent = "المحرك يعمل على CPU";
        $("runtimeComputeDetail").textContent = "لا يوجد CUDA GPU متاح";
        $("analysisRuntimeNote").textContent =
          "تنبيه أداء: هذا التشغيل لا يملك GPU. الرصد الحي سيعمل لكن قد لا يحقق معدل الإطارات المطلوب؛ فعّل GPU في إعدادات Colab ثم أعد تشغيل Runtime.";
      }
      $("backendStatus").textContent = info.processing_ready
        ? (compute.cuda_available ? "YOLO · GPU" : "YOLO · CPU")
        : "حزم ناقصة: " + info.missing_packages.join(", ");
      $("makeModelAvailability").textContent = info.pretrained_vehicle_attributes_enabled
        ? "نماذج اللون والماركة تُحمّل بعد معالجة الفيديو"
        : info.vehicle_make_model_configured
          ? "مصنّف مخصص متصل"
          : "النماذج المتخصصة غير مفعّلة في إعدادات الخادم";
      $("makeModelAvailability").classList.toggle(
        "muted-value",
        !info.pretrained_vehicle_attributes_enabled && !info.vehicle_make_model_configured
      );
      if (!info.processing_ready) {
        setNotice(
          "بيئة التحليل غير مكتملة. الحزم المطلوبة: " +
          info.missing_packages.join(", ") + "."
        );
      } else if (info.model_will_download_on_first_use) {
        setNotice("سيتم تنزيل أوزان YOLO26n عند بدء أول جلسة تحليل.");
      } else {
        setNotice("", false);
      }
      await loadSavedReports();
      await loadEvents();
    } catch (error) {
      $("backendStatus").textContent = "أدخل مفتاح API";
      setNotice("أدخل مفتاح الجلسة الصحيح في الحقل العلوي لتفعيل واجهات التحليل.");
    }
  }

  const savedCalibration = localStorage.getItem("trafficLabLinePosition");
  if (savedCalibration && Number.isFinite(Number(savedCalibration))) {
    $("linePosition").value = String(Math.max(10, Math.min(90, Number(savedCalibration))));
    $("lineValue").textContent = $("linePosition").value + "%";
    $("calibrationLinePosition").value = $("linePosition").value;
    $("calibrationLineValue").textContent = $("linePosition").value + "%";
    $("calibrationStatus").textContent = "تم تحميل موضع خط العد المحفوظ محلياً";
  }
  $("apiKey").value = sessionStorage.getItem("trafficLabApiKey") || "";
  $("apiKey").addEventListener("change", () => {
    const key = $("apiKey").value.trim();
    if (key) {
      sessionStorage.setItem("trafficLabApiKey", key);
      loadCapabilities();
      loadSavedReports();
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
  $("refreshReports").addEventListener("click", loadSavedReports);
  $("refreshEvents").addEventListener("click", loadEvents);
  $("calibrationLinePosition").addEventListener("input", () => {
    $("calibrationLineValue").textContent = $("calibrationLinePosition").value + "%";
  });
  $("applyCalibration").addEventListener("click", () => {
    const value = $("calibrationLinePosition").value;
    $("linePosition").value = value;
    $("lineValue").textContent = value + "%";
    localStorage.setItem("trafficLabLinePosition", value);
    $("calibrationStatus").textContent =
      "تم حفظ موضع خط العد لهذا المتصفح؛ سيُستخدم في الجلسة التالية.";
  });
  document.querySelectorAll("[data-nav]").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll("[data-nav]").forEach((item) => item.classList.remove("active"));
      link.classList.add("active");
    });
  });
  $("savedReportSelect").addEventListener("change", () => {
    const sessionId = $("savedReportSelect").value;
    if (sessionId) loadSavedReport(sessionId).catch((error) => setNotice(error.message));
  });
  $("fullscreenMonitor").addEventListener("click", async () => {
    const frame = document.querySelector(".monitor-frame");
    try {
      if (!document.fullscreenElement) {
        await frame.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch (error) {
      setNotice("تعذر تفعيل ملء الشاشة: " + error.message);
    }
  });
  $("sourcePlayback").addEventListener("timeupdate", redrawSelectedTrack);
  $("sourcePlayback").addEventListener("seeked", redrawSelectedTrack);
  $("resultVideo").addEventListener("timeupdate", redrawSelectedTrack);
  $("resultVideo").addEventListener("seeked", redrawSelectedTrack);
  $("processedPreview").addEventListener("load", redrawSelectedTrack);
  window.addEventListener("resize", redrawSelectedTrack);
  $("toggleAnalysisView").addEventListener("click", () => {
    state.analysisView = !state.analysisView;
    $("sourcePlayback").hidden = state.analysisView;
    $("processedPreview").hidden = !state.analysisView;
    $("analysisModeNote").hidden = state.analysisView;
    $("toggleAnalysisView").textContent = state.analysisView
      ? "عرض الفيديو الأصلي"
      : "عرض إطار التحليل";
    if (state.analysisView) {
      $("sourcePlayback").pause();
    } else {
      $("sourcePlayback").play().catch(() => {});
    }
    redrawSelectedTrack();
  });
  $("confidence").addEventListener("input", () =>
    $("confidenceValue").textContent = $("confidence").value + "%"
  );
  $("linePosition").addEventListener("input", () => {
    $("lineValue").textContent = $("linePosition").value + "%";
    if ($("calibrationLinePosition")) {
      $("calibrationLinePosition").value = $("linePosition").value;
      $("calibrationLineValue").textContent = $("linePosition").value + "%";
    }
  });
  $("videoFile").addEventListener("change", () => {
    const file = $("videoFile").files[0];
    if (!file) return;
    $("selectedFile").textContent = file.name;
    $("fileMeta").textContent = file.name;
    $("filePreviewWrap").hidden = false;
    if (state.sourceUrl) URL.revokeObjectURL(state.sourceUrl);
    state.sourceUrl = URL.createObjectURL(file);
    $("localPreview").src = state.sourceUrl;
    $("sourcePlayback").src = state.sourceUrl;
    $("localPreview").onloadedmetadata = () => {
      $("fileDimensions").textContent =
        $("localPreview").videoWidth + " × " + $("localPreview").videoHeight +
        " · " + $("localPreview").duration.toFixed(1) + " ثانية";
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
