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
- Android CameraX + MediaCodec H.264 + WebRTC/WHIP publisher.
- MediaMTX كـ media gateway، ثم قراءة RTSP داخلياً في Python.
- VPN/TLS ومصادقة نشر لكل stream، وعدم نشر منافذ الكاميرات للعامة.
- بعدها إدارة عدة كاميرات ومزامنتها.
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
