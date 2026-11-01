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

## المرحلة 2 — تشغيل فيديو حقيقي (Single camera vertical slice)
- CLI لتشغيل فيديو محلي مع أوزان يحددها المستخدم.
- حفظ فيديو annotated ومخرجات JSONL.
- detector + tracker + foot-point extraction.
- اختيار إطار زمني مصدر صحيح.
- إخراج خط سير track وعدّ line crossing.
- قياس الأداء CPU/GPU والذاكرة.

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

## المرحلة 5 — Multi-camera orchestration
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
