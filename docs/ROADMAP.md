# خارطة تطوير نظام المراقبة المرورية والأمنية

## المرحلة 0 — فهم النطاق والبحث
**الحالة: مكتملة ومصححة**
- مراجعة مشروع Android السابق واستخلاص الدروس الهندسية.
- بحث الأنظمة المرجعية ITS/VMS/IVA وDeepStream وYOLO trackers ومعايرة السرعة.
- استبدال التفسير السابق الخاطئ: المنتج هو مراقبة مرورية وأمنية مرئية بالكاميرات، لا Endpoint Security.

## المرحلة 1 — Python Vision Core
**الحالة: أساس أولي قيد الاختبار**
- عقود Camera / Detection / Track / Event.
- Homography projection إلى مستوى الطريق.
- Speed estimator مع شرط معايرة وتوقيت موثوقين.
- Line crossing وZone intrusion وLoitering.
- قاعدة Over-speed لا تعمل إلا للقياس المؤهل.
- Video source adapter وUltralytics detector/tracker optional.
- SQLite event store وFastAPI endpoints.
- Unit/API tests وCI.

**حد القبول:**
- اختبارات geometry/speed/line/zone/storage/API ناجحة.
- لا يُصدر speeding alert إذا كان التوقيت Arrival-only أو calibration غير مؤكدة.
- تخزين الأحداث يبقى بعد إعادة تشغيل التطبيق.
- توضيح عدم وجود كاميرات متصلة في بيئة CI.

## المرحلة 2 — المختبر أحادي الكاميرا
- واجهة /lab لرفع فيديو محلي أو تشغيل مصدر RTSP/كاميرا خادم.
- YOLO26n optional + متتبعات ByteTrack/BoT-SORT/OC-SORT وغيرها.
- Green radar boxes وTrack IDs وclass labels وtrails.
- unique track counts وvirtual line crossing counts.
- processed preview أثناء المعالجة وMP4 output.
- اختبار فيديو synthetic في CI وFake detector دون أوزان حقيقية أو كاميرا فعلية.
- تحديث 3 نوفمبر: واجهة مختبر جديدة، MJPEG preview، track inspector، وتصدير تقارير JSON.
- تحديث 3 نوفمبر: SQLite per-session/per-track reports وHSV vehicle colour estimate وoptional make/model classifier hook.
- تحديث 3 نوفمبر: Colab final supervisor cell remains running while it monitors Uvicorn/tunnel.
- الخطوة التالية: تجربة المستخدم على فيديو مرور واقعي ثم benchmark CPU/GPU/الذاكرة والـpreview latency.


## المرحلة 2.1 — بيئة اختبار Google Colab
**الحالة: ملفات التشغيل جاهزة، بانتظار تجربة المستخدم الفعلية**
- دفتر Colab لتثبيت محرك الفيديو وYOLO على Runtime مع GPU اختياري.
- تشغيل FastAPI محليًا داخل الجلسة، مع Cloudflare Quick Tunnel أو ngrok.
- API key إلزامي لحماية عمليات المختبر عند نشر الرابط العام.
- اختيار حفظ نتائج المختبر وقاعدة البيانات في Google Drive أو مساحة الجلسة المؤقتة.
- الخطوة التالية: تشغيل notebook على Colab، رفع فيديو مرور حقيقي، وتسجيل FPS والذاكرة وجودة الكشف والتتبع.
- حد القبول: فتح الصفحة العامة، التحقق من API key، رفع الفيديو، ظهور preview، توليد MP4، واسترجاع ملخص العدّ.


## المرحلة 2.2 — تحسينات المختبر والتحقق من التقارير
**الحالة: التنفيذ البرمجي موجود؛ تحقق الفيديو الواقعي ينتظر تشغيل Colab**
- Modern RTL operations UI، active-object list خارج الفيديو، compact labels، vehicle/person colour separation.
- MJPEG preview بمعدل محدد لتقليل ضغط الواجهة.
- Session/track persistence في SQLite مع JSON report.
- Approximate paint-colour estimation.
- Optional fine-grained vehicle classifier hook; no default weights included.
- CI tests for track reports, SQLite persistence, API key, MJPEG multipart, HTML assets and notebook/JS syntax.
- القبول الميداني: اختبار مقاطع نهارية/ليلية متعددة الدقات، قياس preview latency وprocessing FPS، مقارنة عدّ Track يدوي، ومراجعة جودة اللون.

## المرحلة 3 — Calibration Studio and Traffic Analytics
- واجهة معايرة camera-specific.
- RANSAC + inlier validation + reprojection error.
- BEV preview.
- السرعة المترية والتحقق الميداني.
- lanes وdirection vectors.
- count/flow/density/queue length.
- wrong-way / stopped vehicle / road blockage.

## المرحلة 4 — Visual Security Analytics
- zone intrusion / perimeter crossing.
- loitering / crowding / abandoned-object candidates.
- camera occlusion / frozen frame / tamper.
- review workflow لتقليل false positives.

## المرحلة 5 — تطبيق الهاتف وبوابة البث ثم Multi-camera orchestration
**الحالة الحالية:** تطبيق Android MVP موجود ويعمل ببث WSS/JPEG أحادي الكاميرا. تم اختبار اتصال الهاتف فعلياً بخادم Colab، لكن معدل التحليل في اختبار المستخدم لم يحقق بعد سلاسة الرصد المطلوبة.

- المنفذ حالياً: Android CameraX 640×360، تحويل YUV إلى JPEG، WSS مع X-API-Key، معاينة الهاتف، تخطيط Landscape/scroll/full-screen وأيقونة خاصة.
- يستقبل Python الإطارات عبر LatestFrameBuffer محدود بإطار واحد، ويستبدل الإطار القديم بدلاً من بناء طابور متأخر.
- المسار الحي يستخدم YOLO26n/ByteTrack بإعداد أقل كلفة، ويحدث هويات التتبع ومؤشرات التأخير أثناء الجلسة دون انتظار التقرير النهائي.
- التالي: اختبار FPS الوارد من الهاتف مقابل FPS المعالجة وJPEG encode ms وinference latency وframe age على الهاتف وColab؛ لا يعتمد النظام حتى يحقق قياسات مستقرة على عتاد مستهدف.
- تطوير لاحق: Android Foreground Service، H.264 hardware encoder، WebRTC/WHIP، MediaMTX وTURN، ثم إدارة عدة كاميرات ومزامنتها.
- كاميرات RTSP/ONVIF/USB/ESP32 MJPEG وملفات.
- process منفصل أو worker لكل stream.
- health monitoring وreconnect/backoff.
- مزامنة الوقت والتعامل مع dropped frames.
- stream isolation للـ tracker.
- cross-camera handoff لاحقاً في حال وجود تداخل ومعايرة مناسبة.

## المرحلة 6 — Durable video and evidence platform
- PostgreSQL metadata and configuration.
- Video/clip storage with retention policies.
- pre-event/post-event clip buffer.
- checksums وaudit trail وcontrolled export.
- search by time/camera/event/track.
- RBAC ومصادقة وإدارة مفاتيح.

## المرحلة 7 — Central Web Console
- React + TypeScript.
- Camera Wall + Hotspot.
- Traffic analytics dashboards.
- Alarms and incident workspace.
- Calibration Studio + Zones & Lines editor.
- Playback and Evidence.
- Arabic/English and RTL.

## المرحلة 8 — High-performance inference and advanced analytics
- ONNX Runtime/OpenVINO/DeepStream evaluation.
- GPU decode and batched inference.
- ReID and multi-camera track association.
- Traffic digital-twin-lite.
- Risk interaction / near-miss candidates.
- Model evaluation on local data and public benchmarks.
- Model/version registry and drift monitoring.

## المرحلة 9 — Field validation and production
- اختبار ليلي ونهاري، أمطار وغبار، زوايا ودقات مختلفة.
- قياس precision/recall لكل class/rule.
- قياس HOTA/IDF1 للتتبع.
- قياس MAE/bias لسرعة المركبات.
- benchmark لعدد الكاميرات وFPS وlatency وRAM/VRAM.
- حماية الشبكة وصلاحيات المشغلين والخصوصية.
- توثيق حدود كل ميزة قبل اعتمادها ميدانياً.


## المرحلة 2.3 — الرصد الحي منخفض التأخير وهويات التتبع المباشرة (2026-11-04)
**الحالة البرمجية:** تغييرات المحرك والواجهة واختبارات CI ناجحة؛ قياس الأداء الجديد على Colab وهاتف المستخدم لم يُنفذ بعد.

- اعتماد LatestFrameBuffer سعة إطار واحد مع latest-frame-wins لمنع تراكم إطارات قديمة.
- ملف Live منفصل عن تحليل الملفات: ByteTrack افتراضياً، YOLO26n imgsz=384، max_det=30، max_width=640، وإيقاف MP4 encode وسمات المركبات الثقيلة داخل حلقة الإطار.
- بث snapshot للهويات النشطة إلى لوحة المهام لكل إطار محلل، مع TTL ثلاث ثوانٍ، وترتيب الأحدث أولاً.
- تحديث جدول التتبع المباشر في المتصفح كل 350ms، وتحديث الأحداث كل 2.5 ثانية، وإبقاء التقرير النهائي في SQLite بعد الإيقاف.
- إضافة telemetry: camera ingress FPS، processing FPS، inference latency، frame age، received frames، replaced/dropped frames، وعدد الهويات النشطة.
- تطبيق Android: تحسين نسخ YUV وتحويل JPEG، وعرض FPS الرفع ومقاس الإطار ومتوسط encode ms والتخطي الشبكي/الزمني.
- واجهة Deep Navy زرقاء، رادار 16:9 متناسق، أقسام Analytics/Events/Reports/Camera Setup مربوطة، Layout أفقي للهاتف وتمرير وملء الشاشة وأيقونة.
- خط معايرة العد الحالي يحفظ موضع الخط محلياً فقط؛ لم تُنفذ بعد معايرة Homography المترية أو قياس سرعة موثوق.
- Camera Wall الحالي يعرض مصدراً واحداً؛ لم تُنفذ بعد مصفوفة متعددة الكاميرات أو cross-camera identity.
- سجل قياس المستخدم قبل هذه التغييرات: 111 إطاراً محللاً، 1.72 FPS، 99 إطاراً ساقطاً، 60.3 ثانية، و0.72×. هذا خط أساس للمقارنة وليس نتيجة بعد الإصلاح.
- حد القبول التالي: تسجيل ingress FPS وprocessing FPS وp50/p95 inference latency وframe age في جلسة 3 دقائق على GPU معروف؛ مقارنة عد المركبات يدوياً، واختبار عدم تأخر الهويات في الجدول. لا ندعي 10 FPS أو أقل من ثانية قبل هذا القياس.
