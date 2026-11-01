# خارطة بناء النظام

**الحالة الحالية:** Phase 0 مكتملة توثيقياً، وPhase 1 بدأ بنواة Ingestion/Normalization/Detection قابلة للاختبار.

## مبادئ ترتيب العمل

- نبني Vertical Slice صغيرة قابلة للتشغيل ثم نوسعها.
- لا نضيف مكونات تشغيلية ثقيلة قبل benchmark يثبت الحاجة.
- لا نبني عدة واجهات ومصادر قبل تثبيت نموذج الحدث.
- كل مرحلة تنتهي باختبارات CI وتحديث PROJECT_CONTEXT.md.
- العمل مباشرة على main حسب تفضيل المستخدم، ما لم تتعارض سياسة المستودع مع ذلك.

## Phase 0 — Research and project foundation

**الحالة: منجزة**
- مراجعة أنظمة SIEM/XDR/NSM والـ detection frameworks.
- تعريف المجال على أنه مراقبة سيبرانية دفاعية.
- وضع التصميم الطبقي والمبادئ والأمان.
- إضافة ملف بحث وUI specification وroadmap.

## Phase 1 — Python core vertical slice

**الحالة: التنفيذ الأولي أُضيف**
- FastAPI application factory.
- Pydantic configuration and event model.
- Event normalization with raw-event retention.
- In-memory repository behind an abstraction.
- Authentication failure burst rule.
- REST ingest/events/alerts/status/health endpoints.
- Unit/API tests and GitHub Actions.

**معيار القبول:**
- بناء الحزمة وتثبيت الاعتمادات.
- جميع اختبارات الوحدة والـ API ناجحة.
- رفض مفتاح API غير الصحيح.
- عدم تكرار الحدث ذي المعرف نفسه.
- كشف موجة فشل تسجيل الدخول في النافذة المحددة.
- إظهار أن التخزين الحالي مؤقت وغير دائم بوضوح.

## Phase 2 — Durable storage and event search

- PostgreSQL للبيانات التشغيلية والحالات والسياسات.
- تقييم OpenSearch مقابل ClickHouse للأحداث حسب workload، وليس بالحدس.
- Migrations وretention وindices وbackups.
- Pagination وtime range filtering وsearch.
- Dead-letter storage للأحداث غير الصالحة مع سبب الرفض.
- اختبار استعادة النسخ الاحتياطية.

## Phase 3 — Real ingestion connectors

التوصيل على مراحل وبإذن صريح:
- Syslog over TCP/TLS وUDP في بيئة موثوقة مع توثيق مخاطر UDP.
- قراءة Zeek JSON logs.
- قراءة Suricata EVE JSON.
- Wazuh alerts/API.
- osquery/Fleet export.
- Cloud audit APIs بعد تحديد مزود السحابة.

كل Connector له schema mapping واختبارات عينات وhealth metrics.

## Phase 4 — Detection and correlation engine

- Rule registry/versioning.
- Sigma parser/import بعد تدقيق توافق الحقول.
- Time-window and threshold aggregations.
- Stateful sequence rules.
- Cross-source correlation.
- Alert fingerprint and dedup.
- ATT&CK v20 metadata synchronization and coverage view.
- Detection replay/regression.

## Phase 5 — SOC Web Interface

- React + TypeScript.
- Overview + Live Events + Alerts Queue.
- Investigations and Episode Graph.
- Asset/Sensor inventory.
- Detection Center.
- Authentication, RBAC, audit logs.
- Arabic/English, RTL, accessibility.

## Phase 6 — Threat intelligence and incident response

- STIX/TAXII feeds or OpenCTI/MISP connectors.
- IOC reputation with source trust, confidence, expiry and allowlists.
- Cases and evidence references.
- Cortex/TheHive or defensive integration adapters.
- Human approval for active response.

## Phase 7 — Behavioral analytics and anomaly detection

- Baselines per host/user/service with robust seasonal/time segmentation.
- Change-point/anomaly scoring.
- Graph/sequence analytics.
- Explainability and contributing features.
- Shadow mode and analyst feedback loop before operational alerting.
- False-positive and drift monitoring.

## Phase 8 — Scale, resilience and deployment

- Throughput/latency benchmarks and soak tests.
- NATS JetStream/Kafka evaluation.
- Horizontal workers and backpressure.
- High availability and disaster recovery.
- Tenant isolation and secrets management.
- Containerized deployment and hardening.
- End-to-end audit and privacy review.

## أولويات تنفيذ قريبة

1. تأكيد نجاح CI على أول commit برمجي.
2. معالجة أي خطأ بناء/اختبار قبل إضافة ميزات.
3. إضافة قواعد اختبارات لأكثر من شكل سجل واقعي (بعد إزالة البيانات الحساسة).
4. وضع persistence adapter ثم PostgreSQL.
5. تثبيت نموذج الأحداث والـ API قبل الواجهة النهائية.
