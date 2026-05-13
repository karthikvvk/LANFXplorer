// sender.cpp — Correct QUIC file sender using MsQuic
//
// Key fixes vs previous versions:
//   1. QUIC_BUFFER and data are in SEPARATE allocations — MsQuic holds the
//      QUIC_BUFFER* internally until SEND_COMPLETE; we must not touch it.
//   2. QUIC_SEND_FLAG_FIN is sent via a SEPARATE zero-length send AFTER the
//      data send — not combined. Combining FIN+data caused the internal
//      assertion Stream->SendRequests != NULL in stream_send.c:665.
//   3. Stream context is freed only in SHUTDOWN_COMPLETE, not SEND_COMPLETE,
//      because MsQuic may still reference internal state after SEND_COMPLETE.
//
// Build:
//   g++ -std=c++17 -O2 sender.cpp -lmsquic -o sender
//
// Usage:
//   ./sender <file> <host> <port> [max_inflight]
//
//   max_inflight (argv[4], optional, default 32):
//     Maximum number of unidirectional chunk-streams that may be in-flight
//     simultaneously over the single QUIC connection.  Higher values push
//     more data into the congestion window at once; lower values reduce
//     memory pressure on constrained hardware.
//     Recommended range: 8 (low-mem / slow link) – 64 (GigE / fast NVMe).

#include <msquic.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <thread>
#include <atomic>
#include <chrono>
#include <algorithm>

static constexpr uint32_t    CHUNK_SIZE   = 4 * 1024 * 1024;
static int                   MAX_INFLIGHT = 32;  // overridden by argv[4] at runtime
static constexpr const char* ALPN_STR        = "quicfile";
static constexpr uint32_t    IDLE_TIMEOUT_MS = 60'000;

static const QUIC_API_TABLE* MsQuic    = nullptr;
static HQUIC                 Reg       = nullptr;
static HQUIC                 Config    = nullptr;

static std::atomic<int>  Inflight  {0};
static std::atomic<bool> HasError  {false};
static std::atomic<bool> Connected {false};

// One per stream. Owns the data buffer.
// QUIC_BUFFER is a *separate* stack/heap object passed to StreamSend —
// MsQuic returns it via SEND_COMPLETE.ClientContext, which is the QUIC_BUFFER*.
struct ChunkCtx {
    uint8_t*     data;    // [8-byte offset header][chunk bytes]  malloc'd
    uint32_t     len;     // total length of data
    QUIC_BUFFER  qbuf;    // points into data — passed to StreamSend
};

QUIC_STATUS QUIC_API StreamCallback(HQUIC Stream, void* ctx, QUIC_STREAM_EVENT* ev) {
    auto* cc = static_cast<ChunkCtx*>(ctx);
    switch (ev->Type) {

    case QUIC_STREAM_EVENT_SEND_COMPLETE:
        // MsQuic is done with qbuf — we can now free data.
        // Do NOT free cc yet; stream may still be open.
        free(cc->data);
        cc->data = nullptr;
        break;

    case QUIC_STREAM_EVENT_SHUTDOWN_COMPLETE:
        // Stream fully torn down — safe to free everything.
        free(cc);
        --Inflight;
        break;

    case QUIC_STREAM_EVENT_PEER_SEND_ABORTED:
    case QUIC_STREAM_EVENT_PEER_RECEIVE_ABORTED:
        HasError = true;
        break;

    default:
        break;
    }
    return QUIC_STATUS_SUCCESS;
}

QUIC_STATUS QUIC_API ConnCallback(HQUIC, void*, QUIC_CONNECTION_EVENT* ev) {
    switch (ev->Type) {
    case QUIC_CONNECTION_EVENT_CONNECTED:
        printf("[sender] Connected (0-RTT=%s)\n",
               ev->CONNECTED.SessionResumed ? "yes" : "no");
        Connected = true;
        break;
    case QUIC_CONNECTION_EVENT_SHUTDOWN_INITIATED_BY_TRANSPORT:
        fprintf(stderr, "[sender] Transport shutdown 0x%llx\n",
                (unsigned long long)ev->SHUTDOWN_INITIATED_BY_TRANSPORT.ErrorCode);
        HasError = true;
        break;
    case QUIC_CONNECTION_EVENT_SHUTDOWN_COMPLETE:
        break;
    default:
        break;
    }
    return QUIC_STATUS_SUCCESS;
}

// Open a unidirectional stream and send one chunk.
// Wire format: [uint64_le file_offset][raw chunk bytes]
// FIN is sent as a separate zero-length trailing send so MsQuic's
// internal send queue is never empty when we ask to flush.
bool SendChunk(HQUIC Conn, const uint8_t* chunkData, size_t chunkLen,
               uint64_t fileOffset) {

    auto* cc  = static_cast<ChunkCtx*>(malloc(sizeof(ChunkCtx)));
    if (!cc) return false;

    cc->len  = static_cast<uint32_t>(8 + chunkLen);
    cc->data = static_cast<uint8_t*>(malloc(cc->len));
    if (!cc->data) { free(cc); return false; }

    memcpy(cc->data,     &fileOffset, 8);
    memcpy(cc->data + 8, chunkData,   chunkLen);

    cc->qbuf.Buffer = cc->data;
    cc->qbuf.Length = cc->len;

    HQUIC stream = nullptr;
    QUIC_STATUS st;

    st = MsQuic->StreamOpen(Conn,
                            QUIC_STREAM_OPEN_FLAG_UNIDIRECTIONAL,
                            StreamCallback, cc, &stream);
    if (QUIC_FAILED(st)) {
        fprintf(stderr, "[sender] StreamOpen failed: 0x%x\n", st);
        free(cc->data); free(cc); return false;
    }

    st = MsQuic->StreamStart(stream, QUIC_STREAM_START_FLAG_IMMEDIATE);
    if (QUIC_FAILED(st)) {
        fprintf(stderr, "[sender] StreamStart failed: 0x%x\n", st);
        free(cc->data); free(cc);
        MsQuic->StreamClose(stream);
        return false;
    }

    // Send the data — NO FIN flag here.
    st = MsQuic->StreamSend(stream, &cc->qbuf, 1,
                            QUIC_SEND_FLAG_NONE,
                            &cc->qbuf  /* ClientContext */);
    if (QUIC_FAILED(st)) {
        fprintf(stderr, "[sender] StreamSend(data) failed: 0x%x\n", st);
        free(cc->data); free(cc);
        MsQuic->StreamClose(stream);
        return false;
    }

    // Send a separate zero-length FIN to close the stream gracefully.
    // This is queued *after* the data send, so the send queue is never empty.
    st = MsQuic->StreamSend(stream, nullptr, 0,
                            QUIC_SEND_FLAG_FIN,
                            nullptr  /* ClientContext — ignored for zero-len */);
    if (QUIC_FAILED(st)) {
        // Non-fatal: stream will time out, but data was sent.
        fprintf(stderr, "[sender] StreamSend(FIN) failed: 0x%x (non-fatal)\n", st);
    }

    ++Inflight;
    return true;
}

int main(int argc, char* argv[]) {
    if (argc < 4) {
        fprintf(stderr, "usage: sender <file> <host> <port> [max_inflight]\n");
        return 1;
    }
    const char* path = argv[1];
    const char* host = argv[2];
    uint16_t    port = static_cast<uint16_t>(atoi(argv[3]));

    // argv[4] — optional max in-flight streams (default 32)
    if (argc >= 5) {
        int mf = atoi(argv[4]);
        if (mf > 0) MAX_INFLIGHT = mf;
        printf("[sender] max_inflight=%d (from argv[4])\n", MAX_INFLIGHT);
    }

    // ── load file ──────────────────────────────────────────────────────────
    FILE* f = fopen(path, "rb");
    if (!f) { perror("fopen"); return 1; }
    fseek(f, 0, SEEK_END);
    size_t fileSize = static_cast<size_t>(ftell(f));
    rewind(f);
    std::vector<uint8_t> fileData(fileSize);
    if (fread(fileData.data(), 1, fileSize, f) != fileSize) {
        perror("fread"); fclose(f); return 1;
    }
    fclose(f);
    printf("[sender] %s  %zu bytes  (%.1f MB)\n",
           path, fileSize, fileSize / 1e6);

    // ── MsQuic init ────────────────────────────────────────────────────────
    if (QUIC_FAILED(MsQuicOpen2(&MsQuic))) {
        fprintf(stderr, "MsQuicOpen2 failed\n"); return 1;
    }

    QUIC_REGISTRATION_CONFIG regCfg{ "sender", QUIC_EXECUTION_PROFILE_LOW_LATENCY };
    MsQuic->RegistrationOpen(&regCfg, &Reg);

    QUIC_SETTINGS s{};
    s.IdleTimeoutMs       = IDLE_TIMEOUT_MS;
    s.IsSet.IdleTimeoutMs = 1;

    QUIC_BUFFER alpn{ (uint32_t)strlen(ALPN_STR),
                      (uint8_t*)const_cast<char*>(ALPN_STR) };
    MsQuic->ConfigurationOpen(Reg, &alpn, 1, &s, sizeof(s), nullptr, &Config);

    QUIC_CREDENTIAL_CONFIG cred{};
    cred.Type  = QUIC_CREDENTIAL_TYPE_NONE;
    cred.Flags = QUIC_CREDENTIAL_FLAG_CLIENT |
                 QUIC_CREDENTIAL_FLAG_NO_CERTIFICATE_VALIDATION;
    MsQuic->ConfigurationLoadCredential(Config, &cred);

    // ── connect ────────────────────────────────────────────────────────────
    HQUIC conn = nullptr;
    MsQuic->ConnectionOpen(Reg, ConnCallback, nullptr, &conn);
    MsQuic->ConnectionStart(conn, Config, QUIC_ADDRESS_FAMILY_UNSPEC, host, port);

    for (int i = 0; i < 200 && !Connected && !HasError; ++i)
        std::this_thread::sleep_for(std::chrono::milliseconds(25));
    if (!Connected) {
        fprintf(stderr, "[sender] Handshake failed.\n"); return 1;
    }

    // ── send ───────────────────────────────────────────────────────────────
    size_t numChunks = (fileSize + CHUNK_SIZE - 1) / CHUNK_SIZE;
    printf("[sender] %zu chunks x %u MB\n", numChunks, CHUNK_SIZE >> 20);

    size_t   offset = 0;
    unsigned n      = 0;
    auto     t0     = std::chrono::steady_clock::now();

    while (offset < fileSize && !HasError) {
        // Throttle to avoid overwhelming flow control / memory
        while (Inflight.load() >= MAX_INFLIGHT && !HasError)
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        if (HasError) break;

        size_t len = std::min<size_t>(CHUNK_SIZE, fileSize - offset);

        if (!SendChunk(conn, fileData.data() + offset, len, offset)) {
            HasError = true; break;
        }
        printf("[sender] chunk %u/%zu  off=%-12zu  fly=%d\n",
               ++n, numChunks, offset, Inflight.load());
        offset += len;
    }

    // Drain
    while (Inflight.load() > 0)
        std::this_thread::sleep_for(std::chrono::milliseconds(5));

    double secs = std::chrono::duration<double>(
                      std::chrono::steady_clock::now() - t0).count();
    printf("[sender] Done. %.1f MB / %.2f s = %.1f MB/s\n",
           fileSize / 1e6, secs, (fileSize / 1e6) / secs);

    MsQuic->ConnectionShutdown(conn, QUIC_CONNECTION_SHUTDOWN_FLAG_NONE, 0);
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    MsQuic->ConnectionClose(conn);
    MsQuic->ConfigurationClose(Config);
    MsQuic->RegistrationClose(Reg);
    MsQuicClose(MsQuic);
    return HasError ? 1 : 0;
}