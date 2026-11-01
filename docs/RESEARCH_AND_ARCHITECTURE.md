# بحث الأنظمة المرجعية والمعمارية المقترحة

**تاريخ البحث:** 2026-11-01  
**النطاق المفترض:** منصة مراقبة أمنية دفاعية (SIEM / XDR / SOC) للأصول والشبكات والخدمات التي نملكها أو لدينا تصريح بمراقبتها.  
**ملاحظة:** البحث يدرس المعمارية والواجهات والقدرات المنشورة في الوثائق الرسمية، ولا يدّعي تنفيذ كل تلك المنتجات أو إجراء اختبار أداء مقارن بينها.

---

## 1. خلاصة البحث

المنصات المركزية القوية لا تعتمد على كاشف واحد. قوتها تأتي من سلسلة كاملة:

1. جمع أحداث متعددة المصادر، مع موثوقية النقل ومراقبة صحة المجمعات.
2. تطبيع الحقول إلى مخطط مشترك حتى يمكن مقارنة منتجات مختلفة.
3. إثراء الحدث بسياق الأصل والحساب والتهديد والثغرة والوقت.
4. كشف توقيعات وقواعد وسلوكيات داخل نافذة زمنية.
5. ربط نتائج متعددة لتشكيل قصة أو تسلسل هجوم قابل للتفسير.
6. إدارة التنبيه كحالة عمل: إقرار، تعيين، تصعيد، تحقيق، أدلة، إغلاق.
7. قياس جودة الكشف، والضجيج، وفجوات الرؤية، واستهلاك الموارد.
8. الاحتفاظ بالأثر الخام مع نسخة مطبّعة حتى يمكن إعادة التحليل لاحقاً.

لهذا السبب لن يكون المشروع مجرد مجموعة سكربتات Python أو صفحة تعرض عدادات. سيكون منصة ذات عقود بيانات واضحة ومحركات مستقلة وواجهات تشغيل وتحقيق.

## 2. الأنظمة المرجعية التي تمت دراستها

| النظام | الفكرة التي نتعلم منها | دور محتمل في نظامنا |
|---|---|---|
| Wazuh | فصل Agent وManager وIndexer وDashboard، مع تطبيع وإثراء وقواعد وإدارة Agents | مرجع لطبقة Endpoint والحوكمة والصحة والتقارير |
| Security Onion | جمع Network Visibility وHost Visibility وIDS وPCAP وThreat Hunting وCase Management في منصة تشغيلية | مرجع لتوحيد مشاهدات الشبكة والمضيف والتحقيق |
| Zeek | تحليل بروتوكولي عالي المستوى وحالة تدفق مستمرة وسجلات قابلة للتخصيص | مصدر غني لسياق الاتصالات وDNS وHTTP وTLS |
| Suricata | IDS/IPS وتحليل بروتوكولات، مع مخرجات EVE JSON منظمة تشمل التنبيهات والتدفقات وDNS وHTTP وTLS والإحصاءات | مصدر إشارات كشف الشبكة |
| osquery | عرض حالة نظام التشغيل على شكل جداول SQL واستعلامات مجدولة وتغيّرات | مصدر Endpoint telemetry مضبوط |
| Fleet | إدارة مركزية لعقد osquery والتوزيع الأفقي مع استمرار تخزين النتائج مؤقتاً عند الانقطاع | مرجع لإدارة أسطول الأجهزة |
| Velociraptor | لغة VQL وArtifacts وHunting وجمع الأدلة والتحقيق الجنائي الرقمي | تكامل اختياري للتحقيق المصرح به والاستجابة |
| OpenSearch Security Analytics | Detectors وRules وFindings وAlerts ومحرك Correlation بين أنواع سجلات مختلفة، مع دعم Sigma | مرجع للبحث والكشف والارتباط |
| OCSF | مخطط أحداث أمني مشترك ومحايد عن المورد | أساس التطبيع الداخلي |
| Sigma | صيغة قواعد كشف قابلة للنقل بين منصات SIEM، مع قواعد ارتباط | صيغة استيراد/تصدير مستقبلية |
| MITRE ATT&CK | وصف سلوك الخصم واستراتيجيات الكشف والتحليلات | إطار لتفسير التغطية والفجوات |
| OpenTelemetry Collector | Receive → Process → Export pipelines مع موصلات قابلة للتمديد | مرجع لتصميم موصلات جمع مستقلة |
| NATS JetStream | تدفق رسائل دائم، replay، consumers، acknowledgements وتسليم at-least-once | وسيط رسائل محتمل عند إثبات الحاجة |
| TheHive / Cortex | إدارة الحالات وتحليل المؤشرات والاستجابة عبر API | مرجع للتحقيق والـ Case management |
| Shuffle | سير عمل أتمتة مرئي يعتمد Apps وTriggers وConditions وVariables | مرجع لمحرك SOAR مستقبلي |

### ملاحظات تقنية مهمة

- Wazuh يفصل بين جمع البيانات وتحليلها وفهرستها وعرضها، ويدعم أيضاً إرسال سجلات الأجهزة التي لا يمكن تثبيت Agent عليها. هذا الفصل أساسي لتجنب ربط الواجهة مباشرة بالمستشعرات.
- Security Onion يجمع Suricata وZeek ورؤية المضيف وإدارة الحالات؛ يوضح أن SIEM قوي يحتاج بيانات شبكة ومضيف معاً.
- Zeek ليس مجرد IDS توقيعي؛ أهميته في إنتاج سياق بروتوكولي Stateful يمكن ربطه مع الأحداث الأخرى.
- Suricata يوفّر EVE JSON كخرج منظم، لذا نستهلك السجلات المنظمة بدلاً من إعادة كتابة محلل بروتوكولات كامل داخل Python.
- osquery يقدم قيماً منظمة من نظام التشغيل، بينما Fleet يعالج الإدارة المركزية والتوزيع والتحمل عند انقطاع الاتصال.
- OpenSearch Security Analytics يوضح فائدة الفصل بين rule match وfinding وalert، ويقدم correlation عبر مصادر مختلفة.
- NATS JetStream يضيف تخزين الرسائل وإمكانية replay وacknowledgement. دلالة at-least-once تعني أن المستهلك يجب أن يكون idempotent ويتعامل مع الرسائل المكررة.
- OCSF يوفر مخططاً محايداً عن المورد؛ يجب الاحتفاظ بالمصدر الخام لأن التطبيع قد يفقد حقولاً خاصة بالمورد.

## 3. تحديث مهم: MITRE ATT&CK في نوفمبر 2026

بحسب صفحة الإصدارات الرسمية، الإصدار الحالي هو **ATT&CK v20.0** المنشور في 13 أكتوبر 2026. الإصدار 18 نقل بنية الدفاع من قوائم Detection داخل التقنيات إلى Detection Strategies وAnalytics، مع إلغاء نهج Data Sources القديمة بوصفها بنية متجددة. إصدار v20 وسّع بدوره استراتيجيات الكشف والـ Analytics، بما في ذلك أنماط أحدث مرتبطة بالذكاء الاصطناعي وسلاسل السلوك.

**قرار معماري:** نخزن روابط ATT&CK كمعرفات وإصدارات ونسخ بيانات قابلة للتحديث، ولا نربط المحرك بملف ثابت أو نفترض أن Data Sources القديمة هي مصدر التغطية الوحيد. يجب أن يربط كل كشف - عند توفر ذلك - بين:
- Detection rule ID / version
- ATT&CK technique/sub-technique
- Detection Strategy / Analytics references
- Data components أو متطلبات الرؤية
- مستوى الثقة ومصدر الدليل
- الإصدار الذي تم التحقق منه من ATT&CK

لا يعني الربط بـ ATT&CK أن الحدث أثبت وجود هجوم أو أن التقنية نُفذت؛ إنه تصنيف تحليلي مع دليل يجب فحصه.

## 4. ما نقتبسه من الواجهات المركزية

الواجهات الأفضل في هذا المجال تنظّم العمل حول أسئلة المحلل، لا حول أسماء المكتبات:

- **Overview:** هل البيانات تصل؟ ما الأصول المتصلة؟ ما التنبيهات الجديدة والحرجة؟ ما مصادر الرؤية المتوقفة؟
- **Event Explorer:** ماذا حدث؟ متى؟ أين؟ من؟ ما المصدر؟ ما الحقول الخام والمطبّعة؟
- **Detection Center:** ما القاعدة التي اشتغلت؟ ما إصدارها؟ لماذا طابقت؟ ما حدودها والـ false positives؟
- **Alert Queue:** ما الذي يحتاج إجراء الآن؟ ما المسؤول؟ ما SLA؟ هل تم الإقرار أو التصعيد؟
- **Investigation Workspace:** ما تسلسل الأحداث والأصول والحسابات والاتصالات المرتبطة؟
- **Asset & Sensor Inventory:** ما الذي نراقبه؟ ما الذي لا يرسل بيانات؟ ما سياسة الاحتفاظ؟
- **Threat Intelligence:** ما الـ IOC أو الكيان المرتبط؟ ما المصدر وعمر المعلومة والثقة؟
- **Case Management:** الأدلة، الملاحظات، المهام، القرارات، التوقيت، وسجل التدقيق.
- **System Health:** معدل الإدخال، التأخر، إسقاط الأحداث، أخطاء الموصلات، حجم التخزين، واستهلاك الموارد.

لا نريد خريطة جغرافية مزخرفة أو رسوماً كثيرة بلا قيمة. نريد جداول عالية الكثافة قابلة للفرز، فلاتر محفوظة، تفاصيل قابلة للفتح، Timeline، وGraph يظهر فقط عندما يوضح علاقة حقيقية.

## 5. التصميم المقترح لنظامنا

~~~text
                    DATA SOURCES
       +---------------+------------------+
       |               |                  |
     ENDPOINTS       NETWORK             CLOUD
  Wazuh/osquery   Zeek/Suricata        Audit APIs
       |               |                  |
       +---------------+------------------+
                       |
               INGESTION ADAPTERS
          HTTP / Syslog / Files / APIs
                       |
              VALIDATION + NORMALIZE
                  OCSF-aligned
                       |
                EVENT ENRICHMENT
       Asset context / Identity / TI / Geo (optional)
                       |
                DETECTION FABRIC
      Sigma rules / Thresholds / Sequences / Graph
                       |
               ALERT CORRELATION
         Dedup / Risk / Episode / Provenance
                       |
              INVESTIGATION SERVICE
        Cases / Evidence / Timeline / Audit trail
                       |
                 SOC WEB CONSOLE
~~~

### 5.1 طبقات Python

**API Layer**
- FastAPI وPydantic.
- OpenAPI لواجهات الإدخال والاستعلام.
- مصادقة ومفاتيح خدمة وRBAC لاحقاً.
- لا تضع منطق الكشف داخل route handlers.

**Domain Layer**
- Event / Finding / Alert / Case / Asset / Sensor.
- عقود ثابتة ومستقلة عن FastAPI أو قاعدة البيانات.
- الوقت دائماً timezone-aware ومخزن بصيغة UTC.

**Ingestion Layer**
- Adapter لكل تنسيق أو مصدر.
- يحتفظ بالـ raw payload وبهوية المستشعر ووقت الجمع.
- يدعم batch limits، rate limits، idempotency وdead-letter لاحقاً.

**Normalization Layer**
- نموذج داخلي مستوحى من OCSF.
- خرائط من ECS/Zeek/Suricata/osquery/Wazuh إلى الحقول المشتركة.
- لا يحذف حقول المصدر غير المعروفة.
- يضيف schema_version وnormalizer_version لتسهيل إعادة التطبيع.

**Detection Layer**
- Exact matching / Sigma-like rules.
- Threshold windows.
- Stateful sequences.
- Cross-source correlation.
- Baselines/anomaly detection.
- كل كاشف يعيد سبب المطابقة وأحداث الدليل والقيود، وليس score فقط.

**Storage Layer**
- فصل بيانات التشغيل والمعاملات عن أحجام الأحداث.
- بداية التطوير: In-memory adapter للاختبارات فقط.
- المرحلة الصغيرة: PostgreSQL للبيانات التشغيلية وpartitioning/retention مناسب للأحداث.
- عند نمو معدل الإدخال والبحث: تقييم ClickHouse أو OpenSearch وفق workload حقيقي.
- لا نضيف Kafka أو NATS أو ClickHouse لمجرد أنها تقنيات مشهورة؛ نضيفها بعد قياس throughput والـ latency والذاكرة والتكلفة.

**Streaming Layer**
- البداية: واجهة Ingestion مباشرة قابلة للاستبدال.
- لاحقاً: NATS JetStream أو Kafka/Redpanda عند الحاجة إلى فصل المنتجين عن المستهلكين وإعادة تشغيل الأحداث.
- يجب أن تكون المعالجة idempotent بسبب احتمالية إعادة التسليم.

**Frontend**
- React + TypeScript كتطبيق ويب منفصل عن محرك Python.
- ECharts للرسوم الكثيفة، وواجهة جداول قابلة للفرز والتصفية.
- WebSocket/SSE للتحديثات الحية عند جاهزية خدمة التنبيهات.
- لا ينبغي وضع منطق أمني موثوق داخل المتصفح.

## 6. خوارزميات الكشف المقترحة

لن نستخدم نموذج Machine Learning واحداً لكل شيء. نستخدم حزمة متعددة المستويات:

1. **Deterministic rules:** توقيعات وأحداث معروفة مع أسباب مطابقة صريحة.
2. **Window aggregations:** عدّ وتواتر وDistinct counts ضمن نوافذ زمنية.
3. **Sequence detection:** تسلسل أحداث مرتب زمنياً (مثلاً فشل دخول متكرر ثم نجاح ثم جلسة جديدة).
4. **Entity graph correlation:** ربط المستخدم والجهاز وعنوان الشبكة والعملية والجلسة والملف ضمن رسم بياني زمني.
5. **Risk accumulation:** رفع مستوى الحادث عندما تتراكم إشارات مستقلة على الكيان نفسه، مع عدم جمع درجات متشابهة مرتين.
6. **Behavioral baselines:** مقارنة السلوك بخط أساس خاص بالمستخدم أو الجهاز أو الوقت، مع نافذة تعلم ومقاومة للتسميم البطيء.
7. **Anomaly detection:** نماذج إحصائية/ML كإشارة مساعدة، لا كحكم نهائي ولا كإجراء تلقائي.
8. **Detection quality:** قياس precision/recall عندما تتوفر بيانات موسومة، ومعدل الضجيج، والـ coverage، وزمن الاكتشاف.

### ابتكار مقترح: Behavioral Episode Graph

بدلاً من عرض كل تنبيه كحادثة منفصلة، نبني **حلقة سلوك (Episode)**:

- كل Event عقدة.
- المستخدم والجهاز وIP والعملية والجلسة كيانات مرتبطة.
- كل علاقة تحمل نوعها ومصدرها ووقت بدايتها ونهايتها.
- قواعد التسلسل تضيف حوافاً مفسّرة مثل "بعد فشل الدخول حدث نجاح من المصدر نفسه".
- يسجل النظام لماذا ضمّ حدثين إلى الحلقة، ولماذا لم يضم أحداثاً أخرى.
- النتيجة صفحة تحقيق بجدول زمن + رسم علاقات + أدلة، لا مجرد رسم شبكي جميل.

### ابتكار مقترح: Sensor Confidence & Blind-Spot Engine

يقيس النظام جودة الرؤية لكل مصدر:
- آخر وقت وصول.
- معدل وصول متوقع مقابل الفعلي.
- فجوات الوقت والعدادات.
- تغيّر شكل البيانات أو اختفاء الحقول.
- نسبة الرفض أو فشل التطبيع.
- تأخر الإدخال.
- ما إذا كانت التغطية المطلوبة لاستراتيجية كشف معينة موجودة فعلاً.

النتيجة ليست فقط "لا توجد تهديدات"، بل "لم نرَ تهديداً ضمن مصادر كانت سليمة وتغطي السلوك المتوقع" أو "لا يمكن الحكم بسبب فجوة مستشعر". هذه نقطة مهمة لمنع الاطمئنان الكاذب.

### ابتكار مقترح: Detection Replay & Regression Lab

كل قاعدة كشف تحتفظ بإصدارها، وبعينات الاختبار المتوقعة، والحقول المطلوبة. عند تغيير قاعدة أو Normalizer:
- نعيد تشغيل مجموعة أحداث اختبار محفوظة.
- نقارن التنبيهات القديمة والجديدة.
- نعرض الزيادة في التنبيهات المكررة أو النتائج المفقودة.
- لا ننشر القاعدة إذا فشلت اختبارات regression أو توسعت المطابقة بشكل غير مفهوم.

## 7. مخطط التخزين المستقبلي

نبدأ بكيانات صريحة قابلة للتطور:

- Tenant
- Asset
- Sensor
- SecurityEvent
- DetectionRule
- Finding
- Alert
- BehavioralEpisode
- Case
- EvidenceReference
- Indicator
- RuleExecution
- AuditEntry

الأحداث عالية الحجم لا ينبغي أن تربك جداول الحالات والمستخدمين. لذلك سنفصل لاحقاً:
- مخزن الأحداث/التحليلات.
- PostgreSQL للكيانات التشغيلية والعلاقات المرجعية.
- مخزن artifacts للأدلة الكبيرة، مع hashes وسياسة احتفاظ.
- فهرس بحث عند الحاجة.

كل سجل دليل يجب أن يتضمن المصدر والوقت والـ hash وسياسة الاحتفاظ وإمكانية إعادة الوصول، مع تجنب تخزين أسرار أو محتوى حساس غير ضروري.

## 8. الأمان والخصوصية

- كل مصدر مراقبة يجب أن يكون مصرحاً به ومُسجلاً في Inventory.
- لا نطوّر Agent خفياً أو آليات تجاوز حماية؛ التكامل يكون عبر Agents معلنة أو Syslog أو APIs أو أدوات دفاعية موثقة.
- TLS بين المكونات عند الانتقال من Loopback.
- RBAC وMFA وسجل تدقيق عند إضافة مستخدمين.
- مفاتيح API في secrets manager أو environment، لا في Git.
- أقل صلاحية لازمة لكل Connector.
- عدم تخزين كلمات مرور أو session tokens في الأحداث.
- تشفير البيانات الحساسة والنسخ الاحتياطية.
- الاحتفاظ والحذف وفق سياسة صريحة، مع إظهار ما يجمعه كل Sensor.
- كل رد آلي عالي الأثر يحتاج مراجعة بشرية، وسياسة موافقة، وسجل قرار.

## 9. خطة النشر حسب الحجم

| النمط | الاستخدام | التقنية |
|---|---|---|
| Developer / Lab | تطوير واختبارات وبيانات تجريبية | Python API + In-memory/Test adapters |
| Small single-node | بيئة مصرح بها محدودة | FastAPI + PostgreSQL + ملفات أحداث أو مخزن خفيف |
| Central platform | عدة مصادر ومعدل بيانات أكبر | API + Queue + PostgreSQL + OpenSearch أو ClickHouse |
| Distributed | عدة مواقع ومصادر كثيرة | Ingestion gateways + replicated queue + partitioned storage + horizontally scaled workers |

يجب اختيار النمط بعد قياس عدد المستشعرات، events/second، متوسط حجم الحدث، retention، وعدد المحللين المتزامنين. لا معنى لوعد "منافس للمؤسسات" قبل قياس هذه المتغيرات.

---

## 10. المصادر الرسمية المستخدمة

1. Wazuh architecture: https://documentation.wazuh.com/current/getting-started/architecture.html
2. Wazuh components and XDR/SIEM design: https://documentation.wazuh.com/current/getting-started/components/index.html
3. Wazuh Dashboard: https://documentation.wazuh.com/current/getting-started/components/wazuh-dashboard.html
4. Security Onion architecture and visibility: https://docs.securityonion.net/en/3/dev/introduction/
5. Zeek repository and network analysis capabilities: https://github.com/zeek/zeek
6. Zeek Logging Framework: https://docs.zeek.org/en/current/frameworks/logging.html
7. Suricata EVE JSON output: https://docs.suricata.io/en/latest/output/eve/eve-json-output.html
8. osquery architecture: https://github.com/osquery/osquery
9. osquery query packs: https://osquery.readthedocs.io/en/latest/deployment/configuration/
10. Fleet reference architectures: https://fleetdm.com/docs/deploy/reference-architectures
11. Velociraptor documentation: https://docs.velociraptor.app/
12. OCSF schema: https://github.com/ocsf/ocsf-schema
13. Sigma specification: https://sigmahq.io/sigma-specification/
14. Sigma correlation rules: https://sigmahq.io/sigma-specification/specification/sigma-correlation-rules-specification.html
15. MITRE ATT&CK current releases: https://attack.mitre.org/resources/versions/
16. MITRE ATT&CK October 2026 updates: https://attack.mitre.org/resources/updates/updates-october-2026/
17. OpenSearch Security Analytics: https://docs.opensearch.org/latest/security-analytics/
18. OpenSearch correlation rules: https://docs.opensearch.org/latest/security-analytics/sec-analytics-config/correlation-config/
19. OpenTelemetry Collector architecture: https://opentelemetry.io/docs/collector/architecture/
20. NATS JetStream: https://docs.nats.io/concepts/jetstream
21. TheHive/Cortex: https://docs.strangebee.com/cortex/
22. Shuffle workflows: https://shuffle.security/docs/workflows
23. Pydantic Settings: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/

### كيف نستخدم المراجع

هذه المصادر تثبت القدرات المنشورة في الوثائق الرسمية، لكنها لا تثبت أن دمجاً معيناً هو الأسرع أو الأنسب لكل جهاز. أي اختيار إنتاجي سيُبنى على اختبار حقيقي بنفس عينة السجلات ونفس معدل الأحداث ونفس متطلبات retention والأداء.
