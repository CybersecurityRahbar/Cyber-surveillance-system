# تشغيل Cyber Surveillance System على Google Colab

## الهدف

تشغيل منصة Python المركزية داخل Colab وفتح واجهة المختبر عبر رابط HTTPS مؤقت، دون تثبيت بيئة النظام على اللابتوب.

دفتر التشغيل:
[Google_Colab_Lab.ipynb](../notebooks/Google_Colab_Lab.ipynb)

## ما الذي يعمل؟

يستضيف Colab:
- FastAPI وواجهة المختبر والملفات الثابتة.
- معالجة الفيديو عبر PyAV/OpenCV.
- كشف YOLO26n والتتبع عبر Ultralytics.
- preview أثناء المعالجة، عدّ هويات المركبات والأشخاص، عبور خط العد، وMP4 ناتج.
- أحداث SQLite وملفات المختبر في مساحة runtime أو Google Drive اختياريًا.

## المتطلبات والتشغيل

يتطلب المشروع Python `>=3.12,<3.14`. تحقق من الإصدار الحالي داخل الدفتر؛ نسخة Colab 2026.10 المنشورة من Google تسجل Python 3.13.18، وهي متوافقة مع هذا النطاق.

1. افتح دفتر Colab.
2. اختر Runtime → Change runtime type → GPU إن توفر.
3. شغّل الخلايا بالترتيب من الأعلى للأسفل.
4. أدخل API key طويلًا في prompt مخفي.
5. انتظر جاهزية Uvicorn ثم رابط النفق.
6. افتح الرابط مع `/lab`، وأدخل المفتاح في حقل API key، ثم انقر خارج الحقل.
7. ارفع مقطعًا قصيرًا واختبر الكشف والتتبع والعد والفيديو الناتج.

## Cloudflare Quick Tunnel

- لا يحتاج حسابًا أو نطاقًا.
- ينشئ رابطًا عشوائيًا مؤقتًا `*.trycloudflare.com`؛ تتولى الخلية الأخيرة مراقبة عملية النفق وتبقى نشطة بينما يعمل.
- يتوقف الرابط عند إيقاف cloudflared أو انتهاء Runtime.
- Quick Tunnels للاختبار والتطوير، وليست نشرًا دائمًا.
- الصفحة وملفاتها الثابتة متاحة لمن يعرف الرابط؛ مسارات `/api/v1` محمية بمفتاح API.
- يمكن تجربة قيد البريد باستخدام `--allowed-mail` وفق دعم Quick Tunnels الحالي.

التوثيق: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/ وhttps://blog.cloudflare.com/protected-quick-tunnels

## ngrok

- يتطلب حسابًا وAuth Token.
- أدخل الرمز في prompt مخفي، ولا تحفظه في notebook أو GitHub.
- راجع حدود الاستخدام المجاني الحالية: https://ngrok.com/docs/pricing-limits

## حماية الوصول

- يعمل Uvicorn على `127.0.0.1:8000` فقط، والـTunnel يمرر الطلبات إلى الخدمة المحلية.
- يضبط الدفتر `TRAFFIC_SURVEILLANCE_API_KEY`; عمليات المختبر ورفع الفيديو تتطلب ترويسة `X-API-Key`.
- /lab و/lab-assets عامان لمن يعرف رابط النفق. حقل API key في الواجهة يخزن المفتاح داخل sessionStorage للمتصفح الحالي.
- لا تضع مفاتيح API أو ngrok token في شيفرة notebook أو outputs محفوظة أو GitHub.
- هذه الحماية مناسبة لاختبار محدود وليست بديلًا عن RBAC وإدارة هويات المشغلين ونشر إنتاجي.
- استخدم فيديوهات مصرحًا بتحليلها ولا تنشر بث كاميرا خاصًا عبر رابط عام.

## حفظ البيانات

الافتراضي `/content/cyber-surveillance-data` مؤقت. يمكن تفعيل Google Drive cell لحفظ SQLite والملفات الناتجة. يحفظ SQLite الآن سجلات الجلسة وهويات Track ومساراتها وسماتها. أوزان YOLO تُخزن في cache runtime وقد يلزم تنزيلها عند إعادة إنشاء الجلسة.

## حدود Colab

- Colab خدمة تفاعلية وليست VPS دائمًا.
- توفر GPU والحدود ومدة الجلسة تتغير؛ FAQ يذكر أن المجاني قد يصل إلى 12 ساعة كحد أقصى وفق التوفر والاستخدام، وليس ضمانًا لمدة ثابتة.
- النفق والرابط يتوقفان عند انقطاع Runtime.
- حد Cloudflare الموثق لحجم جسم الطلب في خطتي Free وPro هو 100 MB. يضبط الدفتر حد التطبيق على 90 MB لتجنب وصول الطلب إلى الحد الأقصى بسبب multipart overhead. استخدم مقطعًا قصيرًا أو جرّب ngrok عند الحاجة إلى رفع أكبر، مع مراعاة حدود نقل البيانات والمهلة في حسابك. المصدر: https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/
- تقدير اللون الحالي heuristic عبر HSV وليس مصنف ألوان مدرباً؛ سجّل النتيجة مع confidence ولا تعاملها كتأكيد نهائي.
- لا توجد أوزان ماركة/طراز مضمنة. يمكن تمرير مسار مصنف Ultralytics classification عبر `TRAFFIC_SURVEILLANCE_VEHICLE_MODEL_PATH` في خلية Colab؛ يجب أن تكون labels المدربة واضحة مثل `Toyota_Hilux` أو `Hyundai_Tucson`. التوصيل البرمجي اختياري ولم يُختبر بوزن مخصص بعد.
- الخلية النشطة لا تتجاوز الحد الأقصى لجلسة Colab أو سحب الموارد؛ إنها تمنع فقط انتهاء خلية بدء الخدمة بعد تنفيذ أمر background.
- لا تستخدمه للمراقبة الإنتاجية 24/7.

مصادر Google:
- https://research.google.com/colaboratory/faq.html
- https://research.google.com/colaboratory/runtime-version-faq.html

## قائمة اختبار القبول

- [ ] Python 3.12/3.13 confirmed
- [ ] CUDA visible or CPU fallback recorded
- [ ] all imports succeed
- [ ] /healthz returns status=ok
- [ ] tunnel opens /lab
- [ ] no API key is rejected
- [ ] valid API key unlocks capabilities
- [ ] video upload creates job
- [ ] continuous MJPEG preview appears and updates smoothly
- [ ] separate active-object list updates
- [ ] per-track reports persist in SQLite
- [ ] JSON report export works
- [ ] detections, Track IDs and counts update
- [ ] output MP4 plays/downloads
- [ ] persistence verified when Drive mode enabled
