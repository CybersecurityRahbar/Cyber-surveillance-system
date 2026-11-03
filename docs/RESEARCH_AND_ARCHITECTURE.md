# البحث المرجعي: أنظمة المراقبة المرورية والأمنية بالفيديو

**تاريخ المراجعة:** 1 نوفمبر 2026  
**النطاق:** Intelligent Transportation Systems (ITS)، Video Management Systems (VMS)، Intelligent Video Analytics (IVA)، Multi-Camera Tracking.

## 1. التصحيح الأساسي لنطاق المنتج

المشروع ليس SIEM ولا Endpoint Protection. إنه نظام مركزي لتحليل الفيديو من كاميرات الطرق والمنشآت، واكتشاف الحركة والأحداث المرورية والأمنية المرئية، وتقديمها للمشغل في مركز تحكم.

## 2. الأنظمة والمنصات المرجعية

| النظام | الدور | ما نستفيده |
|---|---|---|
| NVIDIA DeepStream 9.2 | Video analytics pipeline | فك فيديو متعدد المصادر، preprocessing، batching، inference، tracking، tiling، metadata outputs، hardware acceleration |
| Ultralytics YOLO + Trackers | Object detection and tracking | كشف الكائنات وتتبع IDs مع ByteTrack وBoT-SORT وOC-SORT وDeep OC-SORT وFastTracker وTrackTrack |
| Milestone XProtect | VMS / Control room | Live + recorded views، camera wall، hotspots، maps، alarms، bookmarks، evidence locking |
| Frigate | Camera NVR + object detection | Zones، مناطق مقنّعة، فلاتر الأجسام، loitering، إدارة الكاميرات |
| CVAT | Video annotation | Tracks، keyframes، interpolation، إعداد بيانات تدريب واختبار عالية الجودة |
| OpenCV | Image/video processing and geometry | فك الفيديو، تحويل الإطارات، معايرة، Homography، معالجة هندسية |
| AI City Challenge | Research benchmark | multi-camera tracking، traffic safety analysis، road-object/fisheye detection، anomalous transportation |
| HOTA / TrackEval | Tracking evaluation | قياس جودة الكشف والارتباط والتموضع بدل الاكتفاء بالدقة أو FPS |

### أ. NVIDIA DeepStream

DeepStream 9.2 يبني graph على GStreamer: مصادر فيديو → decoder → preprocessing → stream muxer لدمج الإطارات من عدة مصادر → inference → tracker → visualization/tiler → output أو metadata broker. يدعم مصادر USB/CSI وRTSP والملفات، ويسمح بإرسال الفيديو أو metadata إلى الوجهات.

**قرارنا:** نحتفظ بمسار Python عام قابل للتشغيل على CPU/أجهزة متعددة، ونضع DeepStream كـ backend تسريع اختياري عندما يكون الخادم مزوداً بعتاد NVIDIA مدعوم. وثائق 9.2 تشير إلى أن Python bindings القديمة Deprecated وتوصي بـ PyServiceMaker؛ لذا لا نبني تصميم المستقبل على bindings القديمة.

### ب. كشف وتتبع الأجسام

الكشف يحدد صنف الجسم وموقعه في الإطار، والتتبع يربط مشاهدات الجسم عبر الإطارات ويمنحه track ID مؤقتاً داخل الكاميرا.

- **ByteTrack:** خط أساس خفيف؛ يربط الصناديق عالية الثقة ثم يستعيد بعض الصناديق منخفضة الثقة لتقليل فقد التتبع.
- **BoT-SORT:** يضيف تعويض حركة الكاميرا وإمكانية Re-ID.
- **OC-SORT / Deep OC-SORT:** يستخدمان تحديثات تركز على المشاهدات للتعامل مع الحركة غير الخطية والانسداد.
- **FastTracker:** خيار خفيف مع rollback للتعامل مع الانسداد.
- **TrackTrack:** association متعددة الإشارات وتهيئة track واعية بالتكرار، مفيد للمشاهد المزدحمة وفق المقارنة في الوثائق الحالية.

لا يوجد tracker أفضل لكل كاميرا. يجب benchmark على زاوية الكاميرا والدقة والازدحام والأجسام الصغيرة والإضاءة الليلية ومعدل الإطارات. لكل stream حالة tracker منفصلة؛ لا تشارك حالة tracker بين كاميرتين.

### ج. المعايرة وقياس السرعة

قياس السرعة من monocular CCTV أصعب من تحويل إزاحة pixels إلى رقم. المطلوب عادة:
1. تحديد موضع ملامسة المركبة للطريق (bottom-center / road contact point).
2. معرفة نقاط في الصورة تقابل نقاطاً أرضية مقاسة بالأمتار.
3. تقدير Homography بين مستوى الصورة ومستوى الطريق.
4. إسقاط نقاط track إلى المستوى المتري.
5. قياس المسافة المترية على مدى زمني موثوق.
6. التحقق مقابل رادار أو مرجع مستقل وقياس الانحياز وMAE.

الطريق يفترض تقريباً سطحاً مستوياً في المنطقة المعايرة؛ الميل والتضاريس والمنحنيات أو تغير موضع الكاميرا قد تتطلب calibration أكثر تعقيداً أو إعادة معايرة. أي تغيير في موضع/Zoom/Focus/زاوية الكاميرا قد يبطل المعايرة.

**قرار أمان:** وقت وصول RTSP/MJPEG عبر الشبكة ليس بالضرورة وقت التقاط الكاميرا. لا نستخدم وصول الإطار إلى الخادم لفرض مخالفة سرعة. يجب أن يكون الزمن المصدر أو PTS موثوقاً، والمعايرة موثقة، وقياس السرعة مختبراً.

### د. Multi-camera tracking

نبدأ بتتبع محلي لكل كاميرا. الانتقال عبر الكاميرات يتطلب:
- تزامن ساعات الكاميرات.
- مواقع الكاميرات ومجالات الرؤية.
- مناطق تداخل أو بوابات انتقال.
- أزمنة سفر منطقية.
- Re-ID/appearance embeddings عند الحاجة وبعد مراجعة الخصوصية.
- confidence score وسجل سبب الربط.

معرّف track داخل كاميرا واحدة ليس هوية عالمية، ولا يعني أن جسمين متشابهين في كاميرتين هما الجسم نفسه.

### هـ. واجهات مراكز التحكم

من تجربة XProtect وSmart Wall نتعلم:
- Views متعددة قابلة للتخصيص.
- تخطيط Grid لكاميرات متعددة.
- Hotspot لعرض الكاميرا المختارة بدقة أكبر.
- Alarm list مرتبة وقابلة للإقرار والإسناد.
- Smart maps تظهر الكاميرات والأحداث ومواقعها.
- Bookmarks ومقاطع وسياق زمني للتحقيق.
- Video wall يمكن توجيه الأحداث الحرجة إليه.

من Frigate نتعلم أن Zone ليست مجرد مستطيل: يمكن تعريف مضلع، وربطه بأنواع أجسام، وعتبة تواجد، وسلوك مثل loitering. يجب أن يعتمد دخول المنطقة على نقطة تمثيل للكائن مناسبة للمشهد؛ نقطة أسفل الصندوق قد تكون أفضل من تداخل مساحة الصندوق كلها مع المنطقة.

## 3. خوارزميات ومنظومة التحليل المقترحة

### 3.1 طبقة الرؤية
- Object detection للمركبات، الحافلات، الشاحنات، الدراجات، الأشخاص، والعناصر المهمة بحسب السيناريو.
- Segmentation عند الحاجة إلى فهم حدود الطريق والممرات.
- Vehicle/person keypoints أو orientation عند الحاجة إلى اتجاه وحجم أفضل.
- OCR/ANPR كإضافة اختيارية فقط بعد تثبيت الحاجة والضوابط القانونية.
- Image quality/anomaly: blur، darkness، glare، camera moved، frozen frames.

### 3.2 طبقة التتبع
- Kalman motion prediction.
- IoU / Hungarian assignment.
- ByteTrack-style two-stage association.
- Appearance Re-ID optional.
- Optical-flow/global-motion compensation للكاميرات المتحركة.
- Lost-track recovery وduplicate-track suppression.
- تقييم HOTA وIDF1 وMOTA وfragmentation على dataset معلّمة.

### 3.3 تحليلات المرور
- Line crossing وdirectional counting.
- Lane/zone occupancy and density.
- Speed estimation after ground-plane calibration.
- Wrong-way candidate from projected direction vs configured lane vector.
- Queue length and congestion over a time window.
- Stopped vehicle detection from low world-coordinate displacement over time.
- Road blockage detection from persistent occupancy.
- Traffic light state recognition كمسار مستقل يتطلب dataset وتحققاً.
- Near-miss/risk interaction: أقرب مسافة ومسارات متقاطعة وتوقيت الاقتراب كإشارة مرشحة، لا كحكم حادث مؤكد.

### 3.4 تحليلات الأمن المرئي
- Restricted-zone intrusion.
- Virtual tripwire/perimeter crossing.
- Loitering with dwell-time thresholds.
- Crowd-density anomalies.
- Abandoned/unattended object candidates.
- After-hours motion rules.
- Camera tampering / occlusion / field-of-view change.
- كل إنذار يعرض clip وframe وtrack context والقاعدة والحدود والـ confidence؛ يحتاج مراجعة بشرية.

## 4. ابتكارات مقترحة لهذا المشروع

### Traffic Flow Digital Twin Lite
تمثيل التقاطع/المقطع المروري في إحداثيات أرضية، وتكوين مسارات track مترية، ثم استخراج التدفق والكثافة والسرعة والصفوف ومناطق التعارض. يبدأ كطبقة هندسية ثنائية الأبعاد بدلاً من بناء محاكاة ثلاثية الأبعاد باهظة.

### Risk Interaction Engine
يبني مسارات متوقعة قصيرة للمركبات والمشاة، ويقيس closest approach وtime-to-collision وoverlap of predicted corridors. ينتج مؤشر خطر قابل للتفسير، مع تجنب ادعاء collision إذا كانت الإشارات غير كافية.

### Camera Health & Blind-Spot Monitor
يراقب انقطاع البث، تجمد الإطار، التأخر، blur، dark frames، انسداد العدسة، فقدان الحقول الزمنية، وتغير منظور الكاميرا. يوقف صلاحية المعايرة عندما تتغير هندسة الصورة ويطلب إعادة فحص.

### Cross-Camera Handoff
يربط track بين كاميرتين عبر بوابات مكانية وزمنية ومعالم مركبة عامة (اختياري)، ويعرض confidence والتفسير، مع قابلية رفض الربط. لا نحول similarity إلى هوية إنسان مؤكدة.

### Evidence Timeline
يحتفظ بمقطع قبل الحدث وبعده، لقطات مفتاحية، track metadata، مصدر الإطار وPTS، calibration version، hash، ومَن فتح أو صدّر الدليل. تُضاف سلسلة الحيازة القانونية فقط بعد تنفيذ سياسات غير قابلة للعبث واختبارها.

## 5. المعمارية التقنية المقترحة

~~~text
CAMERA SOURCES
RTSP / ONVIF / USB / ESP32 MJPEG / Files
        |
SOURCE ADAPTERS + CAMERA HEALTH
        |
DECODE / FRAME PTS / SYNCHRONIZATION
        |
DETECTION (YOLO / ONNX / OpenVINO / DeepStream)
        |
PER-CAMERA TRACKERS (ByteTrack / BoT-SORT / ...)
        |
GROUND-PLANE CALIBRATION + MULTI-CAMERA ALIGNMENT
        |
+-----------------------------+-----------------------------+
| TRAFFIC ANALYTICS           | VISUAL SECURITY ANALYTICS    |
| speed / count / lanes       | zone / tripwire / loitering  |
| direction / queue / risk    | crowd / object / perimeter   |
+-----------------------------+-----------------------------+
        |
EVENT CORRELATION + EVIDENCE CLIPS
        |
API / DB / SEARCH / AUDIT
        |
CENTRAL CONTROL ROOM WEB UI
~~~

### طبقات التنفيذ
- **Python control plane:** إعداد الكاميرات، قواعد التحليل، الأحداث، التخزين، API، والتقارير.
- **Video data plane:** workers منفصلة لكل كاميرا أو مجموعة كاميرات، وتستطيع استخدام CPU/GPU backends.
- **Inference backend:** واجهة abstract تسمح بتبديل Ultralytics/ONNX Runtime/OpenVINO/DeepStream حسب العتاد والترخيص.
- **Event storage:** SQLite للتطوير الفردي، ثم PostgreSQL للبيانات التشغيلية، وClickHouse عند احتياج أحداث عالية الحجم، وobject storage للمقاطع.
- **Frontend:** React + TypeScript، بث WebRTC/HLS حسب التأخير والبنية، WebSocket/SSE للـ metadata والإنذارات.
- **Messaging:** لا نضيف Kafka/NATS في البداية قبل قياس streams وFPS وعدد workers. يمكن استخدامهما عند الحاجة للفصل وإعادة المحاولة وتوسيع المعالجة.

## 6. البيانات المرجعية والاختبار

- AI City Challenge 2026: تحديات متعددة الكاميرات وثلاثية الأبعاد وحركة الأشخاص/المركبات وتحليل السلامة المرورية.
- AI City Challenge 2025: تتبع متعدد الكاميرات، Traffic Safety Description and Analysis، fisheye road-object detection.
- BrnoCompSpeed: مرجع معروف لقياس سرعة المركبات من كاميرات المرور.
- MOTChallenge/TrackEval: قياس جودة التتبع؛ لا يكفي تقييم detector وحده.
- CVAT: تعليم tracks وkeyframes وإعداد مجموعة اختبار داخلية.

لا نبدأ تدريب نموذج ضخم قبل أن نحدد classes والسيناريوهات وزاوية الكاميرا والدقة ونحصل على dataset ممثل. يمكن البدء بنماذج عامة للكشف ثم بناء dataset خاص للمناطق والأحداث المحلية عند توافر صور وفيديو مصرح بها.

## 7. قيود العتاد والاستراتيجية

- CPU-only: عدد كاميرات قليل ودقة أو FPS محدودان، مع sampling مدروس.
- GPU استهلاكي بذاكرة محدودة: نموذج صغير أو ONNX، batching محسوب، decoding مناسب، وتحديد FPS لكل كاميرا.
- NVIDIA T4/Jetson مدعوم: تقييم DeepStream/TensorRT لتوسيع عدد streams.
- لا نعد بعدد كاميرات أو FPS مسبقاً؛ يجب benchmark على نفس الدقة والترميز ومعدل الإطارات وطراز GPU وعمليات التسجيل.
- نحتفظ بمسار inference خارجي/موزع لاحقاً إذا كان الخادم المركزي لا يستطيع فك كل الفيديو وتحليله.

## 8. المصادر الرسمية والأبحاث التي تمت مراجعتها

1. NVIDIA DeepStream 9.2 overview and architecture: https://docs.nvidia.com/metropolis/deepstream/9.2/text/DS_Overview.html
2. NVIDIA DeepStream SDK guide: https://docs.nvidia.com/deepstream/9.2/
3. DeepStream reference application: https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_ref_app_deepstream.html
4. Ultralytics tracking documentation: https://docs.ultralytics.com/modes/track/
5. Ultralytics tracking datasets overview: https://docs.ultralytics.com/datasets/track/
6. AI City Challenge 2026: https://www.aicitychallenge.org/
7. AI City Challenge 2026 Track 1: https://www.aicitychallenge.org/2026-track1/
8. AI City Challenge dataset access: https://www.aicitychallenge.org/ai-city-challenge-dataset-access/
9. AI City Challenge 2025: https://www.aicitychallenge.org/2025-ai-city-challenge/
10. HOTA paper: https://arxiv.org/abs/2009.07736
11. Robust Automatic Monocular Vehicle Speed Estimation for Traffic Surveillance (ICCV 2021): https://openaccess.thecvf.com/content/ICCV2021/papers/Revaud_Robust_Automatic_Monocular_Vehicle_Speed_Estimation_for_Traffic_Surveillance_ICCV_2021_paper.pdf
12. Automatic Roadside Camera Calibration with Transformers: https://pmc.ncbi.nlm.nih.gov/articles/PMC10708783/
13. Vision-based vehicle speed estimation survey: https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/itr2.12079
14. Toward Planet-Wide Traffic Camera Calibration (WACV 2024): https://openaccess.thecvf.com/content/WACV2024/papers/Vuong_Toward_Planet-Wide_Traffic_Camera_Calibration_WACV_2024_paper.pdf
15. Milestone XProtect Smart Client 2026r1: https://doc.milestonesys.com/xprotect/xprotect-smart-client/2026r1/en/what-is-xprotect-smart-client-.html
16. Milestone XProtect Smart Maps: https://doc.milestonesys.com/xprotect/xprotect-smart-client/2026r1/en/maps-and-smart-maps-197006
17. Milestone XProtect Smart Wall: https://doc.milestonesys.com/xprotect/xprotect-smart-wall-for-users/2026r1/en/displaying-content-on-video-walls.html
18. Frigate zones: https://docs.frigate.video/configuration/zones/
19. CVAT track mode and interpolation: https://docs.cvat.ai/docs/annotation/manual-annotation/modes/track-mode-basics/

### ملاحظة حول المصادر
الوثائق تشرح إمكانات الأدوات المرجعية، والأبحاث توضح أساليب القياس. لا يعني ذلك أن دمج هذه المكونات في مشروعنا جاهز أو أن نتائجها ستنتقل مباشرة إلى كاميراتنا. سنختبر كل خوارزمية على فيديوهات ممثلة ونحتفظ بمقاييس الأخطاء والموارد قبل اعتمادها.


---

## تحديث البحث: المختبر أحادي الكاميرا وبث الهاتف

### YOLO26 والمتتبعات
وثائق Ultralytics الحالية تعرض YOLO26 كأحدث عائلة معلنة في يناير 2026. نموذج YOLO26n هو نقطة بداية صغيرة للمختبر، لكن لا نفترض FPS أو دقة قبل benchmark على CPU/GPU الفعلي.

وثائق Track Mode تعرض ستة متتبعات:
- ByteTrack: association على مرحلتين واسترجاع الصناديق منخفضة الثقة، كبداية خفيفة.
- BoT-SORT: Kalman مع تعويض حركة الكاميرا وإمكانية ReID.
- OC-SORT وDeep OC-SORT: observation-centric لمواجهة الحركة غير الخطية والـ occlusion.
- FastTracker: استعادة عبر rollback عند الانسداد.
- TrackTrack: ربط متعدد الإشارات.

تستمر حالة tracker عبر الإطارات المتتابعة من المصدر نفسه؛ لذلك ينشئ المختبر detector/tracker جديداً لكل فيديو أو جلسة بث ولا يعيد استخدام حالة بين مصادر مختلفة.

### DeepStream 9.2
DeepStream Service Maker لـ Python يقدم Flow APIs لتجميع capture/inference/tracking/output، وPipeline APIs لتخصيص أعمق، ويتطلب DeepStream SDK أو Docker مدعوماً. نحتفظ به كمسار تسريع اختياري عند توفر خادم NVIDIA مناسب، وليس شرطاً للنواة العامة.

### التوقيت والفيديو
PyAV مبني على FFmpeg ويتيح الوصول إلى frame PTS وtime_base. يعتمد المختبر على PyAV لاستخراج توقيت الإطار عندما يكون موجوداً. كاميرا webcam المحلية تستخدم arrival monotonic timing ولا تعتبر PTS للمصدر.

### MediaMTX لتجميع بث الهاتف والكاميرات
MediaMTX خادم وسائط متعدد البروتوكولات:
- WebRTC publish/read مع WHIP للنشر.
- RTSP للكاميرات والبث الداخلي.
- SRT للنقل المرن مع retransmission.
- RTMP وHLS وغيرها.

القرار المقترح للهاتف: WebRTC/WHIP للنشر من Android إلى MediaMTX، ثم RTSP داخلي إلى Python. عند ضعف الشبكة نختبر SRT. لا نبني تطبيق الهاتف على الاتصال الوارد المباشر للهاتف عبر الإنترنت بسبب NAT وعناوين الهاتف المتغيرة.

### ANPR/OCR
YOLO26n العام يصنف المركبات لكنه لا يقرأ اللوحات. مسار ANPR الصحيح:
1. Vehicle detection/tracking.
2. Plate detector متخصص، مدرب/مختبر على شكل اللوحات المحلي.
3. تصحيح المنظور وقص اللوحة واختبار جودة الصورة.
4. OCR يدعم الأرقام والحروف المحلية.
5. Temporal consensus عبر عدة إطارات للمركبة نفسها.
6. إظهار القراءة فقط إذا كانت الثقة والجودة كافيتين، وإلا إبقاء crop للمراجعة.

PaddleOCR يملك إصدارات حديثة مثل PP-OCRv6، لكن النموذج العام لا يضمن القراءة الصحيحة لنمط اللوحة المحلي دون تهيئة وتقييم.

### الترخيص
Ultralytics تنص على أن الشيفرة والأوزان تقع افتراضياً تحت AGPL-3.0، وأن الاستخدامات التي لا تريد الالتزام بشروطها قد تحتاج Enterprise License. يجب مراجعة الشروط قبل توزيع المنتج أو استخدامه تجارياً.

### مصادر إضافية
- YOLO26 models: https://docs.ultralytics.com/models/yolo26
- Ultralytics tracking: https://docs.ultralytics.com/modes/track/
- Ultralytics license: https://www.ultralytics.com/license
- DeepStream Service Maker Python: https://docs.nvidia.com/metropolis/deepstream/9.2/text/DS_service_maker_python
- MediaMTX introduction: https://mediamtx.org/docs/kickoff/introduction
- MediaMTX publish/read protocols: https://mediamtx.org/docs/features/publish-and-read
- MediaMTX WebRTC publisher/WHIP: https://mediamtx.org/docs/publish/webrtc
- MediaMTX SRT: https://mediamtx.org/docs/publish/srt
- MediaMTX ICE/STUN/TURN: https://mediamtx.org/docs/features/webrtc-specific-features
- PyAV time and frame PTS: https://pyav.basswood.io/docs/stable/api/time.html
- OpenCV video I/O properties: https://docs.opencv.org/4.12.0/d4/d15/group__videoio__flags__base.html
- Milestone XProtect 2026r1 views and video wall: https://doc.milestonesys.com/xprotect/xprotect-smart-client/2026r1/en/content-in-view-items
- PaddleOCR PP-OCRv6: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md


## 9. التعرف على لون المركبة والماركة/الطراز

- كشف YOLO العام يصنف فئة المركبة ولا يتعرف وحده على الماركة أو الطراز.
- أضيف تقدير لون HSV مبسط من منطقة داخل صندوق المركبة مع تجميع عينات عبر عدة إطارات. هذا تقدير heuristic حساس للإضاءة والانعكاس والخلفية، ويُحفظ معه confidence وعدد العينات. ليس بديلاً عن مصنف ألوان مدرب.
- يمكن ربط مصنف سيارات fine-grained منفصل من نوع Ultralytics `classify` عبر `TRAFFIC_SURVEILLANCE_VEHICLE_MODEL_PATH`. يجب أن تكون الفئات التي دُرب عليها النموذج واضحة، وأن تكون البيانات والأوزان مرخصة للغرض المقصود. لا تتضمن الشيفرة أوزاناً جاهزة لتحديد Toyota Hilux أو Hyundai Tucson أو Mercedes G-Class.
- CompCars يضم تصنيفات make/model كثيرة لكنه للاستخدام البحثي غير التجاري وفق ترخيصه/شروطه: https://mmlab.ie.cuhk.edu.hk/datasets/comp_cars/
- DeepCar 5.0 مجموعة بحثية أيضاً: https://github.com/DeepCar/Deepcar5.0
- يمكن استخدام نموذج تقدير اللون المفتوح MIT المتاح هنا كبديل لاحق للـHSV: https://huggingface.co/piotreksl/vehicle-color-recognition
- قبل اعتماد مصنف make/model، يجب تقييم top-1/top-5 accuracy حسب زاوية الكاميرا، حجم المركبة، الطقس، والبلد/السوق. لا نعتبر التنبؤ صحيحاً لمجرد ظهور اسم طراز.
