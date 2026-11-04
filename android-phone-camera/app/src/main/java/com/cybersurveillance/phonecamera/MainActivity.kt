package com.cybersurveillance.phonecamera

import android.Manifest
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.os.Bundle
import android.os.SystemClock
import android.util.Size
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.io.ByteArrayOutputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private lateinit var previewView: PreviewView
    private lateinit var endpointInput: EditText
    private lateinit var cameraIdInput: EditText
    private lateinit var apiKeyInput: EditText
    private lateinit var statusText: TextView
    private lateinit var controlsScroll: ScrollView
    private lateinit var contentLayout: LinearLayout
    private lateinit var previewCard: FrameLayout
    private lateinit var fullscreenButton: Button
    private lateinit var cameraExecutor: ExecutorService

    private val httpClient = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private var lastSentAt = 0L
    private var sentFrames = 0
    private var skippedBackpressureFrames = 0
    private var fullscreen = false

    @Volatile
    private var sending = false

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) connectAndStart() else status("إذن الكاميرا مطلوب لبدء البث")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        cameraExecutor = Executors.newSingleThreadExecutor()
        buildScreen()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        val values = currentInputs()
        super.onConfigurationChanged(newConfig)
        buildScreen(values)
        if (sending) bindCamera()
    }

    private data class CameraInputs(
        val endpoint: String,
        val cameraId: String,
        val apiKey: String
    )

    private fun currentInputs(): CameraInputs {
        return CameraInputs(
            if (::endpointInput.isInitialized) endpointInput.text.toString() else "",
            if (::cameraIdInput.isInitialized) cameraIdInput.text.toString() else "road-01",
            if (::apiKeyInput.isInitialized) apiKeyInput.text.toString() else ""
        )
    }

    private fun buildScreen(values: CameraInputs = currentInputs()) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setBackgroundColor(0xFF041329.toInt())
        }

        val toolbar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(4), dp(2), dp(4), dp(8))
        }
        val titleGroup = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val title = TextView(this).apply {
            text = "CYBERVISION CAMERA"
            textSize = 18f
            setTextColor(0xFFEAF3FF.toInt())
        }
        val subtitle = TextView(this).apply {
            text = "بث مباشر آمن · 640 × 360 · WSS"
            textSize = 11f
            setTextColor(0xFF82A7D2.toInt())
        }
        titleGroup.addView(title)
        titleGroup.addView(subtitle, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = dp(3) })
        fullscreenButton = Button(this).apply {
            text = if (fullscreen) "إظهار الإعدادات" else "⛶ ملء الشاشة"
            textSize = 11f
            setOnClickListener {
                fullscreen = !fullscreen
                applyLayoutMode()
            }
        }
        toolbar.addView(titleGroup, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        toolbar.addView(fullscreenButton)
        root.addView(toolbar)

        statusText = TextView(this).apply {
            text = if (sending) "البث نشط" else "متوقف"
            textSize = 12f
            setTextColor(0xFF58D9EE.toInt())
            setPadding(dp(7), dp(3), dp(7), dp(9))
        }
        root.addView(statusText)

        contentLayout = LinearLayout(this).apply {
            orientation = if (resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE) {
                LinearLayout.HORIZONTAL
            } else {
                LinearLayout.VERTICAL
            }
        }

        controlsScroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
        }
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(5), dp(5), dp(9), dp(12))
        }

        endpointInput = field(
            "رابط النظام HTTPS",
            values.endpoint.ifBlank { "https://your-colab-tunnel.trycloudflare.com" }
        )
        cameraIdInput = field("معرّف الكاميرا", values.cameraId.ifBlank { "road-01" })
        apiKeyInput = field("مفتاح API", values.apiKey).apply { inputType = 129 }

        controls.addView(sectionLabel("إعداد الاتصال"))
        controls.addView(endpointInput)
        controls.addView(cameraIdInput)
        controls.addView(apiKeyInput)

        val start = Button(this).apply {
            text = "بدء البث المباشر"
            setOnClickListener {
                if (ContextCompat.checkSelfPermission(
                        this@MainActivity, Manifest.permission.CAMERA
                    ) == PackageManager.PERMISSION_GRANTED
                ) {
                    connectAndStart()
                } else {
                    cameraPermission.launch(Manifest.permission.CAMERA)
                }
            }
        }
        val stop = Button(this).apply {
            text = "إيقاف البث"
            setOnClickListener { stopStreaming() }
        }
        controls.addView(start)
        controls.addView(stop)

        val guide = TextView(this).apply {
            text = "عند تدوير الهاتف أفقياً تظهر الإعدادات في عمود جانبي وتبقى معاينة الكاميرا واضحة. يمكنك إخفاء الإعدادات بزر ملء الشاشة."
            textSize = 11f
            setTextColor(0xFF91AAC8.toInt())
            setPadding(dp(5), dp(10), dp(5), dp(10))
        }
        controls.addView(guide)
        controlsScroll.addView(controls)

        previewCard = FrameLayout(this).apply {
            setBackgroundColor(0xFF010917.toInt())
            setPadding(dp(1), dp(1), dp(1), dp(1))
        }
        previewView = PreviewView(this).apply {
            implementationMode = PreviewView.ImplementationMode.PERFORMANCE
            scaleType = PreviewView.ScaleType.FIT_CENTER
        }
        previewCard.addView(
            previewView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        contentLayout.addView(controlsScroll)
        contentLayout.addView(previewCard)
        root.addView(
            contentLayout,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
            )
        )
        setContentView(root)
        applyLayoutMode()
    }

    private fun sectionLabel(text: String): TextView {
        return TextView(this).apply {
            this.text = text
            textSize = 13f
            setTextColor(0xFF75B9FF.toInt())
            setPadding(dp(3), dp(7), dp(3), dp(5))
        }
    }

    private fun field(label: String, value: String): EditText {
        return EditText(this).apply {
            hint = label
            setText(value)
            textSize = 13f
            setTextColor(0xFFEAF3FF.toInt())
            setHintTextColor(0xFF7794B4.toInt())
            setSingleLine(true)
        }
    }

    private fun applyLayoutMode() {
        if (!::contentLayout.isInitialized) return
        val landscape = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
        fullscreenButton.text = if (fullscreen) "إظهار الإعدادات" else "⛶ ملء الشاشة"
        controlsScroll.visibility = if (fullscreen) View.GONE else View.VISIBLE

        if (landscape) {
            contentLayout.orientation = LinearLayout.HORIZONTAL
            controlsScroll.layoutParams = LinearLayout.LayoutParams(
                if (fullscreen) 0 else dp(300),
                LinearLayout.LayoutParams.MATCH_PARENT,
                if (fullscreen) 0f else 0f
            )
            previewCard.layoutParams = LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.MATCH_PARENT,
                1f
            )
        } else {
            contentLayout.orientation = LinearLayout.VERTICAL
            controlsScroll.layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                if (fullscreen) 0f else 1f
            )
            val previewParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                if (fullscreen) 0 else dp(250),
                if (fullscreen) 1f else 0f
            )
            previewCard.layoutParams = previewParams
        }
        previewCard.requestLayout()
        controlsScroll.requestLayout()
    }

    private fun connectAndStart() {
        val base = endpointInput.text.toString().trim().trimEnd('/')
        val cameraId = cameraIdInput.text.toString().trim()
        val key = apiKeyInput.text.toString().trim()
        if (!base.startsWith("https://") ||
            cameraId.isBlank() ||
            !cameraId.matches(Regex("[A-Za-z0-9_-]{1,48}")) ||
            key.length < 32
        ) {
            status("أدخل رابط HTTPS صحيحاً ومعرّف كاميرا صالحاً ومفتاحاً لا يقل عن 32 حرفاً")
            return
        }

        stopStreaming()
        val host = base.removePrefix("https://")
        val streamUrl = "wss://" + host + "/api/v1/phone/stream/" + cameraId
        val request = Request.Builder()
            .url(streamUrl)
            .header("X-API-Key", key)
            .build()

        status("جارٍ الاتصال بالخادم…")
        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(socket: WebSocket, response: Response) {
                runOnUiThread {
                    sending = true
                    sentFrames = 0
                    skippedBackpressureFrames = 0
                    status("تم الاتصال؛ تهيئة الكاميرا وإرسال الإطارات")
                    bindCamera()
                }
            }

            override fun onMessage(socket: WebSocket, text: String) {
                runOnUiThread {
                    if (text.contains("frame_rejected")) {
                        status("رفض الخادم إطار JPEG غير صالح")
                    }
                }
            }

            override fun onFailure(socket: WebSocket, t: Throwable, response: Response?) {
                runOnUiThread {
                    sending = false
                    val detail = if (response != null) {
                        "HTTP " + response.code + " " + response.message
                    } else {
                        t.message ?: "network error"
                    }
                    status("فشل اتصال البث: " + detail)
                    unbindCamera()
                }
            }

            override fun onClosed(socket: WebSocket, code: Int, reason: String) {
                runOnUiThread {
                    sending = false
                    unbindCamera()
                    if (reason == "Stopped by operator") {
                        status("تم إيقاف البث")
                    } else {
                        val detail = when (code) {
                            4400 -> "معرّف الكاميرا غير صالح"
                            4401 -> "مفتاح API غير مطابق أو غير مضبوط في الخادم"
                            else -> reason.ifBlank { "لا توجد تفاصيل" }
                        }
                        status("أُغلق الاتصال (" + code + "): " + detail)
                    }
                }
            }
        })
    }

    private fun bindCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            try {
                val provider = future.get()
                cameraProvider = provider
                val selector = ResolutionSelector.Builder()
                    .setAspectRatioStrategy(
                        AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY
                    )
                    .setResolutionStrategy(
                        ResolutionStrategy(
                            Size(640, 360),
                            ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER
                        )
                    )
                    .build()

                val preview = Preview.Builder()
                    .setResolutionSelector(selector)
                    .build()
                    .also {
                        it.surfaceProvider = previewView.surfaceProvider
                    }

                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(selector)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                    .build()

                analysis.setAnalyzer(cameraExecutor) { image ->
                    try {
                        val now = SystemClock.elapsedRealtime()
                        if (sending && now - lastSentAt >= 100) {
                            val socket = webSocket
                            if (socket != null && socket.queueSize() < 1_000_000L) {
                                val jpeg = imageToJpeg(image)
                                if (jpeg != null && jpeg.size <= 900 * 1024) {
                                    val accepted = socket.send(ByteString.of(*jpeg))
                                    if (accepted) {
                                        lastSentAt = now
                                        sentFrames += 1
                                        if (sentFrames % 20 == 0) {
                                            runOnUiThread {
                                                status(
                                                    "البث نشط · " + sentFrames +
                                                        " إطار · " + skippedBackpressureFrames +
                                                        " إطار متجاوز بسبب الشبكة"
                                                )
                                            }
                                        }
                                    }
                                }
                            } else {
                                skippedBackpressureFrames += 1
                            }
                        }
                    } catch (error: Exception) {
                        runOnUiThread {
                            status("خطأ في تجهيز إطار الكاميرا: " + error.message)
                        }
                    } finally {
                        image.close()
                    }
                }

                provider.unbindAll()
                provider.bindToLifecycle(
                    this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis
                )
            } catch (error: Exception) {
                status("تعذر تشغيل الكاميرا: " + error.message)
                stopStreaming()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun imageToJpeg(image: ImageProxy): ByteArray? {
        if (image.format != ImageFormat.YUV_420_888) return null
        val width = image.width
        val height = image.height
        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]
        val nv21 = ByteArray(width * height * 3 / 2)
        var position = 0
        val yBuffer = yPlane.buffer.duplicate()
        for (row in 0 until height) {
            if (yPlane.pixelStride == 1) {
                yBuffer.position(row * yPlane.rowStride)
                yBuffer.get(nv21, position, width)
                position += width
            } else {
                for (col in 0 until width) {
                    nv21[position++] = yBuffer.get(
                        row * yPlane.rowStride + col * yPlane.pixelStride
                    )
                }
            }
        }

        val uBuffer = uPlane.buffer.duplicate()
        val vBuffer = vPlane.buffer.duplicate()
        val chromaWidth = width / 2
        val chromaHeight = height / 2
        for (row in 0 until chromaHeight) {
            val uRow = row * uPlane.rowStride
            val vRow = row * vPlane.rowStride
            for (col in 0 until chromaWidth) {
                nv21[position++] = vBuffer.get(vRow + col * vPlane.pixelStride)
                nv21[position++] = uBuffer.get(uRow + col * uPlane.pixelStride)
            }
        }

        val output = ByteArrayOutputStream()
        val yuv = YuvImage(nv21, ImageFormat.NV21, width, height, null)
        if (!yuv.compressToJpeg(Rect(0, 0, width, height), 60, output)) return null
        return output.toByteArray()
    }

    private fun unbindCamera() {
        sending = false
        cameraProvider?.unbindAll()
    }

    private fun stopStreaming() {
        sending = false
        unbindCamera()
        webSocket?.close(1000, "Stopped by operator")
        webSocket = null
        status("تم إيقاف البث")
    }

    private fun status(message: String) {
        if (::statusText.isInitialized) statusText.text = message
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).toInt()
    }

    override fun onDestroy() {
        stopStreaming()
        cameraExecutor.shutdown()
        httpClient.dispatcher.executorService.shutdown()
        super.onDestroy()
    }
}
