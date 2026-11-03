package com.cybersurveillance.phonecamera

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.os.Bundle
import android.os.SystemClock
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
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
    private lateinit var cameraExecutor: ExecutorService
    private val httpClient = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .build()
    private var webSocket: WebSocket? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private var lastSentAt = 0L
    private var sentFrames = 0
    @Volatile private var sending = false

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

    private fun buildScreen() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 28, 28, 20)
            setBackgroundColor(0xFF07182D.toInt())
        }
        val title = TextView(this).apply {
            text = "CYBERVISION CAMERA"
            textSize = 21f
            setTextColor(0xFFEAF3FF.toInt())
        }
        val subtitle = TextView(this).apply {
            text = "بث كاميرا الهاتف إلى منصة المراقبة"
            textSize = 15f
            setTextColor(0xFF8FAFD0.toInt())
        }
        endpointInput = field("رابط النظام (https://...)", "https://your-colab-tunnel.trycloudflare.com")
        cameraIdInput = field("معرّف الكاميرا", "road-01")
        apiKeyInput = field("مفتاح API", "")
        apiKeyInput.inputType = 129
        val start = Button(this).apply {
            text = "بدء البث"
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
        statusText = TextView(this).apply {
            text = "متوقف"
            textSize = 14f
            setTextColor(0xFF68DDB7.toInt())
        }
        previewView = PreviewView(this).apply {
            implementationMode = PreviewView.ImplementationMode.PERFORMANCE
        }
        root.addView(title)
        root.addView(subtitle)
        root.addView(endpointInput)
        root.addView(cameraIdInput)
        root.addView(apiKeyInput)
        root.addView(start)
        root.addView(stop)
        root.addView(statusText)
        root.addView(
            previewView,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f
            )
        )
        setContentView(root)
    }

    private fun field(label: String, value: String): EditText {
        return EditText(this).apply {
            hint = label
            setText(value)
            textSize = 14f
            setTextColor(0xFFEAF3FF.toInt())
            setHintTextColor(0xFF7794B4.toInt())
            setSingleLine(true)
        }
    }

    private fun connectAndStart() {
        val base = endpointInput.text.toString().trim().trimEnd('/')
        val cameraId = cameraIdInput.text.toString().trim()
        val key = apiKeyInput.text.toString().trim()
        if (!base.startsWith("https://") ||
            cameraId.isBlank() || key.length < 32
        ) {
            status("استخدم رابط HTTPS موثوقاً، ومعرّف كاميرا ومفتاح API بطول 32 حرفاً على الأقل")
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
                    status("اتصلت الكاميرا؛ بدء إرسال الإطارات")
                    bindCamera()
                }
            }

            override fun onMessage(socket: WebSocket, text: String) {
                runOnUiThread {
                    if (text.contains("frame_rejected")) status("رفض الخادم إطاراً غير صالح")
                }
            }

            override fun onFailure(socket: WebSocket, t: Throwable, response: Response?) {
                runOnUiThread {
                    sending = false
                    status("فشل اتصال البث: " + (t.message ?: "network error"))
                    unbindCamera()
                }
            }

            override fun onClosed(socket: WebSocket, code: Int, reason: String) {
                runOnUiThread {
                    sending = false
                    val detail = when (code) {
                        4400 -> "Invalid camera ID"
                        4401 -> "API key rejected by server"
                        else -> reason.ifBlank { "No details" }
                    }
                    status("Connection closed (" + code + "): " + detail)
                    unbindCamera()
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
                val preview = Preview.Builder().build().also {
                    it.surfaceProvider = previewView.surfaceProvider
                }
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                    .build()
                analysis.setAnalyzer(cameraExecutor) { image ->
                    try {
                        val now = SystemClock.elapsedRealtime()
                        if (sending && now - lastSentAt >= 100) {
                            val jpeg = imageToJpeg(image)
                            if (jpeg != null && jpeg.size <= 4 * 1024 * 1024) {
                                val accepted = webSocket?.send(ByteString.of(*jpeg)) == true
                                if (accepted) {
                                    lastSentAt = now
                                    sentFrames += 1
                                    if (sentFrames % 25 == 0) {
                                        runOnUiThread {
                                            status("البث نشط · " + sentFrames + " إطار مرسل")
                                        }
                                    }
                                }
                            }
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
        val yBuffer = yPlane.buffer
        for (row in 0 until height) {
            for (col in 0 until width) {
                nv21[position++] = yBuffer.get(
                    row * yPlane.rowStride + col * yPlane.pixelStride
                )
            }
        }
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer
        for (row in 0 until height / 2) {
            for (col in 0 until width / 2) {
                nv21[position++] = vBuffer.get(
                    row * vPlane.rowStride + col * vPlane.pixelStride
                )
                nv21[position++] = uBuffer.get(
                    row * uPlane.rowStride + col * uPlane.pixelStride
                )
            }
        }
        val output = ByteArrayOutputStream()
        val yuv = YuvImage(nv21, ImageFormat.NV21, width, height, null)
        if (!yuv.compressToJpeg(Rect(0, 0, width, height), 72, output)) return null
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

    override fun onDestroy() {
        stopStreaming()
        cameraExecutor.shutdown()
        httpClient.dispatcher.executorService.shutdown()
        super.onDestroy()
    }
}
