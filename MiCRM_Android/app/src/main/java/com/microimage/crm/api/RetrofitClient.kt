package com.microimage.crm.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {
    const val DEFAULT_HOST = "micrm.microimageph.com"

    private var _baseUrl: String = "https://$DEFAULT_HOST/api/v1/"
    val baseUrl: String get() = _baseUrl

    private var retrofit: Retrofit? = null

    fun updateBaseUrl(newHost: String) {
        val host = newHost.trim()
        // Public hosts go over HTTPS; only LAN/dev servers fall back to cleartext.
        val formattedHost = when {
            host.startsWith("http://") || host.startsWith("https://") -> host
            isLocalHost(host) -> "http://$host"
            else -> "https://$host"
        }
        val finalUrl = if (!formattedHost.endsWith("/")) "$formattedHost/" else formattedHost
        val finalApiUrl = if (!finalUrl.endsWith("api/v1/")) "${finalUrl}api/v1/" else finalUrl

        if (this._baseUrl != finalApiUrl) {
            this._baseUrl = finalApiUrl
            this.retrofit = null // Reset retrofit instance to recreate with new URL
        }
    }

    private fun isLocalHost(host: String): Boolean {
        val name = host.substringBefore('/').substringBefore(':')
        return name == "localhost" ||
            name.endsWith(".local") ||
            name.startsWith("10.") ||
            name.startsWith("127.") ||
            name.startsWith("192.168.") ||
            Regex("""^172\.(1[6-9]|2\d|3[01])\.""").containsMatchIn(name)
    }

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val httpClient = OkHttpClient.Builder()
        .addInterceptor(loggingInterceptor)
        .build()

    private fun buildRetrofit(): Retrofit {
        return Retrofit.Builder()
            .baseUrl(_baseUrl)
            .addConverterFactory(GsonConverterFactory.create())
            .client(httpClient)
            .build()
    }

    val apiService: ApiService
        get() {
            if (retrofit == null) {
                retrofit = buildRetrofit()
            }
            return retrofit!!.create(ApiService::class.java)
        }
}
